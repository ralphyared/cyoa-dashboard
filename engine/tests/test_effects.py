from __future__ import annotations

import io
import os
import random
import select
import sys
import time

import pytest
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


def test_numbered_type_speeds():
    slowest, fastest = ClockTerminal(), ClockTerminal()
    play("[type 1]abcd[/type]", slowest)
    play("[type 9]abcd[/type]", fastest)
    assert round(slowest.slept, 3) == round(4 / 10, 3)
    assert round(fastest.slept, 4) == round(4 / 350, 4)


def test_plain_type_uses_the_given_speed():
    term = ClockTerminal()
    [page] = style("[type]abcd[/type]")
    player = LinePlayer(term, base_delay=0.0, effects=True, type_cps=10, rng=random.Random(1))
    for line in to_text(page).wrap(term.console, 70):
        player.play(line)
    assert round(term.slept, 3) == 0.4


@pytest.mark.skipif(os.name == "nt", reason="Unix terminals")
def test_keys_are_hidden_and_thrown_away_while_text_animates(monkeypatch):
    import pty
    import termios

    master, slave = pty.openpty()
    stdin = os.fdopen(slave, "r")
    monkeypatch.setattr(sys, "stdin", stdin)

    def line_mode_and_echo() -> int:
        return termios.tcgetattr(slave)[3] & (termios.ICANON | termios.ECHO)

    def pressed_soon(term: Terminal) -> bool:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if term.key_pressed():
                return True
            time.sleep(0.01)
        return False

    try:
        term = Terminal(Console(file=io.StringIO()), interactive=True)
        assert line_mode_and_echo() == termios.ICANON | termios.ECHO
        with term.skippable():
            assert line_mode_and_echo() == 0
            os.write(master, b"x")  # any key, not just Enter
            assert pressed_soon(term)
            os.write(master, b"\r")
        assert line_mode_and_echo() == termios.ICANON | termios.ECHO
        assert not term.key_pressed()  # thrown away
        ready, _, _ = select.select([master], [], [], 0.1)
        assert not ready or b"x" not in os.read(master, 1024)  # never echoed
    finally:
        stdin.close()
        os.close(master)
