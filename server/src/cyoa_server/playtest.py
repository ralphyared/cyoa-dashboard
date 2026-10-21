"""In-browser playtesting: the real terminal player, run in a pseudo-terminal.

Protocol (JSON text frames).

Browser → server:
    {"type": "start", "cols": 80, "rows": 24, "scene": "id"?, "state": {...}?}
    {"type": "input", "data": "..."}             keystrokes from xterm.js
    {"type": "resize", "cols": 100, "rows": 30}
    {"type": "reload"}                           latest edits, same position and state
    {"type": "goto", "scene": "id"}              jump (runs the scene's on-enter effects)
    {"type": "set_var", "name": "hp", "value": "5"}
    {"type": "items", "item": "rope", "amount": 1}   negative amounts take items away

Server → browser:
    {"type": "output", "data": "..."}
    {"type": "state", "state": {...}, "scene_title": "...", "problems": [...]}
    {"type": "exit", "code": 0}
    {"type": "error", "message": "..."}

With neither ``scene`` nor ``state``, the player opens at its title screen.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import fcntl
import json
import logging
import os
import pty
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cyoa.runtime import GameError, GameState, Runtime

from . import store
from .auth import access_to, websocket_user
from .config import Config

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["playtest"])
GUEST_PLAYTESTS = 1  # at a time, per person; the owner is limited only by the overall cap


def _clamp_size(cols: Any, rows: Any) -> tuple[int, int]:
    try:
        return max(20, min(int(cols), 400)), max(5, min(int(rows), 200))
    except (TypeError, ValueError):
        return 80, 24


class PlayerProcess:
    """One run of the terminal player attached to a pseudo-terminal."""

    def __init__(
        self,
        workdir: Path,
        game: dict[str, Any],
        cols: int,
        rows: int,
        scene: str | None,
        state: dict[str, Any] | None,
    ) -> None:
        self.workdir = workdir
        game_path = workdir / "game.cyoa.json"
        game_path.write_text(json.dumps(game), encoding="utf-8")
        args = [
            sys.executable,
            "-m",
            "cyoa",
            str(game_path),
            "--debug",
            "--no-options",
            "--save-dir",
            str(workdir / "saves"),
        ]
        if state is not None:
            state_path = workdir / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            args += ["--state", str(state_path)]
        if scene:
            args += ["--start", scene]

        self.master, slave = pty.openpty()
        self.resize(cols, rows, fd=slave)
        state_r, state_w = os.pipe()
        args += ["--state-fd", str(state_w)]
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(workdir),
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "LANG": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
        try:
            self.proc = subprocess.Popen(
                args,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                pass_fds=(state_w,),
                cwd=workdir,
                env=env,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            os.close(slave)
            os.close(state_w)
        self.state_r = state_r
        for fd in (self.master, self.state_r):
            os.set_blocking(fd, False)

    def resize(self, cols: int, rows: int, fd: int | None = None) -> None:
        with contextlib.suppress(OSError):
            fcntl.ioctl(
                self.master if fd is None else fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", rows, cols, 0, 0),
            )

    def write(self, data: str) -> None:
        with contextlib.suppress(OSError):
            os.write(self.master, data.encode("utf-8"))

    def stop(self) -> None:
        if self.proc.poll() is None:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait()
        for fd in (self.master, self.state_r):
            with contextlib.suppress(OSError):
                os.close(fd)


class PlaytestSession:
    def __init__(self, websocket: WebSocket, config: Config, game_id: str) -> None:
        self.ws = websocket
        self.config = config
        self.game_id = game_id
        self.workdir = Path(tempfile.mkdtemp(prefix="cyoa-playtest-"))
        self.loop = asyncio.get_running_loop()
        self.outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.process: PlayerProcess | None = None
        self.generation = 0
        self.cols, self.rows = 80, 24
        self.last_state: dict[str, Any] | None = None
        self.last_input = time.monotonic()

    # -- process management -----------------------------------------------------------

    def load_game(self) -> dict[str, Any]:
        db = self.ws.app.state.db.new_session()
        try:
            return store.load_game_model(db, self.game_id).to_player_dict()
        finally:
            db.close()

    def launch(self, scene: str | None, state: dict[str, Any] | None) -> None:
        self.stop_process()
        self.generation += 1
        generation = self.generation
        game = self.load_game()
        self.process = PlayerProcess(self.workdir, game, self.cols, self.rows, scene, state)
        process = self.process
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        state_buffer = bytearray()

        def on_output() -> None:
            try:
                chunk = os.read(process.master, 65536)
            except BlockingIOError:
                return
            except OSError:
                chunk = b""
            if not chunk:
                self.loop.remove_reader(process.master)
                return
            text = decoder.decode(chunk)
            if text:
                self.outbox.put_nowait({"type": "output", "data": text})

        def on_state() -> None:
            try:
                chunk = os.read(process.state_r, 65536)
            except BlockingIOError:
                return
            except OSError:
                chunk = b""
            if not chunk:
                self.loop.remove_reader(process.state_r)
                return
            state_buffer.extend(chunk)
            while b"\n" in state_buffer:
                line, _, rest = bytes(state_buffer).partition(b"\n")
                state_buffer[:] = rest
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "state":
                    self.last_state = event.get("state")
                    self.outbox.put_nowait(event)

        self.loop.add_reader(process.master, on_output)
        self.loop.add_reader(process.state_r, on_state)

        async def watch() -> None:
            code = await asyncio.to_thread(process.proc.wait)
            if generation == self.generation:
                await asyncio.sleep(0.1)  # let the last output drain first
                self.outbox.put_nowait({"type": "exit", "code": code})

        asyncio.create_task(watch())  # noqa: RUF006 - finishes when the process exits

    def stop_process(self) -> None:
        if self.process is None:
            return
        for fd in (self.process.master, self.process.state_r):
            with contextlib.suppress(ValueError, OSError):
                self.loop.remove_reader(fd)
        self.process.stop()
        self.process = None

    def close(self) -> None:
        self.generation += 1
        self.stop_process()
        shutil.rmtree(self.workdir, ignore_errors=True)

    # -- state edits from the side panel ----------------------------------------------------

    def runtime(self) -> Runtime:
        db = self.ws.app.state.db.new_session()
        try:
            return Runtime(store.load_game_model(db, self.game_id))
        finally:
            db.close()

    def edited_state(self, message: dict[str, Any]) -> dict[str, Any]:
        rt = self.runtime()
        if self.last_state is None:
            raise GameError("start a game first")
        state, _ = rt.restore_save({"state": self.last_state})
        if message["type"] == "set_var":
            name = str(message.get("name", ""))
            rt.debug_set(state, name, rt.parse_value(name, str(message.get("value", ""))))
        else:
            rt.debug_items(state, str(message.get("item", "")), int(message.get("amount", 1)))
        return state.to_dict()

    async def handle(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "input":
            self.last_input = time.monotonic()
            if self.process is not None:
                self.process.write(str(message.get("data", "")))
        elif kind == "resize":
            self.cols, self.rows = _clamp_size(message.get("cols"), message.get("rows"))
            if self.process is not None:
                self.process.resize(self.cols, self.rows)
        elif kind == "start":
            self.cols, self.rows = _clamp_size(
                message.get("cols", self.cols), message.get("rows", self.rows)
            )
            state = message.get("state")
            self.launch(message.get("scene") or None, state if isinstance(state, dict) else None)
        elif kind == "reload":
            self.launch(None, self.last_state)
        elif kind == "goto":
            base = self.last_state or GameState(scene="").to_dict()
            self.launch(str(message.get("scene", "")), base if self.last_state else None)
        elif kind in ("set_var", "items"):
            try:
                state = self.edited_state(message)
            except (GameError, ValueError) as e:
                await self.ws.send_json({"type": "error", "message": str(e)})
                return
            self.launch(None, state)
        else:
            await self.ws.send_json({"type": "error", "message": f"unknown message {kind!r}"})

    # -- main loop -------------------------------------------------------------------------

    async def pump(self) -> None:
        while True:
            event = await self.outbox.get()
            await self.ws.send_json(event)

    async def idle_watch(self) -> None:
        limit = self.config.playtest_idle_minutes * 60
        while True:
            await asyncio.sleep(30)
            if time.monotonic() - self.last_input > limit:
                await self.ws.send_json(
                    {"type": "error", "message": "playtest stopped after being idle"}
                )
                await self.ws.close()
                return

    async def run(self) -> None:
        pump = asyncio.create_task(self.pump())
        idle = asyncio.create_task(self.idle_watch())
        try:
            while True:
                try:
                    message = await self.ws.receive_json()
                except (ValueError, KeyError):
                    continue
                if isinstance(message, dict):
                    try:
                        await self.handle(message)
                    except Exception as e:
                        log.exception("playtest message failed")
                        await self.ws.send_json({"type": "error", "message": str(e)})
        except WebSocketDisconnect:
            pass
        finally:
            pump.cancel()
            idle.cancel()
            self.close()


@router.websocket("/games/{game_id}/playtest")
async def playtest(websocket: WebSocket, game_id: str) -> None:
    app_state = websocket.app.state
    db = app_state.db.new_session()
    try:
        user = websocket_user(websocket, db)
        # Anyone who can read a game can play it (playing never changes the game).
        allowed = user is not None and access_to(db, user, game_id) is not None
        exists = allowed and db.get(store.GameRow, game_id) is not None
        user_id, guest = (user.id, not user.is_owner) if user else (0, True)
    finally:
        db.close()
    if user is None:
        await websocket.close(code=4401)
        return
    if not exists:
        await websocket.close(code=4404)
        return
    config: Config = app_state.config
    running = app_state.playtest_users
    busy = None
    if app_state.playtests >= config.playtest_limit:
        busy = "too many playtests running; close one first"
    elif guest and running[user_id] >= GUEST_PLAYTESTS:
        busy = "you already have a playtest open; close it first"
    if busy:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": busy})
        await websocket.close()
        return
    await websocket.accept()
    app_state.playtests += 1
    running[user_id] += 1
    try:
        await PlaytestSession(websocket, config, game_id).run()
    finally:
        app_state.playtests -= 1
        running[user_id] -= 1
