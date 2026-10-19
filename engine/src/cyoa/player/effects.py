"""Animated scene text: typewriter, [pause N], [type …] and [glitch].

Effects travel from the markup to here as rich Style metadata (``meta["fx"]``);
pauses are zero-width marker characters carrying ``meta["pause"]``. Any key press
(Enter) skips the remaining animation on the page.
"""

from __future__ import annotations

import random

from rich.cells import cell_len
from rich.control import Control
from rich.style import Style
from rich.text import Text

from ..markup import StyledSpan
from ..typing_speed import TYPING_CPS
from .terminal import Terminal

MARKER = "​"  # zero-width; holds a pause
GLYPHS = "!#$%&*+/<=>?@\\^|~0123456789"
GLITCH_COLORS = ("red", "magenta", "cyan", "bright_white", "green")
GLITCH_FRAMES = 14
GLITCH_FRAME_SECONDS = 0.045


def to_text(spans: list[StyledSpan]) -> Text:
    text = Text()
    for span in spans:
        if span.pause:
            text.append(MARKER, style=Style(meta={"pause": span.pause}))
            continue
        style = Style.parse(span.rich_style()) if span.rich_style() else Style()
        if span.effect:
            style = style + Style(meta={"fx": span.effect})
        text.append(span.text, style=style)
    return text


def strip_markers(line: Text) -> Text:
    """The line without pause markers (for instant, unanimated printing)."""
    if MARKER not in line.plain:
        return line
    positions = [i for i, c in enumerate(line.plain) if c == MARKER]
    cuts = sorted({*positions, *(p + 1 for p in positions)})
    pieces = [piece for piece in line.divide(cuts) if piece.plain != MARKER]
    return Text("").join(pieces)


class LinePlayer:
    """Prints wrapped lines one piece at a time, honouring effects."""

    def __init__(
        self,
        term: Terminal,
        *,
        base_delay: float,
        effects: bool,
        type_cps: float,
        rng: random.Random | None = None,
    ) -> None:
        self.term = term
        self.base_delay = base_delay
        self.effects = effects
        self.type_delays = {
            "type": 1.0 / type_cps,
            **{f"type_{level}": 1.0 / cps for level, cps in TYPING_CPS.items()},
        }
        self.rng = rng or random.Random()
        self.skipping = False

    def play(self, line: Text) -> None:
        line = line.copy()
        line.end = ""
        for segment in line.render(self.term.console):
            text, style = segment.text, segment.style or Style()
            if not text:
                continue
            meta = style.meta or {}
            if MARKER in text:
                if "pause" in meta and self.effects and not self.skipping:
                    self._wait(float(meta["pause"]) * text.count(MARKER))
                text = text.replace(MARKER, "")
                if not text:
                    continue
            fx = meta.get("fx") if self.effects else None
            if self.skipping:
                self._write(text, style)
            elif fx == "glitch":
                self._glitch(text, style)
            elif fx in self.type_delays:
                self._type(text, style, self.type_delays[fx])
            elif self.base_delay:
                self._type(text, style, self.base_delay)
            else:
                self._write(text, style)

    def _write(self, text: str, style: Style) -> None:
        if text:
            self.term.print(Text(text, style=style), end="", soft_wrap=True)

    def _check_skip(self) -> bool:
        if self.term.key_pressed():
            self.skipping = True
        return self.skipping

    def _wait(self, seconds: float) -> None:
        remaining = seconds
        while remaining > 0:
            step = min(0.05, remaining)
            self.term.sleep(step)
            remaining -= step
            if self._check_skip():
                return

    def _type(self, text: str, style: Style, delay: float) -> None:
        for i, char in enumerate(text):
            self._write(char, style)
            if not char.isspace():
                self.term.sleep(delay)
            if self._check_skip():
                self._write(text[i + 1 :], style)
                return

    def _glitch(self, text: str, style: Style) -> None:
        width = cell_len(text)
        lock = [self.rng.randint(2, GLITCH_FRAMES) for _ in text]
        for frame_no in range(GLITCH_FRAMES):
            frame = Text()
            for char, locked_at in zip(text, lock, strict=True):
                if char.isspace() or frame_no >= locked_at:
                    frame.append(char, style=style)
                else:
                    frame.append(
                        self.rng.choice(GLYPHS),
                        style=Style(
                            color=self.rng.choice(GLITCH_COLORS), bold=self.rng.random() < 0.3
                        ),
                    )
            self.term.print(frame, end="", soft_wrap=True)
            self.term.sleep(GLITCH_FRAME_SECONDS)
            if width:
                self.term.console.control(Control.move(-width, 0))
            if self._check_skip():
                break
        self._write(text, style)
