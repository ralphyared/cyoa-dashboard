from __future__ import annotations

import io
import json

import pytest
from rich.console import Console

from cyoa.player.app import Player
from cyoa.player.cli import main
from cyoa.player.storage import AUTO, Options, OptionsStore, SaveStore
from cyoa.player.terminal import Terminal

from .conftest import make_game


class FakeTerminal(Terminal):
    def __init__(self, inputs: list[str], width: int = 80) -> None:
        console = Console(
            file=io.StringIO(),
            width=width,
            force_terminal=False,
            color_system=None,
            highlight=False,
        )
        super().__init__(console, interactive=False)
        self.inputs = list(inputs)

    def input(self, prompt: str = "") -> str:
        self.console.print(prompt, end="")
        if not self.inputs:
            raise EOFError
        answer = self.inputs.pop(0)
        self.console.print(answer)
        return answer

    def clear(self) -> None:
        self.console.print("<<CLEAR>>")

    @property
    def output(self) -> str:
        file = self.console.file
        assert isinstance(file, io.StringIO)
        return file.getvalue()


def run(inputs, tmp_path, game=None, state=None, **kwargs):
    term = FakeTerminal(inputs)
    player = Player(
        game or make_game(),
        term,
        saves=SaveStore(tmp_path / "saves"),
        options=OptionsStore(tmp_path / "options.json"),
        **kwargs,
    )
    player.run(state)
    return term, player


def test_full_playthrough_to_victory(tmp_path):
    term, _ = run(["1", "2", "1", "1", "3", "5"], tmp_path)
    out = term.output
    assert "Test Game" in out
    assert "You have 5 gold." in out
    assert "HP 10/10 | Gold 5" in out
    assert "Chapter 1" in out
    assert "1) Go to the bridge" in out
    assert "You have 2 gold." in out  # bought rope
    assert "You made it." in out
    assert "THE END" in out and "The Climber" in out
    assert "Goodbye!" in out
    assert term.inputs == []


def test_death_ending(tmp_path):
    # new game, bridge, fight, fight -> dead, back to title, quit
    term, _ = run(["1", "1", "1", "1", "3", "5"], tmp_path)
    assert "YOU DIED" in term.output
    assert "Troll food" in term.output


def test_locked_choices_are_shown_but_not_numbered(tmp_path):
    term, _ = run(["1", "1", "q", "5"], tmp_path)
    assert "-) Climb down  [Requires: Rope]" in term.output
    assert "1) Fight" in term.output


def test_invalid_input_message(tmp_path):
    term, _ = run(["1", "9", "x", "q", "5"], tmp_path)
    assert "Choose a number from 1 to 3, or a letter in brackets." in term.output


def test_inventory_screen(tmp_path):
    term, _ = run(["1", "3", "2", "i", "", "q", "5"], tmp_path)
    out = term.output
    assert "Inventory" in out
    assert "Arrow ×2" in out
    assert "Rope" in out


def test_empty_inventory(tmp_path):
    term, _ = run(["1", "i", "", "q", "5"], tmp_path)
    assert "You aren't carrying anything." in term.output


def test_autosave_and_continue(tmp_path):
    run(["1", "2", "q", "5"], tmp_path)
    saves = SaveStore(tmp_path / "saves")
    info = saves.info(AUTO)
    assert info is not None and info.label == "Chapter 1 · Start"
    term, _ = run(["2", "q", "6"], tmp_path)  # title now has Continue + Load Game
    assert "2) Continue" in term.output
    assert "You have 2 gold." in term.output


def test_save_and_load_slots(tmp_path):
    term, _ = run(["1", "2", "s", "3", "1", "l", "3", "q", "5"], tmp_path)
    out = term.output
    assert "Saved to slot 3." in out
    data = SaveStore(tmp_path / "saves").read("3")
    assert data is not None and data["state"]["vars"]["gold"] == 2
    assert data["state"]["scene"] == "start"
    # loading slot 3 from the bridge returns us to the start scene
    assert out.count("You have 2 gold.") >= 2


def test_overwrite_requires_confirmation(tmp_path):
    term, _ = run(["1", "s", "1", "s", "1", "n", "", "q", "5"], tmp_path)
    assert "Overwrite slot 1? (y/n)" in term.output


def test_options_persist(tmp_path):
    run(["2", "1", "2", "3", "", "3"], tmp_path)
    options = OptionsStore(tmp_path / "options.json").load()
    assert options == Options(typewriter=True, speed="fast", width=60)


def test_intro_and_multi_page_scene(tmp_path):
    game = make_game()
    game.settings.intro = "Long ago...\n---\nIn a land far away."
    game.scenes[0].text = "Page one.\n---\nPage two."
    term, _ = run(["1", "", "", "", "q", "5"], tmp_path, game=game)
    out = term.output
    assert out.index("Long ago...") < out.index("In a land far away.") < out.index("Page one.")
    assert "press Enter to begin" in out
    page_one = out.index("Page one.")
    assert page_one < out.index("press Enter to continue", page_one) < out.index("Page two.")


def test_redraw_shows_only_last_page(tmp_path):
    game = make_game()
    game.scenes[0].text = "Page one.\n---\nPage two."
    term, _ = run(["1", "", "x", "q", "5"], tmp_path, game=game)
    assert term.output.count("Page one.") == 1
    assert term.output.count("Page two.") == 1


def test_debug_commands_and_problems(tmp_path):
    game = make_game()
    game.scenes[0].text = "Gold {gold}. {nope}"
    term, _ = run(
        ["1", ":set gold 42", ":give arrow 3", ":goto win", "3", "5"],
        tmp_path,
        game=game,
        debug=True,
    )
    out = term.output
    assert "unknown variable 'nope'" in out
    assert "debug: gold = 42" in out
    assert "Gold 42." in out
    assert "debug: arrow ×3" in out
    assert "You made it." in out
    assert "[:]debug" in out


def test_debug_commands_disabled_without_debug(tmp_path):
    term, _ = run(["1", ":goto win", "q", "5"], tmp_path)
    assert "You made it." not in term.output


def test_state_sink_and_start_state(tmp_path):
    events = []
    game = make_game()
    from cyoa.runtime import Runtime

    rt = Runtime(game)
    state = rt.initial_state()
    rt.enter(state, "bridge")
    term = FakeTerminal(["2", "q", "5"])
    player = Player(game, term, saves=SaveStore(tmp_path), debug=True, state_sink=events.append)
    player.run(state)
    assert events[0]["state"]["scene"] == "bridge"
    assert events[0]["scene_title"] == "Bridge"
    assert events[1]["state"]["scene"] == "start"


def test_fatal_error_on_missing_start(tmp_path):
    game = make_game(start_scene="missing")
    term, _ = run(["1", "", "5"], tmp_path, game=game)
    assert "The game can't continue" in term.output


def test_softlocked_scene_message(tmp_path):
    game = make_game()
    game.scenes[0].choices = []
    term, _ = run(["1", "1", "q", "5"], tmp_path, game=game)
    assert "There's nothing you can do here." in term.output
    assert "Choose a letter in brackets." in term.output


# -- command line ----------------------------------------------------------------------


@pytest.fixture
def game_file(tmp_path):
    path = tmp_path / "test.cyoa.json"
    path.write_text(json.dumps(make_game().to_player_dict()))
    return path


def test_cli_check_ok(game_file, capsys):
    assert main([str(game_file), "--check"]) == 0
    assert "No errors." in capsys.readouterr().out


def test_cli_check_reports_errors(tmp_path, capsys):
    game = make_game()
    game.scenes[0].choices[0].target = "nowhere"
    path = tmp_path / "bad.cyoa.json"
    path.write_text(json.dumps(game.to_player_dict()))
    assert main([str(path), "--check"]) == 1
    out = capsys.readouterr().out
    assert "scene 'start' / choice 'bridge' (target)" in out
    assert "doesn't exist" in out


def test_cli_refuses_games_with_errors(tmp_path, capsys):
    game = make_game(start_scene="")
    path = tmp_path / "bad.cyoa.json"
    path.write_text(json.dumps(game.to_player_dict()))
    assert main([str(path)]) == 2
    assert "can't be played safely" in capsys.readouterr().out


def test_cli_bad_files(tmp_path, capsys):
    bad = tmp_path / "bad.cyoa.json"
    bad.write_text("{not json")
    assert main([str(bad)]) == 2
    assert "not valid JSON" in capsys.readouterr().out
    bad.write_text(json.dumps({"format": 99}))
    assert main([str(bad)]) == 2
    assert "newer version" in capsys.readouterr().out
    bad.write_text(json.dumps({"scenes": "nope"}))
    assert main([str(bad)]) == 2
    assert "invalid fields" in capsys.readouterr().out
    assert main([str(tmp_path / "missing.cyoa.json")]) == 2


def test_cli_messages_are_not_hard_wrapped(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "40")
    deep = tmp_path / ("very_long_folder_name_" * 4)
    deep.mkdir()
    bad = deep / "bad.cyoa.json"
    bad.write_text("{not json")
    assert main([str(bad)]) == 2
    out = capsys.readouterr().out
    assert f"{bad} is not valid JSON" in out
    assert out.count("\n") == 1


def test_cli_finds_single_game_in_folder(game_file, monkeypatch, capsys):
    monkeypatch.chdir(game_file.parent)
    assert main(["--check"]) == 0
