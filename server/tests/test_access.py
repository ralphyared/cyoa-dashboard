"""Accounts, sharing and permissions: who may do what."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from conftest import PASSWORD, invite, join, scene
from fastapi.routing import APIRoute
from starlette.websockets import WebSocketDisconnect
from test_playtest import read_until

from cyoa_server import (
    auth,
    backups,
    routes_games,
    routes_people,
    routes_players,
    routes_scenes,
    routes_tools,
)
from cyoa_server.app import create_app
from cyoa_server.db import InviteRow, now

ROUTERS = (auth, routes_people, routes_games, routes_scenes, routes_tools, routes_players, backups)

PUBLIC, USER, OWNER, READ, EDIT = "public", "user", "owner", "read", "edit"

# Every API route and who may use it. A new route must be added here (see below).
ROUTES = {
    ("GET", "/api/health"): PUBLIC,
    ("POST", "/api/login"): PUBLIC,
    ("POST", "/api/logout"): PUBLIC,
    ("GET", "/api/me"): PUBLIC,
    ("PATCH", "/api/me"): USER,
    ("POST", "/api/me/password"): USER,
    ("GET", "/api/users"): OWNER,
    ("DELETE", "/api/users/{user_id}"): OWNER,
    ("POST", "/api/users/{user_id}/reset-link"): OWNER,
    ("GET", "/api/games/{game_id}/sharing"): OWNER,
    ("POST", "/api/games/{game_id}/invites"): OWNER,
    ("DELETE", "/api/games/{game_id}/invites/{invite_id}"): OWNER,
    ("PUT", "/api/games/{game_id}/people/{user_id}"): OWNER,
    ("DELETE", "/api/games/{game_id}/people/{user_id}"): OWNER,
    ("GET", "/api/invites/{token}"): PUBLIC,
    ("POST", "/api/invites/{token}/accept"): USER,
    ("POST", "/api/invites/{token}/join"): PUBLIC,
    ("GET", "/api/password-resets/{token}"): PUBLIC,
    ("POST", "/api/password-resets/{token}"): PUBLIC,
    ("GET", "/api/games"): USER,
    ("POST", "/api/games"): OWNER,
    ("POST", "/api/games/import"): OWNER,
    ("GET", "/api/games/{game_id}"): READ,
    ("PATCH", "/api/games/{game_id}"): EDIT,
    ("DELETE", "/api/games/{game_id}"): OWNER,
    ("POST", "/api/games/{game_id}/duplicate"): OWNER,
    ("GET", "/api/games/{game_id}/export"): EDIT,
    ("GET", "/api/trash"): OWNER,
    ("POST", "/api/trash/games/{game_id}/restore"): OWNER,
    ("DELETE", "/api/trash/games/{game_id}"): OWNER,
    ("POST", "/api/games/{game_id}/scenes"): EDIT,
    ("PATCH", "/api/games/{game_id}/scenes/{pk}"): EDIT,
    ("DELETE", "/api/games/{game_id}/scenes/{pk}"): EDIT,
    ("POST", "/api/games/{game_id}/scenes/positions"): EDIT,
    ("POST", "/api/games/{game_id}/scenes/order"): EDIT,
    ("GET", "/api/games/{game_id}/scenes/{pk}/revisions"): READ,
    ("POST", "/api/games/{game_id}/scenes/{pk}/revisions/{revision_id}/restore"): EDIT,
    ("POST", "/api/trash/scenes/{pk}/restore"): OWNER,
    ("DELETE", "/api/trash/scenes/{pk}"): OWNER,
    ("GET", "/api/games/{game_id}/issues"): READ,
    ("POST", "/api/games/{game_id}/check"): READ,
    ("POST", "/api/games/{game_id}/rename"): EDIT,
    ("GET", "/api/games/{game_id}/references"): READ,
    ("GET", "/api/reference"): USER,
    ("GET", "/api/players"): USER,
    ("POST", "/api/players/update"): OWNER,
    ("GET", "/api/games/{game_id}/standalone"): EDIT,
    ("GET", "/api/backups"): OWNER,
    ("POST", "/api/backups"): OWNER,
    ("GET", "/api/backups/{name}"): OWNER,
}
CHECKS = {
    USER: auth.current_user,
    OWNER: auth.require_owner,
    READ: auth.can_read,
    EDIT: auth.can_edit,
}


def _calls(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from _calls(dep)


def test_every_route_checks_permissions(app):
    routers = [app.router] + [module.router for module in ROUTERS]
    found = {}
    for router in routers:
        for route in router.routes:
            if isinstance(route, APIRoute):
                for method in route.methods:
                    found[(method, route.path)] = route
    assert set(found) == set(ROUTES), "classify new routes in ROUTES"
    # ...and no router is missing from ROUTERS
    schema = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert schema == set(ROUTES) - {("GET", "/api/health")}
    for key, need in ROUTES.items():
        calls = set(_calls(found[key].dependant))
        if need == PUBLIC:
            assert auth.current_user not in calls, key
        else:
            assert CHECKS[need] in calls, f"{key} should check {need}"


def _url(path, game, ids):
    values = {
        "game_id": game["id"],
        "pk": scene(game, "start")["pk"],
        "revision_id": 1,
        "invite_id": 999,
        "user_id": ids.get("user_id", 999),
        "token": "nope",
        "name": "manual-20260101-000000.db",
    }
    return path.format(**values)


def _call(client, method, url):
    if method in ("GET", "DELETE"):
        return client.request(method, url)
    return client.request(method, url, json={})


def test_logged_out_people_get_nothing(anon, client, game, browser):
    stranger = browser()
    for (method, path), need in ROUTES.items():
        if need != PUBLIC:
            r = _call(stranger, method, _url(path, game, {}))
            assert r.status_code == 401, (method, path, r.status_code)


def _outcome(r):
    if r.status_code == 404 and r.json().get("detail") == "game not found":
        return "hidden"  # as if the game didn't exist
    if r.status_code == 403:
        return "denied"
    assert r.status_code != 401
    return "allowed"  # past the permission check (it may still fail for other reasons)


EXPECTED = {
    "outsider": {OWNER: "denied", READ: "hidden", EDIT: "hidden"},
    "reader": {OWNER: "denied", READ: "allowed", EDIT: "denied"},
    "editor": {OWNER: "denied", READ: "allowed", EDIT: "allowed"},
}


def test_reader_editor_and_outsider_permissions(client, game, reader, editor, outsider):
    ids = {"user_id": reader.get("/api/me").json()["user"]["id"]}
    people = {"outsider": outsider, "reader": reader, "editor": editor}
    for (method, path), need in ROUTES.items():
        if need in (PUBLIC, USER):
            continue
        url = _url(path, game, ids)
        for who, person in people.items():
            r = _call(person, method, url)
            assert _outcome(r) == EXPECTED[who][need], (who, method, path, r.status_code, r.text)


def test_invite_join_and_shared_list(client, game, browser):
    gid = game["id"]
    token = invite(client, gid, "read", note="for Sam")
    sharing = client.get(f"/api/games/{gid}/sharing").json()
    assert sharing["people"] == []
    assert [(i["level"], i["note"]) for i in sharing["invites"]] == [("read", "for Sam")]

    sam = browser()
    info = sam.get(f"/api/invites/{token}").json()
    assert info == {"game_title": "Test Quest", "level": "read", "user": None}
    join(sam, token, "Sam.W")  # stored lowercase
    assert sam.get("/api/me").json()["user"] == {"id": 2, "username": "sam.w", "owner": False}

    games = sam.get("/api/games").json()
    assert [(g["id"], g["access"]) for g in games] == [(gid, "read")]
    assert sam.get(f"/api/games/{gid}").json()["access"] == "read"

    # the link is used up
    assert browser().get(f"/api/invites/{token}").status_code == 404
    sharing = client.get(f"/api/games/{gid}/sharing").json()
    assert sharing["invites"] == []
    assert [(p["username"], p["level"]) for p in sharing["people"]] == [("sam.w", "read")]
    owner_games = client.get("/api/games").json()
    assert owner_games[0]["access"] == "owner" and owner_games[0]["shared_with"] == 1


def test_join_checks_names_and_passwords(client, game, browser):
    token = invite(client, game["id"])
    person = browser()
    url = f"/api/invites/{token}/join"
    assert person.post(url, json={"username": "a", "password": "longenough"}).status_code == 422
    assert (
        person.post(url, json={"username": "has space", "password": "longenough"}).status_code
        == 422
    )
    assert person.post(url, json={"username": "OWNER", "password": "longenough"}).status_code == 409
    assert person.post(url, json={"username": "sam", "password": "short"}).status_code == 422
    # nothing above used the link up
    join(person, token, "sam")


def test_logged_in_person_accepts_another_invite(client, game, reader):
    second = client.post("/api/games", json={"title": "Second"}).json()
    token = invite(client, second["id"], "edit")
    info = reader.get(f"/api/invites/{token}").json()
    assert info["user"]["username"] == "riley"
    assert reader.post(f"/api/invites/{token}/accept").json() == {"game_id": second["id"]}
    assert {g["title"]: g["access"] for g in reader.get("/api/games").json()} == {
        "Test Quest": "read",
        "Second": "edit",
    }
    # the owner already has everything
    token = invite(client, second["id"])
    assert client.post(f"/api/invites/{token}/accept").status_code == 409


def test_invite_links_expire_and_can_be_cancelled(app, client, game, browser):
    gid = game["id"]
    token = invite(client, gid)
    invite_id = client.get(f"/api/games/{gid}/sharing").json()["invites"][0]["id"]
    assert client.delete(f"/api/games/{gid}/invites/{invite_id}").json() == {"ok": True}
    assert browser().get(f"/api/invites/{token}").status_code == 404

    token = invite(client, gid)
    with app.state.db.new_session() as db:
        for row in db.query(InviteRow):
            row.expires_at = now() - timedelta(minutes=1)
        db.commit()
    r = browser().post(
        f"/api/invites/{token}/join", json={"username": "late", "password": "longenough"}
    )
    assert r.status_code == 404
    assert "expired" in r.json()["detail"]
    # expired links are cleaned up when the owner looks at the sharing list
    assert client.get(f"/api/games/{gid}/sharing").json()["invites"] == []


def test_invites_to_trashed_games_stop_working(client, game, browser):
    token = invite(client, game["id"])
    client.delete(f"/api/games/{game['id']}")
    assert browser().get(f"/api/invites/{token}").status_code == 404


def test_change_and_remove_access(client, game, reader):
    gid = game["id"]
    uid = reader.get("/api/me").json()["user"]["id"]
    start = scene(game, "start")
    edit = {"title": "Changed by Riley"}
    assert reader.patch(f"/api/games/{gid}/scenes/{start['pk']}", json=edit).status_code == 403

    assert client.put(f"/api/games/{gid}/people/{uid}", json={"level": "edit"}).json() == {
        "ok": True
    }
    assert reader.patch(f"/api/games/{gid}/scenes/{start['pk']}", json=edit).status_code == 200
    assert (
        client.put(f"/api/games/{gid}/people/{uid}", json={"level": "comment"}).status_code == 422
    )
    assert client.put(f"/api/games/{gid}/people/1", json={"level": "read"}).status_code == 400

    assert client.delete(f"/api/games/{gid}/people/{uid}").json() == {"ok": True}
    assert reader.get(f"/api/games/{gid}").status_code == 404
    assert reader.get("/api/games").json() == []
    assert client.delete(f"/api/games/{gid}/people/{uid}").status_code == 404


def test_guests_dont_see_trashed_games(client, game, editor):
    client.delete(f"/api/games/{game['id']}")
    assert editor.get("/api/games").json() == []
    assert editor.get(f"/api/games/{game['id']}").status_code == 404


def test_guest_login_and_password_change(client, game, browser, editor):
    other = browser()
    bad = other.post("/api/login", json={"username": "eden", "password": "wrong-pass"})
    assert bad.status_code == 401
    assert (
        other.post("/api/login", json={"username": "Eden", "password": "secret-pass"}).status_code
        == 200
    )
    assert other.get("/api/me").json()["user"]["username"] == "eden"
    assert other.post("/api/login", json={"username": "nobody", "password": "x"}).status_code == 401

    change = {"current": "nope", "new": "brand-new-pass"}
    assert editor.post("/api/me/password", json=change).status_code == 400
    change["current"] = "secret-pass"
    assert editor.post("/api/me/password", json={**change, "new": "short"}).status_code == 422
    assert editor.post("/api/me/password", json=change).json() == {"ok": True}
    # other devices are logged out; this one isn't
    assert other.get("/api/me").json() == {"authenticated": False}
    assert editor.get("/api/me").json()["authenticated"] is True
    fresh = browser()
    assert (
        fresh.post(
            "/api/login", json={"username": "eden", "password": "brand-new-pass"}
        ).status_code
        == 200
    )

    # the owner's password lives in .env
    owner_change = {"current": PASSWORD, "new": "whatever-123"}
    assert client.post("/api/me/password", json=owner_change).status_code == 400


def test_rename_account(client, editor, reader):
    assert editor.patch("/api/me", json={"username": "Eden2"}).json()["username"] == "eden2"
    assert editor.patch("/api/me", json={"username": "riley"}).status_code == 409
    assert editor.patch("/api/me", json={"username": "x"}).status_code == 422
    assert client.patch("/api/me", json={"username": "Author"}).json() == {
        "id": 1,
        "username": "author",
        "owner": True,
    }
    # the owner can still log in without a username
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 200
    assert (
        client.post("/api/login", json={"username": "author", "password": PASSWORD}).status_code
        == 200
    )


def test_people_list_reset_link_and_removal(client, game, browser, editor):
    people = client.get("/api/users").json()
    assert [(p["username"], p["owner"]) for p in people] == [("owner", True), ("eden", False)]
    eden = people[1]
    assert [(g["title"], g["level"]) for g in eden["games"]] == [("Test Quest", "edit")]
    assert eden["last_login_at"] is not None

    assert client.post("/api/users/1/reset-link").status_code == 400
    link = client.post(f"/api/users/{eden['id']}/reset-link").json()
    assert link["username"] == "eden"
    person = browser()
    url = f"/api/password-resets/{link['token']}"
    assert person.get(url).json() == {"username": "eden"}
    assert person.post(url, json={"password": "short"}).status_code == 422
    assert person.post(url, json={"password": "reset-password"}).json() == {"ok": True}
    assert person.get("/api/me").json()["user"]["username"] == "eden"
    assert editor.get("/api/me").json() == {"authenticated": False}  # logged out elsewhere
    assert person.post(url, json={"password": "again-password"}).status_code == 404  # used up

    assert client.delete("/api/users/1").status_code == 400
    assert client.delete(f"/api/users/{eden['id']}").json() == {"ok": True}
    assert person.get("/api/me").json() == {"authenticated": False}
    r = browser().post("/api/login", json={"username": "eden", "password": "reset-password"})
    assert r.status_code == 401
    assert client.get(f"/api/games/{game['id']}/sharing").json()["people"] == []


def test_history_records_who_changed_what(client, game, editor):
    gid = game["id"]
    start = scene(game, "start")
    url = f"/api/games/{gid}/scenes/{start['pk']}"
    client.patch(url, json={"text": "owner edit"})
    editor.patch(url, json={"text": "editor edit"})
    editor.patch(url, json={"text": "editor edit 2"})  # coalesces with the editor's own edit
    revisions = editor.get(f"{url}/revisions").json()
    assert [(r["by"], r["snapshot"]["text"]) for r in revisions[:2]] == [
        ("eden", "editor edit 2"),
        ("owner", "owner edit"),
    ]


def test_playtest_permissions(client, game, reader, outsider):
    gid = game["id"]
    with reader.websocket_connect(f"/api/games/{gid}/playtest") as ws:
        ws.send_json({"type": "start", "cols": 80, "rows": 24})
        read_until(ws, lambda out, m: "New Game" in out)
        # one at a time for guests
        with reader.websocket_connect(f"/api/games/{gid}/playtest") as second:
            message = second.receive_json()
            assert message == {
                "type": "error",
                "message": "you already have a playtest open; close it first",
            }
        # the owner isn't limited that way
        with client.websocket_connect(f"/api/games/{gid}/playtest") as owners:
            owners.send_json({"type": "start", "cols": 80, "rows": 24})
            read_until(owners, lambda out, m: "New Game" in out)
    with (
        pytest.raises(WebSocketDisconnect) as info,
        outsider.websocket_connect(f"/api/games/{gid}/playtest") as ws,
    ):
        ws.receive_json()
    assert info.value.code == 4404


def test_databases_from_before_accounts_are_upgraded(config):
    """Old sessions are dropped (log in again); history gains an author column."""
    config.data_dir.mkdir(parents=True)
    conn = sqlite3.connect(config.db_path)
    conn.executescript(
        """
        CREATE TABLE sessions (token_hash VARCHAR PRIMARY KEY, created_at DATETIME,
                               expires_at DATETIME);
        INSERT INTO sessions VALUES ('abc', '2026-01-01', '2099-01-01');
        CREATE TABLE revisions (id INTEGER PRIMARY KEY, scene_pk INTEGER, reason VARCHAR,
                                snapshot JSON, created_at DATETIME, updated_at DATETIME);
        INSERT INTO revisions VALUES (1, 1, 'edit', '{}', '2026-01-01', '2026-01-01');
        """
    )
    conn.close()
    create_app(config, run_backups=False)
    conn = sqlite3.connect(config.db_path)
    assert conn.execute("SELECT count(*) FROM sessions").fetchone() == (0,)
    assert conn.execute("SELECT user_id FROM revisions").fetchall() == [(None,)]
    assert conn.execute("SELECT username, is_owner FROM users").fetchall() == [("owner", 1)]
    conn.close()
