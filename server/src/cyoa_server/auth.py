"""Accounts, login sessions and who may do what.

The owner (whose password is ``CYOA_PASSWORD``) can do everything. Everyone else
gets an account through an invite link and can open only the games shared with
them, at the level they were given: read, or edit.

Every route depends on one of: ``current_user`` (any account), ``require_owner``,
or for a game, ``can_read`` / ``can_edit``. ``tests/test_access.py`` checks that
no route is left out.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import Config
from .db import SessionRow, ShareRow, UserRow, aware, now
from .deps import get_config, get_db
from .passwords import DUMMY_HASH, verify_password

COOKIE = "cyoa_session"
MAX_FAILURES = 5  # per client address
MAX_GLOBAL_FAILURES = 50  # all clients together (addresses behind a proxy can be faked)
FAILURE_WINDOW = 15 * 60  # seconds
GLOBAL = "*"
OWNER_NAME = "owner"
USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
MIN_PASSWORD = 8
MAX_PASSWORD = 200

router = APIRouter(prefix="/api", tags=["auth"])
DB = Annotated[Session, Depends(get_db)]


class Access(StrEnum):
    READ = "read"
    EDIT = "edit"
    OWNER = "owner"


RANK = {Access.READ: 1, Access.EDIT: 2, Access.OWNER: 3}


class _Limiter:
    def __init__(self) -> None:
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        q = self.failures[key]
        cutoff = time.monotonic() - FAILURE_WINDOW
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, key: str, limit: int = MAX_FAILURES) -> bool:
        return len(self._prune(key)) >= limit

    def fail(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self.failures.pop(key, None)


limiter = _Limiter()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    if limiter.blocked(client_ip(request)) or limiter.blocked(GLOBAL, MAX_GLOBAL_FAILURES):
        raise HTTPException(429, "too many attempts; try again in a few minutes")


def record_failure(request: Request) -> None:
    limiter.fail(client_ip(request))
    limiter.fail(GLOBAL)


# -- accounts -------------------------------------------------------------------------


def user_api(user: UserRow) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "owner": user.is_owner}


def normalize_username(name: str) -> str:
    username = name.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(
            422, "a username needs 3–32 letters, digits, dots, dashes or underscores"
        )
    return username


def check_username_free(db: Session, username: str, *, ignore: int | None = None) -> None:
    taken = db.scalar(select(UserRow).where(UserRow.username == username))
    if taken is not None and taken.id != ignore:
        raise HTTPException(409, f"the username '{username}' is taken")


def check_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"a password needs at least {MIN_PASSWORD} characters")
    if len(password) > MAX_PASSWORD:
        raise HTTPException(422, "that password is too long")


def find_user(db: Session, username: str) -> UserRow | None:
    return db.scalar(select(UserRow).where(UserRow.username == username.strip().lower()))


def owner(db: Session) -> UserRow:
    row = db.scalar(select(UserRow).where(UserRow.is_owner))
    assert row is not None, "ensure_owner runs at startup"
    return row


def ensure_owner(db: Session) -> None:
    """The dashboard's owner always has an account (its password is CYOA_PASSWORD)."""
    if db.scalar(select(UserRow).where(UserRow.is_owner)) is not None:
        return
    taken = set(db.scalars(select(UserRow.username)))
    name, n = OWNER_NAME, 2
    while name in taken:
        name, n = f"{OWNER_NAME}{n}", n + 1
    db.add(UserRow(username=name, is_owner=True))
    db.commit()


def password_ok(user: UserRow | None, password: str, config: Config) -> bool:
    if user is None:
        verify_password(password, DUMMY_HASH)  # take as long as a real check
        return False
    if user.is_owner:
        return hmac.compare_digest(password.encode(), config.password.encode())
    return verify_password(password, user.password_hash)


# -- sessions ---------------------------------------------------------------------------


def start_session(db: Session, response: Response, config: Config, user: UserRow) -> None:
    """Log ``user`` in on this browser (commits)."""
    token = secrets.token_urlsafe(32)
    lifetime = timedelta(days=config.session_days)
    db.execute(delete(SessionRow).where(SessionRow.expires_at < now()))
    db.add(SessionRow(token_hash=hash_token(token), user_id=user.id, expires_at=now() + lifetime))
    user.last_login_at = now()
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=config.secure_cookies,
        samesite="lax",
        path="/",
    )


def end_sessions(db: Session, user_id: int, *, keep: str | None = None) -> None:
    """Log someone out everywhere (except the browser whose cookie is ``keep``)."""
    query = delete(SessionRow).where(SessionRow.user_id == user_id)
    if keep:
        query = query.where(SessionRow.token_hash != hash_token(keep))
    db.execute(query)


def session_user(db: Session, token: str | None) -> UserRow | None:
    if not token:
        return None
    row = db.get(SessionRow, hash_token(token))
    if row is None:
        return None
    if aware(row.expires_at) < now():
        db.delete(row)
        db.commit()
        return None
    return db.get(UserRow, row.user_id)


# -- permission checks (FastAPI dependencies) ---------------------------------------


def current_user(request: Request, db: DB) -> UserRow:
    user = session_user(db, request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "not logged in")
    db.info["user_id"] = user.id  # scene history records who made each change
    return user


CurrentUser = Annotated[UserRow, Depends(current_user)]


def require_owner(user: CurrentUser) -> UserRow:
    if not user.is_owner:
        raise HTTPException(403, "only the owner can do that")
    return user


Owner = Annotated[UserRow, Depends(require_owner)]


def access_to(db: Session, user: UserRow, game_id: str) -> Access | None:
    if user.is_owner:
        return Access.OWNER
    share = db.get(ShareRow, (game_id, user.id))
    return Access(share.level) if share else None


def share_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(ShareRow.game_id, func.count()).group_by(ShareRow.game_id))
    return {game_id: count for game_id, count in rows}


def _requires(level: Access) -> Callable[..., Access]:
    def check(game_id: str, user: CurrentUser, db: DB) -> Access:
        access = access_to(db, user, game_id)
        if access is None:
            raise HTTPException(404, "game not found")  # don't reveal that it exists
        if RANK[access] < RANK[level]:
            raise HTTPException(403, "you can only read this game, not change it")
        return access

    check.__name__ = f"can_{level.value}"
    return check


can_read = _requires(Access.READ)
can_edit = _requires(Access.EDIT)
CanRead = Annotated[Access, Depends(can_read)]
CanEdit = Annotated[Access, Depends(can_edit)]


def same_origin(origin: str | None, host: str | None) -> bool:
    """Requests that carry an Origin must come from this site."""
    if not origin:
        return True
    return bool(host) and urlsplit(origin).netloc == host


def websocket_user(websocket: WebSocket, db: Session) -> UserRow | None:
    if not same_origin(websocket.headers.get("origin"), websocket.headers.get("host")):
        return None
    return session_user(db, websocket.cookies.get(COOKIE))


# -- routes ---------------------------------------------------------------------------------


class LoginBody(BaseModel):
    username: str = ""  # empty means the owner
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: DB) -> dict[str, bool]:
    config = get_config(request)
    check_rate_limit(request)
    user = find_user(db, body.username) if body.username.strip() else owner(db)
    if not password_ok(user, body.password, config):
        record_failure(request)
        raise HTTPException(401, "wrong username or password")
    assert user is not None
    limiter.reset(client_ip(request))
    start_session(db, response, config, user)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: DB) -> dict[str, bool]:
    token = request.cookies.get(COOKIE)
    if token:
        row = db.get(SessionRow, hash_token(token))
        if row is not None:
            db.delete(row)
            db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: DB) -> dict[str, Any]:
    user = session_user(db, request.cookies.get(COOKIE))
    if user is None:
        return {"authenticated": False}
    return {"authenticated": True, "user": user_api(user)}
