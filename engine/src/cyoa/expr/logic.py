"""Can a set of conditions all be false at once?

Used to tell whether a scene always has a choice available. Each condition becomes
a yes/no formula over its basic tests (``gold >= 3``, ``has("rope")``, a bool
variable). Opposite comparisons share one test, so ``gold < 3`` is
``not gold >= 3`` and ``x != 0`` is ``not x == 0``. The tests are then treated as
independent: if every combination of answers makes some condition true, one always
is, whatever the game state. The answer is never wrong when it says "yes", but it
can miss cases that need to know values (``class == "mage"`` or ``"warrior"`` being
the only classes).
"""

from __future__ import annotations

import itertools
import json
from typing import Any

from .nodes import Binary, Bool, Call, Expr, Name, Number, Str, Unary, walk

MAX_TESTS = 12  # 4096 combinations; beyond that, don't try

Formula = tuple[Any, ...]


def one_always_true(conditions: list[Expr]) -> bool:
    """True if, whatever the values, at least one of ``conditions`` is true."""
    tests: dict[str, int] = {}
    formulas = [_formula(c, tests) for c in conditions]
    if not formulas or len(tests) > MAX_TESTS:
        return False
    for answers in itertools.product((False, True), repeat=len(tests)):
        if not any(_holds(f, answers) for f in formulas):
            return False
    return True


def _formula(node: Expr, tests: dict[str, int]) -> Formula:
    match node:
        case Binary(op="and" | "or" as op, left=left, right=right):
            return (op, _formula(left, tests), _formula(right, tests))
        case Unary(op="not", operand=operand):
            return ("not", _formula(operand, tests))
        case Bool(value=value):
            return ("const", value)
        case (
            Binary(op="==" | "!=" as op, left=Bool() as lit, right=other)
            | Binary(op="==" | "!=" as op, left=other, right=Bool() as lit)
        ):
            # x == true is x, x == false / x != true is not x
            inner = _formula(other, tests)
            return inner if lit.value == (op == "==") else ("not", inner)
        case Binary(op="==" | "!=" as op, left=left, right=right):
            a, b = sorted((_key(left), _key(right)))
            test = _test(f"{a} == {b}", node, tests)
            return test if op == "==" else ("not", test)
        case Binary(op=">=" | "<" as op, left=left, right=right):
            test = _test(f"{_key(left)} >= {_key(right)}", node, tests)
            return test if op == ">=" else ("not", test)
        case Binary(op="<=" | ">" as op, left=left, right=right):
            test = _test(f"{_key(right)} >= {_key(left)}", node, tests)
            return test if op == "<=" else ("not", test)
        case _:
            return _test(_key(node), node, tests)


def _test(key: str, node: Expr, tests: dict[str, int]) -> Formula:
    # A division can fail (by zero), which makes a condition false at play time
    # whichever way it's written, so such tests are never treated as opposites.
    if any(isinstance(n, Binary) and n.op in ("/", "%") for n in walk(node)):
        key = f"{key}#{len(tests)}"
    return ("test", tests.setdefault(key, len(tests)))


def _key(node: Expr) -> str:
    """The same text for the same expression, however it was spaced or quoted."""
    match node:
        case Number(value=value):
            return repr(int(value) if float(value).is_integer() else value)
        case Str(value=value):
            return json.dumps(value)
        case Bool(value=value):
            return "true" if value else "false"
        case Name(name=name):
            return name
        case Call(func=func, args=args):
            return f"{func}({', '.join(_key(a) for a in args)})"
        case Unary(op=op, operand=operand):
            return f"({op} {_key(operand)})"
        case Binary(op=op, left=left, right=right):
            return f"({_key(left)} {op} {_key(right)})"


def _holds(formula: Formula, answers: tuple[bool, ...]) -> bool:
    match formula:
        case ("test", index):
            return answers[index]
        case ("not", inner):
            return not _holds(inner, answers)
        case ("and", left, right):
            return _holds(left, answers) and _holds(right, answers)
        case ("or", left, right):
            return _holds(left, answers) or _holds(right, answers)
        case ("const", value):
            return value
    raise ValueError(f"bad formula {formula!r}")
