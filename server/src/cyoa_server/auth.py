"""Single-password login with server-side sessions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .db import SessionRow, aware, now
from .deps import get_config, get_db

COOKIE = "cyoa_session"
MAX_FAILURES = 5  # per client address
MAX_GLOBAL_FAILURES = 50  # all clients together (addresses behind a proxy can be faked)
FAILURE_WINDOW = 15 * 60  # seconds
GLOBAL = "*"

router = APIRouter(prefix="/api", tags=["auth"])


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


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def session_valid(db: Session, token: str | None) -> bool:
    if not token:
        return False
    row = db.get(SessionRow, _hash(token))
    if row is None:
        return False
    if aware(row.expires_at) < now():
        db.delete(row)
        db.commit()
        return False
    return True


def require_auth(request: Request, db: Annotated[Session, Depends(get_db)]) -> None:
    if not session_valid(db, request.cookies.get(COOKIE)):
        raise HTTPException(401, "not logged in")


def same_origin(origin: str | None, host: str | None) -> bool:
    """Requests that carry an Origin must come from this site."""
    if not origin:
        return True
    return bool(host) and urlsplit(origin).netloc == host


def websocket_authorized(websocket: WebSocket, db: Session) -> bool:
    if not same_origin(websocket.headers.get("origin"), websocket.headers.get("host")):
        return False
    return session_valid(db, websocket.cookies.get(COOKIE))


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, bool]:
    config = get_config(request)
    ip = _client_ip(request)
    if limiter.blocked(ip) or limiter.blocked(GLOBAL, MAX_GLOBAL_FAILURES):
        raise HTTPException(429, "too many attempts; try again in a few minutes")
    if not hmac.compare_digest(body.password.encode(), config.password.encode()):
        limiter.fail(ip)
        limiter.fail(GLOBAL)
        raise HTTPException(401, "wrong password")
    limiter.reset(ip)
    token = secrets.token_urlsafe(32)
    lifetime = timedelta(days=config.session_days)
    db.execute(delete(SessionRow).where(SessionRow.expires_at < now()))
    db.add(SessionRow(token_hash=_hash(token), expires_at=now() + lifetime))
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
    return {"ok": True}


@router.post("/logout")
def logout(
    request: Request, response: Response, db: Annotated[Session, Depends(get_db)]
) -> dict[str, bool]:
    token = request.cookies.get(COOKIE)
    if token:
        row = db.get(SessionRow, _hash(token))
        if row is not None:
            db.delete(row)
            db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    return {"authenticated": session_valid(db, request.cookies.get(COOKIE))}
