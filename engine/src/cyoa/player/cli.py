"""Command line entry point: ``cyoa-play [GAME_FILE]``."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.text import Text

from .. import __version__
from ..model import Game, GameFileError, load_game
from ..runtime import GameError, GameState, Runtime
from ..validate import Severity, validate
from .app import Player, StateSink
from .storage import OptionsStore, SaveStore
from .terminal import Terminal

GAME_SUFFIX = ".cyoa.json"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cyoa-play",
        description="Play a choose-your-own-adventure game in the terminal.",
    )
    p.add_argument("game", nargs="?", help=f"the game file (*{GAME_SUFFIX})")
    p.add_argument("--check", action="store_true", help="check the game for problems and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    debug = p.add_argument_group("authoring / playtest")
    debug.add_argument(
        "--debug", action="store_true", help="show author problems and enable : debug commands"
    )
    debug.add_argument("--start", metavar="SCENE", help="start directly at this scene")
    debug.add_argument("--state", metavar="FILE", help="start from a saved state (JSON)")
    debug.add_argument(
        "--state-fd",
        type=int,
        metavar="FD",
        help="write state updates as JSON lines to this file descriptor",
    )
    debug.add_argument("--save-dir", metavar="DIR", help="keep saves in this folder")
    debug.add_argument(
        "--no-options", action="store_true", help="don't read or write the player's saved options"
    )
    debug.add_argument(
        "--ignore-errors", action="store_true", help="play even if the game has errors"
    )
    return p


def find_game_file() -> Path | None:
    """With no argument, look for a single game next to the player or in the current folder."""
    folders = [Path.cwd()]
    if getattr(sys, "frozen", False):
        folders.insert(0, Path(sys.executable).resolve().parent)
    for folder in folders:
        found = sorted(folder.glob(f"*{GAME_SUFFIX}"))
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            return _pick(found)
    return None


def _message_console() -> Console:
    """Output for command-line messages: never hard-wrapped, so paths and errors
    stay intact when copied, piped or grepped (the terminal wraps them instead)."""
    return Console(highlight=False, emoji=False, soft_wrap=True)


def _pick(files: list[Path]) -> Path | None:
    console = _message_console()
    console.print("Several games found:")
    for i, f in enumerate(files, start=1):
        console.print(f"  {i}) {f.name}")
    while True:
        try:
            answer = console.input("Which one? ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(files):
            return files[int(answer) - 1]


def _print_issues(console: Console, game: Game, *, errors_only: bool) -> int:
    issues = validate(game)
    shown = [i for i in issues if i.severity == Severity.ERROR or not errors_only]
    for issue in shown:
        where = " / ".join(
            f"{k} '{v}'"
            for k, v in (
                ("scene", issue.scene),
                ("choice", issue.choice),
                ("rule", issue.rule),
                ("variable", issue.variable),
                ("item", issue.item),
            )
            if v
        )
        if issue.field:
            where = f"{where} ({issue.field})" if where else issue.field
        style = "red" if issue.severity == Severity.ERROR else "yellow"
        console.print(
            Text.assemble((f"{issue.severity.value:>7}", style), f"  {where}: ", issue.message)
        )
    return sum(1 for i in issues if i.severity == Severity.ERROR)


def _state_sink(fd: int) -> StateSink:
    stream = os.fdopen(fd, "w", buffering=1, encoding="utf-8")

    def sink(event: dict[str, Any]) -> None:
        with contextlib.suppress(OSError, ValueError):
            stream.write(json.dumps(event) + "\n")

    return sink


def _starting_state(game: Game, args: argparse.Namespace) -> GameState | None:
    if not (args.start or args.state):
        return None
    rt = Runtime(game)
    if args.state:
        data = json.loads(Path(args.state).read_text(encoding="utf-8"))
        state, _ = rt.restore_save({"state": data})
    else:
        state = rt.initial_state()
    if args.start:
        rt.enter(state, args.start)
    elif not args.state:
        rt.enter(state, game.start_scene)
    return state


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    console = _message_console()

    path = Path(args.game) if args.game else find_game_file()
    if path is None:
        console.print(f"No game file found. Usage: cyoa-play GAME{GAME_SUFFIX}", style="red")
        return 2
    try:
        game = load_game(path)
    except GameFileError as e:
        console.print(f"Can't open the game: {e}", style="red")
        return 2

    if args.check:
        errors = _print_issues(console, game, errors_only=False)
        if errors == 0:
            console.print("No errors.", style="green")
        return 1 if errors else 0

    if not (args.debug or args.ignore_errors):
        errors = [i for i in validate(game) if i.severity == Severity.ERROR]
        if errors:
            console.print("This game has errors and can't be played safely:\n", style="red")
            _print_issues(console, game, errors_only=True)
            console.print("\nPlease let the author know. (Use --ignore-errors to play anyway.)")
            return 2

    saves = SaveStore.for_game(game.id, Path(args.save_dir) if args.save_dir else None)
    options = OptionsStore(None) if args.no_options else OptionsStore.default()
    sink = _state_sink(args.state_fd) if args.state_fd is not None else None
    try:
        start = _starting_state(game, args)
    except (OSError, ValueError, GameError) as e:
        console.print(f"Can't start there: {e}", style="red")
        return 2
    screen = Terminal(Console(highlight=False, emoji=False))
    player = Player(game, screen, saves=saves, options=options, debug=args.debug, state_sink=sink)
    player.run(start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
