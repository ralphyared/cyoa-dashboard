# CYOA Dashboard

A web dashboard for writing choose-your-own-adventure games (in the spirit of
Wizard's Choice and Magium) that are played in the terminal with a Warsim-like
look: numbered menus, colors, ASCII art, a status bar, save slots.

- **Write** scenes with formatted text, variables (`{gold}`) and conditional text.
- **Branch** with choices that can require things (`gold >= 10 and has("rope")`),
  change things (`gold -= 10`, `give("rope")`), and show up locked with a hint.
- **Track** HP, resources and inventory; global rules (e.g. `hp <= 0` → death scene).
- **See** the whole story as a graph, and find problems in the Issues panel:
  broken links, dead ends, unreachable scenes, typos in conditions.
- **Playtest** in the browser with the real terminal player, tweak variables
  live, and reload after edits without losing your place.
- **Export** a `.cyoa.json` game file that the standalone player runs.

## Layout

```
engine/   Python package `cyoa`: game format, expression language, scene markup,
          runtime, validation, and the terminal player (`cyoa-play`)
server/   Python package `cyoa_server`: FastAPI backend on SQLite
web/      React + TypeScript dashboard (Vite)
docs/     SPEC.md (design), FORMAT.md (game file format)
```

## Running it (Docker, behind Nginx Proxy Manager)

```sh
cp .env.example .env      # set CYOA_PASSWORD, and CYOA_UID/CYOA_GID from `id`
mkdir -p data
docker compose up -d --build
```

The container joins the `npm_network` Docker network. In Nginx Proxy Manager add a
Proxy Host:

| Field | Value |
|---|---|
| Domain | `cyoa.mine-own.dev` |
| Scheme / Forward Hostname / Port | `http` / `cyoa-dashboard` / `8000` |
| Websockets Support | **on** (the playtest terminal needs it) |
| Block Common Exploits | on |
| SSL | Request a new Let's Encrypt certificate, Force SSL, HTTP/2 |

Everything lives in `./data`: the SQLite database and `backups/` (one automatic
snapshot a day, the last 14 kept; more from the Backups page).

**Restoring a backup:** `docker compose down`, copy the backup file over
`data/cyoa.db` (and delete `data/cyoa.db-wal` / `data/cyoa.db-shm`), then
`docker compose up -d`. To move a single game, use *Export → Project backup* and
*Import* on the games page instead.

**Updating:** `git pull && docker compose up -d --build`.

## Logging in, and letting others in

You log in as `owner` with `CYOA_PASSWORD` (rename yourself on the Account page).
To let someone read or edit one game, open it and use **Share**: pick "can read" or
"can edit", create an invite link and send it to them. The link works once, for 7
days; opening it creates their account. Readers see the whole game and can playtest
it but can't change anything; editors can change anything in that game. Only you can
create, delete or share games, and see trash and backups. The **People** page lists
everyone, makes password links for people who forgot theirs, and removes accounts.

## Exporting for players

*Export → Ready-to-play game* builds a download for your players' system:

- **Windows:** one `<Title>.exe`. The story is attached to a copy of the player,
  so double-clicking it starts the game.
- **Linux:** the same single program, in a `.tar.gz` (keeps it executable).
- **macOS:** a zip with the player, the story file and a short "How to play".
  Apple only runs programs whose signature matches, so the Mac player is shipped
  unmodified and finds the story next to it.

The player builds come from this repo's GitHub releases: the *Player executables*
workflow builds them for every system when a tag like `player-v1.0.0` is pushed,
and the dashboard downloads the newest release the first time you export (or when
you click "Check for a newer player"). The repo must be public for that, or set
`CYOA_PLAYER_REPO` to a public repo that publishes the same assets.

Players' saves go to their user data folder (e.g. `%LOCALAPPDATA%\cyoa\saves` on
Windows, `~/.local/share/cyoa/saves` on Linux), one folder per story.

The bare game file (*Export → Game file only*) can also be played with
`cyoa-play my_game.cyoa.json`, or checked with `cyoa-play my_game.cyoa.json --check`.

## Development

Requirements: [uv](https://docs.astral.sh/uv/) and Node 24.

```sh
uv sync                                  # Python deps (engine + server + dev tools)
cd web && npm install && cd ..

# backend on :8000 (in one terminal)
CYOA_PASSWORD=dev CYOA_SECURE_COOKIES=false CYOA_DATA_DIR=./data-dev uv run python -m cyoa_server
# frontend on :5173 with /api proxied to :8000 (in another)
cd web && npm run dev
```

Checks (all run in CI):

```sh
uv run pytest -q && uv run ruff check engine server && uv run ruff format --check engine server && uv run pyright
cd web && npm run typecheck && npm run lint && npm test && npm run build
```
