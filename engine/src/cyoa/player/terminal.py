"""Terminal input/output, isolated so the player can be driven by tests."""

from __future__ import annotations

import contextlib
import os
import sys
import time
from collections.abc import Iterator
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
        """True if the player pressed a key since the last check (see ``skippable``)."""
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

    @contextlib.contextmanager
    def skippable(self) -> Iterator[None]:
        """While text animates: keys skip it, aren't shown, and are thrown away after.

        On Unix the terminal echoes keys as they're typed, and an echoed Enter moves
        the cursor to the next line in the middle of the text. Turning off echo and
        line mode also lets any key skip, not just Enter. Windows doesn't echo keys
        nobody is reading, so there it only throws them away.
        """
        saved = self._quiet_keys()
        try:
            yield
        finally:
            self.drain_input()
            if saved is not None:
                import termios

                with contextlib.suppress(OSError, ValueError, termios.error):
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSAFLUSH, saved)

    def _quiet_keys(self) -> list[Any] | None:
        """Turn off echo and line mode on Unix; returns the settings to restore."""
        if not self.interactive or os.name == "nt":
            return None
        import termios

        try:
            fd = sys.stdin.fileno()
            saved = termios.tcgetattr(fd)
            quiet = termios.tcgetattr(fd)
            quiet[3] &= ~(termios.ECHO | termios.ICANON)
            quiet[6][termios.VMIN] = 1
            quiet[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, quiet)
        except (OSError, ValueError, termios.error):
            return None
        return saved

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
