"""Reading and writing games, scenes and revisions."""

from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cyoa.model import Game, Scene
from cyoa.validate import SLUG_RE, text_word_count

from .db import GameRow, RevisionRow, SceneRow, aware, now

META_FIELDS = (
    "title",
    "author",
    "description",
    "version",
    "start_scene",
    "settings",
    "variables",
    "items",
    "rules",
    "chapters",
)
SCENE_FIELDS = (
    "title",
    "chapter",
    "text",
    "art",
    "on_enter",
    "choices",
    "ending",
    "tags",
    "notes",
    "position",
    "hidden_warnings",
)
REVISION_WINDOW = timedelta(minutes=10)
MAX_REVISIONS = 200


# -- ids -----------------------------------------------------------------------------


def new_game_id() -> str:
    return uuid.uuid4().hex


def new_choice_id() -> str:
    return secrets.token_hex(4)


def slugify(text: str, fallback: str = "scene") -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    slug = slug[:48].rstrip("_")
    return slug or fallback


def unique_slug(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def check_slug(slug: str, what: str = "scene id") -> None:
    if not SLUG_RE.match(slug):
        raise HTTPException(
            422, f"'{slug}' isn't a valid {what}: use lowercase letters, digits and _"
        )


# -- normalization ---------------------------------------------------------------------


def _validation_detail(error: ValidationError) -> str:
    first = error.errors()[0]
    where = ".".join(str(p) for p in first["loc"])
    return f"{where}: {first['msg']}" if where else first["msg"]


def normalize_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Validate the game-level fields and fill in defaults."""
    try:
        game = Game.model_validate({**meta, "scenes": []})
    except ValidationError as e:
        raise HTTPException(422, _validation_detail(e)) from None
    dumped = game.model_dump(mode="json")
    return {key: dumped[key] for key in META_FIELDS}


def normalize_scene(scene_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Validate a scene's fields, giving every choice a unique id."""
    try:
        scene = Scene.model_validate({**data, "id": scene_id})
    except ValidationError as e:
        raise HTTPException(422, _validation_detail(e)) from None
    taken: set[str] = set()
    for choice in scene.choices:
        if not choice.id or choice.id in taken:
            choice.id = new_choice_id()
            while choice.id in taken:
                choice.id = new_choice_id()
        taken.add(choice.id)
    dumped = scene.model_dump(mode="json")
    return {key: dumped[key] for key in SCENE_FIELDS}


# -- reading ---------------------------------------------------------------------------


def get_game(db: Session, game_id: str, *, deleted: bool = False) -> GameRow:
    row = db.get(GameRow, game_id)
    if row is None or (row.deleted_at is not None) != deleted:
        raise HTTPException(404, "game not found")
    return row


def live_scenes(db: Session, game_id: str) -> list[SceneRow]:
    return list(
        db.scalars(
            select(SceneRow)
            .where(SceneRow.game_id == game_id, SceneRow.deleted_at.is_(None))
            .order_by(SceneRow.sort, SceneRow.pk)
        )
    )


def get_scene(db: Session, game_id: str, pk: int, *, deleted: bool = False) -> SceneRow:
    row = db.get(SceneRow, pk)
    if row is None or row.game_id != game_id or (row.deleted_at is not None) != deleted:
        raise HTTPException(404, "scene not found")
    return row


def scene_api(row: SceneRow) -> dict[str, Any]:
    return {
        "pk": row.pk,
        "id": row.scene_id,
        "rev": row.rev,
        "sort": row.sort,
        "updated_at": aware(row.updated_at).isoformat(),
        **row.data,
    }


def game_api(row: GameRow, scenes: list[SceneRow], access: str) -> dict[str, Any]:
    """The whole game, plus what the person asking may do with it (read/edit/owner)."""
    return {
        "id": row.id,
        "access": access,
        "rev": row.rev,
        "created_at": aware(row.created_at).isoformat(),
        "updated_at": aware(row.updated_at).isoformat(),
        "meta": row.meta,
        "scenes": [scene_api(s) for s in scenes],
    }


def game_summary(row: GameRow, scenes: list[SceneRow]) -> dict[str, Any]:
    words = sum(text_word_count(s.data.get("text", "")) for s in scenes)
    return {
        "id": row.id,
        "title": row.meta.get("title", ""),
        "author": row.meta.get("author", ""),
        "scenes": len(scenes),
        "words": words,
        "updated_at": aware(row.updated_at).isoformat(),
        "deleted_at": aware(row.deleted_at).isoformat() if row.deleted_at else None,
    }


def assemble(row: GameRow, scenes: list[SceneRow]) -> Game:
    """The stored game as an engine model (used for validation, export and playtest)."""
    return Game.model_validate(
        {
            "id": row.id,
            **row.meta,
            "scenes": [{**s.data, "id": s.scene_id} for s in scenes],
        }
    )


def load_game_model(db: Session, game_id: str) -> Game:
    row = get_game(db, game_id)
    return assemble(row, live_scenes(db, game_id))


# -- writing ---------------------------------------------------------------------------


def touch(game: GameRow) -> None:
    game.updated_at = now()


def snapshot(row: SceneRow) -> dict[str, Any]:
    return {"id": row.scene_id, **row.data}


def record_revision(db: Session, row: SceneRow, reason: str = "edit") -> None:
    """Remember the scene's current content. Rapid edits by one person share a revision.

    The person is whoever the request's ``current_user`` check found (``db.info``).
    """
    db.flush()
    user_id = db.info.get("user_id")
    latest = db.scalars(
        select(RevisionRow)
        .where(RevisionRow.scene_pk == row.pk)
        .order_by(RevisionRow.id.desc())
        .limit(1)
    ).first()
    stamp = now()
    if (
        reason == "edit"
        and latest is not None
        and latest.reason == "edit"
        and latest.user_id == user_id
        and stamp - aware(latest.created_at) < REVISION_WINDOW
    ):
        latest.snapshot = snapshot(row)
        latest.updated_at = stamp
    else:
        db.add(
            RevisionRow(
                scene_pk=row.pk,
                reason=reason,
                snapshot=snapshot(row),
                user_id=user_id,
                created_at=stamp,
                updated_at=stamp,
            )
        )
        db.flush()
        count = db.scalar(select(func.count()).where(RevisionRow.scene_pk == row.pk)) or 0
        if count > MAX_REVISIONS:
            old_ids = list(
                db.scalars(
                    select(RevisionRow.id)
                    .where(RevisionRow.scene_pk == row.pk)
                    .order_by(RevisionRow.id)
                    .limit(count - MAX_REVISIONS)
                )
            )
            db.execute(delete(RevisionRow).where(RevisionRow.id.in_(old_ids)))


def add_scene(
    db: Session,
    game: GameRow,
    scene_id: str,
    data: dict[str, Any],
    sort: float | None = None,
    reason: str = "created",
) -> SceneRow:
    if sort is None:
        max_sort = db.scalar(
            select(func.max(SceneRow.sort)).where(
                SceneRow.game_id == game.id, SceneRow.deleted_at.is_(None)
            )
        )
        sort = (max_sort or 0.0) + 1.0
    row = SceneRow(
        game_id=game.id, scene_id=scene_id, data=normalize_scene(scene_id, data), sort=sort
    )
    db.add(row)
    db.flush()
    record_revision(db, row, reason)
    touch(game)
    return row


def create_game(db: Session, game: Game) -> GameRow:
    row = GameRow(id=game.id, meta=normalize_meta(game.model_dump(mode="json")))
    db.add(row)
    db.flush()
    for i, scene in enumerate(game.scenes):
        data = scene.model_dump(mode="json")
        add_scene(db, row, scene.id, data, sort=float(i + 1))
    return row


def apply_game(db: Session, row: GameRow, scenes: list[SceneRow], game: Game, reason: str) -> None:
    """Write back a modified copy of an assembled game (scenes matched by position)."""
    dumped = game.model_dump(mode="json")
    meta = {key: dumped[key] for key in META_FIELDS}
    if meta != row.meta:
        row.meta = meta
        row.rev += 1
    for scene_row, scene in zip(scenes, game.scenes, strict=True):
        data = scene.model_dump(mode="json")
        new_data = {key: data[key] for key in SCENE_FIELDS}
        if scene.id != scene_row.scene_id or new_data != scene_row.data:
            scene_row.scene_id = scene.id
            scene_row.data = new_data
            scene_row.rev += 1
            scene_row.updated_at = now()
            record_revision(db, scene_row, reason)
    touch(row)


def taken_scene_ids(db: Session, game_id: str) -> set[str]:
    return set(
        db.scalars(
            select(SceneRow.scene_id).where(
                SceneRow.game_id == game_id, SceneRow.deleted_at.is_(None)
            )
        )
    )
