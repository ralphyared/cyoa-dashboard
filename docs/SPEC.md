# CYOA Dashboard — Spec (approved 2026-10-18; kept up to date)

A web dashboard for writing choose-your-own-adventure games (in the style of
Wizard's Choice / Magium) that are played in the terminal with a Warsim-like look:
numbered menus, ANSI colors, ASCII art.

## Decisions so far

| Topic | Decision |
|---|---|
| Game structure | Pure branching story: scenes of text + choices. No hub/turn sim. |
| Mechanics | Variables (HP, resources, flags) + inventory. Nothing else in v1. |
| Logic authoring | Point-and-click builders that write expressions, with hand-editing as an option. |
| Editing | Forms to write scenes + a graph view to see/navigate the flow. |
| Playtest | In-browser terminal running the real CLI player. |
| Users | One owner (you, password from `.env`); games can be shared with others at read or edit level (2026-10-21). |
| Games | Multiple games per dashboard. |
| Validation | Yes: broken links, dead ends, unreachable scenes, bad expressions. |
| Player | Python, numbered menus, colors + ASCII art + clear screen, typewriter optional. |
| Saves | Multiple slots + autosave. |
| Distribution | Dashboard exports a game file; one generic player runs any game file. |
| Modding | No. |
| Hosting | Docker on this VPS behind Nginx Proxy Manager. |
| Content | None. No sample story ships; small test fixtures only. |

## Architecture

```
cyoa-dashboard/
  engine/   Python package `cyoa` — the single source of truth for game rules
            model.py        game file schema (pydantic)
            expr/           expression language: parser, evaluator, type checker, renamer
            markup.py       scene text: interpolation, conditional text, styling
            runtime.py      game state, applying choices/effects/rules, saves
            validate.py     all validation checks
            player/         the CLI player (rich), title screen, menus, saves, options
  server/   FastAPI app: REST API, auth, SQLite storage, export/import,
            revisions, backups, playtest WebSocket
  web/      React + TypeScript + Vite dashboard
  docs/     SPEC.md, FORMAT.md (author reference for expressions + markup)
```

**Why this split:** the engine is written once, in Python. The CLI player, the
server's validation/export, and the in-browser playtest all use that same code.
The playtest panel runs the actual player in a pseudo-terminal on the server and
streams it to an xterm.js terminal in the browser. So what you see while testing
is exactly what players see, colors and line wrapping included, and logic can't
drift between the editor and the game.

**Stack:**
- Engine/player: Python 3.14, pydantic, rich, platformdirs. Custom expression
  parser (no `eval`), with clear error messages that point at the column.
- Server: FastAPI, SQLAlchemy + SQLite (WAL mode), uvicorn.
- Web: React, TypeScript, Vite, TanStack Query, React Flow + ELK (graph),
  CodeMirror 6 (text/expression editors with highlighting + autocomplete),
  xterm.js (playtest), Tailwind + shadcn/ui, dark theme.
- Tests: pytest (engine heavily covered), Vitest, Playwright smoke tests.

## Game data model

```
Game
  title, author, description, version
  start_scene
  settings      title-screen ASCII art, intro text, accent colors,
                status bar format (e.g. "HP {hp}/{max_hp} | Gold {gold}"),
                text width, typewriter default on/off
  variables[]   name, type (number | bool | text), initial value,
                min/max (a number or another variable, e.g. hp max = max_hp),
                display label
  items[]       id, name, description, stackable (shows quantity)
  rules[]       global triggers checked after every change:
                condition → effects and/or goto scene
                e.g. "hp <= 0" → goto "death"
  chapters[]    title, order, color (organizes scenes + graph)
  scenes[]

Scene
  id            readable slug ("forest_bridge"); renaming updates every reference
  title, chapter
  text          markup (see below)
  art           optional ASCII art block
  on_enter      effects applied on arrival (e.g. "hp -= 2")
  choices[]
  ending        none | { kind: death | victory | neutral, title }
  notes         private author notes (never exported)
  tags          for filtering
  position      graph coordinates
  hidden_warnings  warnings the author checked and hid (never exported to players)

Choice
  text          "Pay the toll"
  target        scene id
  condition     optional, e.g. gold >= 10
  when_locked   hide | show greyed with a hint ("Requires 10 gold")
  hint          optional custom locked hint (auto-generated if empty)
  effects       optional, e.g. gold -= 10
  once          disappears after being chosen (for "Ask about…" dialogue options)
```

### Expression language

Conditions:
```
hp > 0 and has("rusty_key")
gold >= 10 or not met_wizard
count("arrow") >= 3
visited("tower_top")
class == "mage"
```
Effects (one per line, or separated by `;`):
```
gold -= 10
hp = min(hp + 5, max_hp)
met_wizard = true
give("arrow", 5)
take("rusty_key")
```
- Operators: `+ - * / %`, `== != < <= > >=`, `and or not`, parentheses.
- Functions: `has(item[, n])`, `count(item)`, `visited(scene)`, `min`, `max`.
- Type-checked against the declared variables/items, so typos and
  `hp == "abc"` are caught in the editor, not by a player.
- Variables are clamped to their min/max after every change.

The builders cover the common shapes: rows like `[gold ▾] [>= ▾] [10]` joined
with All/Any, `[has item ▾] [rusty_key ▾]`, `[visited ▾] [scene ▾]`, and effect
rows like `[gold ▾] [− ▾] [10]` / `[give ▾] [arrow ▾] [5]`. Switch to text at any
time. If what you typed fits the builder shapes, it switches back to the builder.

### Scene text markup

```
You have {gold} gold coins.

{if hp < 3}Your vision swims. You won't survive another hit.{else}You feel steady.{/if}

**Bold**, *italic*, [red]colored text[/red]

---            ← "press Enter to continue" break for long scenes
```
Blank lines separate paragraphs; text wraps to the terminal width automatically.

## CLI player

```
 HP 8/10 │ Gold 25 │ Mana 3                        Chapter 2: The Crossing
──────────────────────────────────────────────────────────────────────────
        /\
       /  \    (scene ASCII art)
──────────────────────────────────────────────────────────────────────────
The bridge sways over the gorge. A troll squats at the far end, one
hand extended, palm up.

  1) Cross the bridge
  2) Pay the toll (10 gold)
  3) Climb down the cliff              [Requires: Rope]   ← locked, greyed

  I) Inventory   S) Save   L) Load   O) Options   Q) Quit
> _
```
- Title screen: game title art, New Game / Continue / Load / Quit.
- Inventory screen: items, quantities, descriptions (view-only).
- Save slots 1–5 + autosave on every scene, stored in the player's user data
  folder per game. Loading a save from an older game version is handled: you get
  a warning, and if the saved scene no longer exists, a safe fallback.
- Options: typewriter effect on/off + speed, text width.
- Endings: an ending screen ("YOU DIED" / "THE END" + ending title), then
  load / restart / quit.
- Usage: `cyoa-play mygame.cyoa.json`.

## Dashboard

- **Login:** username + password, session cookie, rate-limited. The owner's password is
  `CYOA_PASSWORD` (username `owner` by default, changeable on the Account page);
  everyone else gets an account from an invite link.
- **Sharing:** the owner shares one game at a time from its Share button: an invite
  link (single use, 7 days, no email: copied and sent by hand) at **read** (read
  everything, playtest) or **edit** (change anything in that game). Only the owner
  creates, imports, duplicates, deletes or shares games, and sees trash, backups and
  the People page (accounts, password-reset links, removing someone). Readers get the
  whole editor read-only; the server checks every request. Scene history records who
  made each change.
- **Games:** create / rename / duplicate / delete (with confirm), import/export.
- **Workspace layout:** left sidebar with chapters → scenes tree, search, and tag
  filter; the editor in the center; issues and playtest in a right-hand panel.
  Ctrl+K quick-jumps to any scene.
- **Scene editor:** title, id, chapter, text editor (highlighting for
  `{var}`/`{if}`, autocomplete for variables, items, and scene ids), art box,
  on-enter effects, ending toggle, notes.
  - Choices: drag to reorder, condition and effect builders, locked behaviour.
  - Target picker with search and **"create new scene" inline**, so you can keep
    writing forward without leaving the page.
  - "What leads here" list of incoming choices.
  - "Playtest from here".
  - Autosaves with a saved/saving indicator.
- **Graph view:** auto-layout plus manual dragging (positions saved).
  - Nodes colored by chapter, endings drawn as a distinct shape, conditional
    choices drawn dashed.
  - Click a node to edit it; drag from a node to empty space to create a new
    scene and choice.
  - Chapter filter, search-to-node, minimap.
- **Variables / Items / Rules / Settings:** table editors. Renaming a variable or
  item safely updates every expression and text reference. "Where used" for each.
- **Issues panel (live):**
  - Errors (block export): syntax errors, missing targets, unknown
    variables/items, type mismatches, missing start scene.
  - Warnings: unreachable scenes, dead ends (a non-ending scene with no choices),
    possible soft-locks (every choice conditional), unused variables/items, empty
    text.
  - Click any issue to jump to it.
- **Stats:** scene, word, and ending counts, overall and per chapter.
- **History:** per-scene revision history with diff + restore. Deleted scenes go
  to a trash and can be restored.
- **Playtest:** a real terminal in the browser.
  - Side panel shows live variables, inventory, and visited scenes. You can
    edit values or jump to any scene.
  - **Reload** picks up your latest edits while keeping your current position
    and state, for a fast write → test loop.
  - Start from the beginning, or from any scene with preset values.
- **Export:** downloads `<title>.cyoa.json`. Blocked only by errors, not
  warnings.

## Storage, backups, security

- SQLite in a Docker volume, one row per scene so autosave writes are small.
- Automatic daily backup snapshot (keeps 14) + manual JSON export anytime.
- Playtest runs only the player process, never a shell. Each session is
  time-limited and killed on disconnect.

## Deployment

- One Docker image (builds the web app, then a slim Python runtime serving the
  API and the built frontend), started with docker-compose on `npm_network`,
  like your other services.
- `cyoa.mine-own.dev` (the wildcard DNS already points here). You add a Proxy
  Host in Nginx Proxy Manager → `cyoa-dashboard:8000` with SSL. I'll give exact
  settings.

## Milestones

1. **Engine + player:** model, expressions, markup, runtime, validation, CLI
   player. Fully tested and playable from a JSON file.
2. **Server:** API, storage, auth, export/import, revisions, backups.
3. **Dashboard core:** games, scene editor with builders, variables, items,
   rules, settings, and the issues panel.
4. **Graph view + playtest terminal.**
5. **Deploy** to `cyoa.mine-own.dev`.
6. **Player distribution:** standalone player executables, so players don't
   need Python.

All six milestones are done and deployed (2026-10-18).

## Added since v1 (requested by the author)

| Date | Feature | Notes |
|---|---|---|
| 2026-10-18 | Ready-to-play exports | Export → one Windows `.exe` / Linux program with the story attached, or a macOS zip (player + game file). Player builds come from `player-v*` GitHub releases. Repo made public for this. |
| 2026-10-19 | Mobile-friendly dashboard | Phones: scene drawer, ⋯ menu, full-screen panels and graph editor, stacked cards, playtest tap bar. Goal: everything works on a phone; long writing on tablet/computer. |
| 2026-10-19 | Timing & text effects | `[pause N]`, `[type]…[/type]`, `[glitch]…[/glitch]`; play on first draw, Enter skips, players can turn them off. |
| 2026-10-19 | Typing speed levels | 1 (slowest) – 9 (fastest); game-wide default in Settings (with "type out all text"); `[type N]` per passage; players can override. |
| 2026-10-19 | Changes in scene text | `{x = 1}`, `{hp -= 2}`, `{give("rope")}` anywhere in scene text, including inside `{if}`; applied once when the scene is read on arrival; the text as read is kept for redraws and saves. |
| 2026-10-19 | Fix: skipping animations | Pressing Enter while text typed or glitched in broke the line (and left glitch symbols behind) on Linux/macOS and in the playtest, because the terminal echoed the key. Keys are now hidden while text animates, and any key skips. Player v1.3.1. |
| 2026-10-20 | Smarter dead-end warning, hiding warnings | "Every choice has a condition" only warns when the conditions could all be false at once (opposites like `x` / `not x` or `gold >= 3` / `gold < 3` count as covered; choices that can only be picked once don't count). Any scene warning can be hidden ("Hide" in the scene or Problems panel); hidden ones are listed under "Hidden" in Problems and come back when what they're about changes. |
| 2026-10-21 | Logins and sharing (stage 1) | Owner + guest accounts; Share a game by invite link at "can read" or "can edit"; read-only editor for readers; People page with password-reset links; history shows who changed what. Stage 2 (a "can comment" level with comment threads on scenes) is next. |

Decided against: conditional lines inside effect lists (`if …: x = 1`). Changes in
scene text cover the same need in the way the author writes.

## Still open (ideas, not started)

Dice/random checks, stat-point allocation (Magium-style), achievements, usable
items from the inventory screen, undo-last-choice. Sharing stage 2: "can comment"
(comment threads per scene, quote selected text, resolve; never exported).
