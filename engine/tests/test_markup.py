from __future__ import annotations

import pytest

from cyoa.expr import ExprError, RefKind
from cyoa.expr.evaluator import evaluate
from cyoa.markup import (
    StyledSpan,
    effect_tag_problems,
    escape,
    parse_template,
    plain,
    rename_in_markup,
    render,
    resolve_template,
    style,
    template_expressions,
    unknown_style_tags,
)


class Ctx:
    def __init__(self, **vars):
        self.vars = vars

    def get_var(self, name):
        return self.vars[name]

    def item_count(self, item):
        return 1 if item == "lantern" else 0

    def visit_count(self, scene):
        return 0


def resolve(text: str, **vars) -> str:
    ctx = Ctx(**vars)
    return resolve_template(parse_template(text), lambda e: evaluate(e, ctx))


def show(text: str, **vars) -> str:
    ctx = Ctx(**vars)
    return plain(render(text, lambda e: evaluate(e, ctx)))


# -- templates ------------------------------------------------------------------


def test_interpolation():
    assert show("You have {gold} gold and {gold * 2} silver.", gold=3) == (
        "You have 3 gold and 6 silver."
    )


def test_conditionals_inline():
    text = "{if hp < 3}Weak.{elif hp < 6}Hurt.{else}Fine.{/if}"
    assert show(text, hp=1) == "Weak."
    assert show(text, hp=4) == "Hurt."
    assert show(text, hp=9) == "Fine."


def test_nested_conditionals():
    text = "{if a}A{if b}B{/if}{else}C{/if}"
    assert show(text, a=True, b=True) == "AB"
    assert show(text, a=True, b=False) == "A"
    assert show(text, a=False, b=True) == "C"


def test_standalone_block_tags_leave_no_blank_lines():
    text = (
        'You enter.\n\n{if has("lantern")}\nThe lantern glows.\n{/if}\n{if dark}\n'
        "It is dark.\n{/if}\n\nThe end."
    )
    assert show(text, dark=False) == "You enter.\n\nThe lantern glows.\n\nThe end."
    assert show(text, dark=True) == "You enter.\n\nThe lantern glows.\nIt is dark.\n\nThe end."


def test_escaped_braces():
    assert show(r"a \{literal\} brace") == "a {literal} brace"


def test_interpolated_values_cannot_inject_styling():
    pages = render("{name}", lambda e: "**[red]x[/red]**\n---")
    assert plain(pages) == "**[red]x[/red]**\n---"
    assert pages[0][0].bold is False


def test_quoted_braces_inside_tags():
    assert show('{if name == "}"}yes{/if}', name="}") == "yes"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{if hp > 1}never closed", "never closed"),
        ("{/if}", "without a matching {if}"),
        ("{else}", "without a matching {if}"),
        ("{if a}x{else}y{else}z{/if}", "after {else}"),
        ("{if a}x{endif}", "close conditional text with {/if}"),
        ("{gold", "missing '}'"),
        ("{}", "empty {}"),
        ("{if}", "needs a condition"),
        ("{if gold >}x{/if}", "incomplete"),
    ],
)
def test_template_errors(text, message):
    with pytest.raises(ExprError, match=message.replace("{", r"\{").replace("}", r"\}")):
        parse_template(text)


def test_error_offsets_point_into_scene_text():
    text = "Hello {if gold >> 2}x{/if}"
    with pytest.raises(ExprError) as info:
        parse_template(text)
    assert text[info.value.start] == ">"


def test_template_expressions_offsets():
    text = "a {gold} b {if hp > 1}c{/if}"
    found = [(text[o : o + 4], cond) for _, o, cond in template_expressions(parse_template(text))]
    assert found == [("gold", False), (" hp ", True)]


def test_variable_named_like_keyword_prefix():
    assert show("{iffy}", iffy=7) == "7"


# -- styling ----------------------------------------------------------------------


def test_bold_italic_color():
    [page] = style("a **b** *c* [red]d[/red] [#ff8800]e[/] f")
    assert [(s.text, s.bold, s.italic, s.color) for s in page] == [
        ("a ", False, False, None),
        ("b", True, False, None),
        (" ", False, False, None),
        ("c", False, True, None),
        (" ", False, False, None),
        ("d", False, False, "red"),
        (" ", False, False, None),
        ("e", False, False, "#ff8800"),
        (" f", False, False, None),
    ]


def test_unmatched_markers_render_literally():
    assert plain(style("2 * 3 = 6 and a ** b")) == "2 * 3 = 6 and a ** b"
    assert plain(style("**unclosed bold")) == "**unclosed bold"
    assert plain(style("a [/red] b")) == "a [/red] b"


def test_unknown_tags_are_text():
    assert plain(style("[sic] and [Requires: Rope]")) == "[sic] and [Requires: Rope]"


def test_nested_styles():
    [page] = style("[red]a [bold]b[/bold] c[/red]")
    assert [(s.text, s.bold, s.color) for s in page] == [
        ("a ", False, "red"),
        ("b", True, "red"),
        (" c", False, "red"),
    ]


def test_color_aliases():
    [page] = style("[grey]x[/grey]")
    assert page[0].color == "bright_black"


def test_page_breaks_and_blank_line_tidying():
    pages = style("one\n\n\n\ntwo\n---\nthree\n   ---   \n\n---\n")
    assert [plain([p]) for p in pages] == ["one\n\ntwo", "three"]


def test_escape_roundtrip():
    raw = r"**not bold** [red] - \ x"
    assert plain(style(escape(raw))) == raw


def test_rich_style_string():
    assert StyledSpan("x", bold=True, color="red").rich_style() == "bold red"


# -- references -------------------------------------------------------------------


def test_rename_in_markup():
    text = 'Gold: {gold}. {if gold > 1 and has("rope")}Rich.{/if} gold stays'
    assert rename_in_markup(text, RefKind.VARIABLE, "gold", "coins") == (
        'Gold: {coins}. {if coins > 1 and has("rope")}Rich.{/if} gold stays'
    )
    assert rename_in_markup(text, RefKind.ITEM, "rope", "cord") == (
        'Gold: {gold}. {if gold > 1 and has("cord")}Rich.{/if} gold stays'
    )


def test_unknown_style_tags():
    assert unknown_style_tags("[rde]x[/rde] [red]y[/red] [/]") == [("rde", 6, 12)]


# -- timing effects ----------------------------------------------------------------


def test_effect_spans():
    [page] = style("[glitch]drip[/glitch] [type slow]slow[/type] [type]norm[/] [pause 2]end")
    shown = [(s.text, s.effect, s.pause) for s in page]
    assert shown == [
        ("drip", "glitch", 0.0),
        (" ", None, 0.0),
        ("slow", "type_slow", 0.0),
        (" ", None, 0.0),
        ("norm", "type", 0.0),
        (" ", None, 0.0),
        ("", None, 2.0),
        ("end", None, 0.0),
    ]


def test_effects_combine_with_styles():
    [page] = style("[red][glitch]a[/glitch][/red] [glitch]**b**[/glitch]")
    assert [(s.text, s.color, s.bold, s.effect) for s in page] == [
        ("a", "red", False, "glitch"),
        (" ", None, False, None),
        ("b", None, True, "glitch"),
    ]


def test_pause_alone_on_a_line_leaves_no_blank_line():
    [page] = style("drip\n[pause 2]\nYou wake.\n\n  [pause]  \nLater.\n[pause 3]")
    assert plain([page]) == "drip\nYou wake.\n\nLater."
    assert [s.pause for s in page if s.pause] == [2.0, 1.0, 3.0]


@pytest.mark.parametrize(
    "text", ["[pause soon]", "[pause 0]", "[pause 99]", "[type sideways]x", "[glitch 3]x"]
)
def test_invalid_effect_tags_are_plain_text(text):
    [page] = style(text)
    assert all(s.effect is None and not s.pause for s in page)
    assert plain([page]) == text


def test_effect_tag_problems():
    problems = effect_tag_problems("[pause soon] [pause 2] [type sideways] [glitch x] [type fast]")
    assert [p[0].split(",")[0] for p in problems] == [
        "[pause] needs a number of seconds up to 30",
        "use [type]",
        "[glitch] doesn't take a setting",
    ]


def test_escaped_effect_tags_stay_literal():
    assert plain(style(r"\[pause 2]")) == "[pause 2]"
    assert effect_tag_problems(r"\[pause soon]") == []


def test_effect_closing_tags_are_known():
    assert unknown_style_tags("[type]a[/type] [glitch]b[/glitch]") == []
