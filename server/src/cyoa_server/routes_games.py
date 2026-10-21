"""Games: list, create, edit settings, delete/restore, duplicate, import, export."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from cyoa.model import Game, GameFileError, Scene, game_from_dict
from cyoa.validate import has_errors, validate

from . import store
from .auth import Access, CanEdit, CanRead, CurrentUser, Owner, current_user, share_counts
from .db import GameRow, SceneRow, ShareRow, aware, now
from .deps import get_db

router = APIRouter(prefix="/api", tags=["games"], dependencies=[Depends(current_user)])
DB = Annotated[Session, Depends(get_db)]


class NewGame(BaseModel):
    title: str = "Untitled"


@router.get("/games")
def list_games(db: DB, user: CurrentUser) -> list[dict[str, Any]]:
    """The owner's games (all of them), or the games shared with this person."""
    live = GameRow.deleted_at.is_(None)
    if user.is_owner:
        counts = share_counts(db)
        rows = [
            (r, Access.OWNER.value, counts.get(r.id, 0))
            for r in db.scalars(select(GameRow).where(live))
        ]
    else:
        shared = db.execute(
            select(GameRow, ShareRow.level)
            .join(ShareRow, ShareRow.game_id == GameRow.id)
            .where(live, ShareRow.user_id == user.id)
        )
        rows = [(r, level, 0) for r, level in shared]
    summaries = [
        {**store.game_summary(r, store.live_scenes(db, r.id)), "access": access, "shared_with": n}
        for r, access, n in rows
    ]
    return sorted(summaries, key=lambda g: g["updated_at"], reverse=True)


@router.post("/games", status_code=201)
def create_game(body: NewGame, db: DB, _: Owner) -> dict[str, Any]:
    title = body.title.strip() or "Untitled"
    game = Game(
        id=store.new_game_id(),
        title=title,
        start_scene="start",
        scenes=[Scene(id="start", title="Start")],
    )
    row = store.create_game(db, game)
    db.commit()
    return store.game_api(row, store.live_scenes(db, row.id), Access.OWNER)


@router.get("/games/{game_id}")
def get_game(game_id: str, db: DB, access: CanRead) -> dict[str, Any]:
    row = store.get_game(db, game_id)
    return store.game_api(row, store.live_scenes(db, game_id), access)


@router.patch("/games/{game_id}")
def update_game(
    game_id: str, db: DB, _: CanEdit, changes: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    """Change game-level fields (title, settings, variables, items, rules, chapters...).

    Pass ``rev`` to make sure nobody else changed the game since you loaded it.
    """
    row = store.get_game(db, game_id)
    expected = changes.pop("rev", None)
    if expected is not None and expected != row.rev:
        raise HTTPException(409, "the game was changed elsewhere; reload to see the latest")
    unknown = set(changes) - set(store.META_FIELDS)
    if unknown:
        raise HTTPException(422, f"unknown fields: {', '.join(sorted(unknown))}")
    meta = store.normalize_meta({**row.meta, **changes})
    if meta != row.meta:
        row.meta = meta
        row.rev += 1
        store.touch(row)
    db.commit()
    return {"rev": row.rev, "meta": row.meta}


@router.delete("/games/{game_id}")
def delete_game(game_id: str, db: DB, _: Owner) -> dict[str, bool]:
    row = store.get_game(db, game_id)
    row.deleted_at = now()
    db.commit()
    return {"ok": True}


@router.post("/games/{game_id}/duplicate", status_code=201)
def duplicate_game(game_id: str, db: DB, _: Owner) -> dict[str, Any]:
    game = store.load_game_model(db, game_id)
    copy = game.model_copy(update={"id": store.new_game_id(), "title": f"{game.title} (copy)"})
    row = store.create_game(db, copy)
    db.commit()
    return store.game_api(row, store.live_scenes(db, row.id), Access.OWNER)


@router.post("/games/import", status_code=201)
def import_game(db: DB, _: Owner, data: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    try:
        game = game_from_dict(data)
    except GameFileError as e:
        raise HTTPException(422, str(e)) from None
    if not game.id or db.get(GameRow, game.id) is not None:
        game.id = store.new_game_id()
    ids = [s.id for s in game.scenes]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "the file has two scenes with the same id")
    for scene_id in ids:
        store.check_slug(scene_id)
    row = store.create_game(db, game)
    db.commit()
    return store.game_api(row, store.live_scenes(db, row.id), Access.OWNER)


@router.get("/games/{game_id}/export")
def export_game(
    game_id: str,
    db: DB,
    _: CanEdit,
    format: Annotated[str, Query(pattern="^(player|project)$")] = "player",
) -> Response:
    game = store.load_game_model(db, game_id)
    if format == "player":
        issues = validate(game)
        if has_errors(issues):
            errors = [i.to_dict() for i in issues if i.severity == "error"]
            raise HTTPException(
                409, {"message": "fix the errors before exporting", "issues": errors}
            )
        data = game.to_player_dict()
        suffix = ".cyoa.json"
    else:
        data = game.to_project_dict()
        suffix = ".project.json"
    filename = store.slugify(game.title, "game") + suffix
    return Response(
        json.dumps(data, ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -- trash ------------------------------------------------------------------------------


@router.get("/trash")
def trash(db: DB, _: Owner) -> dict[str, Any]:
    games = db.scalars(select(GameRow).where(GameRow.deleted_at.is_not(None))).all()
    scene_rows = db.execute(
        select(SceneRow, GameRow)
        .join(GameRow, GameRow.id == SceneRow.game_id)
        .where(SceneRow.deleted_at.is_not(None), GameRow.deleted_at.is_(None))
        .order_by(SceneRow.deleted_at.desc())
    ).all()
    return {
        "games": [store.game_summary(g, store.live_scenes(db, g.id)) for g in games],
        "scenes": [
            {
                "pk": s.pk,
                "id": s.scene_id,
                "title": s.data.get("title", ""),
                "game_id": g.id,
                "game_title": g.meta.get("title", ""),
                "deleted_at": aware(s.deleted_at).isoformat() if s.deleted_at else None,
            }
            for s, g in scene_rows
        ],
    }


@router.post("/trash/games/{game_id}/restore")
def restore_game(game_id: str, db: DB, _: Owner) -> dict[str, bool]:
    row = store.get_game(db, game_id, deleted=True)
    row.deleted_at = None
    store.touch(row)
    db.commit()
    return {"ok": True}


@router.delete("/trash/games/{game_id}")
def purge_game(game_id: str, db: DB, _: Owner) -> dict[str, bool]:
    row = store.get_game(db, game_id, deleted=True)
    db.delete(row)
    db.commit()
    return {"ok": True}
