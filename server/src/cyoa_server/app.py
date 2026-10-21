"""The FastAPI application."""

from __future__ import annotations

import asyncio
import contextlib
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import (
    auth,
    backups,
    playtest,
    routes_games,
    routes_people,
    routes_players,
    routes_scenes,
    routes_tools,
)
from .config import Config
from .db import Database
from .players import PlayerStore

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(config: Config, *, run_backups: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(backups.backup_loop(config)) if run_backups else None
        yield
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="CYOA Dashboard",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.config = config
    app.state.db = Database(config.db_path)
    with app.state.db.new_session() as db:
        auth.ensure_owner(db)
    app.state.playtests = 0
    app.state.playtest_users = Counter[int]()
    app.state.players = PlayerStore(config.data_dir / "players", config.player_repo)

    @app.middleware("http")
    async def check_origin(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in UNSAFE_METHODS and not auth.same_origin(
            request.headers.get("origin"), request.headers.get("host")
        ):
            return JSONResponse({"detail": "cross-site request refused"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    for module in (
        auth,
        routes_people,
        routes_games,
        routes_scenes,
        routes_tools,
        routes_players,
        backups,
        playtest,
    ):
        app.include_router(module.router)

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict[str, bool]:
        return {"ok": True}

    if config.static_dir is not None:
        _mount_frontend(app, config.static_dir)
    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    index = static_dir / "index.html"
    assets = static_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and static_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
