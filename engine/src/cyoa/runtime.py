"""Running a game: state, choices, effects, rules and saves.

The runtime never crashes on author mistakes. A broken condition counts as false,
a broken effect is skipped, and a broken interpolation shows ``?``. Each problem
is recorded in :attr:`Runtime.problems` so the player (and the playtest panel)
can show it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any

from . import markup
from .expr import (
    EvalError,
    Expr,
    ExprError,
    Program,
    Type,
    describe_requirement,
    evaluate,
    execute,
    normalize,
    parse_expression,
    parse_program,
)
from .expr.nodes import Value
from .markup import Page, StyledSpan
from .model import Choice, Ending, Game, LockedMode, Scene, Variable

MAX_REDIRECTS = 50
MAX_RULE_PASSES = 20
SAVE_FORMAT = 1


class GameError(Exception):
    """The game can't continue from here (e.g. a choice leads to a missing scene)."""


@dataclass(slots=True)
class GameState:
    scene: str
    vars: dict[str, Value] = field(default_factory=dict)
    inventory: dict[str, int] = field(default_factory=dict)
    visits: dict[str, int] = field(default_factory=dict)
    used_choices: set[str] = field(default_factory=set)
    active_rules: set[str] = field(default_factory=set)
    steps: int = 0
    # The current scene's text as the player read it on arrival (pages of span
    # dicts), so redraws and loaded saves show the same text without re-applying
    # changes made in the text.
    text: list[list[dict[str, Any]]] | None = None
    text_scene: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene": self.scene,
            "vars": dict(self.vars),
            "inventory": dict(self.inventory),
            "visits": dict(self.visits),
            "used_choices": sorted(self.used_choices),
            "active_rules": sorted(self.active_rules),
            "steps": self.steps,
            "text": self.text,
            "text_scene": self.text_scene,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameState:
        return cls(
            scene=str(data.get("scene", "")),
            vars=dict(data.get("vars", {})),
            inventory={str(k): int(v) for k, v in dict(data.get("inventory", {})).items()},
            visits={str(k): int(v) for k, v in dict(data.get("visits", {})).items()},
            used_choices=set(data.get("used_choices", [])),
            active_rules=set(data.get("active_rules", [])),
            steps=int(data.get("steps", 0)),
            text=data.get("text") if isinstance(data.get("text"), list) else None,
            text_scene=data.get("text_scene") if isinstance(data.get("text_scene"), str) else None,
        )

    def copy(self) -> GameState:
        return GameState.from_dict(self.to_dict())


@dataclass(slots=True)
class ChoiceView:
    choice: Choice
    text: list[StyledSpan]
    enabled: bool
    hint: str | None  # requirement text for locked choices

    @property
    def id(self) -> str:
        return self.choice.id

    @property
    def plain_text(self) -> str:
        return "".join(s.text for s in self.text)


@dataclass(slots=True)
class SceneView:
    scene: Scene
    title: str
    chapter_title: str
    art: str
    pages: list[Page]
    status: list[StyledSpan] | None
    choices: list[ChoiceView]
    ending: Ending | None


def _type_of(value: Value) -> Type:
    if isinstance(value, bool):
        return Type.BOOL
    if isinstance(value, int | float):
        return Type.NUMBER
    return Type.TEXT


def default_for(var: Variable) -> Value:
    """The variable's initial value, coerced to its type."""
    value = var.initial
    if _type_of(value) == var.type:
        return normalize(value)
    return {Type.NUMBER: 0, Type.BOOL: False, Type.TEXT: ""}[var.type]


class _Ctx:
    """Bridges the expression evaluator to a game state."""

    def __init__(self, runtime: Runtime, state: GameState) -> None:
        self.runtime = runtime
        self.state = state

    def get_var(self, name: str) -> Value:
        if name not in self.state.vars:
            raise EvalError(f"unknown variable '{name}'")
        return self.state.vars[name]

    def set_var(self, name: str, value: Value) -> None:
        var = self.runtime.variables.get(name)
        if var is None:
            raise EvalError(f"unknown variable '{name}'")
        if _type_of(value) != var.type:
            raise EvalError(f"'{name}' holds {var.type.value}, can't set it to {value!r}")
        self.state.vars[name] = normalize(value)
        self.runtime.clamp(self.state, name)

    def item_count(self, item: str) -> int:
        return self.state.inventory.get(item, 0)

    def give(self, item: str, amount: int) -> None:
        spec = self.runtime.items.get(item)
        if spec is None:
            raise EvalError(f"unknown item '{item}'")
        if amount <= 0:
            return
        current = self.state.inventory.get(item, 0)
        self.state.inventory[item] = current + amount if spec.stackable else 1

    def take(self, item: str, amount: int) -> None:
        if item not in self.runtime.items:
            raise EvalError(f"unknown item '{item}'")
        remaining = self.state.inventory.get(item, 0) - amount
        if remaining > 0:
            self.state.inventory[item] = remaining
        else:
            self.state.inventory.pop(item, None)

    def visit_count(self, scene: str) -> int:
        return self.state.visits.get(scene, 0)


class Runtime:
    def __init__(self, game: Game) -> None:
        self.game = game
        self.scenes = {s.id: s for s in game.scenes}
        self.variables = {v.name: v for v in game.variables}
        self.items = {i.id: i for i in game.items}
        self.chapters = {c.id: c for c in game.chapters}
        self.problems: list[str] = []
        self._exprs: dict[str, Expr | ExprError] = {}
        self._programs: dict[str, Program | ExprError] = {}
        self._templates: dict[str, list[markup.TNode] | ExprError] = {}
        self._labels = {v.name: v.display_label for v in game.variables}
        self._item_names = {i.id: i.display_name for i in game.items}

    # -- compiling (cached) ----------------------------------------------------

    def _expr(self, src: str) -> Expr | ExprError:
        if src not in self._exprs:
            try:
                self._exprs[src] = parse_expression(src)
            except ExprError as e:
                self._exprs[src] = e
        return self._exprs[src]

    def _program(self, src: str) -> Program | ExprError:
        if src not in self._programs:
            try:
                self._programs[src] = parse_program(src)
            except ExprError as e:
                self._programs[src] = e
        return self._programs[src]

    def _template(self, src: str) -> list[markup.TNode] | ExprError:
        if src not in self._templates:
            try:
                self._templates[src] = markup.parse_template(src)
            except ExprError as e:
                self._templates[src] = e
        return self._templates[src]

    # -- evaluation helpers -------------------------------------------------------

    def condition(self, state: GameState, src: str, where: str) -> bool:
        """Evaluate a condition; empty means always true, errors mean false."""
        if not src.strip():
            return True
        expr = self._expr(src)
        if isinstance(expr, ExprError):
            self.problems.append(f"{where}: {expr.message}")
            return False
        try:
            result = evaluate(expr, _Ctx(self, state))
        except EvalError as e:
            self.problems.append(f"{where}: {e}")
            return False
        if not isinstance(result, bool):
            self.problems.append(f"{where}: condition gave {result!r} instead of true/false")
            return False
        return result

    def run_effects(self, state: GameState, src: str, where: str) -> None:
        if not src.strip():
            return
        program = self._program(src)
        if isinstance(program, ExprError):
            self.problems.append(f"{where}: {program.message}")
            return
        ctx = _Ctx(self, state)
        for statement in program.statements:
            try:
                execute(Program((statement,)), ctx)
            except EvalError as e:
                self.problems.append(f"{where}: {e}")
        self.clamp_all(state)

    def _bound(self, state: GameState, bound: int | float | str | None) -> int | float | None:
        if bound is None:
            return None
        if isinstance(bound, str):
            value = state.vars.get(bound)
            if isinstance(value, bool) or not isinstance(value, int | float):
                return None
            return value
        return bound

    def clamp(self, state: GameState, name: str) -> None:
        var = self.variables.get(name)
        if var is None or var.type != Type.NUMBER:
            return
        value = state.vars.get(name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return
        lo = self._bound(state, var.min)
        hi = self._bound(state, var.max)
        if lo is not None and value < lo:
            value = lo
        if hi is not None and value > hi:
            value = hi
        state.vars[name] = normalize(value)

    def clamp_all(self, state: GameState) -> None:
        for name in self.variables:
            self.clamp(state, name)

    def render_text(self, state: GameState, src: str, where: str) -> list[Page]:
        """Render markup with the current values. Changes written in it are skipped."""
        return self._render(state, src, where, apply_changes=False)

    def _render(self, state: GameState, src: str, where: str, *, apply_changes: bool) -> list[Page]:
        if not src.strip():
            return []
        template = self._template(src)
        if isinstance(template, ExprError):
            self.problems.append(f"{where}: {template.message}")
            return markup.style(markup.escape(src))
        ctx = _Ctx(self, state)

        def ev(expr: Expr) -> Value:
            try:
                return evaluate(expr, ctx)
            except EvalError as e:
                self.problems.append(f"{where}: {e}")
                return "?"

        def run(program: Program) -> None:
            for statement in program.statements:
                try:
                    execute(Program((statement,)), ctx)
                except EvalError as e:
                    self.problems.append(f"{where}: {e}")
            self.clamp_all(state)

        resolved = markup.resolve_template(template, ev, run if apply_changes else None)
        return markup.style(resolved)

    def read_scene(self, state: GameState, scene: Scene) -> None:
        """The player reads the scene on arrival: changes in its text apply in reading
        order (only in the parts shown), and the text is kept as read."""
        pages = self._render(state, scene.text, f"scene '{scene.id}' text", apply_changes=True)
        state.text = [[asdict(span) for span in page] for page in pages]
        state.text_scene = scene.id

    def _text_as_read(self, state: GameState, scene: Scene) -> list[Page] | None:
        if state.text is None or state.text_scene != scene.id:
            return None
        allowed = {f.name for f in fields(StyledSpan)}
        try:
            return [
                [StyledSpan(**{k: v for k, v in span.items() if k in allowed}) for span in page]
                for page in state.text
            ]
        except (TypeError, AttributeError):
            return None

    def forget_text(self, state: GameState) -> None:
        """Re-render the scene text from the current values next time it's shown."""
        state.text = None
        state.text_scene = None

    def render_line(self, state: GameState, src: str, where: str) -> list[StyledSpan]:
        """Render markup that must fit on one line (choice text, status bar)."""
        pages = self.render_text(state, src, where)
        spans = [s for page in pages for s in page if not s.pause]
        return [
            StyledSpan(s.text.replace("\n", " "), s.bold, s.italic, s.underline, s.dim, s.color)
            for s in spans
        ]

    # -- game flow ----------------------------------------------------------------

    def initial_state(self) -> GameState:
        """Variables at their starting values, before entering the first scene."""
        state = GameState(scene="", vars={v.name: default_for(v) for v in self.game.variables})
        self.clamp_all(state)
        return state

    def new_game(self) -> GameState:
        self.problems = []
        state = self.initial_state()
        self.enter(state, self.game.start_scene)
        return state

    def enter(self, state: GameState, scene_id: str, _depth: int = 0) -> None:
        """Move to a scene, run its on-enter effects and any rules they trigger."""
        if _depth > MAX_REDIRECTS:
            raise GameError(
                "too many automatic scene changes in a row; check your rules and on-enter "
                "effects for a loop"
            )
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise GameError(
                f"scene '{scene_id}' doesn't exist"
                if scene_id
                else "no scene to go to (missing start scene or choice target)"
            )
        state.scene = scene_id
        state.visits[scene_id] = state.visits.get(scene_id, 0) + 1
        self.run_effects(state, scene.on_enter, f"scene '{scene_id}' on-enter effects")
        self.read_scene(state, scene)
        target = self.check_rules(state)
        if target is not None:
            self.enter(state, target, _depth + 1)

    def check_rules(self, state: GameState) -> str | None:
        """Fire rules whose condition just became true. Returns a scene to jump to."""
        for _ in range(MAX_RULE_PASSES):
            fired = False
            for rule in self.game.rules:
                if not rule.condition.strip():
                    continue
                where = f"rule '{rule.name or rule.id}'"
                now = self.condition(state, rule.condition, where)
                was = rule.id in state.active_rules
                if now and not was:
                    state.active_rules.add(rule.id)
                    fired = True
                    self.run_effects(state, rule.effects, where)
                    if rule.goto:
                        return rule.goto
                elif was and not now:
                    state.active_rules.discard(rule.id)
            if not fired:
                return None
        self.problems.append(
            f"rules kept triggering each other; stopped after {MAX_RULE_PASSES} rounds"
        )
        return None

    def current_scene(self, state: GameState) -> Scene:
        scene = self.scenes.get(state.scene)
        if scene is None:
            raise GameError(f"scene '{state.scene}' doesn't exist")
        return scene

    def choices(self, state: GameState) -> list[ChoiceView]:
        scene = self.current_scene(state)
        if scene.ending is not None:
            return []
        views: list[ChoiceView] = []
        for choice in scene.choices:
            if choice.once and f"{scene.id}/{choice.id}" in state.used_choices:
                continue
            where = f"scene '{scene.id}', choice '{choice.text or choice.id}'"
            enabled = self.condition(state, choice.condition, where)
            if not enabled and choice.when_locked == LockedMode.HIDE:
                continue
            hint = None
            if not enabled:
                hint = choice.hint.strip() or self._auto_hint(choice.condition)
            text = self.render_line(state, choice.text, where)
            views.append(ChoiceView(choice, text, enabled, hint))
        return views

    def _auto_hint(self, condition: str) -> str | None:
        expr = self._expr(condition)
        if isinstance(expr, ExprError):
            return None
        return describe_requirement(expr, self._labels, self._item_names)

    def choose(self, state: GameState, choice_id: str) -> None:
        self.problems = []
        view = next((v for v in self.choices(state) if v.id == choice_id), None)
        if view is None:
            raise GameError(f"choice '{choice_id}' isn't available here")
        if not view.enabled:
            raise GameError("that choice is locked")
        choice = view.choice
        if choice.once:
            state.used_choices.add(f"{state.scene}/{choice.id}")
        self.run_effects(state, choice.effects, f"scene '{state.scene}', choice effects")
        state.steps += 1
        target = self.check_rules(state)
        self.enter(state, target if target is not None else choice.target)

    def view(self, state: GameState) -> SceneView:
        scene = self.current_scene(state)
        chapter = self.chapters.get(scene.chapter) if scene.chapter else None
        status_src = self.game.settings.status_format
        status = self.render_line(state, status_src, "status bar") if status_src.strip() else None
        return SceneView(
            scene=scene,
            title=scene.title,
            chapter_title=chapter.title if chapter else "",
            art=scene.art,
            pages=self._text_as_read(state, scene)
            or self.render_text(state, scene.text, f"scene '{scene.id}' text"),
            status=status,
            choices=self.choices(state),
            ending=scene.ending,
        )

    def intro(self, state: GameState) -> list[Page]:
        return self.render_text(state, self.game.settings.intro, "intro text")

    # -- debugging (playtest) ---------------------------------------------------------

    def parse_value(self, name: str, raw: str) -> Value:
        var = self.variables.get(name)
        if var is None:
            raise GameError(f"unknown variable '{name}'")
        raw = raw.strip()
        if var.type == Type.NUMBER:
            try:
                return normalize(float(raw))
            except ValueError:
                raise GameError(f"'{name}' needs a number") from None
        if var.type == Type.BOOL:
            if raw.lower() in ("true", "yes", "1", "on"):
                return True
            if raw.lower() in ("false", "no", "0", "off"):
                return False
            raise GameError(f"'{name}' needs true or false")
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        return raw

    def debug_set(self, state: GameState, name: str, value: Value) -> None:
        self.forget_text(state)
        _Ctx(self, state).set_var(name, value)

    def debug_items(self, state: GameState, item: str, amount: int) -> None:
        self.forget_text(state)
        ctx = _Ctx(self, state)
        try:
            if amount >= 0:
                ctx.give(item, amount)
            else:
                ctx.take(item, -amount)
        except EvalError as e:
            raise GameError(str(e)) from None

    # -- saves -----------------------------------------------------------------------

    def make_save(self, state: GameState) -> dict[str, Any]:
        scene = self.scenes.get(state.scene)
        chapter = self.chapters.get(scene.chapter) if scene and scene.chapter else None
        label = (chapter.title + " · " if chapter and chapter.title else "") + (
            scene.title if scene and scene.title else state.scene
        )
        return {
            "format": SAVE_FORMAT,
            "game_id": self.game.id,
            "game_version": self.game.version,
            "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "label": label,
            "state": state.to_dict(),
        }

    def restore_save(
        self, data: dict[str, Any], *, keep_text: bool = True
    ) -> tuple[GameState, list[str]]:
        """Load a save, repairing anything the current game version no longer has.

        ``keep_text=False`` re-renders the scene text from the saved values instead of
        showing it as the player read it (used when playtesting edited text)."""
        warnings: list[str] = []
        if data.get("game_id") not in (None, self.game.id):
            raise GameError("this save belongs to a different game")
        try:
            state = GameState.from_dict(dict(data["state"]))
        except (KeyError, TypeError, ValueError) as e:
            raise GameError(f"the save file is damaged ({e})") from None
        if data.get("game_version") not in (None, self.game.version):
            warnings.append(
                f"This save is from version {data.get('game_version')} of the game; "
                f"you're playing version {self.game.version}."
            )
        fixed: dict[str, Value] = {}
        for var in self.game.variables:
            value = state.vars.get(var.name)
            fixed[var.name] = (
                value if value is not None and _type_of(value) == var.type else default_for(var)
            )
        state.vars = fixed
        state.inventory = {k: v for k, v in state.inventory.items() if k in self.items and v > 0}
        state.active_rules &= {r.id for r in self.game.rules}
        if state.scene not in self.scenes:
            warnings.append(
                "The saved scene no longer exists, so you're back at the start "
                "(your stats and items are kept)."
            )
            state.scene = self.game.start_scene
            keep_text = False
            if state.scene not in self.scenes:
                raise GameError("the game has no valid start scene")
        if not keep_text:
            self.forget_text(state)
        self.clamp_all(state)
        return state, warnings
