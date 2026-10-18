"""Terminal input/output, isolated so the player can be driven by tests."""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from rich.console import Console


class Terminal:
    def __init__(self, console: Console | None = None, *, interactive: bool | None = None) -> None:
        self.console = console or Console(highlight=False, emoji=False)
        self.interactive = (
            sys.stdin.isatty() and self.console.is_terminal if interactive is None else interactive
        )

    @property
    def width(self) -> int:
        return self.console.width

    def clear(self) -> None:
        self.console.clear()

    def print(self, *objects: Any, **kwargs: Any) -> None:
        self.console.print(*objects, **kwargs)

    def input(self, prompt: str = "") -> str:
        return self.console.input(prompt)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def key_pressed(self) -> bool:
        """True if the player pressed a key (Enter on Unix) since the last check."""
        if not self.interactive:
            return False
        if os.name == "nt":
            import msvcrt

            return bool(msvcrt.kbhit())  # type: ignore[attr-defined]
        import select

        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
        except (OSError, ValueError):
            return False
        return bool(ready)

    def drain_input(self) -> None:
        """Throw away keys pressed while text was printing."""
        if not self.interactive:
            return
        if os.name == "nt":
            import msvcrt

            while msvcrt.kbhit():  # type: ignore[attr-defined]
                msvcrt.getwch()  # type: ignore[attr-defined]
            return
        try:
            import termios

            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        except (ImportError, OSError, ValueError):
            pass
