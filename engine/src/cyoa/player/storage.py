"""Player options and save slots on disk."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "cyoa"
SLOTS = ("1", "2", "3", "4", "5")
AUTO = "auto"
SPEEDS = {"slow": 35.0, "normal": 80.0, "fast": 200.0}  # characters per second
WIDTHS = (None, 60, 70, 80, 100, 120)  # None: use the game's setting


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass(slots=True)
class Options:
    typewriter: bool | None = None  # None: use the game's default
    speed: str = "normal"
    width: int | None = None


class OptionsStore:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    @classmethod
    def default(cls) -> OptionsStore:
        return cls(Path(user_config_dir(APP_NAME)) / "options.json")

    def load(self) -> Options:
        if self.path is None or not self.path.exists():
            return Options()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            options = Options(
                typewriter=data.get("typewriter"),
                speed=data.get("speed", "normal"),
                width=data.get("width"),
            )
        except (OSError, ValueError, AttributeError):
            return Options()
        if options.speed not in SPEEDS:
            options.speed = "normal"
        if options.width not in WIDTHS:
            options.width = None
        return options

    def save(self, options: Options) -> None:
        if self.path is None:
            return
        # options are a convenience; never crash over them
        with contextlib.suppress(OSError):
            _atomic_write(self.path, asdict(options))


@dataclass(slots=True)
class SlotInfo:
    slot: str
    label: str
    saved_at: str
    damaged: bool = False


class SaveStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @classmethod
    def for_game(cls, game_id: str, base: Path | None = None) -> SaveStore:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", game_id) or "game"
        root = base if base is not None else Path(user_data_dir(APP_NAME)) / "saves"
        return cls(root / safe_id)

    def _path(self, slot: str) -> Path:
        return self.directory / ("auto.json" if slot == AUTO else f"slot{slot}.json")

    def write(self, slot: str, data: dict[str, Any]) -> None:
        _atomic_write(self._path(slot), data)

    def read(self, slot: str) -> dict[str, Any] | None:
        path = self._path(slot)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def info(self, slot: str) -> SlotInfo | None:
        if not self._path(slot).exists():
            return None
        data = self.read(slot)
        if data is None:
            return SlotInfo(slot, "(damaged save)", "", damaged=True)
        saved_at = str(data.get("saved_at", ""))[:16].replace("T", " ")
        return SlotInfo(slot, str(data.get("label", "")), saved_at)

    def delete(self, slot: str) -> None:
        self._path(slot).unlink(missing_ok=True)

    def any_saves(self) -> bool:
        return any(self.info(s) is not None for s in (AUTO, *SLOTS))
