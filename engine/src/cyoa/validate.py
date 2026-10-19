"""Everything that can be wrong with a game, as a list of located issues.

Errors block exporting a game for players; warnings are worth a look but don't.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from . import markup
from .expr import (
    RESERVED_NAMES,
    Env,
    ExprError,
    Type,
    check_condition,
    check_expression,
    check_program,
    parse_expression,
    parse_program,
)
from .expr.nodes import Assign, Call, Name, Node, Str, walk
from .model import Game, Scene

VAR_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(slots=True)
class Issue:
    severity: Severity
    code: str
    message: str
    scene: str | None = None
    choice: str | None = None
    rule: str | None = None
    variable: str | None = None
    item: str | None = None
    chapter: str | None = None
    field: str | None = None
    start: int | None = None
    end: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(slots=True)
class Loc:
    """Where a piece of expression/markup source lives in the game."""

    field: str
    scene: str | None = None
    choice: str | None = None
    rule: str | None = None
    variable: str | None = None

    def issue(
        self,
        severity: Severity,
        code: str,
        message: str,
        start: int | None = None,
        end: int | None = None,
    ) -> Issue:
        return Issue(
            severity,
            code,
            message,
            scene=self.scene,
            choice=self.choice,
            rule=self.rule,
            variable=self.variable,
            field=self.field,
            start=start,
            end=end,
        )


@dataclass(slots=True)
class Source:
    loc: Loc
    text: str
    mode: str  # "condition", "effects", "markup"


def iter_sources(game: Game) -> Iterator[Source]:
    """Every condition, effect list and piece of markup in the game."""
    settings = game.settings
    yield Source(Loc("status_format"), settings.status_format, "markup")
    yield Source(Loc("intro"), settings.intro, "markup")
    for rule in game.rules:
        yield Source(Loc("condition", rule=rule.id), rule.condition, "condition")
        yield Source(Loc("effects", rule=rule.id), rule.effects, "effects")
    for scene in game.scenes:
        yield Source(Loc("text", scene=scene.id), scene.text, "markup")
        yield Source(Loc("on_enter", scene=scene.id), scene.on_enter, "effects")
        for choice in scene.choices:
            loc = dict(scene=scene.id, choice=choice.id)
            yield Source(Loc("choice_text", **loc), choice.text, "markup")
            yield Source(Loc("condition", **loc), choice.condition, "condition")
            yield Source(Loc("effects", **loc), choice.effects, "effects")


def parse_source(source: Source) -> list[tuple[Node, int, bool]] | ExprError:
    """Parse a source into ``(node, offset, is_condition)`` triples."""
    if not source.text.strip():
        return []
    try:
        if source.mode == "condition":
            return [(parse_expression(source.text), 0, True)]
        if source.mode == "effects":
            return [(parse_program(source.text), 0, False)]
        nodes = markup.parse_template(source.text)
        return list(markup.template_expressions(nodes))
    except ExprError as e:
        return e


@dataclass(slots=True)
class Usage:
    reads: set[str]
    writes: set[str]
    items_checked: set[str]
    items_given: set[str]
    items_taken: set[str]
    scenes: set[str]


def collect_usage(game: Game) -> Usage:
    usage = Usage(set(), set(), set(), set(), set(), set())
    for source in iter_sources(game):
        parsed = parse_source(source)
        if isinstance(parsed, ExprError):
            continue
        for node, _, _ in parsed:
            for n in walk(node):
                match n:
                    case Name(name=name):
                        usage.reads.add(name)
                    case Call(func=func, args=(Str(value=value), *_)):
                        if func in ("has", "count"):
                            usage.items_checked.add(value)
                        elif func == "give":
                            usage.items_given.add(value)
                        elif func == "take":
                            usage.items_taken.add(value)
                        elif func in ("visited", "visits"):
                            usage.scenes.add(value)
                    case Assign(target=target, op=op):
                        usage.writes.add(target)
                        if op != "=":
                            usage.reads.add(target)
                    case _:
                        pass
    for var in game.variables:
        for bound in (var.min, var.max):
            if isinstance(bound, str):
                usage.reads.add(bound)
    return usage


def build_env(game: Game) -> Env:
    return Env(
        variables={v.name: v.type for v in game.variables},
        items={i.id for i in game.items},
        scenes={s.id for s in game.scenes},
    )


def _type_of(value: Any) -> Type:
    if isinstance(value, bool):
        return Type.BOOL
    if isinstance(value, int | float):
        return Type.NUMBER
    return Type.TEXT


def validate(game: Game) -> list[Issue]:
    issues: list[Issue] = []
    add = issues.append
    E, W = Severity.ERROR, Severity.WARNING

    # -- ids --------------------------------------------------------------------
    def check_ids(kind: str, ids: list[str], pattern: re.Pattern[str], hint: str) -> None:
        seen: set[str] = set()
        for ident in ids:
            if not pattern.match(ident):
                issue = Issue(E, f"invalid_{kind}_id", f"'{ident}' isn't a valid {kind} id: {hint}")
                setattr(issue, kind, ident)
                add(issue)
            if ident in seen:
                issue = Issue(E, f"duplicate_{kind}", f"two {kind}s are called '{ident}'")
                setattr(issue, kind, ident)
                add(issue)
            seen.add(ident)

    slug_hint = "use lowercase letters, digits and _"
    check_ids(
        "variable",
        [v.name for v in game.variables],
        VAR_NAME_RE,
        "use lowercase letters, digits and _, not starting with a digit",
    )
    check_ids("item", [i.id for i in game.items], SLUG_RE, slug_hint)
    check_ids("scene", [s.id for s in game.scenes], SLUG_RE, slug_hint)
    check_ids("chapter", [c.id for c in game.chapters], SLUG_RE, slug_hint)
    for var in game.variables:
        if var.name in RESERVED_NAMES:
            add(
                Issue(
                    E,
                    "reserved_variable",
                    f"'{var.name}' is a reserved word and can't be a variable name",
                    variable=var.name,
                )
            )
    for scene in game.scenes:
        seen_choices: set[str] = set()
        for choice in scene.choices:
            if choice.id in seen_choices:
                add(
                    Issue(
                        E,
                        "duplicate_choice",
                        f"two choices share the id '{choice.id}'",
                        scene=scene.id,
                        choice=choice.id,
                    )
                )
            seen_choices.add(choice.id)

    scene_ids = {s.id for s in game.scenes}
    chapter_ids = {c.id for c in game.chapters}
    variables = {v.name: v for v in game.variables}

    # -- game -------------------------------------------------------------------
    if not game.start_scene:
        add(Issue(E, "no_start_scene", "no start scene is set", field="start_scene"))
    elif game.start_scene not in scene_ids:
        add(
            Issue(
                E,
                "missing_start_scene",
                f"the start scene '{game.start_scene}' doesn't exist",
                field="start_scene",
            )
        )

    # -- variables ----------------------------------------------------------------
    for var in game.variables:
        if _type_of(var.initial) != var.type:
            add(
                Issue(
                    E,
                    "initial_type",
                    f"'{var.name}' holds {var.type.value} but starts as {var.initial!r}",
                    variable=var.name,
                    field="initial",
                )
            )
        for which in ("min", "max"):
            bound = getattr(var, which)
            if bound is None:
                continue
            if var.type != Type.NUMBER:
                add(
                    Issue(
                        E,
                        "bound_on_non_number",
                        f"only number variables can have a {which}",
                        variable=var.name,
                        field=which,
                    )
                )
            elif isinstance(bound, str):
                other = variables.get(bound)
                if other is None:
                    add(
                        Issue(
                            E,
                            "unknown_bound_variable",
                            f"{which} refers to unknown variable '{bound}'",
                            variable=var.name,
                            field=which,
                        )
                    )
                elif other.type != Type.NUMBER:
                    add(
                        Issue(
                            E,
                            "bound_not_number",
                            f"{which} refers to '{bound}', which isn't a number",
                            variable=var.name,
                            field=which,
                        )
                    )
        lo, hi = var.min, var.max
        if isinstance(lo, int | float) and isinstance(hi, int | float):
            if lo > hi:
                add(
                    Issue(
                        E,
                        "min_above_max",
                        f"'{var.name}' has min {lo} above max {hi}",
                        variable=var.name,
                        field="min",
                    )
                )
            elif (
                isinstance(var.initial, int | float)
                and not isinstance(var.initial, bool)
                and not lo <= var.initial <= hi
            ):
                add(
                    Issue(
                        W,
                        "initial_out_of_bounds",
                        f"'{var.name}' starts at {var.initial}, outside {lo}–{hi}; it will be "
                        "clamped",
                        variable=var.name,
                        field="initial",
                    )
                )

    # -- expressions & markup -------------------------------------------------------
    env = build_env(game)
    for source in iter_sources(game):
        parsed = parse_source(source)
        loc = source.loc
        if isinstance(parsed, ExprError):
            add(loc.issue(E, "syntax", parsed.message, parsed.start, parsed.end))
            continue
        for node, offset, is_condition in parsed:
            if source.mode == "effects":
                errors = check_program(node, env)  # type: ignore[arg-type]
            elif is_condition:
                errors = check_condition(node, env)  # type: ignore[arg-type]
            else:
                errors = check_expression(node, env)[1]  # type: ignore[arg-type]
            for err in errors:
                code = "unknown_reference" if err.message.startswith("unknown ") else "type"
                add(loc.issue(E, code, err.message, err.start + offset, err.end + offset))
        if source.mode == "markup":
            for message, start, end in markup.effect_tag_problems(source.text):
                add(loc.issue(W, "invalid_effect", message, start, end))
            for name, start, end in markup.unknown_style_tags(source.text):
                add(
                    loc.issue(
                        W,
                        "unknown_style",
                        f"unknown style '{name}' (it will show as plain text)",
                        start,
                        end,
                    )
                )

    # -- rules ------------------------------------------------------------------------
    for rule in game.rules:
        if not rule.condition.strip():
            add(
                Issue(
                    W,
                    "rule_without_condition",
                    "this rule has no condition, so it never fires",
                    rule=rule.id,
                    field="condition",
                )
            )
        if rule.goto and rule.goto not in scene_ids:
            add(
                Issue(
                    E,
                    "missing_target",
                    f"goes to scene '{rule.goto}', which doesn't exist",
                    rule=rule.id,
                    field="goto",
                )
            )
        if not rule.goto and not rule.effects.strip():
            add(
                Issue(
                    W,
                    "rule_does_nothing",
                    "this rule has no effects and no scene to go to",
                    rule=rule.id,
                )
            )

    # -- scenes & choices ----------------------------------------------------------------
    for scene in game.scenes:
        if scene.chapter and scene.chapter not in chapter_ids:
            add(
                Issue(
                    E,
                    "missing_chapter",
                    f"chapter '{scene.chapter}' doesn't exist",
                    scene=scene.id,
                    field="chapter",
                )
            )
        if not scene.text.strip():
            add(Issue(W, "empty_text", "this scene has no text", scene=scene.id, field="text"))
        for choice in scene.choices:
            if not choice.target:
                add(
                    Issue(
                        E,
                        "no_target",
                        "this choice doesn't lead anywhere",
                        scene=scene.id,
                        choice=choice.id,
                        field="target",
                    )
                )
            elif choice.target not in scene_ids:
                add(
                    Issue(
                        E,
                        "missing_target",
                        f"leads to scene '{choice.target}', which doesn't exist",
                        scene=scene.id,
                        choice=choice.id,
                        field="target",
                    )
                )
            if not choice.text.strip():
                add(
                    Issue(
                        W,
                        "empty_choice_text",
                        "this choice has no text",
                        scene=scene.id,
                        choice=choice.id,
                        field="choice_text",
                    )
                )
        if scene.ending is not None:
            if scene.choices:
                add(
                    Issue(
                        W,
                        "ending_with_choices",
                        "this is an ending, so its choices are never shown",
                        scene=scene.id,
                    )
                )
            continue
        if not scene.choices:
            add(
                Issue(
                    W,
                    "dead_end",
                    "no choices and not marked as an ending: the player gets stuck here",
                    scene=scene.id,
                )
            )
        elif all(c.condition.strip() or c.once for c in scene.choices):
            add(
                Issue(
                    W,
                    "possible_softlock",
                    "every choice here has a condition or can only "
                    "be picked once; if none is available the player gets stuck",
                    scene=scene.id,
                )
            )

    # -- reachability ----------------------------------------------------------------------
    if game.start_scene in scene_ids:
        for scene_id in sorted(scene_ids - reachable_scenes(game)):
            add(
                Issue(
                    W, "unreachable", "no path leads to this scene from the start", scene=scene_id
                )
            )

    # -- usage ----------------------------------------------------------------------------
    usage = collect_usage(game)
    for var in game.variables:
        if var.name not in usage.reads and var.name not in usage.writes:
            add(Issue(W, "unused_variable", f"'{var.name}' is never used", variable=var.name))
        elif var.name not in usage.reads:
            add(
                Issue(
                    W,
                    "write_only_variable",
                    f"'{var.name}' is changed but never checked or shown",
                    variable=var.name,
                )
            )
    for item in game.items:
        mentioned = item.id in (usage.items_checked | usage.items_given | usage.items_taken)
        if not mentioned:
            add(Issue(W, "unused_item", f"'{item.id}' is never used", item=item.id))
        elif item.id not in usage.items_given:
            add(
                Issue(
                    W,
                    "item_never_given",
                    f"'{item.id}' is never given to the player, so checking for it is always false",
                    item=item.id,
                )
            )

    return issues


def reachable_scenes(game: Game) -> set[str]:
    scenes = {s.id: s for s in game.scenes}
    seen: set[str] = set()
    queue: deque[str] = deque()

    def push(scene_id: str | None) -> None:
        if scene_id and scene_id in scenes and scene_id not in seen:
            seen.add(scene_id)
            queue.append(scene_id)

    push(game.start_scene)
    # A rule can fire anywhere, so its destination is reachable whenever any scene is.
    for rule in game.rules:
        if rule.condition.strip():
            push(rule.goto)
    while queue:
        scene = scenes[queue.popleft()]
        for choice in scene.choices:
            push(choice.target)
    return seen


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == Severity.ERROR for i in issues)


_WORD_RE = re.compile(r"[A-Za-z0-9’']+")


def text_word_count(text: str) -> int:
    """Words a player reads: tags, interpolations and styling don't count."""
    text = re.sub(r"\{[^}]*\}", " ", text)
    text = re.sub(r"\[/?[A-Za-z_#0-9]*\]", " ", text)
    return len(_WORD_RE.findall(text))


def word_count(scene: Scene) -> int:
    return text_word_count(scene.text)


def game_stats(game: Game) -> dict[str, Any]:
    chapters: dict[str, dict[str, int]] = {}
    for scene in game.scenes:
        key = scene.chapter or ""
        entry = chapters.setdefault(key, {"scenes": 0, "words": 0, "endings": 0, "choices": 0})
        entry["scenes"] += 1
        entry["words"] += word_count(scene)
        entry["endings"] += scene.ending is not None
        entry["choices"] += len(scene.choices)
    totals = {
        k: sum(c[k] for c in chapters.values()) for k in ("scenes", "words", "endings", "choices")
    }
    return {**totals, "chapters": chapters}
