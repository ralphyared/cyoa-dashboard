"""Authoring tools: validation, live expression checks, renames, references."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cyoa import markup
from cyoa.expr import (
    FUNCTIONS,
    ExprError,
    check_condition,
    check_expression,
    check_program,
    describe_requirement,
    parse_expression,
    parse_program,
    to_json,
)
from cyoa.markup import COLORS, TEXT_STYLES
from cyoa.refactor import Kind, find_references, rename
from cyoa.validate import SLUG_RE, VAR_NAME_RE, build_env, game_stats, validate

from . import store
from .auth import CanEdit, CanRead, current_user
from .deps import get_db

router = APIRouter(prefix="/api", tags=["tools"], dependencies=[Depends(current_user)])
DB = Annotated[Session, Depends(get_db)]


@router.get("/games/{game_id}/issues")
def issues(game_id: str, db: DB, _: CanRead) -> dict[str, Any]:
    game = store.load_game_model(db, game_id)
    return {"issues": [i.to_dict() for i in validate(game)], "stats": game_stats(game)}


class CheckBody(BaseModel):
    source: str
    mode: Literal["condition", "effects", "markup", "value"]


def _err(e: ExprError) -> dict[str, Any]:
    return {"message": e.message, "start": e.start, "end": e.end}


@router.post("/games/{game_id}/check")
def check(game_id: str, body: CheckBody, db: DB, _: CanRead) -> dict[str, Any]:
    """Parse and type-check one piece of source as the author types it.

    Returns the syntax tree (to drive the visual builders) and, for conditions,
    the hint players see when the choice is locked.
    """
    game = store.load_game_model(db, game_id)
    env = build_env(game)
    result: dict[str, Any] = {"errors": [], "ast": None, "hint": None}
    if not body.source.strip():
        return result
    try:
        if body.mode == "condition":
            expr = parse_expression(body.source)
            result["ast"] = to_json(expr)
            result["errors"] = [_err(e) for e in check_condition(expr, env)]
            labels = {v.name: v.display_label for v in game.variables}
            names = {i.id: i.display_name for i in game.items}
            result["hint"] = describe_requirement(expr, labels, names)
        elif body.mode == "value":
            expr = parse_expression(body.source)
            result["ast"] = to_json(expr)
            result["errors"] = [_err(e) for e in check_expression(expr, env)[1]]
        elif body.mode == "effects":
            program = parse_program(body.source)
            result["ast"] = to_json(program)
            result["errors"] = [_err(e) for e in check_program(program, env)]
        else:
            nodes = markup.parse_template(body.source)
            errors = []
            for node, offset, mode in markup.template_expressions(nodes):
                if mode == "effects":
                    found = check_program(node, env)  # type: ignore[arg-type]
                elif mode == "condition":
                    found = check_condition(node, env)  # type: ignore[arg-type]
                else:
                    found = check_expression(node, env)[1]  # type: ignore[arg-type]
                errors += [_err(e.shift(offset)) for e in found]
            result["errors"] = errors
    except ExprError as e:
        result["errors"] = [_err(e)]
    return result


class RenameBody(BaseModel):
    kind: Kind
    old: str
    new: str


@router.post("/games/{game_id}/rename")
def rename_reference(game_id: str, body: RenameBody, db: DB, access: CanEdit) -> dict[str, Any]:
    """Rename a variable, item, scene or chapter and update everything that uses it."""
    row = store.get_game(db, game_id)
    scenes = store.live_scenes(db, game_id)
    game = store.assemble(row, scenes)
    pattern = VAR_NAME_RE if body.kind == Kind.VARIABLE else SLUG_RE
    if not pattern.match(body.new):
        raise HTTPException(
            422,
            f"'{body.new}' isn't a valid {body.kind.value} id: use lowercase letters, digits and _",
        )
    existing = {
        Kind.VARIABLE: {v.name for v in game.variables},
        Kind.ITEM: {i.id for i in game.items},
        Kind.SCENE: {s.id for s in game.scenes},
        Kind.CHAPTER: {c.id for c in game.chapters},
    }[body.kind]
    if body.old not in existing:
        raise HTTPException(404, f"no {body.kind.value} called '{body.old}'")
    if body.new != body.old and body.new in existing:
        raise HTTPException(409, f"a {body.kind.value} called '{body.new}' already exists")
    store.apply_game(db, row, scenes, rename(game, body.kind, body.old, body.new), reason="rename")
    db.commit()
    return store.game_api(row, store.live_scenes(db, game_id), access)


@router.get("/games/{game_id}/references")
def references(
    game_id: str, db: DB, _: CanRead, kind: Kind, name: Annotated[str, Query()]
) -> dict[str, Any]:
    game = store.load_game_model(db, game_id)
    return {"references": find_references(game, kind, name)}


@router.get("/reference")
def language_reference() -> dict[str, Any]:
    """What the editors offer for autocomplete and help."""
    return {
        "functions": [
            {
                "name": f.name,
                "help": f.help,
                "params": list(f.params),
                "returns": f.returns.value if f.returns else None,
            }
            for f in FUNCTIONS.values()
        ],
        "colors": sorted(COLORS),
        "styles": sorted(TEXT_STYLES),
        "keywords": ["and", "or", "not", "true", "false"],
    }
