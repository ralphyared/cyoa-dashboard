"""SQLite storage.

A game's small, table-like data (settings, variables, items, rules, chapters)
lives in one JSON column on the game row. Scenes get a row each, so autosaving
one scene writes only that scene, and each scene keeps its own revision history.

Every game belongs to the dashboard's owner; other people get access to single
games through shares (made from invite links).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Connection,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def now() -> datetime:
    return datetime.now(UTC)


def aware(dt: datetime) -> datetime:
    """SQLite drops time zones; everything is stored in UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class GameRow(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rev: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SceneRow(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        Index(
            "ux_scene_slug",
            "game_id",
            "scene_id",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str] = mapped_column(String)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sort: Mapped[float] = mapped_column(Float, default=0.0)
    rev: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RevisionRow(Base):
    __tablename__ = "revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_pk: Mapped[int] = mapped_column(ForeignKey("scenes.pk", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String, default="edit")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Who made the change. No foreign key: history outlives removed accounts.
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True)  # stored lowercase
    # Empty for the owner, whose password is CYOA_PASSWORD.
    password_hash: Mapped[str] = mapped_column(String, default="")
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionRow(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ShareRow(Base):
    """One person's access to one game."""

    __tablename__ = "shares"

    game_id: Mapped[str] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    level: Mapped[str] = mapped_column(String)  # "read" or "edit"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InviteRow(Base):
    """A single-use link that gives whoever opens it access to a game."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(String, default="")  # who it's for, for the owner
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordResetRow(Base):
    """A single-use link the owner makes for someone who forgot their password."""

    __tablename__ = "password_resets"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _migrate(conn: Connection) -> None:
    """Bring databases from before accounts existed up to date."""
    insp = inspect(conn)
    tables = set(insp.get_table_names())

    def columns(table: str) -> set[str]:
        return {c["name"] for c in insp.get_columns(table)}

    # Sessions from the single-password days belong to nobody: log in again.
    if "sessions" in tables and "user_id" not in columns("sessions"):
        conn.execute(text("DROP TABLE sessions"))
    if "revisions" in tables and "user_id" not in columns("revisions"):
        conn.execute(text("ALTER TABLE revisions ADD COLUMN user_id INTEGER"))


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(conn: Any, _record: Any) -> None:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    with engine.begin() as conn:
        _migrate(conn)
    Base.metadata.create_all(engine)
    return engine


class Database:
    def __init__(self, db_path: Path) -> None:
        self.path = db_path
        self.engine = make_engine(db_path)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Iterator[Session]:
        with self._sessions() as session:
            yield session

    def new_session(self) -> Session:
        return self._sessions()
