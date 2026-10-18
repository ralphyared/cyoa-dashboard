from __future__ import annotations

import json
import sys

import pytest

from cyoa.player.cli import main
from cyoa.standalone import MAGIC, attach, read_attached

from .conftest import make_game


def test_attach_and_read_back(tmp_path):
    exe = tmp_path / "player.exe"
    game = json.dumps(make_game().to_player_dict()).encode()
    exe.write_bytes(attach(b"\x7fELF fake player bytes" * 100, game))
    assert read_attached(exe) == game


def test_read_attached_ignores_plain_files(tmp_path):
    plain = tmp_path / "player"
    plain.write_bytes(b"just a program")
    assert read_attached(plain) is None
    corrupt = tmp_path / "corrupt"
    corrupt.write_bytes(b"x" + MAGIC + (10**9).to_bytes(8, "little"))
    assert read_attached(corrupt) is None
    assert read_attached(tmp_path / "missing") is None


def test_attach_refuses_bootloader_marker():
    with pytest.raises(ValueError):
        attach(b"player", b"MEI\x0c\x0b\x0a\x0b\x0e")


def test_standalone_player_plays_its_attached_game(tmp_path, monkeypatch, capsys):
    exe = tmp_path / "The Crossing.exe"
    exe.write_bytes(attach(b"player", json.dumps(make_game().to_player_dict()).encode()))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.chdir(tmp_path)
    assert main(["--check"]) == 0
    assert "No errors." in capsys.readouterr().out


def test_standalone_player_reports_broken_attachment(tmp_path, monkeypatch, capsys):
    exe = tmp_path / "broken.exe"
    exe.write_bytes(attach(b"player", b"{not json"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert main(["--check"]) == 2
    assert "the built-in game is not valid JSON" in capsys.readouterr().out
