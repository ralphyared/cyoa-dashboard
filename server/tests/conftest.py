from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cyoa_server.app import create_app
from cyoa_server.auth import limiter
from cyoa_server.config import Config

PASSWORD = "correct horse"


@pytest.fixture
def config(tmp_path):
    return Config(password=PASSWORD, data_dir=tmp_path / "data", secure_cookies=False)


@pytest.fixture
def anon(config):
    limiter.failures.clear()
    with TestClient(create_app(config, run_backups=False)) as client:
        yield client


@pytest.fixture
def client(anon):
    response = anon.post("/api/login", json={"password": PASSWORD})
    assert response.status_code == 200
    return anon


@pytest.fixture
def game(client):
    """A new game with a couple of variables, an item and three linked scenes."""
    game = client.post("/api/games", json={"title": "Test Quest"}).json()
    gid = game["id"]
    r = client.patch(
        f"/api/games/{gid}",
        json={
            "variables": [
                {"name": "hp", "type": "number", "initial": 10, "min": 0, "label": "HP"},
                {"name": "gold", "type": "number", "initial": 5, "label": "Gold"},
            ],
            "items": [{"id": "rope", "name": "Rope"}],
            "settings": {"status_format": "HP {hp} | Gold {gold}"},
        },
    )
    assert r.status_code == 200, r.text
    start = game["scenes"][0]
    bridge = client.post(
        f"/api/games/{gid}/scenes",
        json={
            "title": "The Bridge",
            "text": "A troll blocks the way. You have {gold} gold.",
            "choices": [
                {
                    "text": "Climb down",
                    "target": "end",
                    "condition": 'has("rope")',
                    "when_locked": "show",
                },
                {"text": "Go back", "target": "start"},
            ],
        },
    ).json()
    client.post(
        f"/api/games/{gid}/scenes",
        json={
            "id": "end",
            "title": "The End",
            "text": "You made it.",
            "ending": {"kind": "victory", "title": "Climber"},
        },
    )
    r = client.patch(
        f"/api/games/{gid}/scenes/{start['pk']}",
        json={
            "text": "You stand at the start.",
            "choices": [
                {"text": "To the bridge", "target": bridge["id"]},
                {
                    "text": "Buy rope",
                    "target": "start",
                    "condition": "gold >= 3",
                    "effects": 'gold -= 3\ngive("rope")',
                    "once": True,
                },
            ],
        },
    )
    assert r.status_code == 200, r.text
    return client.get(f"/api/games/{gid}").json()


def scene(game_data, scene_id):
    return next(s for s in game_data["scenes"] if s["id"] == scene_id)
