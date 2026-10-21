"""Scenes: create, edit (with safe id renames), delete/restore, positions, history."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from cyoa.refactor import Kind, rename

from . import store
from .auth import CanEdit, CanRead, Owner, current_user
from .db import RevisionRow, SceneRow, UserRow, aware, now
from .deps import get_db

router = APIRouter(prefix="/api", tags=["scenes"], dependencies=[Depends(current_user)])
DB = Annotated[Session, Depends(get_db)]


@router.post("/games/{game_id}/scenes", status_code=201)
def create_scene(
    game_id: str, db: DB, _: CanEdit, body: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    game = store.get_game(db, game_id)
    taken = store.taken_scene_ids(db, game_id)
    requested = body.pop("id", None)
    if requested:
        store.check_slug(requested)
        if requested in taken:
            raise HTTPException(409, f"a scene called '{requested}' already exists")
        scene_id = requested
    else:
        scene_id = store.unique_slug(store.slugify(body.get("title") or "scene"), taken)
    unknown = set(body) - set(store.SCENE_FIELDS)
    if unknown:
        raise HTTPException(422, f"unknown fields: {', '.join(sorted(unknown))}")
    row = store.add_scene(db, game, scene_id, body)
    db.commit()
    return store.scene_api(row)


@router.patch("/games/{game_id}/scenes/{pk}")
def update_scene(
    game_id: str, pk: int, db: DB, access: CanEdit, changes: Annotated[dict[str, Any], Body()]
) -> dict[str, Any]:
    """Change a scene's fields. Changing ``id`` renames every reference to the scene.

    Returns ``{"scene": ...}``, or ``{"game": ...}`` (the whole game) after a rename.
    """
    game = store.get_game(db, game_id)
    row = store.get_scene(db, game_id, pk)
    expected = changes.pop("rev", None)
    if expected is not None and expected != row.rev:
        raise HTTPException(
            409, {"message": "this scene was changed elsewhere", "scene": store.scene_api(row)}
        )
    new_id = changes.pop("id", None)
    unknown = set(changes) - set(store.SCENE_FIELDS)
    if unknown:
        raise HTTPException(422, f"unknown fields: {', '.join(sorted(unknown))}")

    if changes:
        data = store.normalize_scene(row.scene_id, {**row.data, **changes})
        if data != row.data:
            row.data = data
            row.rev += 1
            row.updated_at = now()
            store.record_revision(db, row)
            store.touch(game)

    if new_id is not None and new_id != row.scene_id:
        store.check_slug(new_id)
        if new_id in store.taken_scene_ids(db, game_id):
            raise HTTPException(409, f"a scene called '{new_id}' already exists")
        scenes = store.live_scenes(db, game_id)
        model = store.assemble(game, scenes)
        store.apply_game(
            db, game, scenes, rename(model, Kind.SCENE, row.scene_id, new_id), reason="rename"
        )
        db.commit()
        return {"game": store.game_api(game, store.live_scenes(db, game_id), access)}

    db.commit()
    return {"scene": store.scene_api(row)}


@router.delete("/games/{game_id}/scenes/{pk}")
def delete_scene(game_id: str, pk: int, db: DB, _: CanEdit) -> dict[str, bool]:
    game = store.get_game(db, game_id)
    row = store.get_scene(db, game_id, pk)
    store.record_revision(db, row, "deleted")
    row.deleted_at = now()
    store.touch(game)
    db.commit()
    return {"ok": True}


@router.post("/trash/scenes/{pk}/restore")
def restore_scene(pk: int, db: DB, _: Owner) -> dict[str, Any]:
    row = db.get(SceneRow, pk)
    if row is None or row.deleted_at is None:
        raise HTTPException(404, "scene not found in the trash")
    game = store.get_game(db, row.game_id)
    taken = store.taken_scene_ids(db, row.game_id)
    if row.scene_id in taken:
        row.scene_id = store.unique_slug(f"{row.scene_id}_restored", taken)
    row.deleted_at = None
    row.updated_at = now()
    store.record_revision(db, row, "restored")
    store.touch(game)
    db.commit()
    return store.scene_api(row)


@router.delete("/trash/scenes/{pk}")
def purge_scene(pk: int, db: DB, _: Owner) -> dict[str, bool]:
    row = db.get(SceneRow, pk)
    if row is None or row.deleted_at is None:
        raise HTTPException(404, "scene not found in the trash")
    db.delete(row)
    db.commit()
    return {"ok": True}


class Positions(BaseModel):
    positions: dict[int, tuple[float, float]]


@router.post("/games/{game_id}/scenes/positions")
def set_positions(game_id: str, body: Positions, db: DB, _: CanEdit) -> dict[str, bool]:
    """Save graph layout. Doesn't count as an edit (no revision, no rev change)."""
    store.get_game(db, game_id)
    for pk, (x, y) in body.positions.items():
        row = store.get_scene(db, game_id, pk)
        row.data = {**row.data, "position": [round(x, 1), round(y, 1)]}
    db.commit()
    return {"ok": True}


class Order(BaseModel):
    order: list[int]


@router.post("/games/{game_id}/scenes/order")
def set_order(game_id: str, body: Order, db: DB, _: CanEdit) -> dict[str, bool]:
    store.get_game(db, game_id)
    for i, pk in enumerate(body.order):
        store.get_scene(db, game_id, pk).sort = float(i + 1)
    db.commit()
    return {"ok": True}


@router.get("/games/{game_id}/scenes/{pk}/revisions")
def list_revisions(game_id: str, pk: int, db: DB, _: CanRead) -> list[dict[str, Any]]:
    store.get_game(db, game_id)
    row = db.get(SceneRow, pk)
    if row is None or row.game_id != game_id:
        raise HTTPException(404, "scene not found")
    revisions = db.scalars(
        select(RevisionRow).where(RevisionRow.scene_pk == pk).order_by(RevisionRow.id.desc())
    ).all()
    names = {uid: name for uid, name in db.execute(select(UserRow.id, UserRow.username))}
    return [
        {
            "id": r.id,
            "reason": r.reason,
            # None for changes made before accounts existed
            "by": None if r.user_id is None else names.get(r.user_id, "(removed account)"),
            "created_at": aware(r.created_at).isoformat(),
            "updated_at": aware(r.updated_at).isoformat(),
            "snapshot": r.snapshot,
        }
        for r in revisions
    ]


@router.post("/games/{game_id}/scenes/{pk}/revisions/{revision_id}/restore")
def restore_revision(game_id: str, pk: int, revision_id: int, db: DB, _: CanEdit) -> dict[str, Any]:
    """Bring back an earlier version of the scene's content (its id is kept as is)."""
    game = store.get_game(db, game_id)
    row = store.get_scene(db, game_id, pk)
    revision = db.get(RevisionRow, revision_id)
    if revision is None or revision.scene_pk != pk:
        raise HTTPException(404, "revision not found")
    data = {k: v for k, v in revision.snapshot.items() if k in store.SCENE_FIELDS}
    row.data = store.normalize_scene(row.scene_id, data)
    row.rev += 1
    row.updated_at = now()
    store.record_revision(db, row, "restored")
    store.touch(game)
    db.commit()
    return store.scene_api(row)
