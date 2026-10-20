from __future__ import annotations

import pytest

from cyoa.expr import parse_expression
from cyoa.expr.logic import one_always_true


def always(*conditions: str) -> bool:
    return one_always_true([parse_expression(c) for c in conditions])


@pytest.mark.parametrize(
    "conditions",
    [
        ("lost", "not lost"),
        ("gold >= 3", "gold < 3"),
        ("gold > 3", "gold <= 3"),
        ("3 > gold", "gold >= 3"),
        ("hp == 0", "hp != 0"),
        ("0 == hp", "hp != 0"),
        ("cls == 'mage'", 'cls != "mage"'),
        ("lost == true", "lost == false"),
        ("lost != true", "lost"),
        ('has("rope")', 'not has( "rope" )'),
        ("a and b", "not a", "not b"),
        ("a or b", "not a and not b"),
        ("not (a or b)", "a", "b"),
        ("true",),
        ("x > 1 or x <= 1",),
    ],
)
def test_always_one_available(conditions):
    assert always(*conditions)


@pytest.mark.parametrize(
    "conditions",
    [
        ("lost",),
        ("lost", "won"),
        ("a and b", "not a"),
        ("gold > 3", "gold < 3"),  # 3 itself
        ("cls == 'mage'", "cls == 'warrior'"),  # can't know these are the only classes
        ("gold / n >= 1", "gold / n < 1"),  # n = 0 makes both false at play time
        ("false",),
    ],
)
def test_maybe_none_available(conditions):
    assert not always(*conditions)


def test_no_conditions_means_nothing_available():
    assert not one_always_true([])


def test_too_many_tests_is_not_attempted():
    names = [f"v{i}" for i in range(13)]
    assert not always(" or ".join(names), *(f"not {n}" for n in names))
    assert always(" or ".join(names[:12]), *(f"not {n}" for n in names[:12]))
