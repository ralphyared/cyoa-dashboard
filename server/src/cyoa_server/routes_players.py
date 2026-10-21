"""Standalone game exports and the player builds they're made from."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from cyoa.validate import Severity, validate

from . import store
from .auth import CanEdit, Owner, current_user
from .deps import get_db
from .players import PLATFORMS, PlayerStore, PlayerUnavailable, build_export, content_disposition

router = APIRouter(prefix="/api", tags=["players"], dependencies=[Depends(current_user)])
DB = Annotated[Session, Depends(get_db)]
PLATFORM_PATTERN = "^(" + "|".join(PLATFORMS) + ")$"


def get_players(request: Request) -> PlayerStore:
    return request.app.state.players


Players = Annotated[PlayerStore, Depends(get_players)]


@router.get("/players")
def players_status(players: Players) -> dict[str, Any]:
    return players.status()


@router.post("/players/update")
def update_players(players: Players, _: Owner) -> dict[str, Any]:
    """Fetch the newest player release from GitHub."""
    try:
        return players.update()
    except PlayerUnavailable as e:
        raise HTTPException(404, str(e)) from None
    except Exception as e:
        raise HTTPException(502, f"couldn't reach GitHub: {e}") from None


@router.get("/games/{game_id}/standalone")
def standalone_export(
    game_id: str,
    db: DB,
    _: CanEdit,
    players: Players,
    platform: Annotated[str, Query(pattern=PLATFORM_PATTERN)],
) -> Response:
    """The story as a ready-to-play download for one operating system."""
    game = store.load_game_model(db, game_id)
    errors = [i.to_dict() for i in validate(game) if i.severity == Severity.ERROR]
    if errors:
        raise HTTPException(409, {"message": "fix the errors before exporting", "issues": errors})
    try:
        player = players.ensure(platform)
    except PlayerUnavailable as e:
        raise HTTPException(409, {"message": str(e), "code": "no_player"}) from None
    export = build_export(game, platform, player)
    return Response(
        export.content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": content_disposition(export.filename)},
    )
