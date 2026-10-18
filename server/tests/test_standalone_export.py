from __future__ import annotations

import io
import json
import tarfile
import zipfile

import pytest

from cyoa.standalone import read_attached
from cyoa_server import players as players_module
from cyoa_server.players import PLATFORMS, content_disposition, safe_filename

FAKE_PLAYER = b"\x7fELF-fake-player-" * 64


@pytest.fixture
def fake_github(monkeypatch):
    """Pretend GitHub has a player release with every platform's build."""
    calls = {"downloads": 0}
    release = {
        "tag_name": "player-v1.0.0",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": p.asset,
                "size": len(FAKE_PLAYER),
                "browser_download_url": f"https://x/{p.asset}",
            }
            for p in PLATFORMS.values()
        ],
    }
    releases = [{"tag_name": "v0.1", "assets": []}, release]

    def fake_json(url, timeout=20):
        assert "api.github.com/repos/ralphyared/cyoa-dashboard/releases" in url
        return releases

    def fake_download(url, target, timeout=120):
        calls["downloads"] += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(FAKE_PLAYER)

    monkeypatch.setattr(players_module, "_get_json", fake_json)
    monkeypatch.setattr(players_module, "_download", fake_download)
    return calls


def download(client, gid, platform):
    return client.get(f"/api/games/{gid}/standalone", params={"platform": platform})


def test_windows_export_is_one_executable(client, game, fake_github, tmp_path):
    r = download(client, game["id"], "windows")
    assert r.status_code == 200, r.text
    assert "Test Quest.exe" in r.headers["content-disposition"]
    assert r.content.startswith(FAKE_PLAYER)
    exe = tmp_path / "game.exe"
    exe.write_bytes(r.content)
    attached = json.loads(read_attached(exe))
    assert attached["title"] == "Test Quest"
    assert "notes" not in attached["scenes"][0]
    # the builds are kept: a second export doesn't download again
    download(client, game["id"], "windows")
    assert fake_github["downloads"] == len(PLATFORMS)


def test_linux_export_keeps_the_executable_bit(client, game, fake_github, tmp_path):
    r = download(client, game["id"], "linux")
    assert r.status_code == 200
    assert "Test Quest-linux.tar.gz" in r.headers["content-disposition"]
    with tarfile.open(fileobj=io.BytesIO(r.content)) as tar:
        member = tar.getmember("Test Quest")
        assert member.mode == 0o755
        program = tar.extractfile(member).read()
    path = tmp_path / "program"
    path.write_bytes(program)
    assert json.loads(read_attached(path))["title"] == "Test Quest"


def test_mac_export_is_a_zip_with_the_untouched_player(client, game, fake_github):
    r = download(client, game["id"], "macos-arm64")
    assert r.status_code == 200
    assert "Test Quest-mac.zip" in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
        assert names == {
            "Test Quest/Test Quest",
            "Test Quest/test_quest.cyoa.json",
            "Test Quest/How to play.txt",
        }
        assert zf.read("Test Quest/Test Quest") == FAKE_PLAYER
        assert (zf.getinfo("Test Quest/Test Quest").external_attr >> 16) & 0o111
        assert json.loads(zf.read("Test Quest/test_quest.cyoa.json"))["title"] == "Test Quest"
        assert "Open Anyway" in zf.read("Test Quest/How to play.txt").decode()


def test_export_blocked_by_errors(client, game, fake_github):
    client.patch(f"/api/games/{game['id']}", json={"start_scene": "missing"})
    r = download(client, game["id"], "windows")
    assert r.status_code == 409
    assert r.json()["detail"]["issues"][0]["code"] == "missing_start_scene"


def test_no_release_yet(client, game, monkeypatch):
    monkeypatch.setattr(players_module, "_get_json", lambda url, timeout=20: [])
    r = download(client, game["id"], "windows")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "no_player"
    assert "player-v" in r.json()["detail"]["message"]


def test_github_unreachable(client, game, monkeypatch):
    def boom(url, timeout=20):
        raise OSError("network is down")

    monkeypatch.setattr(players_module, "_get_json", boom)
    r = download(client, game["id"], "linux")
    assert r.status_code == 409
    assert "network is down" in r.json()["detail"]["message"]
    assert client.post("/api/players/update").status_code == 502


def test_player_status_and_update(client, fake_github):
    status = client.get("/api/players").json()
    assert status["version"] is None
    assert not any(p["available"] for p in status["platforms"])
    status = client.post("/api/players/update").json()
    assert status["version"] == "player-v1.0.0"
    assert all(p["available"] for p in status["platforms"])


def test_unknown_platform(client, game):
    assert download(client, game["id"], "amiga").status_code == 422


@pytest.mark.parametrize(
    ("title", "name"),
    [
        ("The Crossing", "The Crossing"),
        ('A/B: "C"?', "A B C"),
        ("   ", "game"),
        ("Ünïcödé Tale", "Ünïcödé Tale"),
    ],
)
def test_safe_filename(title, name):
    assert safe_filename(title) == name


def test_content_disposition_handles_unicode():
    header = content_disposition("Ünïcödé Tale.exe")
    assert 'filename="_n_c_d_ Tale.exe"' in header
    assert "filename*=UTF-8''%C3%9Cn%C3%AFc%C3%B6d%C3%A9%20Tale.exe" in header
