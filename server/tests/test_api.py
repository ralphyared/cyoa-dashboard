from __future__ import annotations

import json

from conftest import PASSWORD, scene


def test_requires_login(anon):
    assert anon.get("/api/games").status_code == 401
    assert anon.get("/api/me").json() == {"authenticated": False}
    assert anon.get("/api/health").json() == {"ok": True}


def test_login_logout(anon):
    assert anon.post("/api/login", json={"password": "nope"}).status_code == 401
    assert anon.post("/api/login", json={"password": PASSWORD}).status_code == 200
    assert anon.get("/api/me").json() == {"authenticated": True}
    assert anon.get("/api/games").status_code == 200
    anon.post("/api/logout")
    assert anon.get("/api/games").status_code == 401


def test_login_rate_limit(anon):
    for _ in range(5):
        assert anon.post("/api/login", json={"password": "nope"}).status_code == 401
    assert anon.post("/api/login", json={"password": PASSWORD}).status_code == 429


def test_global_login_limit(anon, monkeypatch):
    from cyoa_server import auth

    monkeypatch.setattr(auth, "MAX_GLOBAL_FAILURES", 3)
    for _ in range(3):
        auth.limiter.fail(auth.GLOBAL)
    assert anon.post("/api/login", json={"password": PASSWORD}).status_code == 429


def test_cross_site_writes_refused(client):
    r = client.post("/api/games", json={"title": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/games", json={"title": "x"}, headers={"Origin": "http://testserver"})
    assert r.status_code == 201


def test_create_and_list_games(client):
    created = client.post("/api/games", json={"title": "My Game"}).json()
    assert created["meta"]["title"] == "My Game"
    assert created["meta"]["start_scene"] == "start"
    assert [s["id"] for s in created["scenes"]] == ["start"]
    listing = client.get("/api/games").json()
    assert listing[0]["id"] == created["id"]
    assert listing[0]["scenes"] == 1


def test_update_meta_validation_and_conflicts(client, game):
    gid = game["id"]
    r = client.patch(f"/api/games/{gid}", json={"variables": [{"name": "x", "type": "colour"}]})
    assert r.status_code == 422
    r = client.patch(f"/api/games/{gid}", json={"bogus": 1})
    assert r.status_code == 422
    rev = game["rev"]
    r = client.patch(f"/api/games/{gid}", json={"title": "Renamed", "rev": rev})
    assert r.status_code == 200 and r.json()["rev"] == rev + 1
    r = client.patch(f"/api/games/{gid}", json={"title": "Stale", "rev": rev})
    assert r.status_code == 409


def test_scene_create_ids(client, game):
    gid = game["id"]
    a = client.post(f"/api/games/{gid}/scenes", json={"title": "The Bridge"}).json()
    assert a["id"] == "the_bridge_2"
    b = client.post(f"/api/games/{gid}/scenes", json={"title": "Café — Night!"}).json()
    assert b["id"] == "cafe_night"
    assert client.post(f"/api/games/{gid}/scenes", json={"id": "Bad Id"}).status_code == 422
    assert client.post(f"/api/games/{gid}/scenes", json={"id": "end"}).status_code == 409
    assert client.post(f"/api/games/{gid}/scenes", json={"oops": 1}).status_code == 422


def test_choice_ids_are_assigned(game):
    choices = scene(game, "start")["choices"]
    assert all(c["id"] for c in choices)
    assert len({c["id"] for c in choices}) == 2


def test_scene_update_and_conflict(client, game):
    gid = game["id"]
    start = scene(game, "start")
    r = client.patch(
        f"/api/games/{gid}/scenes/{start['pk']}", json={"text": "New text", "rev": start["rev"]}
    )
    assert r.status_code == 200
    updated = r.json()["scene"]
    assert updated["text"] == "New text" and updated["rev"] == start["rev"] + 1
    r = client.patch(
        f"/api/games/{gid}/scenes/{start['pk']}", json={"text": "Stale", "rev": start["rev"]}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["scene"]["text"] == "New text"


def test_rename_scene_updates_references(client, game):
    gid = game["id"]
    bridge = scene(game, "the_bridge")
    start = scene(game, "start")
    client.patch(
        f"/api/games/{gid}/scenes/{bridge['pk']}",
        json={"text": '{if visited("start")}Back again.{/if}'},
    )
    r = client.patch(f"/api/games/{gid}/scenes/{start['pk']}", json={"id": "camp"})
    assert r.status_code == 200
    renamed = r.json()["game"]
    assert renamed["meta"]["start_scene"] == "camp"
    assert scene(renamed, "camp")["pk"] == start["pk"]
    bridge = scene(renamed, "the_bridge")
    assert bridge["choices"][1]["target"] == "camp"
    assert bridge["text"] == '{if visited("camp")}Back again.{/if}'
    r = client.patch(f"/api/games/{gid}/scenes/{start['pk']}", json={"id": "end"})
    assert r.status_code == 409


def test_revisions_coalesce_and_restore(client, game):
    gid = game["id"]
    start = scene(game, "start")
    url = f"/api/games/{gid}/scenes/{start['pk']}"
    client.patch(url, json={"text": "one"})
    client.patch(url, json={"text": "two"})
    revisions = client.get(f"{url}/revisions").json()
    assert [r["reason"] for r in revisions] == ["edit", "created"]
    assert revisions[0]["snapshot"]["text"] == "two"
    created = revisions[1]
    restored = client.post(f"{url}/revisions/{created['id']}/restore").json()
    assert restored["text"] == ""
    assert client.get(f"{url}/revisions").json()[0]["reason"] == "restored"


def test_delete_and_restore_scene(client, game):
    gid = game["id"]
    end = scene(game, "end")
    assert client.delete(f"/api/games/{gid}/scenes/{end['pk']}").status_code == 200
    assert "end" not in [s["id"] for s in client.get(f"/api/games/{gid}").json()["scenes"]]
    trash = client.get("/api/trash").json()
    assert trash["scenes"][0]["id"] == "end"
    client.post(f"/api/games/{gid}/scenes", json={"id": "end"})  # take the slug meanwhile
    restored = client.post(f"/api/trash/scenes/{end['pk']}/restore").json()
    assert restored["id"] == "end_restored"


def test_issues_and_stats(client, game):
    gid = game["id"]
    data = client.get(f"/api/games/{gid}/issues").json()
    assert data["issues"] == []
    assert data["stats"]["scenes"] == 3
    bridge = scene(game, "the_bridge")
    client.patch(
        f"/api/games/{gid}/scenes/{bridge['pk']}",
        json={"choices": [{"text": "Jump", "target": "nowhere"}]},
    )
    codes = {i["code"] for i in client.get(f"/api/games/{gid}/issues").json()["issues"]}
    assert "missing_target" in codes


def test_check_endpoint(client, game):
    gid = game["id"]
    r = client.post(
        f"/api/games/{gid}/check", json={"source": 'gold >= 3 and has("rope")', "mode": "condition"}
    ).json()
    assert r["errors"] == []
    assert r["ast"]["op"] == "and"
    assert r["hint"] == "Gold ≥ 3, Rope"
    r = client.post(f"/api/games/{gid}/check", json={"source": "goldd > 1", "mode": "condition"})
    assert r.json()["errors"][0]["message"] == "unknown variable 'goldd'"
    r = client.post(f"/api/games/{gid}/check", json={"source": "gold -=", "mode": "effects"})
    assert "missing value" in r.json()["errors"][0]["message"]
    r = client.post(
        f"/api/games/{gid}/check", json={"source": "Hi {goldd}!", "mode": "markup"}
    ).json()
    assert (r["errors"][0]["start"], r["errors"][0]["end"]) == (4, 9)


def test_rename_variable_and_references(client, game):
    gid = game["id"]
    refs = client.get(
        f"/api/games/{gid}/references", params={"kind": "variable", "name": "gold"}
    ).json()["references"]
    assert {r["field"] for r in refs} == {"status_format", "text", "condition", "effects"}
    r = client.post(
        f"/api/games/{gid}/rename", json={"kind": "variable", "old": "gold", "new": "coins"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["settings"]["status_format"] == "HP {hp} | Gold {coins}"
    assert scene(data, "start")["choices"][1]["effects"] == 'coins -= 3\ngive("rope")'
    assert (
        client.post(
            f"/api/games/{gid}/rename", json={"kind": "variable", "old": "coins", "new": "hp"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/games/{gid}/rename", json={"kind": "item", "old": "nope", "new": "x"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/games/{gid}/rename", json={"kind": "item", "old": "rope", "new": "Bad"}
        ).status_code
        == 422
    )


def test_export_import_roundtrip(client, game):
    gid = game["id"]
    start = scene(game, "start")
    client.patch(f"/api/games/{gid}/scenes/{start['pk']}", json={"notes": "secret note"})
    r = client.get(f"/api/games/{gid}/export", params={"format": "player"})
    assert r.status_code == 200
    assert "test_quest.cyoa.json" in r.headers["content-disposition"]
    player = json.loads(r.content)
    assert "notes" not in player["scenes"][0]
    project = json.loads(
        client.get(f"/api/games/{gid}/export", params={"format": "project"}).content
    )
    assert project["scenes"][0]["notes"] == "secret note"
    imported = client.post("/api/games/import", json=project).json()
    assert imported["id"] != gid  # id already taken, so a new one is assigned
    assert scene(imported, "start")["notes"] == "secret note"
    assert len(client.get("/api/games").json()) == 2


def test_export_blocked_by_errors(client, game):
    gid = game["id"]
    client.patch(f"/api/games/{gid}", json={"start_scene": "missing"})
    r = client.get(f"/api/games/{gid}/export")
    assert r.status_code == 409
    assert r.json()["detail"]["issues"][0]["code"] == "missing_start_scene"
    assert client.get(f"/api/games/{gid}/export", params={"format": "project"}).status_code == 200


def test_import_rejects_bad_files(client):
    assert client.post("/api/games/import", json={"format": 99}).status_code == 422
    bad = {"start_scene": "a", "scenes": [{"id": "Bad Id"}]}
    assert client.post("/api/games/import", json=bad).status_code == 422


def test_duplicate_and_trash_games(client, game):
    gid = game["id"]
    copy = client.post(f"/api/games/{gid}/duplicate").json()
    assert copy["meta"]["title"] == "Test Quest (copy)"
    assert len(copy["scenes"]) == 3
    client.delete(f"/api/games/{gid}")
    assert client.get(f"/api/games/{gid}").status_code == 404
    assert [g["id"] for g in client.get("/api/trash").json()["games"]] == [gid]
    client.post(f"/api/trash/games/{gid}/restore")
    assert client.get(f"/api/games/{gid}").status_code == 200
    client.delete(f"/api/games/{gid}")
    assert client.delete(f"/api/trash/games/{gid}").status_code == 200
    assert client.get("/api/trash").json()["games"] == []


def test_positions_and_order(client, game):
    gid = game["id"]
    pks = [s["pk"] for s in game["scenes"]]
    start = scene(game, "start")
    r = client.post(
        f"/api/games/{gid}/scenes/positions", json={"positions": {str(start["pk"]): [10.25, 20]}}
    )
    assert r.status_code == 200
    client.post(f"/api/games/{gid}/scenes/order", json={"order": list(reversed(pks))})
    data = client.get(f"/api/games/{gid}").json()
    assert [s["pk"] for s in data["scenes"]] == list(reversed(pks))
    moved = scene(data, "start")
    assert moved["position"] == [10.2, 20.0] or moved["position"] == [10.3, 20.0]
    assert moved["rev"] == start["rev"]  # layout changes aren't edits


def test_backups(client):
    created = client.post("/api/backups").json()
    assert created["kind"] == "manual"
    listing = client.get("/api/backups").json()
    assert listing[0]["name"] == created["name"]
    r = client.get(f"/api/backups/{created['name']}")
    assert r.status_code == 200 and r.content[:15] == b"SQLite format 3"
    assert client.get("/api/backups/../../etc/passwd").status_code == 404
    assert client.get("/api/backups/nope.db").status_code == 404


def test_language_reference(client):
    data = client.get("/api/reference").json()
    assert "has" in {f["name"] for f in data["functions"]}
    assert "red" in data["colors"]


def test_check_markup_with_changes(client, game):
    gid = game["id"]
    r = client.post(
        f"/api/games/{gid}/check", json={"source": "Ouch.{gold -= 1}{goldd = 2}", "mode": "markup"}
    ).json()
    [error] = r["errors"]
    assert error["message"] == "unknown variable 'goldd'"
    assert "Ouch.{gold -= 1}{goldd = 2}"[error["start"] : error["end"]] == "goldd"
