from __future__ import annotations

import time

import pytest
from conftest import scene
from starlette.websockets import WebSocketDisconnect


def read_until(ws, predicate, timeout=15.0):
    """Collect messages until ``predicate(output_so_far, message)`` is true."""
    output = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = ws.receive_json()
        if message["type"] == "output":
            output += message["data"]
        if predicate(output, message):
            return output, message
    raise AssertionError(f"timed out; output so far:\n{output}")


def test_playtest_from_scene_with_live_state(client, game):
    gid = game["id"]
    with client.websocket_connect(f"/api/games/{gid}/playtest") as ws:
        ws.send_json({"type": "start", "cols": 90, "rows": 30, "scene": "the_bridge"})
        output, state = read_until(ws, lambda out, m: m["type"] == "state")
        assert state["state"]["scene"] == "the_bridge"
        assert state["scene_title"] == "The Bridge"
        output, _ = read_until(ws, lambda out, m: "Go back" in out)
        assert "You have 5 gold." in output
        assert "Requires: Rope" in output

        # choose "Go back" (the only enabled choice is number 1)
        ws.send_json({"type": "input", "data": "1\r"})
        _, state = read_until(
            ws, lambda out, m: m["type"] == "state" and m["state"]["scene"] == "start"
        )

        # change a variable from the side panel: the player restarts with it
        ws.send_json({"type": "set_var", "name": "gold", "value": "42"})
        _, state = read_until(ws, lambda out, m: m["type"] == "state")
        assert state["state"]["vars"]["gold"] == 42
        assert state["state"]["scene"] == "start"

        ws.send_json({"type": "items", "item": "rope", "amount": 1})
        _, state = read_until(ws, lambda out, m: m["type"] == "state")
        assert state["state"]["inventory"] == {"rope": 1}

        # edit the scene, then reload: same place, new text
        start = scene(game, "start")
        client.patch(f"/api/games/{gid}/scenes/{start['pk']}", json={"text": "Edited text!"})
        ws.send_json({"type": "reload"})
        output, _ = read_until(ws, lambda out, m: "Edited text!" in out)

        ws.send_json({"type": "goto", "scene": "end"})
        output, _ = read_until(ws, lambda out, m: "THE END" in out)
        assert "You made it." in output

        ws.send_json({"type": "set_var", "name": "nope", "value": "1"})
        _, error = read_until(ws, lambda out, m: m["type"] == "error")
        assert "unknown variable" in error["message"]


def test_playtest_title_screen_and_exit(client, game):
    gid = game["id"]
    with client.websocket_connect(f"/api/games/{gid}/playtest") as ws:
        ws.send_json({"type": "start", "cols": 80, "rows": 24})
        output, _ = read_until(ws, lambda out, m: "New Game" in out)
        assert "Test Quest" in output
        ws.send_json({"type": "input", "data": "3\r"})  # Quit
        _, message = read_until(ws, lambda out, m: m["type"] == "exit")
        assert message["code"] == 0


def test_playtest_requires_login(anon, client, game):
    gid = game["id"]
    anon.post("/api/logout")
    with (
        pytest.raises(WebSocketDisconnect) as info,
        anon.websocket_connect(f"/api/games/{gid}/playtest") as ws,
    ):
        ws.receive_json()
    assert info.value.code == 4401


def test_playtest_rejects_other_origins(client, game):
    with (
        pytest.raises(WebSocketDisconnect) as info,
        client.websocket_connect(
            f"/api/games/{game['id']}/playtest", headers={"Origin": "https://evil.example"}
        ) as ws,
    ):
        ws.receive_json()
    assert info.value.code == 4401
