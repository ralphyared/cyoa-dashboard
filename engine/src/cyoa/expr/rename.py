"""Rename a variable, item or scene inside expression source text.

Edits are made in place using AST spans, so the author's formatting and comments
are preserved. Source that doesn't parse is returned unchanged.
"""

from __future__ import annotations

import json
from enum import StrEnum

from .checker import FUNCTIONS
from .errors import ExprError
from .nodes import Assign, Call, Name, Node, Span, Str, walk
from .parser import parse_expression, parse_program


class RefKind(StrEnum):
    VARIABLE = "variable"
    ITEM = "item"
    SCENE = "scene"


def reference_spans(node: Node, kind: RefKind, name: str) -> list[tuple[Span, str]]:
    """Spans to replace and the replacement style ("name" or "string")."""
    spans: list[tuple[Span, str]] = []
    for n in walk(node):
        match n:
            case Name(name=found, span=s) if kind == RefKind.VARIABLE and found == name:
                spans.append((s, "name"))
            case Assign(target=found, target_span=s) if kind == RefKind.VARIABLE and found == name:
                spans.append((s, "name"))
            case Call(func=func, args=(Str(value=found, span=s), *_)) if (
                func in FUNCTIONS and found == name
            ):
                param = FUNCTIONS[func].params[0]
                if param == kind.value:
                    spans.append((s, "string"))
            case _:
                pass
    return spans


def apply_renames(src: str, spans: list[tuple[Span, str]], new: str) -> str:
    for span, style in sorted(spans, key=lambda x: x[0].start, reverse=True):
        replacement = new if style == "name" else json.dumps(new)
        src = src[: span.start] + replacement + src[span.end :]
    return src


def rename_in_expression(src: str, kind: RefKind, old: str, new: str) -> str:
    if not src.strip():
        return src
    try:
        node = parse_expression(src)
    except ExprError:
        return src
    return apply_renames(src, reference_spans(node, kind, old), new)


def rename_in_program(src: str, kind: RefKind, old: str, new: str) -> str:
    if not src.strip():
        return src
    try:
        node = parse_program(src)
    except ExprError:
        return src
    return apply_renames(src, reference_spans(node, kind, old), new)
