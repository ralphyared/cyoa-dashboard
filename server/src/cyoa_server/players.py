"""Standalone game exports: a prebuilt player with the story attached.

Player executables are built by the "Player executables" GitHub workflow and
published as release assets (tags ``player-v*``). The server downloads the latest
release into ``<data>/players/<tag>/`` on demand and builds exports from there:

- Windows / Linux: one executable per story (the game JSON is appended to the
  player; see ``cyoa.standalone``). Linux ships as .tar.gz to keep the executable bit.
- macOS: a zip with the unmodified player and the game file next to it, because
  changing a signed macOS executable invalidates its signature.
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from cyoa.model import Game
from cyoa.standalone import attach

log = logging.getLogger(__name__)

TAG_PREFIX = "player-v"
USER_AGENT = "cyoa-dashboard"


@dataclass(frozen=True, slots=True)
class Platform:
    key: str
    label: str
    asset: str


PLATFORMS: dict[str, Platform] = {
    p.key: p
    for p in (
        Platform("windows", "Windows", "cyoa-play-windows-x64.exe"),
        Platform("linux", "Linux", "cyoa-play-linux-x64"),
        Platform("macos-arm64", "macOS (Apple Silicon)", "cyoa-play-macos-arm64"),
        Platform("macos-x64", "macOS (Intel)", "cyoa-play-macos-x64"),
    )
}


class PlayerUnavailable(Exception):
    """No player build for that platform (not released yet, or download failed)."""


def _get_json(url: str, timeout: float = 20) -> Any:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _download(url: str, target: Path, timeout: float = 120) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".download-")
    tmp = Path(tmp_name)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(fd, "wb") as f:
            shutil.copyfileobj(response, f)
        tmp.replace(target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class PlayerStore:
    def __init__(self, root: Path, repo: str) -> None:
        self.root = root
        self.repo = repo
        self._lock = threading.Lock()

    @property
    def _current_file(self) -> Path:
        return self.root / "current.json"

    def current(self) -> dict[str, Any] | None:
        try:
            return json.loads(self._current_file.read_text())
        except (OSError, ValueError):
            return None

    def status(self) -> dict[str, Any]:
        current = self.current() or {}
        tag = current.get("tag")
        return {
            "repo": self.repo,
            "version": tag,
            "checked_at": current.get("checked_at"),
            "platforms": [
                {"key": p.key, "label": p.label, "available": self.path(p.key) is not None}
                for p in PLATFORMS.values()
            ],
        }

    def path(self, platform: str) -> Path | None:
        current = self.current()
        spec = PLATFORMS.get(platform)
        if not current or not spec:
            return None
        path = self.root / current["tag"] / spec.asset
        return path if path.is_file() else None

    def update(self) -> dict[str, Any]:
        """Download the newest released player builds (if not already here)."""
        with self._lock:
            releases = _get_json(f"https://api.github.com/repos/{self.repo}/releases?per_page=30")
            release = next(
                (
                    r
                    for r in releases
                    if str(r.get("tag_name", "")).startswith(TAG_PREFIX)
                    and not r.get("draft")
                    and not r.get("prerelease")
                ),
                None,
            )
            if release is None:
                raise PlayerUnavailable(
                    f"no player release found on github.com/{self.repo} (push a "
                    f"'{TAG_PREFIX}…' tag to build one)"
                )
            tag = re.sub(r"[^A-Za-z0-9._-]", "_", release["tag_name"])
            wanted = {p.asset for p in PLATFORMS.values()}
            for asset in release.get("assets", []):
                if asset.get("name") in wanted:
                    target = self.root / tag / asset["name"]
                    if not target.exists() or target.stat().st_size != asset.get("size"):
                        log.info("downloading %s %s", tag, asset["name"])
                        _download(asset["browser_download_url"], target)
            self.root.mkdir(parents=True, exist_ok=True)
            self._current_file.write_text(
                json.dumps(
                    {
                        "tag": tag,
                        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    }
                )
            )
            for old in self.root.iterdir():
                if old.is_dir() and old.name != tag:
                    shutil.rmtree(old, ignore_errors=True)
            return self.status()

    def ensure(self, platform: str) -> Path:
        """The player for ``platform``, fetching releases once if we have none yet."""
        path = self.path(platform)
        if path is None and self.current() is None:
            try:
                self.update()
            except PlayerUnavailable:
                raise
            except Exception as e:  # network trouble, GitHub errors…
                raise PlayerUnavailable(f"couldn't download the player: {e}") from e
            path = self.path(platform)
        if path is None:
            label = PLATFORMS[platform].label if platform in PLATFORMS else platform
            raise PlayerUnavailable(f"the current player release has no {label} build")
        return path


# -- building exports ----------------------------------------------------------------

_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_filename(title: str, fallback: str = "game") -> str:
    name = _UNSAFE_FILENAME.sub(" ", title).strip(" .")
    name = re.sub(r"\s+", " ", name)[:60].strip(" .")
    return name or fallback


def content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


HOW_TO_PLAY_MAC = """\
{title}
{underline}

To play: double-click "{name}". It opens in the Terminal app.

The first time, macOS may say it can't verify the developer. If so:
  1. Open System Settings > Privacy & Security.
  2. Scroll down to the message about "{name}" and click "Open Anyway".
  3. Double-click "{name}" again and confirm.

Keep "{game_file}" in the same folder as "{name}"; that's the story itself.
"""


@dataclass(frozen=True, slots=True)
class Export:
    filename: str
    content: bytes


def build_export(game: Game, platform: str, player: Path) -> Export:
    name = safe_filename(game.title)
    game_json = json.dumps(game.to_player_dict(), ensure_ascii=False).encode("utf-8")
    player_bytes = player.read_bytes()

    if platform == "windows":
        return Export(f"{name}.exe", attach(player_bytes, game_json))

    if platform == "linux":
        buffer = io.BytesIO()
        program = attach(player_bytes, game_json)
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo(name)
            info.size = len(program)
            info.mode = 0o755
            info.mtime = int(time.time())
            tar.addfile(info, io.BytesIO(program))
        return Export(f"{name}-linux.tar.gz", buffer.getvalue())

    if platform.startswith("macos"):
        game_file = f"{safe_filename(game.title, 'game').replace(' ', '_').lower()}.cyoa.json"
        readme = HOW_TO_PLAY_MAC.format(
            title=game.title, underline="=" * len(game.title), name=name, game_file=game_file
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            folder = f"{name}/"
            program = zipfile.ZipInfo(folder + name, date_time=time.localtime()[:6])
            program.external_attr = 0o100755 << 16
            program.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(program, player_bytes)
            zf.writestr(folder + game_file, game_json)
            zf.writestr(folder + "How to play.txt", readme)
        suffix = "mac" if platform == "macos-arm64" else "mac-intel"
        return Export(f"{name}-{suffix}.zip", buffer.getvalue())

    raise ValueError(f"unknown platform {platform!r}")
