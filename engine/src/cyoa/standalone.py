"""Standalone games: a player executable with a game file attached to its end.

The dashboard exports a single file per story by appending the game JSON and a
small trailer to a prebuilt player. The PyInstaller bootloader finds its own
archive by scanning the file back to front for its magic marker, so trailing
data is ignored by it; the player reads the attached game back on startup.

Layout: ``[player executable][game JSON, UTF-8][MAGIC (8 bytes)][length (uint64 LE)]``
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

MAGIC = b"CYOAGAME"
_TRAILER = struct.Struct("<8sQ")


def attach(player: bytes, game_json: bytes) -> bytes:
    """A copy of ``player`` that carries ``game_json``."""
    if b"\x0c\x0b\x0a\x0b\x0e" in game_json:
        # Could be mistaken for the bootloader's own marker; JSON never contains
        # these raw control characters, so this only guards against misuse.
        raise ValueError("game data contains control characters")
    return player + game_json + _TRAILER.pack(MAGIC, len(game_json))


def read_attached(path: str | Path) -> bytes | None:
    """The game JSON attached to the executable at ``path``, if any."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size < _TRAILER.size:
                return None
            f.seek(size - _TRAILER.size)
            magic, length = _TRAILER.unpack(f.read(_TRAILER.size))
            if magic != MAGIC or length > size - _TRAILER.size:
                return None
            f.seek(size - _TRAILER.size - length)
            return f.read(length)
    except OSError:
        return None


def is_frozen() -> bool:
    """True when running as a standalone executable (not via Python)."""
    return bool(getattr(sys, "frozen", False))


def attached_game() -> bytes | None:
    """The game attached to this running executable, if it is a standalone game."""
    if not is_frozen():
        return None
    return read_attached(sys.executable)
