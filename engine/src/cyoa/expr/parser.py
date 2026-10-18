"""Lexer and recursive-descent parser for conditions and effects.

Grammar::

    program    := [statement ((";" | NEWLINE) statement)*]
    statement  := NAME assign_op expr | call
    expr       := or_expr
    or_expr    := and_expr ("or" and_expr)*
    and_expr   := not_expr ("and" not_expr)*
    not_expr   := "not" not_expr | comparison
    comparison := additive [compare_op additive]
    additive   := term (("+" | "-") term)*
    term       := unary (("*" | "/" | "%") unary)*
    unary      := "-" unary | primary
    primary    := NUMBER | STRING | "true" | "false" | NAME | NAME "(" [args] ")" | "(" expr ")"
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ExprError
from .nodes import (
    Assign,
    Binary,
    Bool,
    Call,
    Expr,
    Name,
    Number,
    Program,
    Span,
    Stmt,
    Str,
    Unary,
)

KEYWORDS = frozenset({"and", "or", "not", "true", "false"})
COMPARE_OPS = frozenset({"==", "!=", "<", "<=", ">", ">="})
ASSIGN_OPS = frozenset({"=", "+=", "-=", "*=", "/="})
_TWO_CHAR_OPS = ("==", "!=", "<=", ">=", "+=", "-=", "*=", "/=")
_ONE_CHAR_OPS = "<>=+-*/%(),;"
_FRIENDLY = {
    "&&": "use 'and' instead of '&&'",
    "||": "use 'or' instead of '||'",
    "!": "use 'not' instead of '!'",
    "&": "use 'and' instead of '&'",
    "|": "use 'or' instead of '|'",
}


@dataclass(frozen=True, slots=True)
class Token:
    kind: str  # NUM, STR, NAME, KW, OP, NEWLINE, EOF
    value: str
    start: int
    end: int
    number: int | float = 0


def tokenize(src: str, *, newlines: bool) -> list[Token]:
    """Split ``src`` into tokens.

    When ``newlines`` is true, line breaks outside parentheses become NEWLINE
    tokens (statement separators); otherwise they are plain whitespace.
    """
    tokens: list[Token] = []
    i = 0
    depth = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\n":
            if newlines and depth == 0:
                tokens.append(Token("NEWLINE", "\n", i, i + 1))
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "#":
            while i < n and src[i] != "\n":
                i += 1
        elif c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            start = i
            while i < n and src[i].isdigit():
                i += 1
            is_float = False
            if i < n and src[i] == "." and i + 1 < n and src[i + 1].isdigit():
                is_float = True
                i += 1
                while i < n and src[i].isdigit():
                    i += 1
            if i < n and (src[i].isalpha() or src[i] == "_"):
                raise ExprError("a name can't start with a digit", start, i + 1)
            text = src[start:i]
            value: int | float = float(text) if is_float else int(text)
            tokens.append(Token("NUM", text, start, i, value))
        elif c in "\"'":
            start = i
            quote = c
            i += 1
            chars: list[str] = []
            while True:
                if i >= n or src[i] == "\n":
                    raise ExprError("unterminated text: missing closing quote", start, i)
                ch = src[i]
                if ch == "\\" and i + 1 < n:
                    chars.append(src[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    i += 1
                    break
                chars.append(ch)
                i += 1
            tokens.append(Token("STR", "".join(chars), start, i))
        elif c.isalpha() or c == "_":
            start = i
            while i < n and (src[i].isalnum() or src[i] == "_"):
                i += 1
            word = src[start:i]
            tokens.append(Token("KW" if word in KEYWORDS else "NAME", word, start, i))
        else:
            two = src[i : i + 2]
            if two in _FRIENDLY:
                raise ExprError(_FRIENDLY[two], i, i + 2)
            if two in _TWO_CHAR_OPS:
                tokens.append(Token("OP", two, i, i + 2))
                i += 2
                continue
            if c in _FRIENDLY:
                raise ExprError(_FRIENDLY[c], i, i + 1)
            if c in _ONE_CHAR_OPS:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth = max(0, depth - 1)
                tokens.append(Token("OP", c, i, i + 1))
                i += 1
                continue
            raise ExprError(f"unexpected character {c!r}", i, i + 1)
    tokens.append(Token("EOF", "", n, n))
    return tokens


class _Parser:
    def __init__(self, src: str, tokens: list[Token]) -> None:
        self.src = src
        self.tokens = tokens
        self.pos = 0

    # -- helpers -----------------------------------------------------------

    @property
    def tok(self) -> Token:
        return self.tokens[self.pos]

    def peek(self, offset: int = 1) -> Token:
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    def is_op(self, *ops: str) -> bool:
        return self.tok.kind == "OP" and self.tok.value in ops

    def is_kw(self, word: str) -> bool:
        return self.tok.kind == "KW" and self.tok.value == word

    def expect_op(self, op: str, message: str) -> Token:
        if not self.is_op(op):
            raise self.error_here(message)
        return self.advance()

    def error_here(self, message: str) -> ExprError:
        tok = self.tok
        if tok.kind == "EOF":
            end = len(self.src)
            return ExprError(message, max(0, end - 1) if end else 0, max(end, 1))
        return ExprError(message, tok.start, tok.end)

    # -- programs ------------------------------------------------------------

    def program(self) -> Program:
        statements: list[Stmt] = []
        while True:
            while self.tok.kind == "NEWLINE" or self.is_op(";"):
                self.advance()
            if self.tok.kind == "EOF":
                break
            statements.append(self.statement())
            if not (self.tok.kind in ("NEWLINE", "EOF") or self.is_op(";")):
                raise self.error_here("expected a new line or ';' between effects")
        return Program(tuple(statements))

    def statement(self) -> Stmt:
        tok = self.tok
        nxt = self.peek()
        if tok.kind == "NAME" and nxt.kind == "OP" and nxt.value in ASSIGN_OPS:
            self.advance()
            op = self.advance().value
            if self.tok.kind in ("NEWLINE", "EOF") or self.is_op(";"):
                raise self.error_here(f"missing value after '{op}'")
            value = self.expr()
            return Assign(
                tok.value, op, value, Span(tok.start, tok.end), Span(tok.start, _end(value))
            )
        if tok.kind == "KW" and nxt.kind == "OP" and nxt.value in ASSIGN_OPS:
            raise ExprError(
                f"'{tok.value}' is a reserved word and can't be changed", tok.start, tok.end
            )
        start = tok.start
        expr = self.expr()
        if isinstance(expr, Call):
            return expr
        if isinstance(expr, Binary) and expr.op == "==":
            raise ExprError(
                "this compares values; to change a variable use '=' (e.g. gold = 10)",
                start,
                _end(expr),
            )
        raise ExprError('expected an effect, e.g. gold -= 10 or give("rope")', start, _end(expr))

    # -- expressions -----------------------------------------------------------

    def expr(self) -> Expr:
        return self.or_expr()

    def or_expr(self) -> Expr:
        left = self.and_expr()
        while self.is_kw("or"):
            self.advance()
            right = self.and_expr()
            left = Binary("or", left, right, Span(_start(left), _end(right)))
        return left

    def and_expr(self) -> Expr:
        left = self.not_expr()
        while self.is_kw("and"):
            self.advance()
            right = self.not_expr()
            left = Binary("and", left, right, Span(_start(left), _end(right)))
        return left

    def not_expr(self) -> Expr:
        if self.is_kw("not"):
            tok = self.advance()
            operand = self.not_expr()
            return Unary("not", operand, Span(tok.start, _end(operand)))
        return self.comparison()

    def comparison(self) -> Expr:
        left = self.additive()
        if self.is_op("="):
            raise self.error_here("use '==' to compare values ('=' changes a variable)")
        if self.tok.kind == "OP" and self.tok.value in COMPARE_OPS:
            op = self.advance().value
            right = self.additive()
            node = Binary(op, left, right, Span(_start(left), _end(right)))
            if self.tok.kind == "OP" and self.tok.value in COMPARE_OPS:
                raise self.error_here(
                    "chained comparisons aren't supported; write a < b and b < c instead"
                )
            return node
        return left

    def additive(self) -> Expr:
        left = self.term()
        while self.is_op("+", "-"):
            op = self.advance().value
            right = self.term()
            left = Binary(op, left, right, Span(_start(left), _end(right)))
        return left

    def term(self) -> Expr:
        left = self.unary()
        while self.is_op("*", "/", "%"):
            op = self.advance().value
            right = self.unary()
            left = Binary(op, left, right, Span(_start(left), _end(right)))
        return left

    def unary(self) -> Expr:
        if self.is_op("-"):
            tok = self.advance()
            operand = self.unary()
            if isinstance(operand, Number):
                return Number(-operand.value, Span(tok.start, operand.span.end))
            return Unary("-", operand, Span(tok.start, _end(operand)))
        return self.primary()

    def primary(self) -> Expr:
        tok = self.tok
        if tok.kind == "NUM":
            self.advance()
            return Number(tok.number, Span(tok.start, tok.end))
        if tok.kind == "STR":
            self.advance()
            return Str(tok.value, Span(tok.start, tok.end))
        if tok.kind == "KW" and tok.value in ("true", "false"):
            self.advance()
            return Bool(tok.value == "true", Span(tok.start, tok.end))
        if tok.kind == "NAME":
            self.advance()
            if self.is_op("("):
                self.advance()
                args: list[Expr] = []
                if not self.is_op(")"):
                    while True:
                        args.append(self.expr())
                        if self.is_op(","):
                            self.advance()
                            continue
                        break
                close = self.expect_op(")", f"missing ')' to close {tok.value}(")
                return Call(
                    tok.value, tuple(args), Span(tok.start, tok.end), Span(tok.start, close.end)
                )
            return Name(tok.value, Span(tok.start, tok.end))
        if self.is_op("("):
            self.advance()
            inner = self.expr()
            self.expect_op(")", "missing ')'")
            return inner
        if tok.kind == "EOF":
            raise self.error_here("incomplete expression")
        if tok.kind == "KW":
            raise self.error_here(f"unexpected '{tok.value}'")
        if tok.kind == "NEWLINE":
            raise self.error_here("incomplete expression")
        raise self.error_here(f"unexpected '{tok.value}'")


def _start(node: Expr) -> int:
    return node.span.start


def _end(node: Expr) -> int:
    return node.span.end


def parse_expression(src: str) -> Expr:
    """Parse a single expression (a condition or an interpolated value)."""
    tokens = tokenize(src, newlines=False)
    parser = _Parser(src, tokens)
    if parser.tok.kind == "EOF":
        raise ExprError("empty expression", 0, max(1, len(src)))
    expr = parser.expr()
    if parser.tok.kind != "EOF":
        if parser.tok.kind == "OP" and parser.tok.value in ASSIGN_OPS:
            raise parser.error_here("use '==' to compare values ('=' changes a variable)")
        raise parser.error_here(f"unexpected '{parser.tok.value}'")
    return expr


def parse_program(src: str) -> Program:
    """Parse a list of effects (statements). Empty source gives an empty program."""
    tokens = tokenize(src, newlines=True)
    return _Parser(src, tokens).program()
