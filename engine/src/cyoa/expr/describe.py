"""Turn a choice condition into a short, player-facing requirement hint.

``gold >= 10 and has("rope")`` becomes ``Gold ≥ 10, Rope``. Conditions too
complex to describe honestly return ``None`` and the player shows a generic lock.
"""

from __future__ import annotations

from collections.abc import Mapping

from .evaluator import format_value
from .nodes import Binary, Bool, Call, Expr, Name, Number, Str, Unary

_SYMBOLS = {">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "=", "!=": "≠"}
_FLIP = {">=": "<=", "<=": ">=", ">": "<", "<": ">", "==": "==", "!=": "!="}


def describe_requirement(
    expr: Expr, var_labels: Mapping[str, str], item_names: Mapping[str, str]
) -> str | None:
    return _describe(expr, var_labels, item_names)


def _label(name: str, labels: Mapping[str, str]) -> str:
    return labels.get(name) or name.replace("_", " ").capitalize()


def _item(item: str, names: Mapping[str, str]) -> str:
    return names.get(item) or item.replace("_", " ").capitalize()


def _describe(expr: Expr, labels: Mapping[str, str], items: Mapping[str, str]) -> str | None:
    match expr:
        case Binary(op="and", left=left, right=right):
            a = _describe(left, labels, items)
            b = _describe(right, labels, items)
            return f"{a}, {b}" if a and b else None
        case Binary(op="or", left=left, right=right):
            a = _describe(left, labels, items)
            b = _describe(right, labels, items)
            return f"{a} or {b}" if a and b else None
        case Name(name=name):
            return _label(name, labels)
        case Unary(op="not", operand=Name(name=name)):
            return f"not {_label(name, labels)}"
        case Call(func="has", args=(Str(value=item),)):
            return _item(item, items)
        case Call(func="has", args=(Str(value=item), Number(value=n))):
            return f"{format_value(n)}× {_item(item, items)}" if n != 1 else _item(item, items)
        case Unary(op="not", operand=Call(func="has", args=(Str(value=item),))):
            return f"no {_item(item, items)}"
        case Binary(op=op, left=left, right=right) if op in _SYMBOLS:
            literal_types = (Number, Str, Bool)
            if isinstance(left, Name | Call) and isinstance(right, literal_types):
                subject, value = left, right
            elif isinstance(right, Name | Call) and isinstance(left, literal_types):
                subject, value, op = right, left, _FLIP[op]
            else:
                return None
            if isinstance(subject, Call):
                if (
                    subject.func == "count"
                    and len(subject.args) == 1
                    and isinstance(subject.args[0], Str)
                ):
                    name = _item(subject.args[0].value, items)
                    if op == ">=" and isinstance(value, Number):
                        return f"{format_value(value.value)}× {name}"
                    return f"{name} count {_SYMBOLS[op]} {format_value(value.value)}"
                return None
            label = _label(subject.name, labels)
            if isinstance(value, Bool):
                truthy = value.value if op == "==" else not value.value
                return label if truthy else f"not {label}"
            return f"{label} {_SYMBOLS[op]} {format_value(value.value)}"
        case _:
            return None
