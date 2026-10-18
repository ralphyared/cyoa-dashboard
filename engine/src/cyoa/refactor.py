"""Find and rename references to variables, items, scenes and chapters."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from . import markup
from .expr import ExprError, RefKind, rename_in_expression, rename_in_program
from .expr.rename import reference_spans
from .model import Game
from .validate import Loc, iter_sources, parse_source


class Kind(StrEnum):
    VARIABLE = "variable"
    ITEM = "item"
    SCENE = "scene"
    CHAPTER = "chapter"


def find_references(game: Game, kind: Kind, name: str) -> list[dict[str, object]]:
    """Every place that mentions ``name`` (not counting its own definition)."""
    refs: list[dict[str, object]] = []

    def add(loc: Loc, start: int | None = None, end: int | None = None) -> None:
        entry: dict[str, object] = {"field": loc.field}
        for key in ("scene", "choice", "rule", "variable"):
            value = getattr(loc, key)
            if value is not None:
                entry[key] = value
        if start is not None:
            entry["start"], entry["end"] = start, end
        refs.append(entry)

    if kind != Kind.CHAPTER:
        ref_kind = RefKind(kind.value)
        for source in iter_sources(game):
            parsed = parse_source(source)
            if isinstance(parsed, ExprError):
                continue
            for node, offset, _ in parsed:
                for span, _style in reference_spans(node, ref_kind, name):
                    add(source.loc, span.start + offset, span.end + offset)

    if kind == Kind.VARIABLE:
        for var in game.variables:
            for which in ("min", "max"):
                if getattr(var, which) == name:
                    add(Loc(which, variable=var.name))
    elif kind == Kind.SCENE:
        if game.start_scene == name:
            add(Loc("start_scene"))
        for rule in game.rules:
            if rule.goto == name:
                add(Loc("goto", rule=rule.id))
        for scene in game.scenes:
            for choice in scene.choices:
                if choice.target == name:
                    add(Loc("target", scene=scene.id, choice=choice.id))
    elif kind == Kind.CHAPTER:
        for scene in game.scenes:
            if scene.chapter == name:
                add(Loc("chapter", scene=scene.id))
    return refs


def rename(game: Game, kind: Kind, old: str, new: str) -> Game:
    """A copy of ``game`` with ``old`` renamed to ``new`` everywhere, definition included."""
    g = game.model_copy(deep=True)
    if old == new:
        return g

    if kind == Kind.CHAPTER:
        for chapter in g.chapters:
            if chapter.id == old:
                chapter.id = new
        for scene in g.scenes:
            if scene.chapter == old:
                scene.chapter = new
        return g

    ref_kind = RefKind(kind.value)

    def expr(src: str) -> str:
        return rename_in_expression(src, ref_kind, old, new)

    def prog(src: str) -> str:
        return rename_in_program(src, ref_kind, old, new)

    def text(src: str) -> str:
        return markup.rename_in_markup(src, ref_kind, old, new)

    _rewrite(g, expr, prog, text)

    if kind == Kind.VARIABLE:
        for var in g.variables:
            if var.name == old:
                var.name = new
            if var.min == old:
                var.min = new
            if var.max == old:
                var.max = new
    elif kind == Kind.ITEM:
        for item in g.items:
            if item.id == old:
                item.id = new
    elif kind == Kind.SCENE:
        if g.start_scene == old:
            g.start_scene = new
        for rule in g.rules:
            if rule.goto == old:
                rule.goto = new
        for scene in g.scenes:
            if scene.id == old:
                scene.id = new
            for choice in scene.choices:
                if choice.target == old:
                    choice.target = new
    return g


Rewrite = Callable[[str], str]


def _rewrite(g: Game, expr: Rewrite, prog: Rewrite, text: Rewrite) -> None:
    g.settings.status_format = text(g.settings.status_format)
    g.settings.intro = text(g.settings.intro)
    for rule in g.rules:
        rule.condition = expr(rule.condition)
        rule.effects = prog(rule.effects)
    for scene in g.scenes:
        scene.text = text(scene.text)
        scene.on_enter = prog(scene.on_enter)
        for choice in scene.choices:
            choice.text = text(choice.text)
            choice.condition = expr(choice.condition)
            choice.effects = prog(choice.effects)
