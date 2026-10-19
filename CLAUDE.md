# CYOA Dashboard

A web dashboard (CMS) for writing choose-your-own-adventure games in the style of
Wizard's Choice / Magium, played in a Warsim-like terminal player (numbered menus,
colors, ASCII art). Live at https://cyoa.mine-own.dev, code at
github.com/ralphyared/cyoa-dashboard (public). `docs/SPEC.md` is the agreed design
plus everything added since; `docs/FORMAT.md` is the game file / markup reference;
`README.md` covers running and deploying.

## Working with the author (the user)

- **They write all story content.** Never add sample stories, scenes or text to the
  product. Test fixtures in tests are fine. Don't commit their story text from chat.
- **"I'm inquiring / don't make changes"** means answer only. "Can I …?" questions are
  often feature ideas: answer precisely what works today (verify by running the engine
  on their snippet), then propose a design and ask before building, unless they've
  said "add it".
- They want things done right (no deadline): tests for new behavior, real-terminal
  and real-browser checks, deploy, and report plainly (incl. failures).
- Players use Windows, macOS and Linux; nobody can test on a Mac.
- Mobile goal: everything works on a phone; long writing sessions are on tablet/computer.

## Environment (this VPS)

- Tools live in the user's home, not on PATH by default:
  `~/.local/bin/uv` and `export PATH=~/.local/node/bin:$PATH` for node/npm (Node 24).
- Git pushes go over SSH with a repo-scoped deploy key: `core.sshCommand` is set in
  this repo's config to `~/.ssh/cyoa_dashboard_deploy`. HTTPS GitHub credentials do
  not work from this machine. Commit identity (repo-local): `own <ralphyared@gmail.com>`.
- The dashboard password is in `.env` (gitignored). The permission system blocks
  printing it; to test the live site, read it inline:
  `PW="$(sed -n 's/^CYOA_PASSWORD=//p' .env)" .venv/bin/python - <<'EOF' … EOF`.
- Disk is small (15 GB, ~4–5 GB free). After `docker compose build` run
  `docker image prune -f && docker builder prune -f`. Remove big test images after use.
- Never `pkill -f "python -m cyoa_server"`: the pattern matches your own shell and
  kills it. Stop a dev server by port:
  `kill $(ss -ltnp | grep ':8765' | sed -n 's/.*pid=\([0-9]*\).*/\1/p')`.

## Commands

```sh
~/.local/bin/uv sync                              # Python deps (workspace: engine/, server/)
~/.local/bin/uv run pytest -q                     # engine + server tests
~/.local/bin/uv run ruff check engine server
~/.local/bin/uv run ruff format engine server     # CI runs `ruff format --check`
~/.local/bin/uv run pyright
cd web && npm run typecheck && npm run lint && npm test && npm run build
cd web && npm run dev                             # Vite :5173, proxies /api (+WS) to :8000
CYOA_PASSWORD=dev CYOA_SECURE_COOKIES=false CYOA_DATA_DIR=./data-dev \
  ~/.local/bin/uv run python -m cyoa_server       # backend :8000
```

### Before every commit

All of: `ruff format` (then `ruff format --check`), `ruff check`, `pyright`, `pytest`,
and the four web scripts. CI (`.github/workflows/ci.yml`) fails on unformatted files;
format anything you appended to tests too.

### Ship a change

1. Commit (end messages with the Co-Authored-By line) and `git push`.
2. Deploy: `docker compose up -d --build` in this folder (container `cyoa-dashboard`
   on `npm_network`, behind Nginx Proxy Manager with websockets + Force SSL; data and
   daily backups in `./data`). Check `https://cyoa.mine-own.dev/api/health`, then prune.
3. **If the engine or player changed in a way games can notice** (markup, effects,
   runtime, player UI), publish a new player: `git tag -a player-vX.Y.Z -m "…" &&
   git push origin player-vX.Y.Z`. `.github/workflows/player.yml` builds
   Windows/macOS×2/Linux with PyInstaller (with a smoke test that attaches a story)
   and creates the release. The dashboard re-checks releases every 6 h; to switch
   immediately, log in and `POST /api/players/update` (or the export dialog's
   "Check for a newer player"). Latest: **player-v1.3.0**. Games exported with an
   older player don't get new features until re-exported.
4. Watch GitHub Actions via the public API (no auth needed):
   `curl -s "https://api.github.com/repos/ralphyared/cyoa-dashboard/actions/runs?per_page=5"`.
   Step names of failed jobs are visible; logs need auth (403).

### Verifying for real

- **Terminal player**: drive it in a PTY and render with pyte —
  `~/.local/bin/uv run --with pyte python script.py` where the script uses
  `pty.fork()`, `TIOCSWINSZ`, `pyte.Screen/ByteStream`, and samples the screen over time
  (good for typewriter/pause/glitch timing).
- **Browser UI**: build `web/dist`, run the backend on 127.0.0.1:8765 with
  `CYOA_STATIC_DIR=$PWD/web/dist` and a throwaway `CYOA_DATA_DIR`, then
  `docker run --rm --network host -v /tmp/pwtest:/work -w /work
  mcr.microsoft.com/playwright:v1.64.1-noble node script.mjs` (playwright@1.64.1
  installed in /tmp/pwtest with `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`). Use
  `devices['iPhone 13']` / `devices['iPad (gen 7)']` for mobile. The image is 3.6 GB:
  `docker rmi` it afterwards. Selectors like `text=Variables` can match hidden desktop
  elements on phone layouts; use role or aria-label selectors.
- **Live site**: log in over HTTPS with an `Origin: https://cyoa.mine-own.dev` header,
  create a temporary game, test, then `DELETE /api/games/{id}` and
  `DELETE /api/trash/games/{id}`.

## Architecture

**Engine (`engine/src/cyoa`) is the single source of truth for game rules.** The CLI
player, the server's validation/export and the in-browser playtest all use it.

- `model.py`: game file format (pydantic, `extra="ignore"`). Permissive about ids and
  expressions; author mistakes are reported by `validate.py`, not rejected on load.
  `Settings` includes `typewriter` and `typing_speed` (1–9).
- `expr/`: the expression language. `parser.py` (hand-written; errors carry character
  offsets), `checker.py` (types + `FUNCTIONS` registry), `evaluator.py`,
  `describe.py` (locked-choice hints), `rename.py` (span-based safe renames).
- `markup.py`: scene text in two stages.
  - Stage 1 (`parse_template`/`resolve_template`): `{expr}` values (escaped so they
    can't inject styling), `{if}/{elif}/{else}/{/if}`, and changes like `{x = 1}` /
    `{give("rope")}` (`TEffect`, detected by a top-level assignment op or give/take).
    Changes run only through the `run` callback and only in the branches shown.
    Block tags and change tags alone on a line swallow the line.
    `template_expressions` yields `(node, offset, mode)` with mode
    `value|condition|effects`.
  - Stage 2 (`style`): `**bold**`, `*italic*`, `[color]…[/]`, `[#hex]`, `---` page
    breaks, plus timing effects `[pause N]`, `[type]` / `[type 1-9]` /
    `[type slow|fast]`, `[glitch]` into neutral `StyledSpan`s (`effect`, `pause`
    fields). A pause alone on a line joins the next line. Unknown `[words]` stay text.
- `typing_speed.py`: speed levels 1–9 → characters per second (6 = normal, 80 cps).
- `runtime.py`: game state, choices, effects, edge-triggered rules, clamping, saves
  (repaired when the game changed). Entering a scene: visit count → `on_enter` effects
  → `read_scene` (renders the text once, applying text changes in order) → rules.
  The text as read is frozen in `GameState.text`/`text_scene` so redraws and loaded
  saves never re-apply changes; `forget_text` (used by debug edits) and
  `restore_save(keep_text=False)` (used by playtest restarts) re-render it.
  Never raises on author mistakes: records them in `Runtime.problems`.
- `validate.py`: every issue (errors block exports) + stats; `refactor.py`: find and
  rename variables/items/scenes/chapters everywhere, including inside text.
- `standalone.py`: attach a game to a player executable
  (`[exe][json][MAGIC][len]`). PyInstaller's bootloader scans back to front for its
  own marker, so trailing data is safe. The player loads an attached game when started
  without arguments.
- `player/`: rich-based terminal player. `Terminal` wraps IO so tests drive it with
  scripted input. `effects.py` (`LinePlayer`) plays typewriter, pauses, `[type N]` and
  glitch frames (cursor moves back with rich `Control`); any key skips the rest of the
  page; effects only play on a scene's first draw. Options persist per user
  (typewriter, effects on/off, typing speed level or game default, width).
  `--debug` adds `:goto/:set/:give/:vars`; `--state-fd` streams JSON state for the
  playtest panel. Command-line messages use a soft-wrapping console (no hard wraps).

**Server (`server/src/cyoa_server`)**: FastAPI + SQLAlchemy on SQLite.
- Game-level data (settings, variables, items, rules, chapters) is one JSON column
  (`games.meta`); each scene is a row (`scenes.data` JSON) with its own `rev` and
  revision history (edits within 10 min coalesce). Scene `pk` is stable; the slug
  `scene_id` can be renamed (PATCH `id` runs the refactor across the game).
- Optimistic concurrency: clients send `rev`; a mismatch returns 409.
- `playtest.py`: WebSocket running `python -m cyoa --debug` in a pty (never a shell);
  side-panel edits and Reload restart it with a modified `--state`.
- `players.py` / `routes_players.py`: ready-to-play exports. Downloads `player-v*`
  release assets into `<data>/players/<tag>/` (refreshed when older than 6 h).
  Windows/Linux = player + attached game (Linux as .tar.gz to keep +x); macOS = zip
  of the unmodified player + game file + "How to play" (changing a signed Mac binary
  breaks its signature).
- Auth: single password (`CYOA_PASSWORD`), server-side sessions, per-IP and global
  login rate limits, Origin checks on writes and the WebSocket. Daily backups.

**Web (`web/src`)**: React 19, TanStack Query, React Router, Tailwind v4, CodeMirror 6,
React Flow, xterm.js.
- The `['game', id]` query cache is the editing copy. `lib/save.ts` (`SaveManager`)
  applies edits to the cache immediately and autosaves per scene / meta with `rev`.
  Query notifications are synchronous (`main.tsx`) so controlled inputs don't drop
  keystrokes. Keep it that way.
- Expression checking goes through the server (`/check`, via `useCheck`); the visual
  builders (`components/editor/LogicFields.tsx`, `lib/builder.ts`) turn the returned
  AST into rows and write plain expression text back. There is no client-side parser.
- Syntax highlighting / autocomplete for markup and expressions:
  `components/editor/languages.ts` and `CodeEditor.tsx`. Typing levels mirror the
  engine in `lib/typing.ts`.
- Responsive: `lib/media.ts` (`useIsPhone` < 768px, `useIsTouch`). Phones get a scene
  drawer and a ⋯ menu; Problems/Playtest go full-screen below 1024px; playtest shows a
  tap bar on touch screens; inputs are 16px on phones (iOS zoom).
- Use `cx()` from `components/ui` (clsx + tailwind-merge) so className overrides win.

## Where to change what

| Feature | Files |
|---|---|
| New markup tag / text behavior | `engine/src/cyoa/markup.py`, player `effects.py`, `validate.py` (warnings), web `languages.ts` + `CodeEditor.tsx` completion + `SceneEditor.tsx` toolbar, Help (`ReferencePage.tsx`), `docs/FORMAT.md`; then a new player release |
| New expression function | `expr/checker.py` `FUNCTIONS`, `expr/evaluator.py`, `describe.py` if it gates choices, web completion |
| New game setting | `model.py` `Settings`, player, web `types.ts` + `SettingsPage.tsx`, `docs/FORMAT.md` |
| API endpoint | `server/src/cyoa_server/routes_*.py`, web `lib/api.ts` + `types.ts`, server tests |
