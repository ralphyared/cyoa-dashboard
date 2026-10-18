from __future__ import annotations


class ExprError(Exception):
    """A syntax or type error, located by character offsets into the source."""

    def __init__(self, message: str, start: int = 0, end: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.start = start
        self.end = start + 1 if end is None else end

    def shift(self, offset: int) -> ExprError:
        return ExprError(self.message, self.start + offset, self.end + offset)

    def __repr__(self) -> str:
        return f"ExprError({self.message!r}, {self.start}, {self.end})"


class EvalError(Exception):
    """Raised when evaluating an expression fails at runtime (e.g. division by zero)."""
