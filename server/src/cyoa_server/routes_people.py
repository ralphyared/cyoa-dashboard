"""Sharing games with people: invite links, accounts and password resets.

The owner shares a game by making an invite link (single use, valid for a week)
and sending it however they like. Whoever opens it creates an account, or logs in
to the one they have, and gets the game at the link's level. The owner can change
or take away anyone's access, and make a password reset link for someone who
forgot theirs. There is no email: links are copied and sent by hand.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import store
from .auth import (
    COOKIE,
    CurrentUser,
    Owner,
    check_new_password,
    check_rate_limit,
    check_username_free,
    end_sessions,
    hash_token,
    normalize_username,
    record_failure,
    session_user,
    start_session,
    user_api,
)
from .db import GameRow, InviteRow, PasswordResetRow, ShareRow, UserRow, aware, now
from .deps import get_config, get_db
from .passwords import hash_password, verify_password

LINK_DAYS = 7
router = APIRouter(prefix="/api", tags=["people"])
DB = Annotated[Session, Depends(get_db)]
Level = Literal["read", "edit"]


def _iso(dt: Any) -> str | None:
    return aware(dt).isoformat() if dt else None


def _grant(db: Session, game_id: str, user_id: int, level: str) -> None:
    share = db.get(ShareRow, (game_id, user_id))
    if share is None:
        db.add(ShareRow(game_id=game_id, user_id=user_id, level=level))
    else:
        share.level = level


def _guest(db: Session, user_id: int) -> UserRow:
    user = db.get(UserRow, user_id)
    if user is None:
        raise HTTPException(404, "no such person")
    if user.is_owner:
        raise HTTPException(400, "that's you, the owner")
    return user


# -- your own account -------------------------------------------------------------------


class AccountChanges(BaseModel):
    username: str


@router.patch("/me")
def change_account(body: AccountChanges, user: CurrentUser, db: DB) -> dict[str, Any]:
    username = normalize_username(body.username)
    check_username_free(db, username, ignore=user.id)
    user.username = username
    db.commit()
    return user_api(user)


class PasswordChange(BaseModel):
    current: str
    new: str


@router.post("/me/password")
def change_password(
    body: PasswordChange, request: Request, user: CurrentUser, db: DB
) -> dict[str, bool]:
    if user.is_owner:
        raise HTTPException(400, "your password is CYOA_PASSWORD in the server's .env file")
    check_rate_limit(request)
    if not verify_password(body.current, user.password_hash):
        record_failure(request)
        raise HTTPException(400, "your current password isn't right")
    check_new_password(body.new)
    user.password_hash = hash_password(body.new)
    end_sessions(db, user.id, keep=request.cookies.get(COOKIE))  # log out other devices
    db.commit()
    return {"ok": True}


# -- people (owner) -------------------------------------------------------------------------


@router.get("/users")
def list_users(db: DB, _: Owner) -> list[dict[str, Any]]:
    """Everyone with an account, and which games they can open."""
    games: dict[int, list[dict[str, Any]]] = {}
    shares = db.execute(
        select(ShareRow, GameRow)
        .join(GameRow, GameRow.id == ShareRow.game_id)
        .where(GameRow.deleted_at.is_(None))
    )
    for share, game in shares:
        games.setdefault(share.user_id, []).append(
            {"id": game.id, "title": game.meta.get("title", ""), "level": share.level}
        )
    users = db.scalars(select(UserRow).order_by(UserRow.is_owner.desc(), UserRow.username))
    return [
        {
            **user_api(u),
            "created_at": _iso(u.created_at),
            "last_login_at": _iso(u.last_login_at),
            "games": sorted(games.get(u.id, []), key=lambda g: g["title"].lower()),
        }
        for u in users
    ]


@router.delete("/users/{user_id}")
def remove_user(user_id: int, db: DB, _: Owner) -> dict[str, bool]:
    """Delete an account: its access to every game, and its logins. Its edits stay."""
    db.delete(_guest(db, user_id))
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-link", status_code=201)
def make_reset_link(user_id: int, db: DB, _: Owner) -> dict[str, Any]:
    user = _guest(db, user_id)
    db.execute(delete(PasswordResetRow).where(PasswordResetRow.user_id == user.id))
    token = secrets.token_urlsafe(32)
    expires = now() + timedelta(days=LINK_DAYS)
    db.add(PasswordResetRow(token_hash=hash_token(token), user_id=user.id, expires_at=expires))
    db.commit()
    return {"token": token, "username": user.username, "expires_at": _iso(expires)}


# -- sharing a game (owner) ------------------------------------------------------------------


def _invite_api(row: InviteRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "level": row.level,
        "note": row.note,
        "created_at": _iso(row.created_at),
        "expires_at": _iso(row.expires_at),
    }


@router.get("/games/{game_id}/sharing")
def sharing(game_id: str, db: DB, _: Owner) -> dict[str, Any]:
    store.get_game(db, game_id)
    db.execute(delete(InviteRow).where(InviteRow.expires_at < now()))
    db.commit()
    people = db.execute(
        select(ShareRow, UserRow)
        .join(UserRow, UserRow.id == ShareRow.user_id)
        .where(ShareRow.game_id == game_id)
        .order_by(UserRow.username)
    )
    invites = db.scalars(
        select(InviteRow).where(InviteRow.game_id == game_id).order_by(InviteRow.id)
    )
    return {
        "people": [
            {"user_id": u.id, "username": u.username, "level": s.level, "since": _iso(s.created_at)}
            for s, u in people
        ],
        "invites": [_invite_api(i) for i in invites],
    }


class InviteBody(BaseModel):
    level: Level
    note: str = Field("", max_length=100)


@router.post("/games/{game_id}/invites", status_code=201)
def create_invite(game_id: str, body: InviteBody, db: DB, _: Owner) -> dict[str, Any]:
    """A new invite link. The token is only ever shown here; the server keeps a hash."""
    store.get_game(db, game_id)
    token = secrets.token_urlsafe(32)
    row = InviteRow(
        token_hash=hash_token(token),
        game_id=game_id,
        level=body.level,
        note=body.note.strip(),
        expires_at=now() + timedelta(days=LINK_DAYS),
    )
    db.add(row)
    db.commit()
    return {**_invite_api(row), "token": token}


@router.delete("/games/{game_id}/invites/{invite_id}")
def cancel_invite(game_id: str, invite_id: int, db: DB, _: Owner) -> dict[str, bool]:
    row = db.get(InviteRow, invite_id)
    if row is None or row.game_id != game_id:
        raise HTTPException(404, "invite not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


class LevelBody(BaseModel):
    level: Level


@router.put("/games/{game_id}/people/{user_id}")
def set_level(game_id: str, user_id: int, body: LevelBody, db: DB, _: Owner) -> dict[str, bool]:
    """Give someone who already has an account access, or change their level."""
    store.get_game(db, game_id)
    _grant(db, game_id, _guest(db, user_id).id, body.level)
    db.commit()
    return {"ok": True}


@router.delete("/games/{game_id}/people/{user_id}")
def remove_access(game_id: str, user_id: int, db: DB, _: Owner) -> dict[str, bool]:
    share = db.get(ShareRow, (game_id, user_id))
    if share is None:
        raise HTTPException(404, "they don't have access to this game")
    db.delete(share)
    db.commit()
    return {"ok": True}


# -- opening an invite link (no login needed) ---------------------------------------------


def _open_invite(db: Session, token: str) -> tuple[InviteRow, GameRow]:
    row = db.scalar(select(InviteRow).where(InviteRow.token_hash == hash_token(token)))
    game = db.get(GameRow, row.game_id) if row else None
    if row is None or game is None or game.deleted_at or aware(row.expires_at) < now():
        raise HTTPException(
            404, "this invite link has expired or was already used; ask for a new one"
        )
    return row, game


@router.get("/invites/{token}")
def invite_info(token: str, request: Request, db: DB) -> dict[str, Any]:
    invite, game = _open_invite(db, token)
    user = session_user(db, request.cookies.get(COOKIE))
    return {
        "game_title": game.meta.get("title", ""),
        "level": invite.level,
        "user": user_api(user) if user else None,
    }


@router.post("/invites/{token}/accept")
def accept_invite(token: str, user: CurrentUser, db: DB) -> dict[str, str]:
    """Add the game to the logged-in person's account."""
    invite, game = _open_invite(db, token)
    if user.is_owner:
        raise HTTPException(409, "you're the owner, so you already have every game")
    _grant(db, game.id, user.id, invite.level)
    db.delete(invite)
    db.commit()
    return {"game_id": game.id}


class JoinBody(BaseModel):
    username: str
    password: str


@router.post("/invites/{token}/join")
def join(
    token: str, body: JoinBody, request: Request, response: Response, db: DB
) -> dict[str, str]:
    """Create an account from an invite link, and log in."""
    invite, game = _open_invite(db, token)
    username = normalize_username(body.username)
    check_username_free(db, username)
    check_new_password(body.password)
    user = UserRow(username=username, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    _grant(db, game.id, user.id, invite.level)
    db.delete(invite)
    start_session(db, response, get_config(request), user)
    return {"game_id": game.id}


# -- password reset links (no login needed) ---------------------------------------------


def _open_reset(db: Session, token: str) -> tuple[PasswordResetRow, UserRow]:
    row = db.get(PasswordResetRow, hash_token(token))
    user = db.get(UserRow, row.user_id) if row else None
    if row is None or user is None or aware(row.expires_at) < now():
        raise HTTPException(
            404, "this password link has expired or was already used; ask for a new one"
        )
    return row, user


@router.get("/password-resets/{token}")
def reset_info(token: str, db: DB) -> dict[str, str]:
    _, user = _open_reset(db, token)
    return {"username": user.username}


class NewPassword(BaseModel):
    password: str


@router.post("/password-resets/{token}")
def reset_password(
    token: str, body: NewPassword, request: Request, response: Response, db: DB
) -> dict[str, bool]:
    """Set a new password, log out everywhere else, and log in here."""
    reset, user = _open_reset(db, token)
    check_new_password(body.password)
    user.password_hash = hash_password(body.password)
    end_sessions(db, user.id)
    db.delete(reset)
    start_session(db, response, get_config(request), user)
    return {"ok": True}
