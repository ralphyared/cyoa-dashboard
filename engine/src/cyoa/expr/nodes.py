"""AST node types for the expression language.

Every node carries a ``span`` (start, end) into the source text so errors can
point at the offending characters and references can be renamed in place.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

Value = int | float | bool | str


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int

    def shift(self, offset: int) -> Span:
        return Span(self.start + offset, self.end + offset)


@dataclass(frozen=True, slots=True)
class Number:
    value: int | float
    span: Span


@dataclass(frozen=True, slots=True)
class Str:
    value: str
    span: Span


@dataclass(frozen=True, slots=True)
class Bool:
    value: bool
    span: Span


@dataclass(frozen=True, slots=True)
class Name:
    name: str
    span: Span


@dataclass(frozen=True, slots=True)
class Call:
    func: str
    args: tuple[Expr, ...]
    func_span: Span
    span: Span


@dataclass(frozen=True, slots=True)
class Unary:
    op: str  # "-" or "not"
    operand: Expr
    span: Span


@dataclass(frozen=True, slots=True)
class Binary:
    op: str
    left: Expr
    right: Expr
    span: Span


@dataclass(frozen=True, slots=True)
class Assign:
    target: str
    op: str  # "=", "+=", "-=", "*=", "/="
    value: Expr
    target_span: Span
    span: Span


@dataclass(frozen=True, slots=True)
class Program:
    statements: tuple[Stmt, ...]


Expr = Number | Str | Bool | Name | Call | Unary | Binary
Stmt = Assign | Call
Node = Expr | Assign | Program


def children(node: Node) -> Iterator[Node]:
    match node:
        case Call(args=args):
            yield from args
        case Unary(operand=operand):
            yield operand
        case Binary(left=left, right=right):
            yield left
            yield right
        case Assign(value=value):
            yield value
        case Program(statements=statements):
            yield from statements
        case _:
            pass


def walk(node: Node) -> Iterator[Node]:
    """Yield ``node`` and all of its descendants, depth first."""
    yield node
    for child in children(node):
        yield from walk(child)


def to_json(node: Node) -> dict[str, Any]:
    """Serialize a node for the dashboard (used to drive the visual builders)."""
    match node:
        case Number(value=v, span=s):
            return {"type": "number", "value": v, "span": [s.start, s.end]}
        case Str(value=v, span=s):
            return {"type": "string", "value": v, "span": [s.start, s.end]}
        case Bool(value=v, span=s):
            return {"type": "bool", "value": v, "span": [s.start, s.end]}
        case Name(name=n, span=s):
            return {"type": "name", "name": n, "span": [s.start, s.end]}
        case Call(func=f, args=args, span=s):
            return {
                "type": "call",
                "func": f,
                "args": [to_json(a) for a in args],
                "span": [s.start, s.end],
            }
        case Unary(op=op, operand=operand, span=s):
            return {
                "type": "unary",
                "op": op,
                "operand": to_json(operand),
                "span": [s.start, s.end],
            }
        case Binary(op=op, left=left, right=right, span=s):
            return {
                "type": "binary",
                "op": op,
                "left": to_json(left),
                "right": to_json(right),
                "span": [s.start, s.end],
            }
        case Assign(target=t, op=op, value=value, span=s):
            return {
                "type": "assign",
                "target": t,
                "op": op,
                "value": to_json(value),
                "span": [s.start, s.end],
            }
        case Program(statements=statements):
            return {"type": "program", "statements": [to_json(st) for st in statements]}
