"""The interactive terminal player."""

from __future__ import annotations

import contextlib
import shlex
from collections.abc import Callable
from typing import Any

from rich import box
from rich.align import Align
from rich.cells import cell_len
from rich.color import Color, ColorParseError
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from ..markup import Page, StyledSpan
from ..model import EndingKind, Game
from ..runtime import ChoiceView, GameError, GameState, Runtime, SceneView
from .storage import AUTO, SLOTS, SPEEDS, WIDTHS, Options, OptionsStore, SaveStore
from .terminal import Terminal

StateSink = Callable[[dict[str, Any]], None]
MARGIN = "  "


def to_text(spans: list[StyledSpan]) -> Text:
    text = Text()
    for span in spans:
        text.append(span.text, style=span.rich_style() or None)
    return text


def art_block(art: str, style: str = "") -> Align:
    """ASCII art centered as a block, so its lines keep their alignment."""
    lines = art.strip("\n").splitlines()
    width = max((cell_len(line) for line in lines), default=0)
    text = Text("\n".join(line + " " * (width - cell_len(line)) for line in lines), style=style)
    text.no_wrap = True
    text.overflow = "crop"
    return Align.center(text)


def _valid_color(name: str, fallback: str = "cyan") -> str:
    try:
        Color.parse(name)
    except ColorParseError:
        return fallback
    return name


class _BackToTitle(Exception):
    pass


class Player:
    def __init__(
        self,
        game: Game,
        term: Terminal | None = None,
        *,
        saves: SaveStore | None = None,
        options: OptionsStore | None = None,
        debug: bool = False,
        state_sink: StateSink | None = None,
    ) -> None:
        self.game = game
        self.rt = Runtime(game)
        self.term = term or Terminal()
        self.saves = saves or SaveStore.for_game(game.id)
        self.options_store = options or OptionsStore(None)
        self.options: Options = self.options_store.load()
        self.debug = debug
        self.state_sink = state_sink
        self.accent = _valid_color(game.settings.accent_color)

    # -- layout helpers ------------------------------------------------------------

    @property
    def width(self) -> int:
        wanted = self.options.width or self.game.settings.text_width
        return max(20, min(wanted, self.term.width))

    def out(self, renderable: Any = "", **kwargs: Any) -> None:
        kwargs.setdefault("width", self.width)
        self.term.print(renderable, **kwargs)

    def ask(self, prompt: str = "> ") -> str:
        return self.term.input(f"{MARGIN}[{self.accent}]{prompt}[/]").strip()

    def pause(self, message: str = "press Enter to continue") -> None:
        self.out()
        self.ask(f"— {message} — ")

    def notice(self, message: str, style: str = "yellow") -> None:
        self.out(Text(MARGIN + message, style=style))

    @property
    def typewriter_on(self) -> bool:
        if not self.term.interactive:
            return False
        if self.options.typewriter is None:
            return self.game.settings.typewriter
        return self.options.typewriter

    def write_text(self, text: Text, *, animate: bool) -> None:
        """Print wrapped body text, optionally with the typewriter effect."""
        lines = text.wrap(self.term.console, self.width - len(MARGIN))
        if not (animate and self.typewriter_on):
            for line in lines:
                self.term.print(Text(MARGIN) + line, width=self.width, soft_wrap=True)
            return
        delay = 1.0 / SPEEDS.get(self.options.speed, SPEEDS["normal"])
        skipping = False
        for line in lines:
            self.term.print(MARGIN, end="", soft_wrap=True)
            if skipping:
                self.term.print(line, soft_wrap=True)
                continue
            for i in range(len(line)):
                self.term.print(line[i : i + 1], end="", soft_wrap=True)
                if line.plain[i] != " ":
                    self.term.sleep(delay)
                if self.term.key_pressed():
                    skipping = True
                    self.term.print(line[i + 1 :], end="", soft_wrap=True)
                    break
            self.term.print(soft_wrap=True)
        if skipping:
            self.term.drain_input()

    # -- entry point -------------------------------------------------------------------

    def run(self, state: GameState | None = None) -> None:
        """Play from ``state`` if given (playtest), otherwise start at the title screen."""
        if self.term.interactive:
            self.term.console.set_window_title(self.game.title)
        try:
            if state is not None:
                with contextlib.suppress(_BackToTitle):
                    self.play(state)
            self.title_screen()
        except (KeyboardInterrupt, EOFError):
            self.term.print()
        self.term.print(Text(MARGIN + "Goodbye!", style="dim"))

    # -- title screen --------------------------------------------------------------------

    def draw_title(self) -> None:
        self.term.clear()
        settings = self.game.settings
        if settings.title_art.strip():
            self.out(art_block(settings.title_art, self.accent))
            self.out()
            self.out(Align.center(Text(self.game.title, style=f"bold {self.accent}")))
        else:
            self.out(
                Panel(
                    Align.center(Text(self.game.title, style=f"bold {self.accent}")),
                    box=box.DOUBLE,
                    border_style=self.accent,
                    padding=(1, 2),
                )
            )
        if self.game.author:
            self.out(Align.center(Text(f"by {self.game.author}", style="dim")))
        if self.game.description:
            self.out()
            self.out(Align.center(Text(self.game.description, style="italic")))
        self.out()

    def title_screen(self) -> None:
        message: str | None = None
        while True:
            self.draw_title()
            entries: list[tuple[str, Callable[[], None]]] = [("New Game", self.new_game)]
            if self.saves.info(AUTO) is not None:
                entries.append(("Continue", self.continue_game))
            if self.saves.any_saves():
                entries.append(("Load Game", self.load_from_title))
            entries.append(("Options", self.options_menu))
            entries.append(("Quit", lambda: None))
            for i, (label, _) in enumerate(entries, start=1):
                self.out(Text.assemble(MARGIN, (f"{i}) ", f"bold {self.accent}"), label))
            if message:
                self.out()
                self.notice(message)
                message = None
            self.out()
            answer = self.ask()
            if not answer.isdigit() or not 1 <= int(answer) <= len(entries):
                message = f"Choose a number from 1 to {len(entries)}."
                continue
            label, action = entries[int(answer) - 1]
            if label == "Quit":
                return
            with contextlib.suppress(_BackToTitle):
                action()

    def new_game(self) -> None:
        try:
            state = self.rt.new_game()
        except GameError as e:
            self.show_fatal(e)
            return
        self.show_intro(state)
        self.play(state)

    def show_intro(self, state: GameState) -> None:
        pages = self.rt.intro(state)
        for i, page in enumerate(pages):
            self.term.clear()
            self.out()
            self.write_text(to_text(page), animate=True)
            self.pause("press Enter to begin" if i == len(pages) - 1 else "press Enter to continue")

    def continue_game(self) -> None:
        state = self.restore(AUTO)
        if state is not None:
            self.play(state)

    def load_from_title(self) -> None:
        state = self.load_menu()
        if state is not None:
            self.play(state)

    def show_fatal(self, error: Exception) -> None:
        self.term.clear()
        self.notice(f"The game can't continue: {error}", style="bold red")
        self.pause()

    # -- the game loop ---------------------------------------------------------------------

    def play(self, state: GameState) -> None:
        animate = True
        last_page_only = False
        message: str | None = None
        while True:
            try:
                view = self.rt.view(state)
            except GameError as e:
                self.show_fatal(e)
                return
            if animate and view.ending is None:
                self.autosave(state)
            self.emit(state)
            self.draw_scene(view, animate=animate, last_page_only=last_page_only)
            animate = False
            last_page_only = True
            if view.ending is not None:
                next_state = self.ending_menu(view)
                if next_state is None:
                    return
                state = next_state
                animate = True
                last_page_only = False
                continue
            if message:
                self.notice(message)
                message = None
            command, arg = self.read_command(view)
            if command == "choose":
                try:
                    self.rt.choose(state, arg)
                    animate = True
                    last_page_only = False
                except GameError as e:
                    message = f"⚠ {e}"
            elif command == "inventory":
                self.inventory_screen(state)
            elif command == "save":
                message = self.save_menu(state)
            elif command == "load":
                loaded = self.load_menu()
                if loaded is not None:
                    state = loaded
                    animate = True
                    last_page_only = False
            elif command == "options":
                self.options_menu()
            elif command == "quit":
                return
            elif command == "debug":
                message = self.debug_command(state, arg)
                last_page_only = False

    def autosave(self, state: GameState) -> None:
        with contextlib.suppress(OSError):
            self.saves.write(AUTO, self.rt.make_save(state))

    def emit(self, state: GameState) -> None:
        if self.state_sink is None:
            return
        scene = self.rt.scenes.get(state.scene)
        self.state_sink(
            {
                "type": "state",
                "state": state.to_dict(),
                "scene_title": scene.title if scene else "",
                "problems": list(dict.fromkeys(self.rt.problems)),
            }
        )

    def draw_header(self, view: SceneView) -> None:
        right = view.chapter_title
        if self.game.settings.show_scene_titles and view.title:
            right = f"{right} · {view.title}" if right else view.title
        if view.status is not None or right:
            grid = Table.grid(expand=True)
            grid.add_column(ratio=1)
            grid.add_column(justify="right")
            grid.add_row(
                to_text(view.status) if view.status else Text(""),
                Text(right, style=f"bold {self.accent}"),
            )
            self.out(Padding(grid, (0, 1)))
            self.out(Rule(style=self.accent))
        if view.art.strip():
            self.out(art_block(view.art))
            self.out(Rule(style="dim"))
        self.out()

    def draw_scene(self, view: SceneView, *, animate: bool, last_page_only: bool) -> None:
        pages: list[Page] = view.pages or [[]]
        start = len(pages) - 1 if last_page_only else 0
        for i in range(start, len(pages)):
            self.term.clear()
            self.draw_header(view)
            self.write_text(to_text(pages[i]), animate=animate)
            if i < len(pages) - 1:
                self.pause()
        self.show_problems()
        if view.ending is not None:
            return
        self.out()
        if not view.choices:
            self.notice("There's nothing you can do here.", style="dim italic")
        self.draw_choices(view.choices)
        self.out()
        self.draw_footer()

    def draw_choices(self, choices: list[ChoiceView]) -> None:
        grid = Table.grid(padding=(0, 1))
        grid.add_column(no_wrap=True, justify="right")
        grid.add_column(ratio=1)
        number = 0
        for choice in choices:
            if choice.enabled:
                number += 1
                grid.add_row(Text(f"{number})", style=f"bold {self.accent}"), to_text(choice.text))
            else:
                text = Text(choice.plain_text, style="dim")
                hint = f"Requires: {choice.hint}" if choice.hint else "Locked"
                text.append(f"  [{hint}]", style="dim italic")
                grid.add_row(Text("-)", style="dim"), text)
        self.out(Padding(grid, (0, 0, 0, len(MARGIN))))

    def draw_footer(self) -> None:
        keys = [("I", "nventory"), ("S", "ave"), ("L", "oad"), ("O", "ptions"), ("Q", "uit")]
        parts: list[str | tuple[str, str]] = [MARGIN]
        for key, rest in keys:
            parts += [("[", "dim"), (key, f"bold {self.accent}"), ("]", "dim"), rest, "  "]
        if self.debug:
            parts += [("[", "dim"), (":", "bold magenta"), ("]", "dim"), "debug"]
        self.out(Text.assemble(*parts))

    def show_problems(self) -> None:
        if not self.debug or not self.rt.problems:
            return
        self.out()
        for problem in dict.fromkeys(self.rt.problems):
            self.notice(f"⚠ {problem}", style="magenta")

    def read_command(self, view: SceneView) -> tuple[str, str]:
        enabled = [c for c in view.choices if c.enabled]
        while True:
            answer = self.ask()
            lowered = answer.lower()
            if answer.isdigit() and 1 <= int(answer) <= len(enabled):
                return "choose", enabled[int(answer) - 1].id
            if lowered in ("i", "inv", "inventory"):
                return "inventory", ""
            if lowered in ("s", "save"):
                return "save", ""
            if lowered in ("l", "load"):
                return "load", ""
            if lowered in ("o", "options"):
                return "options", ""
            if lowered in ("q", "quit"):
                return "quit", ""
            if self.debug and answer.startswith(":"):
                return "debug", answer[1:]
            if not answer:
                continue
            if enabled:
                self.notice(f"Choose a number from 1 to {len(enabled)}, or a letter in brackets.")
            else:
                self.notice("Choose a letter in brackets.")

    # -- endings ---------------------------------------------------------------------------

    def ending_menu(self, view: SceneView) -> GameState | None:
        ending = view.ending
        assert ending is not None
        styles = {
            EndingKind.DEATH: ("YOU DIED", "bold red", "red", box.HEAVY),
            EndingKind.VICTORY: ("THE END", "bold green", "green", box.DOUBLE),
            EndingKind.NEUTRAL: ("THE END", f"bold {self.accent}", self.accent, box.ROUNDED),
        }
        banner, text_style, border, panel_box = styles[ending.kind]
        self.out()
        body = Text(banner, style=text_style, justify="center")
        if ending.title:
            body.append("\n" + ending.title, style="italic")
        self.out(Panel(body, box=panel_box, border_style=border, padding=(1, 2)))
        while True:
            self.out()
            entries = [("Start over", "restart")]
            if self.saves.any_saves():
                entries.insert(0, ("Load a save", "load"))
            entries.append(("Back to title", "title"))
            for i, (label, _) in enumerate(entries, start=1):
                self.out(Text.assemble(MARGIN, (f"{i}) ", f"bold {self.accent}"), label))
            self.out()
            answer = self.ask()
            if not answer.isdigit() or not 1 <= int(answer) <= len(entries):
                self.notice(f"Choose a number from 1 to {len(entries)}.")
                continue
            action = entries[int(answer) - 1][1]
            if action == "title":
                return None
            if action == "restart":
                try:
                    state = self.rt.new_game()
                except GameError as e:
                    self.show_fatal(e)
                    return None
                self.show_intro(state)
                return state
            loaded = self.load_menu()
            if loaded is not None:
                return loaded

    # -- menus ---------------------------------------------------------------------------

    def menu_header(self, title: str) -> None:
        self.term.clear()
        self.out(Text(MARGIN + title, style=f"bold {self.accent}"))
        self.out(Rule(style=self.accent))
        self.out()

    def inventory_screen(self, state: GameState) -> None:
        self.menu_header("Inventory")
        owned = [
            (item, state.inventory[item.id])
            for item in self.game.items
            if state.inventory.get(item.id, 0) > 0
        ]
        if not owned:
            self.notice("You aren't carrying anything.", style="dim italic")
        for item, count in owned:
            line = Text(MARGIN + item.display_name, style="bold")
            if item.stackable:
                line.append(f" ×{count}", style=self.accent)
            self.out(line)
            if item.description:
                self.write_text(Text(MARGIN + item.description, style="dim"), animate=False)
        self.pause("press Enter to go back")

    def slot_lines(self, slots: tuple[str, ...]) -> None:
        for slot in slots:
            info = self.saves.info(slot)
            key = "A" if slot == AUTO else slot
            name = "Autosave" if slot == AUTO else f"Slot {slot}"
            line = Text.assemble(MARGIN, (f"{key}) ", f"bold {self.accent}"), (f"{name:<9}", ""))
            if info is None:
                line.append("  — empty —", style="dim")
            else:
                line.append(f"  {info.label}", style="red" if info.damaged else "")
                if info.saved_at:
                    line.append(f"  {info.saved_at}", style="dim")
            self.out(line)

    def save_menu(self, state: GameState) -> str | None:
        self.menu_header("Save Game")
        self.slot_lines(SLOTS)
        self.out()
        while True:
            answer = self.ask("Save to slot (1-5), or Enter to cancel: ")
            if not answer:
                return None
            if answer not in SLOTS:
                self.notice("Choose a slot from 1 to 5.")
                continue
            if self.saves.info(answer) is not None:
                confirm = self.ask(f"Overwrite slot {answer}? (y/n) ").lower()
                if confirm not in ("y", "yes"):
                    continue
            try:
                self.saves.write(answer, self.rt.make_save(state))
            except OSError as e:
                return f"Couldn't save: {e.strerror or e}"
            return f"Saved to slot {answer}."

    def load_menu(self) -> GameState | None:
        self.menu_header("Load Game")
        slots = (AUTO, *SLOTS)
        self.slot_lines(slots)
        self.out()
        while True:
            answer = self.ask("Load which save (A, 1-5), or Enter to cancel: ").lower()
            if not answer:
                return None
            slot = AUTO if answer == "a" else answer
            if slot not in slots:
                self.notice("Choose A or a slot from 1 to 5.")
                continue
            if self.saves.info(slot) is None:
                self.notice("That slot is empty.")
                continue
            state = self.restore(slot)
            if state is not None:
                return state

    def restore(self, slot: str) -> GameState | None:
        data = self.saves.read(slot)
        if data is None:
            self.notice("That save is damaged and can't be loaded.", style="red")
            self.pause()
            return None
        try:
            state, warnings = self.rt.restore_save(data)
        except GameError as e:
            self.notice(f"Can't load this save: {e}", style="red")
            self.pause()
            return None
        if warnings:
            for warning in warnings:
                self.notice(warning)
            self.pause()
        return state

    def options_menu(self) -> None:
        while True:
            self.menu_header("Options")
            opts = self.options
            typewriter = (
                self.typewriter_on
                if self.term.interactive
                else (
                    opts.typewriter
                    if opts.typewriter is not None
                    else self.game.settings.typewriter
                )
            )
            rows = [
                ("Typewriter effect", "on" if typewriter else "off"),
                ("Typewriter speed", opts.speed),
                (
                    "Text width",
                    f"{opts.width} columns"
                    if opts.width
                    else f"game default ({self.game.settings.text_width})",
                ),
            ]
            for i, (label, value) in enumerate(rows, start=1):
                self.out(
                    Text.assemble(
                        MARGIN,
                        (f"{i}) ", f"bold {self.accent}"),
                        f"{label:<20}",
                        (value, self.accent),
                    )
                )
            self.out()
            answer = self.ask("Change which (1-3), or Enter to go back: ")
            if not answer:
                return
            if answer == "1":
                opts.typewriter = not typewriter
            elif answer == "2":
                names = list(SPEEDS)
                opts.speed = names[(names.index(opts.speed) + 1) % len(names)]
            elif answer == "3":
                opts.width = WIDTHS[(WIDTHS.index(opts.width) + 1) % len(WIDTHS)]
            else:
                continue
            self.options_store.save(opts)

    # -- debug (playtest) ----------------------------------------------------------------

    def debug_command(self, state: GameState, line: str) -> str | None:
        try:
            parts = shlex.split(line)
        except ValueError as e:
            return f"debug: {e}"
        if not parts:
            return None
        cmd, args = parts[0].lower(), parts[1:]
        self.rt.problems = []
        try:
            if cmd == "goto" and len(args) == 1:
                self.rt.enter(state, args[0])
                return f"debug: jumped to '{args[0]}'"
            if cmd == "set" and len(args) == 2:
                self.rt.debug_set(state, args[0], self.rt.parse_value(args[0], args[1]))
                return f"debug: {args[0]} = {state.vars[args[0]]}"
            if cmd in ("give", "take") and len(args) in (1, 2):
                amount = int(args[1]) if len(args) == 2 else 1
                self.rt.debug_items(state, args[0], amount if cmd == "give" else -amount)
                return f"debug: {args[0]} ×{state.inventory.get(args[0], 0)}"
            if cmd == "vars":
                self.debug_vars(state)
                return None
        except GameError as e:
            return f"debug: {e}"
        except ValueError:
            return "debug: amounts must be whole numbers"
        return "debug commands: :goto SCENE  :set VAR VALUE  :give ITEM [N]  :take ITEM [N]  :vars"

    def debug_vars(self, state: GameState) -> None:
        self.menu_header(f"Debug · scene '{state.scene}'")
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
        table.add_column("variable")
        table.add_column("value")
        for name, value in state.vars.items():
            table.add_row(name, repr(value))
        for item, count in state.inventory.items():
            table.add_row(f"item: {item}", str(count))
        self.out(Padding(table, (0, 0, 0, len(MARGIN))))
        self.pause("press Enter to go back")
