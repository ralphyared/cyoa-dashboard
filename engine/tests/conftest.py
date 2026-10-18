from __future__ import annotations

from typing import Any

import pytest

from cyoa.model import Game, game_from_dict


def make_game(**overrides: Any) -> Game:
    """A tiny game exercising every mechanic. Override any top-level field."""
    data: dict[str, Any] = {
        "id": "test-game",
        "title": "Test Game",
        "version": "1.0",
        "start_scene": "start",
        "settings": {"status_format": "HP {hp}/{max_hp} | Gold {gold}"},
        "variables": [
            {
                "name": "hp",
                "type": "number",
                "initial": 10,
                "min": 0,
                "max": "max_hp",
                "label": "HP",
            },
            {"name": "max_hp", "type": "number", "initial": 10},
            {"name": "gold", "type": "number", "initial": 5, "min": 0, "label": "Gold"},
            {"name": "met_troll", "type": "bool", "initial": False},
        ],
        "items": [
            {"id": "rope", "name": "Rope"},
            {"id": "arrow", "name": "Arrow", "stackable": True},
        ],
        "rules": [
            {"id": "death", "name": "Death", "condition": "hp <= 0", "goto": "dead"},
        ],
        "chapters": [{"id": "ch1", "title": "Chapter 1"}],
        "scenes": [
            {
                "id": "start",
                "title": "Start",
                "chapter": "ch1",
                "text": "You have {gold} gold.",
                "choices": [
                    {"id": "bridge", "text": "Go to the bridge", "target": "bridge"},
                    {
                        "id": "shop",
                        "text": "Buy rope (3 gold)",
                        "target": "start",
                        "condition": "gold >= 3",
                        "when_locked": "show",
                        "effects": 'gold -= 3\ngive("rope")',
                    },
                    {
                        "id": "ask",
                        "text": "Ask about the troll",
                        "target": "start",
                        "once": True,
                        "effects": 'met_troll = true\ngive("arrow", 2)',
                    },
                ],
            },
            {
                "id": "bridge",
                "title": "Bridge",
                "chapter": "ch1",
                "text": "A troll.{if met_troll} You recognize him.{/if}",
                "on_enter": "hp -= 2",
                "choices": [
                    {
                        "id": "climb",
                        "text": "Climb down",
                        "target": "win",
                        "condition": 'has("rope")',
                        "when_locked": "show",
                    },
                    {"id": "fight", "text": "Fight", "target": "bridge", "effects": "hp -= 5"},
                    {"id": "back", "text": "Go back", "target": "start"},
                ],
            },
            {
                "id": "win",
                "title": "Victory",
                "text": "You made it.",
                "ending": {"kind": "victory", "title": "The Climber"},
            },
            {
                "id": "dead",
                "title": "Dead",
                "text": "You died.",
                "ending": {"kind": "death", "title": "Troll food"},
            },
        ],
    }
    data.update(overrides)
    return game_from_dict(data)


@pytest.fixture
def game() -> Game:
    return make_game()
