"""Scene text markup.

Rendering happens in two stages:

1. **Template** — ``{expr}`` interpolation and ``{if}/{elif}/{else}/{/if}``
   conditional text are resolved against the game state. Interpolated values are
   escaped so they can never be mistaken for styling.
2. **Styling** — ``**bold**``, ``*italic*``, ``[red]...[/red]`` (or ``[/]``) and
   ``---`` page breaks turn the flat text into styled spans, page by page.

A backslash escapes the next character (``\\{``, ``\\*``, ``\\[``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from .expr import (
    Expr,
    ExprError,
    RefKind,
    format_value,
    parse_expression,
)
from .expr.nodes import Value
from .expr.rename import apply_renames, reference_spans
from .typing_speed import TYPING_CPS

# -- stage 1: template ---------------------------------------------------------


@dataclass(slots=True)
class TText:
    text: str


@dataclass(slots=True)
class TInterp:
    expr: Expr
    offset: int  # where the expression source starts in the scene text


@dataclass(slots=True)
class TBranch:
    condition: Expr | None  # None for {else}
    offset: int
    body: list[TNode] = field(default_factory=list)


@dataclass(slots=True)
class TIf:
    branches: list[TBranch]


TNode = TText | TInterp | TIf


@dataclass(frozen=True, slots=True)
class _Tag:
    kind: str  # "if", "elif", "else", "endif", "value"
    payload: str
    payload_offset: int
    start: int
    end: int


_BLOCK_KINDS = {"if", "elif", "else", "endif"}
_IF_RE = re.compile(r"^(\s*)(if|elif)\b(.*)$", re.DOTALL)
_WRONG_CLOSERS = {"endif", "end", "/", "end if", "fi"}


def _find_tag_end(text: str, start: int) -> int:
    """Index of the ``}`` closing the tag opened at ``start`` (skipping quoted text)."""
    i = start + 1
    quote: str | None = None
    while i < len(text):
        c = text[i]
        if c == "\n":
            break
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "}":
            return i
        i += 1
    raise ExprError("missing '}' (write \\{ for a literal brace)", start, start + 1)


def _classify(content: str, offset: int, start: int, end: int) -> _Tag:
    stripped = content.strip()
    lowered = stripped.lower()
    if not stripped:
        raise ExprError("empty {} (write \\{ for a literal brace)", start, end)
    m = _IF_RE.match(content)
    if m and (m.group(3)[:1].isspace() or m.group(3)[:1] in ("(", "")):
        kind = m.group(2)
        cond = m.group(3)
        if not cond.strip():
            raise ExprError(f"{{{kind}}} needs a condition, e.g. {{{kind} gold >= 10}}", start, end)
        return _Tag(kind, cond, offset + len(m.group(1)) + len(kind), start, end)
    if lowered == "else":
        return _Tag("else", "", offset, start, end)
    if lowered == "/if":
        return _Tag("endif", "", offset, start, end)
    if lowered in _WRONG_CLOSERS:
        raise ExprError("close conditional text with {/if}", start, end)
    return _Tag("value", content, offset, start, end)


def _scan(text: str) -> list[tuple[str, int, int] | _Tag]:
    """Split text into literal pieces ``(text, start, end)`` and tags."""
    tags: list[_Tag] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            i += 2
            continue
        if c == "{":
            close = _find_tag_end(text, i)
            tags.append(_classify(text[i + 1 : close], i + 1, i, close + 1))
            i = close + 1
            continue
        i += 1

    # Block tags alone on their line swallow the whole line, so conditional
    # paragraphs don't leave blank lines behind.
    cut: list[tuple[int, int]] = []
    for tag in tags:
        start, end = tag.start, tag.end
        if tag.kind in _BLOCK_KINDS:
            line_start = text.rfind("\n", 0, start) + 1
            line_end = text.find("\n", end)
            line_end = len(text) if line_end == -1 else line_end
            if not text[line_start:start].strip() and not text[end:line_end].strip():
                start = line_start
                end = line_end + 1 if line_end < len(text) else line_end
        if cut and start < cut[-1][1]:
            start = cut[-1][1]
        cut.append((start, end))

    pieces: list[tuple[str, int, int] | _Tag] = []
    pos = 0
    for tag, (start, end) in zip(tags, cut, strict=True):
        if start > pos:
            pieces.append((text[pos:start], pos, start))
        pieces.append(tag)
        pos = max(pos, end)
    if pos < len(text):
        pieces.append((text[pos:], pos, len(text)))
    return pieces


def _unescape_braces(text: str) -> str:
    return text.replace("\\{", "{").replace("\\}", "}")


def _parse_payload(tag: _Tag) -> Expr:
    try:
        return parse_expression(tag.payload)
    except ExprError as e:
        raise e.shift(tag.payload_offset) from None


def parse_template(text: str) -> list[TNode]:
    """Parse scene text. Raises :class:`ExprError` with offsets into ``text``."""
    root: list[TNode] = []
    stack: list[tuple[TIf, _Tag]] = []

    def body() -> list[TNode]:
        return stack[-1][0].branches[-1].body if stack else root

    for piece in _scan(text):
        if isinstance(piece, tuple):
            body().append(TText(_unescape_braces(piece[0])))
            continue
        tag = piece
        if tag.kind == "value":
            body().append(TInterp(_parse_payload(tag), tag.payload_offset))
        elif tag.kind == "if":
            node = TIf([TBranch(_parse_payload(tag), tag.payload_offset)])
            body().append(node)
            stack.append((node, tag))
        elif tag.kind in ("elif", "else"):
            if not stack:
                raise ExprError(f"{{{tag.kind}}} without a matching {{if}}", tag.start, tag.end)
            node = stack[-1][0]
            if node.branches[-1].condition is None:
                raise ExprError(f"{{{tag.kind}}} after {{else}}", tag.start, tag.end)
            cond = _parse_payload(tag) if tag.kind == "elif" else None
            node.branches.append(TBranch(cond, tag.payload_offset))
        else:  # endif
            if not stack:
                raise ExprError("{/if} without a matching {if}", tag.start, tag.end)
            stack.pop()
    if stack:
        tag = stack[-1][1]
        raise ExprError("{if} is never closed with {/if}", tag.start, tag.end)
    return root


def template_expressions(nodes: list[TNode]) -> Iterator[tuple[Expr, int, bool]]:
    """Yield ``(expr, offset, is_condition)`` for every expression in a template."""
    for node in nodes:
        if isinstance(node, TInterp):
            yield node.expr, node.offset, False
        elif isinstance(node, TIf):
            for branch in node.branches:
                if branch.condition is not None:
                    yield branch.condition, branch.offset, True
                yield from template_expressions(branch.body)


_ESCAPE_RE = re.compile(r"([\\*\[\]\-])")


def escape(text: str) -> str:
    """Escape a value so stage 2 shows it literally."""
    return _ESCAPE_RE.sub(r"\\\1", text)


Evaluate = Callable[[Expr], Value]


def resolve_template(nodes: list[TNode], evaluate: Evaluate) -> str:
    out: list[str] = []
    _resolve(nodes, evaluate, out)
    return "".join(out)


def _resolve(nodes: list[TNode], evaluate: Evaluate, out: list[str]) -> None:
    for node in nodes:
        if isinstance(node, TText):
            out.append(node.text)
        elif isinstance(node, TInterp):
            out.append(escape(format_value(evaluate(node.expr))))
        else:
            for branch in node.branches:
                if branch.condition is None or evaluate(branch.condition) is True:
                    _resolve(branch.body, evaluate, out)
                    break


# -- stage 2: styling ------------------------------------------------------------

COLORS: dict[str, str] = {
    name: name
    for name in (
        "black",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "white",
        "bright_black",
        "bright_red",
        "bright_green",
        "bright_yellow",
        "bright_blue",
        "bright_magenta",
        "bright_cyan",
        "bright_white",
    )
}
COLORS |= {
    "gray": "bright_black",
    "grey": "bright_black",
    "orange": "dark_orange",
    "purple": "purple",
    "gold": "gold1",
    "pink": "hot_pink",
}
TEXT_STYLES = {"bold", "italic", "underline", "dim"}
STYLE_NAMES = frozenset(COLORS) | TEXT_STYLES
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Timing effects. [pause N] waits; [type]/[type slow]/[type fast] and [glitch] wrap text.
EFFECT_TAGS = frozenset({"pause", "type", "glitch"})
# [type] uses the game's typing speed; [type N] a speed level 1-9 (see typing_speed.py).
TYPE_SPEEDS: dict[str | None, str] = {
    None: "type",
    "slow": "type_2",
    "fast": "type_8",
    **{str(level): f"type_{level}" for level in TYPING_CPS},
}
EFFECTS = frozenset({"glitch", *TYPE_SPEEDS.values()})
MAX_PAUSE = 30.0


def is_style_name(name: str) -> bool:
    return name.lower() in STYLE_NAMES or bool(_HEX_RE.match(name))


def is_tag_name(name: str) -> bool:
    """Anything that may appear as ``[name]`` / ``[/name]`` markup."""
    return is_style_name(name) or name.lower() in EFFECT_TAGS


def pause_seconds(arg: str | None) -> float | None:
    """Seconds for ``[pause]`` / ``[pause N]``; None if N isn't a sensible duration."""
    if arg is None:
        return 1.0
    try:
        seconds = float(arg)
    except ValueError:
        return None
    return seconds if 0 < seconds <= MAX_PAUSE else None


@dataclass(frozen=True, slots=True)
class StyledSpan:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    dim: bool = False
    color: str | None = None  # a rich color name or #rrggbb
    effect: str | None = None  # "glitch", "type" (game speed) or "type_1" … "type_9"
    pause: float = 0.0  # > 0: a pause marker (its text is empty)

    def rich_style(self) -> str:
        parts = [
            p
            for p, on in (
                ("bold", self.bold),
                ("italic", self.italic),
                ("underline", self.underline),
                ("dim", self.dim),
            )
            if on
        ]
        if self.color:
            parts.append(self.color)
        return " ".join(parts)

    def without_effects(self) -> StyledSpan:
        return StyledSpan(self.text, self.bold, self.italic, self.underline, self.dim, self.color)


Page = list[StyledSpan]

_TAG_RE = re.compile(r"\[(/?)([A-Za-z_]+|#[0-9a-fA-F]{6})?(?:[ \t]+([A-Za-z0-9_.]+))?\]")


@dataclass(slots=True)
class _Tok:
    kind: str  # "text", "star2", "star1", "open", "close", "pause"
    value: str
    style: str | None = None
    can_open: bool = False
    can_close: bool = False
    seconds: float = 0.0


def _opening_tag(name: str, arg: str | None) -> _Tok | None:
    """The token for ``[name arg]``, or None if it isn't valid markup."""
    lowered = name.lower()
    if arg is None and is_style_name(name):
        return _Tok("open", "", lowered)
    if lowered == "pause":
        seconds = pause_seconds(arg)
        return None if seconds is None else _Tok("pause", "", seconds=seconds)
    if lowered == "type":
        effect = TYPE_SPEEDS.get(arg.lower() if arg else None)
        return None if effect is None else _Tok("open", "", effect)
    if lowered == "glitch" and arg is None:
        return _Tok("open", "", "glitch")
    return None


def _tokenize_inline(text: str) -> list[_Tok]:
    toks: list[_Tok] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            toks.append(_Tok("text", "".join(buf)))
            buf.clear()

    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            buf.append(text[i + 1])
            i += 2
            continue
        if c == "*":
            width = 2 if text.startswith("**", i) else 1
            before = text[i - 1] if i > 0 else " "
            after = text[i + width] if i + width < n else " "
            flush()
            toks.append(
                _Tok(
                    "star2" if width == 2 else "star1",
                    "*" * width,
                    can_open=not after.isspace(),
                    can_close=not before.isspace(),
                )
            )
            i += width
            continue
        if c == "[":
            m = _TAG_RE.match(text, i)
            if m:
                closing, name, arg = m.group(1) == "/", m.group(2), m.group(3)
                if (
                    closing
                    and arg is None
                    and (name is None or is_style_name(name) or name.lower() in ("type", "glitch"))
                ):
                    flush()
                    toks.append(_Tok("close", m.group(0), name.lower() if name else None))
                    i = m.end()
                    continue
                tok = _opening_tag(name, arg) if not closing and name else None
                if tok is not None:
                    flush()
                    tok.value = m.group(0)
                    toks.append(tok)
                    i = m.end()
                    continue
        buf.append(c)
        i += 1
    flush()
    return toks


def _pair_stars(toks: list[_Tok], kind: str) -> set[int]:
    """Indexes of star markers that form matched pairs; the rest render literally."""
    matched: set[int] = set()
    opener: int | None = None
    for idx, tok in enumerate(toks):
        if tok.kind != kind:
            continue
        if opener is None:
            if tok.can_open:
                opener = idx
        elif tok.can_close:
            matched.update((opener, idx))
            opener = None
        elif tok.can_open:
            opener = idx
    return matched


def _closes(entry: str, name: str) -> bool:
    return entry == name or (name == "type" and entry.startswith("type"))


def _style_page(text: str) -> Page:
    toks = _tokenize_inline(text)
    active = _pair_stars(toks, "star2") | _pair_stars(toks, "star1")
    spans: Page = []
    bold = italic = False
    stack: list[str] = []

    def emit(s: str) -> None:
        if not s:
            return
        flags = set(stack)
        color = next(
            (
                COLORS.get(name, name)
                for name in reversed(stack)
                if name not in TEXT_STYLES and name not in EFFECTS
            ),
            None,
        )
        effect = next((name for name in reversed(stack) if name in EFFECTS), None)
        span = StyledSpan(
            s,
            bold=bold or "bold" in flags,
            italic=italic or "italic" in flags,
            underline="underline" in flags,
            dim="dim" in flags,
            color=color,
            effect=effect,
        )
        last = spans[-1] if spans else None
        if (
            last is not None
            and not last.pause
            and last.rich_style() == span.rich_style()
            and last.effect == span.effect
        ):
            spans[-1] = StyledSpan(
                last.text + s,
                span.bold,
                span.italic,
                span.underline,
                span.dim,
                span.color,
                span.effect,
            )
        else:
            spans.append(span)

    for idx, tok in enumerate(toks):
        if tok.kind == "text":
            emit(tok.value)
        elif tok.kind in ("star1", "star2"):
            if idx in active:
                if tok.kind == "star2":
                    bold = not bold
                else:
                    italic = not italic
            else:
                emit(tok.value)
        elif tok.kind == "pause":
            spans.append(StyledSpan("", pause=tok.seconds))
        elif tok.kind == "open":
            assert tok.style is not None
            stack.append(tok.style)
        else:  # close
            if tok.style is None:
                if stack:
                    stack.pop()
                else:
                    emit(tok.value)
                continue
            name = tok.style
            pos = next((i for i in range(len(stack) - 1, -1, -1) if _closes(stack[i], name)), None)
            if pos is None:
                emit(tok.value)
            else:
                del stack[pos]
    return spans


_PAGE_BREAK_RE = re.compile(r"^[ \t]*---[ \t]*$", re.MULTILINE)
_BLANK_RUN_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")


def _tidy(text: str) -> str:
    return _BLANK_RUN_RE.sub("\n\n", text).strip("\n").rstrip()


# A pause alone on its line shouldn't leave a blank line: it joins the next line
# (or, at the very end, the previous one).
_PAUSE_LINE_RE = re.compile(r"^[ \t]*(\[pause(?:[ \t]+[0-9.]+)?\])[ \t]*\n", re.M | re.I)
_PAUSE_END_RE = re.compile(r"\n[ \t]*(\[pause(?:[ \t]+[0-9.]+)?\])[ \t]*\Z", re.I)


def style(text: str) -> list[Page]:
    """Split resolved text into pages of styled spans. Empty pages are dropped."""
    pages = []
    for chunk in _PAGE_BREAK_RE.split(text):
        chunk = _PAUSE_END_RE.sub(r"\1", _PAUSE_LINE_RE.sub(r"\1", chunk))
        tidy = _tidy(chunk)
        if tidy.strip():
            pages.append(_style_page(tidy))
    return pages


def plain(pages: list[Page]) -> str:
    return "\n---\n".join("".join(s.text for s in page) for page in pages)


def render(text: str, evaluate: Evaluate) -> list[Page]:
    """Parse, resolve and style scene text in one go."""
    return style(resolve_template(parse_template(text), evaluate))


# -- references ------------------------------------------------------------------

_STYLE_TAG_LIKE_RE = re.compile(r"(?<!\\)\[/([A-Za-z_]+)\]")


def unknown_style_tags(text: str) -> list[tuple[str, int, int]]:
    """Closing tags like ``[/rde]`` that look like a mistyped style."""
    return [
        (m.group(1), m.start(), m.end())
        for m in _STYLE_TAG_LIKE_RE.finditer(text)
        if not is_tag_name(m.group(1))
    ]


_EFFECT_TAG_RE = re.compile(r"(?<!\\)\[(pause|type|glitch)(?:[ \t]+([^\]\n]*))?\]", re.I)


def effect_tag_problems(text: str) -> list[tuple[str, int, int]]:
    """Effect tags that won't work (they would show up as plain text)."""
    problems = []
    for m in _EFFECT_TAG_RE.finditer(text):
        name, arg = m.group(1).lower(), m.group(2)
        arg = arg.strip() if arg is not None else None
        if name == "pause" and pause_seconds(arg) is None:
            problems.append(
                (
                    f"[pause] needs a number of seconds up to {MAX_PAUSE:g}, e.g. [pause 2]",
                    m.start(),
                    m.end(),
                )
            )
        elif name == "type" and (arg.lower() if arg else None) not in TYPE_SPEEDS:
            problems.append(
                (
                    "use [type] for the game's speed, or [type 1] (slowest) to [type 9] (fastest)",
                    m.start(),
                    m.end(),
                )
            )
        elif name == "glitch" and arg:
            problems.append(("[glitch] doesn't take a setting", m.start(), m.end()))
    return problems


def rename_in_markup(text: str, kind: RefKind, old: str, new: str) -> str:
    try:
        nodes = parse_template(text)
    except ExprError:
        return text
    spans = []
    for expr, offset, _ in template_expressions(nodes):
        spans.extend(
            (span.shift(offset), style_) for span, style_ in reference_spans(expr, kind, old)
        )
    return apply_renames(text, spans, new)
