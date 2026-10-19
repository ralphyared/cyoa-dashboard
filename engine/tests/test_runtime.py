from __future__ import annotations

import pytest

from cyoa.markup import plain
from cyoa.runtime import GameError, GameState, Runtime

from .conftest import make_game


def ids(views):
    return [v.id for v in views]


def test_new_game_enters_start(game):
    rt = Runtime(game)
    state = rt.new_game()
    assert state.scene == "start"
    assert state.vars == {"hp": 10, "max_hp": 10, "gold": 5, "met_troll": False}
    assert state.visits == {"start": 1}


def test_view_renders_text_status_and_choices(game):
    rt = Runtime(game)
    state = rt.new_game()
    view = rt.view(state)
    assert plain(view.pages) == "You have 5 gold."
    assert "".join(s.text for s in view.status) == "HP 10/10 | Gold 5"
    assert view.chapter_title == "Chapter 1"
    assert ids(view.choices) == ["bridge", "shop", "ask"]
    assert all(v.enabled for v in view.choices)


def test_effects_inventory_and_locked_choices(game):
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "shop")
    assert state.vars["gold"] == 2
    assert state.inventory == {"rope": 1}
    shop = next(v for v in rt.choices(state) if v.id == "shop")
    assert not shop.enabled
    assert shop.hint == "Gold ≥ 3"
    with pytest.raises(GameError, match="locked"):
        rt.choose(state, "shop")


def test_once_choices_disappear(game):
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "ask")
    assert state.vars["met_troll"] is True
    assert "ask" not in ids(rt.choices(state))
    with pytest.raises(GameError, match="isn't available"):
        rt.choose(state, "ask")


def test_on_enter_and_conditional_text(game):
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "ask")
    rt.choose(state, "bridge")
    assert state.vars["hp"] == 8
    assert plain(rt.view(state).pages) == "A troll. You recognize him."


def test_locked_choice_auto_hint_uses_item_name(game):
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")
    climb = next(v for v in rt.choices(state) if v.id == "climb")
    assert not climb.enabled
    assert climb.hint == "Rope"


def test_rule_redirects_to_death(game):
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")  # hp 8
    rt.choose(state, "fight")  # -5 -> 3, re-enter bridge -2 -> 1
    assert state.scene == "bridge"
    assert state.vars["hp"] == 1
    rt.choose(state, "fight")  # -5 -> 0 (clamped): rule fires before entering bridge
    assert state.scene == "dead"
    assert state.vars["hp"] == 0
    view = rt.view(state)
    assert view.ending is not None and view.ending.kind == "death"
    assert view.choices == []


def test_rules_are_edge_triggered():
    game = make_game(rules=[{"id": "rich", "condition": "gold >= 5", "effects": "max_hp += 1"}])
    rt = Runtime(game)
    state = rt.new_game()
    assert state.vars["max_hp"] == 11  # fired once on start
    rt.choose(state, "ask")
    assert state.vars["max_hp"] == 11  # still true: doesn't fire again
    rt.choose(state, "shop")  # gold 2: rule resets
    assert "rich" not in state.active_rules


def test_clamping_with_variable_bound(game):
    rt = Runtime(game)
    state = rt.new_game()
    rt.debug_set(state, "hp", 50)
    assert state.vars["hp"] == 10
    rt.debug_set(state, "max_hp", 4)
    rt.clamp_all(state)
    assert state.vars["hp"] == 4


def test_non_stackable_items_cap_at_one():
    game = make_game()
    rt = Runtime(game)
    state = rt.new_game()
    rt.run_effects(state, 'give("rope", 3)\ngive("arrow", 3)\ntake("arrow")', "test")
    assert state.inventory == {"rope": 1, "arrow": 2}
    rt.run_effects(state, 'take("arrow", 10)', "test")
    assert state.inventory == {"rope": 1}


def test_broken_expressions_are_reported_not_fatal():
    game = make_game()
    game.scenes[0].choices[0].condition = "nope > 1"
    game.scenes[0].text = "Gold: {gold / 0}"
    game.scenes[0].on_enter = "gold -= ; hp -= 1"
    rt = Runtime(game)
    state = rt.new_game()
    view = rt.view(state)
    assert "bridge" not in ids(view.choices)
    assert plain(view.pages) == "Gold: ?"
    assert any("unknown variable 'nope'" in p for p in rt.problems)
    assert any("division by zero" in p for p in rt.problems)
    assert any("missing value" in p for p in rt.problems)


def test_missing_target_raises(game):
    game.scenes[0].choices[0].target = "nowhere"
    rt = Runtime(game)
    state = rt.new_game()
    with pytest.raises(GameError, match="doesn't exist"):
        rt.choose(state, "bridge")


def test_rules_chain_without_looping():
    game = make_game(
        rules=[
            {"id": "a", "condition": "visits('bridge') >= 1", "goto": "start"},
            {"id": "b", "condition": "visits('start') >= 2", "goto": "bridge"},
        ]
    )
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")  # bridge -> a -> start -> b -> bridge; edge triggers stop it
    assert state.scene == "bridge"
    assert state.visits == {"start": 2, "bridge": 2}


def test_redirect_limit(monkeypatch):
    import cyoa.runtime

    monkeypatch.setattr(cyoa.runtime, "MAX_REDIRECTS", 0)
    game = make_game(rules=[{"id": "a", "condition": "visited('start')", "goto": "bridge"}])
    with pytest.raises(GameError, match="too many automatic scene changes"):
        Runtime(game).new_game()


def test_save_roundtrip(game):
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "shop")
    rt.choose(state, "ask")
    data = rt.make_save(state)
    assert data["label"] == "Chapter 1 · Start"
    restored, warnings = rt.restore_save(data)
    assert warnings == []
    assert restored.to_dict() == state.to_dict()


def test_save_repair_after_game_changes(game):
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "shop")
    rt.choose(state, "bridge")
    data = rt.make_save(state)
    data["state"]["vars"]["removed_var"] = 3
    data["state"]["vars"]["gold"] = "corrupt"
    data["state"]["inventory"]["ghost_item"] = 2
    data["game_version"] = "0.9"
    changed = make_game()
    changed.scenes = [s for s in changed.scenes if s.id != "bridge"]
    restored, warnings = Runtime(changed).restore_save(data)
    assert restored.scene == "start"
    assert "removed_var" not in restored.vars
    assert restored.vars["gold"] == 5
    assert restored.inventory == {"rope": 1}
    assert len(warnings) == 2


def test_save_from_other_game_rejected(game):
    rt = Runtime(game)
    data = rt.make_save(rt.new_game())
    data["game_id"] = "other"
    with pytest.raises(GameError, match="different game"):
        rt.restore_save(data)


def test_state_copy_is_independent(game):
    rt = Runtime(game)
    state = rt.new_game()
    copy = state.copy()
    rt.choose(state, "shop")
    assert copy.vars["gold"] == 5
    assert GameState.from_dict(copy.to_dict()) == copy


def test_parse_value_for_debugging(game):
    rt = Runtime(game)
    assert rt.parse_value("hp", "7") == 7
    assert rt.parse_value("met_troll", "yes") is True
    with pytest.raises(GameError):
        rt.parse_value("hp", "lots")


def test_choice_text_interpolation():
    game = make_game()
    game.scenes[0].choices[1].text = "Buy rope ({gold} gold left)"
    rt = Runtime(game)
    state = rt.new_game()
    shop = next(v for v in rt.choices(state) if v.id == "shop")
    assert shop.plain_text == "Buy rope (5 gold left)"


# -- changes written in scene text -----------------------------------------------------


def text_game(text: str, **overrides):
    game = make_game(**overrides)
    game.scenes[1].text = text  # the bridge
    game.scenes[1].on_enter = ""
    return game


def test_text_changes_apply_once_on_arrival():
    game = text_game("{if gold >= 5}You pay.{gold -= 5}{else}You can't pay.{/if} Gold: {gold}.")
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")
    assert state.vars["gold"] == 0
    assert plain(rt.view(state).pages) == "You pay. Gold: 0."
    # redraws show the text as read and don't apply the change again
    assert plain(rt.view(state).pages) == "You pay. Gold: 0."
    assert state.vars["gold"] == 0


def test_first_visit_greeting_survives_redraws_and_saves():
    game = text_game("{if not met_troll}Hello, stranger.{met_troll = true}{else}You again.{/if}")
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")
    assert state.vars["met_troll"] is True
    assert plain(rt.view(state).pages) == "Hello, stranger."
    restored, _ = rt.restore_save(rt.make_save(state))
    assert plain(rt.view(restored).pages) == "Hello, stranger."
    # re-rendered (playtest reload) it shows the current values instead
    fresh, _ = rt.restore_save(rt.make_save(state), keep_text=False)
    assert plain(rt.view(fresh).pages) == "You again."
    # coming back later reads the scene again
    rt.choose(state, "back")
    rt.choose(state, "bridge")
    assert plain(rt.view(state).pages) == "You again."


def test_text_changes_can_trigger_rules():
    game = text_game("The troll hits you.{hp -= 50}")
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")
    assert state.scene == "dead"
    assert state.vars["hp"] == 0


def test_text_changes_happen_after_arrival_effects_and_items_work():
    game = text_game('{if has("rope")}You coil your rope.{take("rope")}{give("arrow", 2)}{/if}')
    game.scenes[1].on_enter = 'give("rope")'
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")
    assert state.inventory == {"arrow": 2}
    assert plain(rt.view(state).pages) == "You coil your rope."


def test_broken_text_change_is_reported_not_fatal():
    game = text_game("Ouch.{gold -= 1 / 0} Still here.")
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")
    assert plain(rt.view(state).pages) == "Ouch. Still here."
    assert any("division by zero" in p for p in rt.problems)


def test_debug_changes_rerender_the_text():
    game = text_game("Gold: {gold}.")
    rt = Runtime(game)
    state = rt.new_game()
    rt.choose(state, "bridge")
    rt.debug_set(state, "gold", 42)
    assert plain(rt.view(state).pages) == "Gold: 42."
