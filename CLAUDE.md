# CYOA Dashboard

Web dashboard for writing choose-your-own-adventure games played in a terminal
(Warsim-style CLI). See `README.md` for running/deploying and `docs/SPEC.md` for
the agreed design. The author writes all story content themselves: never add
sample stories or content to the product (test fixtures are fine).

## Commands

- `uv sync` — install Python deps (workspace: `engine/`, `server/`)
- `uv run pytest -q` — engine + server tests (`engine/tests`, `server/tests`)
- `uv run ruff check engine server && uv run ruff format engine server && uv run pyright`
- `cd web && npm run dev` — Vite on :5173, proxies `/api` (incl. WebSocket) to :8000
- `cd web && npm run typecheck && npm run lint && npm test && npm run build`
- Backend for dev: `CYOA_PASSWORD=dev CYOA_SECURE_COOKIES=false CYOA_DATA_DIR=./data-dev uv run python -m cyoa_server`
- Deploy: `docker compose up -d --build` (container `cyoa-dashboard` on `npm_network`,
  proxied by Nginx Proxy Manager at cyoa.mine-own.dev; data in `./data`)

Before committing run the Python checks and the web checks above.

## Architecture

**Engine (`engine/src/cyoa`) is the single source of truth for game rules.** The
CLI player, the server's validation/export, and the in-browser playtest all use it.

- `model.py` — game file format (pydantic). Permissive about ids/expressions;
  author mistakes are reported by `validate.py`, not rejected on load.
- `expr/` — expression language: `parser.py` (hand-written, errors carry char
  offsets), `checker.py` (types + `FUNCTIONS` registry), `evaluator.py`,
  `describe.py` (locked-choice hints), `rename.py` (span-based safe renames).
- `markup.py` — scene text: stage 1 resolves `{expr}` / `{if}` (values are escaped),
  stage 2 styles `**bold**`, `*italic*`, `[color]…[/]`, `---` page breaks into
  neutral `StyledSpan`s. Standalone block tags swallow their line.
- `runtime.py` — game state, choices, effects, edge-triggered rules, clamping,
  saves (with repair for changed games). Never raises on author mistakes: records
  them in `Runtime.problems`.
- `validate.py` — all issues (errors block player export) + stats.
- `refactor.py` — find/rename variables, items, scenes, chapters everywhere.
- `player/` — rich-based terminal player. `Terminal` wraps IO so tests drive it
  with scripted input. `--debug` adds `:goto/:set/:give` and `--state-fd` streams
  state as JSON lines (used by the playtest panel).

**Server (`server/src/cyoa_server`)** — FastAPI + SQLAlchemy on SQLite.
- Game-level data (settings, variables, items, rules, chapters) is one JSON column
  on `games.meta`; each scene is a row (`scenes.data` JSON) with its own `rev` and
  revision history (edits within 10 min coalesce). Scene pk is stable; the slug
  `scene_id` can be renamed (PATCH `id` runs the refactor across the game).
- Optimistic concurrency: clients send `rev`; mismatch → 409.
- `playtest.py` — WebSocket that runs `python -m cyoa --debug` in a pty (no shell),
  restarting it with a modified state for side-panel edits / reload.
- Auth: single password (`CYOA_PASSWORD`), server-side sessions, Origin checks on
  writes and the WebSocket.

**Web (`web/src`)** — React 19, TanStack Query, React Router, Tailwind v4.
- The `['game', id]` query cache is the editing copy. `lib/save.ts` (`SaveManager`)
  applies edits to the cache immediately and autosaves per scene / meta with `rev`.
  Query notifications are synchronous (`main.tsx`) so controlled inputs don't drop
  keystrokes — keep it that way.
- Expression checking goes through the server (`/check`) via `useCheck`; builders
  (`components/editor/LogicFields.tsx`, `lib/builder.ts`) convert the returned AST
  to rows and write plain expression text back. No client-side parser.
- Use `cx()` from `components/ui` (clsx + tailwind-merge) so className overrides win.
