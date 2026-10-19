from __future__ import annotations

from cyoa.model import Choice, Scene
from cyoa.refactor import Kind, find_references, rename
from cyoa.runtime import Runtime
from cyoa.validate import game_stats, has_errors, reachable_scenes, validate

from .conftest import make_game


def codes(issues):
    return sorted({i.code for i in issues})


def test_fixture_game_is_clean(game):
    issues = validate(game)
    assert [i.to_dict() for i in issues] == []


def test_broken_links_and_syntax():
    game = make_game()
    game.scenes[0].choices[0].target = "nowhere"
    game.scenes[0].choices[1].condition = "gold >= "
    game.scenes[1].text = "{if met_troll}unclosed"
    game.scenes[1].on_enter = "hpp -= 1"
    issues = validate(game)
    assert has_errors(issues)
    by_code = {i.code: i for i in issues}
    assert by_code["missing_target"].scene == "start"
    assert by_code["missing_target"].choice == "bridge"
    assert by_code["syntax"].field in ("condition", "text")
    unknown = by_code["unknown_reference"]
    assert (unknown.scene, unknown.field, unknown.start, unknown.end) == (
        "bridge",
        "on_enter",
        0,
        3,
    )


def test_markup_expression_offsets():
    game = make_game()
    game.scenes[0].text = "You have {goldd} gold."
    [issue] = [i for i in validate(game) if i.code == "unknown_reference"]
    assert game.scenes[0].text[issue.start : issue.end] == "goldd"


def test_structure_warnings():
    game = make_game()
    game.scenes.append(
        Scene(
            id="orphan",
            text="Nobody comes here.",
            choices=[Choice(id="c", text="Back", target="start")],
        )
    )
    game.scenes.append(Scene(id="stuck", text=""))
    game.scenes[0].choices.append(Choice(id="s", text="", target="stuck"))
    game.scenes.append(
        Scene(
            id="gated",
            text="Gate.",
            choices=[
                Choice(id="g", text="Open", target="start", condition='has("rope")'),
            ],
        )
    )
    game.scenes[1].choices.append(Choice(id="gate", text="To gate", target="gated"))
    issues = validate(game)
    assert {
        "unreachable",
        "dead_end",
        "empty_text",
        "empty_choice_text",
        "possible_softlock",
    } <= set(codes(issues))
    assert not has_errors(issues)
    unreachable = [i.scene for i in issues if i.code == "unreachable"]
    assert unreachable == ["orphan"]


def test_ending_with_choices_warns():
    game = make_game()
    game.scenes[2].choices.append(Choice(id="x", text="Again", target="start"))
    assert "ending_with_choices" in codes(validate(game))


def test_ids_and_declarations():
    game = make_game(
        start_scene="missing",
        variables=[
            {"name": "Bad Name", "type": "number", "initial": 0},
            {"name": "hp", "type": "number", "initial": "ten"},
            {"name": "flag", "type": "bool", "initial": False, "max": 3},
            {"name": "x", "type": "number", "initial": 0, "min": 5, "max": 1},
            {"name": "y", "type": "number", "initial": 0, "max": "nope"},
            {"name": "has", "type": "number", "initial": 0},
            {"name": "hp", "type": "number", "initial": 0},
        ],
    )
    found = set(codes(validate(game)))
    assert {
        "invalid_variable_id",
        "initial_type",
        "bound_on_non_number",
        "min_above_max",
        "unknown_bound_variable",
        "reserved_variable",
        "duplicate_variable",
        "missing_start_scene",
    } <= found


def test_usage_warnings():
    game = make_game(
        variables=[
            *make_game().model_dump()["variables"],
            {"name": "unused", "type": "number", "initial": 0},
            {"name": "written", "type": "number", "initial": 0},
        ],
        items=[
            *make_game().model_dump()["items"],
            {"id": "map", "name": "Map"},
            {"id": "key", "name": "Key"},
        ],
    )
    game.scenes[0].on_enter = "written = 1"
    game.scenes[0].choices[0].condition = 'not has("key")'
    by_code = {(i.code, i.variable or i.item) for i in validate(game)}
    assert ("unused_variable", "unused") in by_code
    assert ("write_only_variable", "written") in by_code
    assert ("unused_item", "map") in by_code
    assert ("item_never_given", "key") in by_code


def test_rule_checks():
    game = make_game(rules=[{"id": "r", "condition": "", "goto": "nope"}])
    assert {"rule_without_condition", "missing_target"} <= set(codes(validate(game)))


def test_reachability_includes_rule_targets(game):
    assert reachable_scenes(game) == {"start", "bridge", "win", "dead"}


def test_unknown_style_warning():
    game = make_game()
    game.scenes[0].text = "[rde]hi[/rde]"
    assert "unknown_style" in codes(validate(game))


def test_stats(game):
    stats = game_stats(game)
    assert stats["scenes"] == 4
    assert stats["endings"] == 2
    assert stats["words"] == 3 + 5 + 3 + 2  # tags and interpolations don't count
    assert stats["chapters"]["ch1"]["scenes"] == 2


# -- refactoring --------------------------------------------------------------------


def test_find_references(game):
    refs = find_references(game, Kind.VARIABLE, "gold")
    fields = sorted(r["field"] for r in refs)
    assert fields == ["condition", "effects", "status_format", "text"]
    assert {r["field"] for r in find_references(game, Kind.SCENE, "start")} == {
        "start_scene",
        "target",
    }
    assert find_references(game, Kind.VARIABLE, "max_hp")[0]["field"] == "status_format"
    assert any(r["field"] == "max" for r in find_references(game, Kind.VARIABLE, "max_hp"))
    assert [r["scene"] for r in find_references(game, Kind.CHAPTER, "ch1")] == ["start", "bridge"]


def test_rename_variable_everywhere(game):
    renamed = rename(game, Kind.VARIABLE, "max_hp", "vitality")
    assert renamed.variables[0].max == "vitality"
    assert renamed.variables[1].name == "vitality"
    assert renamed.settings.status_format == "HP {hp}/{vitality} | Gold {gold}"
    assert validate(renamed) == []
    assert game.variables[1].name == "max_hp"  # original untouched


def test_rename_scene_and_item(game):
    renamed = rename(rename(game, Kind.SCENE, "start", "camp"), Kind.ITEM, "rope", "cord")
    assert renamed.start_scene == "camp"
    assert renamed.scenes[0].id == "camp"
    assert renamed.scenes[1].choices[2].target == "camp"
    assert renamed.scenes[0].choices[1].effects == 'gold -= 3\ngive("cord")'
    assert renamed.scenes[1].choices[0].condition == 'has("cord")'
    assert validate(renamed) == []
    state = Runtime(renamed).new_game()
    assert state.scene == "camp"


def test_rename_chapter(game):
    renamed = rename(game, Kind.CHAPTER, "ch1", "prologue")
    assert renamed.chapters[0].id == "prologue"
    assert {s.chapter for s in renamed.scenes} == {"prologue", None}


def test_player_export_strips_author_fields(game):
    game.scenes[0].notes = "secret"
    game.scenes[0].position = (1.0, 2.0)
    data = game.to_player_dict()
    assert "notes" not in data["scenes"][0]
    assert "position" not in data["scenes"][0]
    assert game.to_project_dict()["scenes"][0]["notes"] == "secret"


def test_invalid_effect_warning():
    game = make_game()
    game.scenes[0].text = "Wait [pause soon] for it."
    [issue] = [i for i in validate(game) if i.code == "invalid_effect"]
    assert issue.severity == "warning"
    assert game.scenes[0].text[issue.start : issue.end] == "[pause soon]"


def test_changes_in_text_are_checked():
    game = make_game()
    game.scenes[0].text = 'Hi.{goldd -= 1}{met_troll = 3}{give("sword")}'
    issues = [i for i in validate(game) if i.scene == "start" and i.field == "text"]
    messages = sorted(i.message for i in issues)
    assert messages == [
        "'met_troll' holds true/false, can't set it to a number",
        "unknown item 'sword'",
        "unknown variable 'goldd'",
    ]
    for issue in issues:
        assert game.scenes[0].text[issue.start : issue.end] in ("goldd", "3", '"sword"')


def test_changes_only_allowed_in_scene_text():
    game = make_game()
    game.scenes[0].choices[0].text = "Go {gold -= 1}"
    game.settings.status_format = "HP {hp}{hp = 1}"
    codes = [(i.code, i.field) for i in validate(game) if i.code == "change_outside_scene_text"]
    assert sorted(codes) == [
        ("change_outside_scene_text", "choice_text"),
        ("change_outside_scene_text", "status_format"),
    ]


def test_variables_changed_in_text_count_as_used():
    game = make_game(
        variables=[
            *make_game().model_dump()["variables"],
            {"name": "initiative", "type": "number", "initial": 0},
        ]
    )
    game.scenes[0].text = "Ready.{initiative = 1}"
    codes = {(i.code, i.variable) for i in validate(game)}
    assert ("unused_variable", "initiative") not in codes
    assert ("write_only_variable", "initiative") in codes
