"""Database snapshots: daily automatic ones plus manual ones on request."""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .auth import require_owner
from .config import Config
from .deps import get_config

log = logging.getLogger(__name__)
NAME_RE = re.compile(r"^(auto|manual)-\d{8}-\d{6}\.db$")
MANUAL_KEEP = 20

# Backups hold every game (and every account), so only the owner gets them.
router = APIRouter(prefix="/api", tags=["backups"], dependencies=[Depends(require_owner)])


def create_backup(config: Config, kind: str = "manual") -> Path:
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = config.backup_dir / f"{kind}-{stamp}.db"
    tmp = target.with_suffix(".tmp")
    src = sqlite3.connect(config.db_path)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    tmp.replace(target)
    prune(config, kind)
    return target


def list_backups(config: Config) -> list[Path]:
    if not config.backup_dir.exists():
        return []
    return sorted(
        (p for p in config.backup_dir.iterdir() if NAME_RE.match(p.name)),
        key=lambda p: p.name.split("-", 1)[1],
        reverse=True,
    )


def prune(config: Config, kind: str) -> None:
    keep = config.backup_keep if kind == "auto" else MANUAL_KEEP
    mine = [p for p in list_backups(config) if p.name.startswith(kind + "-")]
    for old in mine[keep:]:
        old.unlink(missing_ok=True)


def latest_auto(config: Config) -> datetime | None:
    for p in list_backups(config):
        if p.name.startswith("auto-"):
            stamp = p.name.removeprefix("auto-").removesuffix(".db")
            return datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    return None


async def backup_loop(config: Config, interval: timedelta = timedelta(days=1)) -> None:
    while True:
        try:
            last = latest_auto(config)
            if last is None or datetime.now(UTC) - last >= interval:
                path = await asyncio.to_thread(create_backup, config, "auto")
                log.info("automatic backup written to %s", path)
        except Exception:
            log.exception("automatic backup failed")
        await asyncio.sleep(3600)


def _describe(path: Path) -> dict[str, Any]:
    kind, stamp = path.name.removesuffix(".db").split("-", 1)
    when = datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    return {
        "name": path.name,
        "kind": kind,
        "created_at": when.isoformat(),
        "size": path.stat().st_size,
    }


@router.get("/backups")
def backups(config: Annotated[Config, Depends(get_config)]) -> list[dict[str, Any]]:
    return [_describe(p) for p in list_backups(config)]


@router.post("/backups", status_code=201)
def make_backup(config: Annotated[Config, Depends(get_config)]) -> dict[str, Any]:
    return _describe(create_backup(config, "manual"))


@router.get("/backups/{name}")
def download_backup(name: str, request: Request) -> FileResponse:
    config = get_config(request)
    if not NAME_RE.match(name):
        raise HTTPException(404, "backup not found")
    path = config.backup_dir / name
    if not path.exists():
        raise HTTPException(404, "backup not found")
    return FileResponse(path, media_type="application/octet-stream", filename=f"cyoa-{name}")
