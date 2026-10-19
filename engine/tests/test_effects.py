from __future__ import annotations

import io
import random

from rich.console import Console

from cyoa.markup import style
from cyoa.player.effects import MARKER, LinePlayer, strip_markers, to_text
from cyoa.player.terminal import Terminal


class ClockTerminal(Terminal):
    """An interactive-looking terminal that records sleeps instead of waiting."""

    def __init__(self, presses_after: int | None = None) -> None:
        console = Console(file=io.StringIO(), width=80, force_terminal=True, color_system=None)
        super().__init__(console, interactive=True)
        self.slept = 0.0
        self.sleeps = 0
        self.presses_after = presses_after

    def sleep(self, seconds: float) -> None:
        self.slept += seconds
        self.sleeps += 1

    def key_pressed(self) -> bool:
        return self.presses_after is not None and self.sleeps >= self.presses_after

    @property
    def output(self) -> str:
        file = self.console.file
        assert isinstance(file, io.StringIO)
        return file.getvalue()


def play(markup: str, term: ClockTerminal, effects: bool = True, base_delay: float = 0.0):
    [page] = style(markup)
    player = LinePlayer(
        term, base_delay=base_delay, effects=effects, type_cps=80, rng=random.Random(1)
    )
    for line in to_text(page).wrap(term.console, 70):
        player.play(line)
        term.print()
    return player


def test_pause_waits_and_prints_nothing():
    term = ClockTerminal()
    play("Hello\n[pause 2]\nWorld", term)
    assert round(term.slept, 2) == 2.0
    assert MARKER not in term.output
    assert "Hello" in term.output and "World" in term.output


def test_glitch_animates_then_settles():
    term = ClockTerminal()
    play("[glitch]drip drip drip[/glitch]", term)
    assert term.sleeps == 14  # frames
    assert "\x1b[14D" in term.output  # moves back over the text between frames
    assert term.output.rstrip().endswith("drip drip drip")


def test_type_slow_takes_longer_than_type():
    slow, normal = ClockTerminal(), ClockTerminal()
    play("[type slow]abcd[/type]", slow)
    play("[type]abcd[/type]", normal)
    assert slow.slept > normal.slept > 0
    assert "abcd" in slow.output


def test_key_press_skips_the_rest_of_the_page():
    term = ClockTerminal(presses_after=3)
    player = play("[pause 5]\nA\n[pause 5]\n[glitch]B[/glitch]", term)
    assert player.skipping
    assert term.slept < 1
    assert "A" in term.output and "B" in term.output


def test_effects_off_prints_instantly():
    term = ClockTerminal()
    play("[glitch]x[/glitch] [type slow]y[/type]\n[pause 3]\nz", term, effects=False)
    assert term.slept == 0
    assert "x y" in term.output and "z" in term.output


def test_strip_markers():
    [page] = style("a [pause]b")
    text = to_text(page)
    assert MARKER in text.plain
    assert strip_markers(text).plain == "a b"
