"""Settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class Config:
    password: str
    data_dir: Path
    secure_cookies: bool = True
    session_days: int = 30
    static_dir: Path | None = None
    playtest_limit: int = 4
    playtest_idle_minutes: int = 60
    backup_keep: int = 14
    player_repo: str = "ralphyared/cyoa-dashboard"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cyoa.db"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @classmethod
    def from_env(cls) -> Config:
        password = os.environ.get("CYOA_PASSWORD", "")
        if not password:
            raise SystemExit("CYOA_PASSWORD must be set to the dashboard password.")
        static = os.environ.get("CYOA_STATIC_DIR")
        return cls(
            password=password,
            data_dir=Path(os.environ.get("CYOA_DATA_DIR", "data")),
            secure_cookies=_bool(os.environ.get("CYOA_SECURE_COOKIES"), True),
            session_days=int(os.environ.get("CYOA_SESSION_DAYS", "30")),
            static_dir=Path(static) if static else None,
            playtest_limit=int(os.environ.get("CYOA_PLAYTEST_LIMIT", "4")),
            playtest_idle_minutes=int(os.environ.get("CYOA_PLAYTEST_IDLE_MINUTES", "60")),
            backup_keep=int(os.environ.get("CYOA_BACKUP_KEEP", "14")),
            player_repo=os.environ.get("CYOA_PLAYER_REPO", "ralphyared/cyoa-dashboard"),
        )
