"""Static type checking and reference collection for expressions.

The checker knows the game's declared variables, items and scenes, so typos and
type mismatches are reported while writing instead of while playing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .errors import ExprError
from .nodes import Assign, Binary, Bool, Call, Expr, Name, Node, Number, Program, Str, Unary, walk


class Type(StrEnum):
    NUMBER = "number"
    BOOL = "bool"
    TEXT = "text"


_TYPE_WORDS = {Type.NUMBER: "a number", Type.BOOL: "true/false", Type.TEXT: "text"}


def describe_type(t: Type) -> str:
    return _TYPE_WORDS[t]


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    name: str
    params: tuple[str, ...]  # "item", "scene", "number"
    min_args: int
    variadic: bool  # repeat the last param
    returns: Type | None  # None: statement-only (no value)
    help: str


FUNCTIONS: dict[str, FunctionSpec] = {
    f.name: f
    for f in (
        FunctionSpec(
            "has",
            ("item", "number"),
            1,
            False,
            Type.BOOL,
            'has("rope") or has("arrow", 3): true if carrying the item (at least N)',
        ),
        FunctionSpec(
            "count",
            ("item",),
            1,
            False,
            Type.NUMBER,
            'count("arrow"): how many of the item are carried',
        ),
        FunctionSpec(
            "visited",
            ("scene",),
            1,
            False,
            Type.BOOL,
            'visited("tower"): true if the scene has been entered (including now)',
        ),
        FunctionSpec(
            "visits",
            ("scene",),
            1,
            False,
            Type.NUMBER,
            'visits("tower"): how many times the scene has been entered',
        ),
        FunctionSpec(
            "min", ("number", "number"), 2, True, Type.NUMBER, "min(a, b, ...): the smallest value"
        ),
        FunctionSpec(
            "max", ("number", "number"), 2, True, Type.NUMBER, "max(a, b, ...): the largest value"
        ),
        FunctionSpec("round", ("number",), 1, False, Type.NUMBER, "round(x): nearest whole number"),
        FunctionSpec("floor", ("number",), 1, False, Type.NUMBER, "floor(x): round down"),
        FunctionSpec("ceil", ("number",), 1, False, Type.NUMBER, "ceil(x): round up"),
        FunctionSpec("abs", ("number",), 1, False, Type.NUMBER, "abs(x): distance from zero"),
        FunctionSpec(
            "give",
            ("item", "number"),
            1,
            False,
            None,
            'give("arrow") or give("arrow", 5): add the item to the inventory',
        ),
        FunctionSpec(
            "take",
            ("item", "number"),
            1,
            False,
            None,
            'take("arrow") or take("arrow", 5): remove the item from the inventory',
        ),
    )
}

RESERVED_NAMES = frozenset({"and", "or", "not", "true", "false", *FUNCTIONS})


@dataclass(slots=True)
class Env:
    """What an expression may refer to."""

    variables: dict[str, Type] = field(default_factory=dict)
    items: set[str] = field(default_factory=set)
    scenes: set[str] = field(default_factory=set)


class _Checker:
    def __init__(self, env: Env) -> None:
        self.env = env
        self.errors: list[ExprError] = []

    def err(self, message: str, start: int, end: int) -> None:
        self.errors.append(ExprError(message, start, end))

    def expr(self, node: Expr) -> Type | None:
        match node:
            case Number():
                return Type.NUMBER
            case Str():
                return Type.TEXT
            case Bool():
                return Type.BOOL
            case Name(name=name, span=s):
                t = self.env.variables.get(name)
                if t is None:
                    if name in FUNCTIONS:
                        self.err(f"{name} is a function; call it like {name}(...)", s.start, s.end)
                    else:
                        self.err(f"unknown variable '{name}'", s.start, s.end)
                return t
            case Call():
                return self.call(node, as_statement=False)
            case Unary(op="not", operand=operand):
                t = self.expr(operand)
                if t is not None and t != Type.BOOL:
                    self.err(
                        f"'not' needs true/false, got {describe_type(t)}",
                        operand.span.start,
                        operand.span.end,
                    )
                return Type.BOOL
            case Unary(op="-", operand=operand):
                t = self.expr(operand)
                if t is not None and t != Type.NUMBER:
                    self.err(
                        f"'-' needs a number, got {describe_type(t)}",
                        operand.span.start,
                        operand.span.end,
                    )
                return Type.NUMBER
            case Binary(op=op, left=left, right=right, span=s):
                lt = self.expr(left)
                rt = self.expr(right)
                return self.binary(op, lt, rt, left, right, s.start, s.end)
            case _:
                raise AssertionError(f"unexpected node {node!r}")

    def binary(
        self,
        op: str,
        lt: Type | None,
        rt: Type | None,
        left: Expr,
        right: Expr,
        start: int,
        end: int,
    ) -> Type | None:
        if op in ("and", "or"):
            for t, side in ((lt, left), (rt, right)):
                if t is not None and t != Type.BOOL:
                    self.err(
                        f"'{op}' needs true/false on both sides, got {describe_type(t)}",
                        side.span.start,
                        side.span.end,
                    )
            return Type.BOOL
        if op in ("==", "!="):
            if lt is not None and rt is not None and lt != rt:
                self.err(f"can't compare {describe_type(lt)} with {describe_type(rt)}", start, end)
            return Type.BOOL
        if op in ("<", "<=", ">", ">="):
            for t, side in ((lt, left), (rt, right)):
                if t is not None and t != Type.NUMBER:
                    self.err(
                        f"'{op}' compares numbers, got {describe_type(t)}",
                        side.span.start,
                        side.span.end,
                    )
            return Type.BOOL
        if op == "+" and (lt == Type.TEXT or rt == Type.TEXT):
            if lt is not None and rt is not None and lt != rt:
                self.err(f"can't add {describe_type(lt)} and {describe_type(rt)}", start, end)
            return Type.TEXT
        # arithmetic
        for t, side in ((lt, left), (rt, right)):
            if t is not None and t != Type.NUMBER:
                self.err(
                    f"'{op}' needs numbers, got {describe_type(t)}", side.span.start, side.span.end
                )
        return Type.NUMBER

    def call(self, node: Call, *, as_statement: bool) -> Type | None:
        spec = FUNCTIONS.get(node.func)
        fs = node.func_span
        if spec is None:
            if node.func in self.env.variables:
                self.err(f"'{node.func}' is a variable, not a function", fs.start, fs.end)
            else:
                known = ", ".join(sorted(FUNCTIONS))
                self.err(f"unknown function '{node.func}' (available: {known})", fs.start, fs.end)
            for arg in node.args:
                self.expr(arg)
            return None
        if spec.returns is None and not as_statement:
            self.err(
                f"{spec.name}() is an effect and can't be used inside a condition or value",
                node.span.start,
                node.span.end,
            )
        if spec.returns is not None and as_statement:
            self.err(
                f"{spec.name}() gives a value but doesn't change anything; "
                "did you mean to use it in a condition?",
                node.span.start,
                node.span.end,
            )
        nargs = len(node.args)
        max_args = None if spec.variadic else len(spec.params)
        if nargs < spec.min_args or (max_args is not None and nargs > max_args):
            self.err(f"wrong number of arguments: {spec.help}", node.span.start, node.span.end)
        for i, arg in enumerate(node.args):
            if i < len(spec.params):
                kind = spec.params[i]
            elif spec.variadic:
                kind = spec.params[-1]
            else:
                self.expr(arg)
                continue
            self.argument(kind, arg)
        return spec.returns

    def argument(self, kind: str, arg: Expr) -> None:
        s = arg.span
        if kind in ("item", "scene"):
            if not isinstance(arg, Str):
                self.err(f'the {kind} must be written in quotes, e.g. "{kind}_id"', s.start, s.end)
                self.expr(arg)
                return
            pool = self.env.items if kind == "item" else self.env.scenes
            if arg.value not in pool:
                self.err(f"unknown {kind} '{arg.value}'", s.start, s.end)
            return
        t = self.expr(arg)
        if t is not None and t != Type.NUMBER:
            self.err(f"expected a number, got {describe_type(t)}", s.start, s.end)

    def statement(self, node: Assign | Call) -> None:
        if isinstance(node, Call):
            self.call(node, as_statement=True)
            return
        ts = node.target_span
        var_type = self.env.variables.get(node.target)
        value_type = self.expr(node.value)
        if var_type is None:
            if node.target in RESERVED_NAMES:
                self.err(f"'{node.target}' is a reserved name", ts.start, ts.end)
            else:
                self.err(f"unknown variable '{node.target}'", ts.start, ts.end)
            return
        if node.op == "=":
            if value_type is not None and value_type != var_type:
                self.err(
                    f"'{node.target}' holds {describe_type(var_type)}, "
                    f"can't set it to {describe_type(value_type)}",
                    node.value.span.start,
                    node.value.span.end,
                )
            return
        if node.op == "+=" and var_type == Type.TEXT:
            if value_type is not None and value_type != Type.TEXT:
                self.err(
                    f"can only add text to '{node.target}'",
                    node.value.span.start,
                    node.value.span.end,
                )
            return
        if var_type != Type.NUMBER:
            self.err(
                f"'{node.op}' only works on number variables; "
                f"'{node.target}' holds {describe_type(var_type)}",
                ts.start,
                ts.end,
            )
            return
        if value_type is not None and value_type != Type.NUMBER:
            self.err(
                f"expected a number, got {describe_type(value_type)}",
                node.value.span.start,
                node.value.span.end,
            )


def check_expression(expr: Expr, env: Env) -> tuple[Type | None, list[ExprError]]:
    checker = _Checker(env)
    t = checker.expr(expr)
    return t, checker.errors


def check_condition(expr: Expr, env: Env) -> list[ExprError]:
    t, errors = check_expression(expr, env)
    if not errors and t is not None and t != Type.BOOL:
        errors.append(
            ExprError(
                f"a condition must be true or false, but this is {describe_type(t)}",
                expr.span.start,
                expr.span.end,
            )
        )
    return errors


def check_program(program: Program, env: Env) -> list[ExprError]:
    checker = _Checker(env)
    for statement in program.statements:
        checker.statement(statement)
    return checker.errors


@dataclass(slots=True)
class Refs:
    """Everything an expression or program mentions."""

    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    items: set[str] = field(default_factory=set)
    scenes: set[str] = field(default_factory=set)

    def update(self, other: Refs) -> None:
        self.reads |= other.reads
        self.writes |= other.writes
        self.items |= other.items
        self.scenes |= other.scenes


def collect_refs(node: Node) -> Refs:
    refs = Refs()
    for n in walk(node):
        match n:
            case Name(name=name):
                refs.reads.add(name)
            case Assign(target=target, op=op):
                refs.writes.add(target)
                if op != "=":
                    refs.reads.add(target)
            case Call(func=func, args=args) if func in FUNCTIONS and args:
                first = args[0]
                if isinstance(first, Str):
                    kind = FUNCTIONS[func].params[0]
                    if kind == "item":
                        refs.items.add(first.value)
                    elif kind == "scene":
                        refs.scenes.add(first.value)
            case _:
                pass
    return refs
