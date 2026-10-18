from __future__ import annotations

import re

import pytest

from cyoa.expr import (
    Env,
    EvalError,
    ExprError,
    RefKind,
    Type,
    check_condition,
    check_program,
    collect_refs,
    describe_requirement,
    evaluate,
    execute,
    format_value,
    parse_expression,
    parse_program,
    rename_in_expression,
    rename_in_program,
    to_json,
)


class Ctx:
    def __init__(self, **variables):
        self.vars = dict(variables)
        self.inv: dict[str, int] = {}
        self.visits: dict[str, int] = {}

    def get_var(self, name):
        if name not in self.vars:
            raise EvalError(f"unknown variable {name}")
        return self.vars[name]

    def set_var(self, name, value):
        self.vars[name] = value

    def item_count(self, item):
        return self.inv.get(item, 0)

    def give(self, item, amount):
        self.inv[item] = self.inv.get(item, 0) + amount

    def take(self, item, amount):
        self.inv[item] = max(0, self.inv.get(item, 0) - amount)

    def visit_count(self, scene):
        return self.visits.get(scene, 0)


ENV = Env(
    variables={
        "hp": Type.NUMBER,
        "gold": Type.NUMBER,
        "met_king": Type.BOOL,
        "name": Type.TEXT,
        "max_hp": Type.NUMBER,
    },
    items={"rope", "arrow"},
    scenes={"start", "tower"},
)


def ev(src: str, ctx: Ctx | None = None):
    return evaluate(parse_expression(src), ctx or Ctx(hp=5, gold=20, met_king=False, name="Ana"))


# -- parsing & evaluation -------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("10 / 4", 2.5),
        ("10 / 2", 5),
        ("7 % 3", 1),
        ("-hp + 1", -4),
        ("2 - -3", 5),
        ("hp > 3 and gold >= 20", True),
        ("hp > 3 and gold > 20", False),
        ("not met_king", True),
        ("not met_king and hp == 5", True),
        ("met_king or hp < 10", True),
        ("name == 'Ana'", True),
        ('name + " the Bold"', "Ana the Bold"),
        ("hp != 5", False),
        ("min(hp + 10, 12)", 12),
        ("max(1, 2, 3)", 3),
        ("round(2.5)", 3),
        ("round(-2.5)", -3),
        ("floor(2.7)", 2),
        ("ceil(2.1)", 3),
        ("abs(-4)", 4),
        ("true", True),
        ("1.5 + 1.5", 3),
    ],
)
def test_evaluate(src, expected):
    result = ev(src)
    assert result == expected
    assert type(result) is type(expected)


def test_short_circuit_avoids_errors():
    assert ev("false and 1 / 0 > 1") is False
    assert ev("true or 1 / 0 > 1") is True


def test_inventory_and_visits():
    ctx = Ctx()
    ctx.inv = {"arrow": 3}
    ctx.visits = {"tower": 2}
    assert ev('has("arrow")', ctx) is True
    assert ev('has("arrow", 4)', ctx) is False
    assert ev('has("rope")', ctx) is False
    assert ev('count("arrow")', ctx) == 3
    assert ev('visited("tower")', ctx) is True
    assert ev('visited("start")', ctx) is False
    assert ev('visits("tower")', ctx) == 2


def test_division_by_zero():
    with pytest.raises(EvalError, match="division by zero"):
        ev("1 / 0")


def test_execute_program():
    ctx = Ctx(hp=5, gold=20, name="Ana")
    program = parse_program(
        "gold -= 5\nhp = min(hp + 10, 8); give(\"arrow\", 3)\ntake('arrow')  # one used\n"
        'name += "!"\ngold *= 2\ngold /= 3'
    )
    execute(program, ctx)
    assert ctx.vars == {"hp": 8, "gold": 10, "name": "Ana!"}
    assert ctx.inv == {"arrow": 2}


def test_empty_program():
    assert parse_program("").statements == ()
    assert parse_program("  \n ; \n # just a comment").statements == ()


# -- syntax errors --------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "message"),
    [
        ("hp = 5", "use '=='"),
        ("hp > 1 && gold > 2", "use 'and'"),
        ("hp > 1 || gold > 2", "use 'or'"),
        ("!met_king", "use 'not'"),
        ("1 < hp < 10", "chained comparisons"),
        ("(hp > 1", "missing ')'"),
        ("hp >", "incomplete"),
        ("'abc", "unterminated"),
        ("hp > 1 gold", "unexpected 'gold'"),
        ("", "empty"),
        ("3d6", "can't start with a digit"),
        ("hp @ 2", "unexpected character"),
    ],
)
def test_expression_syntax_errors(src, message):
    with pytest.raises(ExprError, match=re.escape(message)):
        parse_expression(src)


@pytest.mark.parametrize(
    ("src", "message"),
    [
        ("gold == 10", "to change a variable use '='"),
        ("gold", "expected an effect"),
        ("gold -= ", "missing value"),
        ("gold -= 1 hp += 1", "new line or ';'"),
        ("true = 1", "reserved word"),
    ],
)
def test_program_syntax_errors(src, message):
    with pytest.raises(ExprError, match=re.escape(message)):
        parse_program(src)


def test_error_location_points_at_token():
    with pytest.raises(ExprError) as info:
        parse_expression("hp > 1 && gold > 2")
    assert (info.value.start, info.value.end) == (7, 9)


def test_multiline_expression_in_parens_in_program():
    program = parse_program("hp = min(\n  hp + 1,\n  10\n)")
    assert len(program.statements) == 1


# -- type checking ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "message"),
    [
        ("hpp > 3", "unknown variable 'hpp'"),
        ('has("ropee")', "unknown item 'ropee'"),
        ('visited("towr")', "unknown scene 'towr'"),
        ("has(rope)", "must be written in quotes"),
        ('hp == "five"', "can't compare a number with text"),
        ("hp + 1", "must be true or false"),
        ("met_king > 1", "compares numbers"),
        ("hp and met_king", "needs true/false"),
        ("not hp", "'not' needs true/false"),
        ('give("rope")', "is an effect"),
        ("foo(1)", "unknown function 'foo'"),
        ('has("rope", 1, 2)', "wrong number of arguments"),
        ("min(1)", "wrong number of arguments"),
        ('name + 1 == "x"', "can't add text and a number"),
        ("has > 1", "is a function"),
    ],
)
def test_condition_type_errors(src, message):
    errors = check_condition(parse_expression(src), ENV)
    assert errors, f"expected an error for {src!r}"
    assert any(message in e.message for e in errors), [e.message for e in errors]


@pytest.mark.parametrize(
    "src",
    [
        "hp > 3 and has('rope')",
        "not met_king or gold >= 10",
        'name == "Ana" and visits("tower") >= 2',
        "count('arrow') > max(1, hp)",
        "met_king",
    ],
)
def test_valid_conditions(src):
    assert check_condition(parse_expression(src), ENV) == []


@pytest.mark.parametrize(
    ("src", "message"),
    [
        ("goldd -= 1", "unknown variable 'goldd'"),
        ('gold = "lots"', "holds a number"),
        ("met_king += 1", "only works on number variables"),
        ("name += 1", "can only add text"),
        ('has("rope")', "doesn't change anything"),
        ('give("sword")', "unknown item 'sword'"),
        ("give(rope)", "must be written in quotes"),
        ("hp = hp > 1", "can't set it to true/false"),
    ],
)
def test_program_type_errors(src, message):
    errors = check_program(parse_program(src), ENV)
    assert any(message in e.message for e in errors), [e.message for e in errors]


def test_valid_program():
    src = 'gold -= 5\nmet_king = true\nname = "Bo"\ngive("rope")\ntake("arrow", hp)'
    assert check_program(parse_program(src), ENV) == []


def test_type_error_spans():
    errors = check_condition(parse_expression("hp > 1 and hpp > 2"), ENV)
    assert [(e.start, e.end) for e in errors] == [(11, 14)]


# -- references, renaming, hints, json --------------------------------------------


def test_collect_refs():
    refs = collect_refs(parse_program('gold -= 1\nhp = max_hp\ngive("rope")'))
    assert refs.writes == {"gold", "hp"}
    assert refs.reads == {"gold", "max_hp"}
    assert refs.items == {"rope"}
    refs = collect_refs(parse_expression('visited("tower") and count("arrow") > 1'))
    assert refs.scenes == {"tower"}
    assert refs.items == {"arrow"}


def test_rename_variable_preserves_formatting():
    src = "gold  -= 5  # pay\nhp = min(hp + gold, 10)"
    assert rename_in_program(src, RefKind.VARIABLE, "gold", "coins") == (
        "coins  -= 5  # pay\nhp = min(hp + coins, 10)"
    )


def test_rename_item_and_scene():
    src = "has('rope') and visited(\"tower\") and count('rope') > 1"
    assert rename_in_expression(src, RefKind.ITEM, "rope", "cord") == (
        'has("cord") and visited("tower") and count("cord") > 1'
    )
    assert rename_in_expression(src, RefKind.SCENE, "tower", "spire") == (
        "has('rope') and visited(\"spire\") and count('rope') > 1"
    )


def test_rename_leaves_text_literals_alone():
    src = 'name == "gold"'
    assert rename_in_expression(src, RefKind.VARIABLE, "gold", "coins") == src
    assert rename_in_expression(src, RefKind.ITEM, "gold", "coins") == src


def test_rename_unparseable_is_noop():
    assert rename_in_expression("gold >", RefKind.VARIABLE, "gold", "x") == "gold >"


LABELS = {"gold": "Gold", "hp": "HP"}
ITEMS = {"rope": "Rope", "arrow": "Arrow"}


@pytest.mark.parametrize(
    ("src", "hint"),
    [
        ("gold >= 10", "Gold ≥ 10"),
        ("10 <= gold", "Gold ≥ 10"),
        ('has("rope")', "Rope"),
        ('has("arrow", 3)', "3× Arrow"),
        ('count("arrow") >= 2', "2× Arrow"),
        ('gold >= 10 and has("rope")', "Gold ≥ 10, Rope"),
        ('has("rope") or hp > 5', "Rope or HP > 5"),
        ('not has("rope")', "no Rope"),
        ("met_king", "Met king"),
        ("met_king == false", "not Met king"),
        ('visited("tower")', None),
        ('gold >= 10 and visited("tower")', None),
        ("gold + hp > 10", None),
    ],
)
def test_describe_requirement(src, hint):
    assert describe_requirement(parse_expression(src), LABELS, ITEMS) == hint


def test_to_json_shape():
    data = to_json(parse_expression("gold >= 10"))
    assert data["type"] == "binary"
    assert data["op"] == ">="
    assert data["left"] == {"type": "name", "name": "gold", "span": [0, 4]}
    assert data["right"]["value"] == 10


@pytest.mark.parametrize(
    ("value", "text"), [(5, "5"), (2.5, "2.5"), (2.0, "2"), (1 / 3, "0.33"), (True, "true")]
)
def test_format_value(value, text):
    assert format_value(value) == text
