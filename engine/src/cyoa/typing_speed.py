"""Typing speed levels for the typewriter effect and [type N] passages."""

from __future__ import annotations

# Level → characters per second. 1 is the slowest, 9 the fastest.
TYPING_CPS: dict[int, float] = {
    1: 10.0,
    2: 18.0,
    3: 28.0,
    4: 40.0,
    5: 60.0,
    6: 80.0,
    7: 120.0,
    8: 200.0,
    9: 350.0,
}
TYPING_NAMES: dict[int, str] = {
    1: "very slow",
    2: "slow",
    3: "unhurried",
    4: "relaxed",
    5: "steady",
    6: "normal",
    7: "brisk",
    8: "fast",
    9: "very fast",
}
DEFAULT_TYPING_SPEED = 6
SLOWEST, FASTEST = min(TYPING_CPS), max(TYPING_CPS)


def describe(level: int) -> str:
    return f"{level} · {TYPING_NAMES[level]}"
