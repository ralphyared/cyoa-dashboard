# Game file format (`.cyoa.json`)

A game is one JSON file. The dashboard writes it; the terminal player reads it.
The same format with author-only fields included is the *project backup*.

```jsonc
{
  "format": 1,                       // file format version
  "id": "3f2a…",                     // stable id; saves are stored per game id
  "title": "The Crossing",
  "author": "",
  "description": "",                 // shown on the title screen
  "version": "1.0",                  // saves remember it
  "start_scene": "start",
  "settings": {
    "title_art": "",                 // ASCII art above the title
    "intro": "",                     // markup shown after New Game
    "accent_color": "cyan",
    "status_format": "HP {hp}/{max_hp} │ Gold {gold}",   // markup; "" = no status bar
    "show_scene_titles": false,
    "text_width": 80,
    "typewriter": false,             // type out all scene text by default
    "typing_speed": 6                // 1 (slowest) … 9 (fastest); also used by [type]
  },
  "variables": [
    { "name": "hp", "type": "number", "initial": 10, "min": 0, "max": "max_hp", "label": "HP" }
  ],                                 // type: number | bool | text; min/max: number or variable name
  "items": [
    { "id": "rope", "name": "Rope", "description": "", "stackable": false }
  ],
  "rules": [
    { "id": "r1", "name": "Death", "condition": "hp <= 0", "effects": "", "goto": "dead" }
  ],
  "chapters": [ { "id": "ch1", "title": "Chapter 1", "color": "#22d3ee" } ],
  "scenes": [
    {
      "id": "start",
      "title": "Camp",               // for the author (optionally shown to players)
      "chapter": "ch1",
      "text": "You have {gold} gold.",
      "art": "",
      "on_enter": "",                // effects applied on every visit
      "choices": [
        {
          "id": "a1b2c3d4",
          "text": "Buy rope",
          "target": "start",
          "condition": "gold >= 3",
          "when_locked": "show",     // hide | show
          "hint": "",                // custom locked hint; auto-generated if empty
          "effects": "gold -= 3\ngive(\"rope\")",
          "once": true
        }
      ],
      "ending": null,                // or { "kind": "death" | "victory" | "neutral", "title": "…" }
      "tags": [],
      "notes": "",                   // project backups only
      "position": [0, 0],            // project backups only (graph layout)
      "hidden_warnings": []          // project backups only (warnings the author hid)
    }
  ]
}
```

## Expressions

Conditions are a single expression that must be true/false. Effects are
statements, one per line (or separated by `;`); `#` starts a comment.

| | |
|---|---|
| Values | numbers `10`, `2.5`; text `"Ana"` or `'Ana'`; `true`, `false`; variable names |
| Operators | `+ - * / %`, `== != < <= > >=`, `and or not`, parentheses |
| Statements | `x = v`, `x += v`, `x -= v`, `x *= v`, `x /= v`, `give("item"[, n])`, `take("item"[, n])` |
| Functions | `has(item[, n])`, `count(item)`, `visited(scene)`, `visits(scene)`, `min`, `max`, `round`, `floor`, `ceil`, `abs` |

Item and scene names are always quoted literals so they can be checked and renamed.
Number variables are clamped to their `min`/`max` after every change.

## Scene text markup

- `{expr}` shows a value; `{if c}…{elif c}…{else}…{/if}` shows text conditionally.
  A block tag alone on its line removes the whole line.
- `{x = 1}`, `{hp -= 2}`, `{give("rope")}` (any effect; several with `;`) change
  values when the player reads that part of a scene, only in the branches shown.
  Scene text only (not choice text, status bar or intro). Alone on a line, the tag
  removes the line.
- `**bold**`, `*italic*`, `[red]…[/red]` (or `[/]`), `[bold]`, `[italic]`,
  `[underline]`, `[dim]`, `[#rrggbb]`. Unknown `[words]` are plain text.
- A line containing only `---` is a page break ("press Enter to continue").
- Timing effects: `[pause N]` waits N seconds (default 1, at most 30; alone on a
  line it leaves no blank line), `[type]…[/type]` types text out letter by letter at
  the game's typing speed, `[type 1]` … `[type 9]` at a given speed (1 slowest; `slow`
  = 2, `fast` = 8), `[glitch]…[/glitch]` flickers text in as random
  symbols. They play the first time a page is shown; any key skips them, and
  players can switch them off in Options.
- `\` shows the next character literally (`\{`, `\*`, `\[`).

## Turn order

1. Choice effects apply (and `once` choices are marked used).
2. Rules are checked: a rule fires when its condition *becomes* true (it can
   fire again only after being false). It applies its effects and may `goto`.
3. The target scene (or the rule's `goto`) is entered: its visit count goes up,
   `on_enter` effects apply, then its text is read top to bottom (resolving values
   and conditions, and applying changes written in the text, in order); rules are
   checked again.
4. The scene shows the text as it was read (redraws and loaded saves keep it, so
   changes in the text never apply twice); available choices are listed with
   current values.
