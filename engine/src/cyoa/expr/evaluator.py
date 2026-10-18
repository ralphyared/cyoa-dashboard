"""Evaluate expressions and run effect programs against a game context."""

from __future__ import annotations

import math
from typing import Protocol

from .errors import EvalError
from .nodes import Assign, Binary, Bool, Call, Expr, Name, Number, Program, Str, Unary, Value


class Context(Protocol):
    def get_var(self, name: str) -> Value: ...
    def set_var(self, name: str, value: Value) -> None: ...
    def item_count(self, item: str) -> int: ...
    def give(self, item: str, amount: int) -> None: ...
    def take(self, item: str, amount: int) -> None: ...
    def visit_count(self, scene: str) -> int: ...


def normalize(value: Value) -> Value:
    """Turn whole-number floats into ints so 10 / 2 shows as 5, not 5.0."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def format_value(value: Value) -> str:
    """How a value is shown inside scene text."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _number(value: Value, what: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvalError(f"{what} needs a number, got {value!r}")
    return value


def _boolean(value: Value, what: str) -> bool:
    if not isinstance(value, bool):
        raise EvalError(f"{what} needs true/false, got {value!r}")
    return value


def _amount(value: Value) -> int:
    n = _number(value, "an item amount")
    return int(n)


def evaluate(expr: Expr, ctx: Context) -> Value:
    match expr:
        case Number(value=v) | Str(value=v) | Bool(value=v):
            return v
        case Name(name=name):
            return ctx.get_var(name)
        case Unary(op="not", operand=operand):
            return not _boolean(evaluate(operand, ctx), "'not'")
        case Unary(op="-", operand=operand):
            return normalize(-_number(evaluate(operand, ctx), "'-'"))
        case Binary(op="and", left=left, right=right):
            return _boolean(evaluate(left, ctx), "'and'") and _boolean(
                evaluate(right, ctx), "'and'"
            )
        case Binary(op="or", left=left, right=right):
            return _boolean(evaluate(left, ctx), "'or'") or _boolean(evaluate(right, ctx), "'or'")
        case Binary(op=op, left=left, right=right):
            return _binary(op, evaluate(left, ctx), evaluate(right, ctx))
        case Call():
            return _call(expr, ctx)
        case _:
            raise EvalError(f"can't evaluate {expr!r}")


def _binary(op: str, a: Value, b: Value) -> Value:
    if op == "==":
        return (type(a) is type(b) and a == b) or (_is_num(a) and _is_num(b) and a == b)
    if op == "!=":
        return not _binary("==", a, b)
    if op == "+" and isinstance(a, str) and isinstance(b, str):
        return a + b
    x = _number(a, f"'{op}'")
    y = _number(b, f"'{op}'")
    match op:
        case "<":
            return x < y
        case "<=":
            return x <= y
        case ">":
            return x > y
        case ">=":
            return x >= y
        case "+":
            return normalize(x + y)
        case "-":
            return normalize(x - y)
        case "*":
            return normalize(x * y)
        case "/":
            if y == 0:
                raise EvalError("division by zero")
            return normalize(x / y)
        case "%":
            if y == 0:
                raise EvalError("division by zero")
            return normalize(x % y)
    raise EvalError(f"unknown operator {op!r}")


def _is_num(v: Value) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _str_arg(expr: Call, index: int) -> str:
    if index >= len(expr.args):
        raise EvalError(f"{expr.func}() is missing an argument")
    arg = expr.args[index]
    if not isinstance(arg, Str):
        raise EvalError(f"{expr.func}() needs a quoted name")
    return arg.value


def _call(expr: Call, ctx: Context) -> Value:
    func = expr.func
    args = expr.args
    match func:
        case "has":
            need = _amount(evaluate(args[1], ctx)) if len(args) > 1 else 1
            return ctx.item_count(_str_arg(expr, 0)) >= need
        case "count":
            return ctx.item_count(_str_arg(expr, 0))
        case "visited":
            return ctx.visit_count(_str_arg(expr, 0)) > 0
        case "visits":
            return ctx.visit_count(_str_arg(expr, 0))
        case "min" | "max":
            if not args:
                raise EvalError(f"{func}() needs at least one value")
            values = [_number(evaluate(a, ctx), f"{func}()") for a in args]
            return normalize(min(values) if func == "min" else max(values))
        case "round" | "floor" | "ceil" | "abs":
            if len(args) != 1:
                raise EvalError(f"{func}() needs exactly one value")
            x = _number(evaluate(args[0], ctx), f"{func}()")
            if func == "round":
                # round half away from zero (Python's round() uses banker's rounding)
                return math.floor(abs(x) + 0.5) * (1 if x >= 0 else -1)
            if func == "floor":
                return math.floor(x)
            if func == "ceil":
                return math.ceil(x)
            return normalize(abs(x))
    raise EvalError(f"{func}() can't be used here")


def execute(program: Program, ctx: Context) -> None:
    for statement in program.statements:
        match statement:
            case Assign(target=target, op=op, value=value_expr):
                value = evaluate(value_expr, ctx)
                if op != "=":
                    current = ctx.get_var(target)
                    if op == "+=" and isinstance(current, str) and isinstance(value, str):
                        value = current + value
                    else:
                        value = _binary(op[0], current, value)
                ctx.set_var(target, value)
            case Call(func="give" | "take" as func, args=args):
                item = _str_arg(statement, 0)
                amount = _amount(evaluate(args[1], ctx)) if len(args) > 1 else 1
                if amount < 0:
                    raise EvalError(f"{func}() amount can't be negative")
                if func == "give":
                    ctx.give(item, amount)
                else:
                    ctx.take(item, amount)
            case Call(func=func):
                raise EvalError(f"{func}() doesn't change anything and can't be used as an effect")
