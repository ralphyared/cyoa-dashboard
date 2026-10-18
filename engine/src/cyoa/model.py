"""The game file format.

The model is deliberately permissive about ids and expression text: structural
problems (bad JSON, wrong field types) are rejected on load, while everything an
author can get wrong while writing is reported by :mod:`cyoa.validate`.
"""

from __future__ import annotations

import json
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .expr import Type

FORMAT_VERSION = 1

VarType = Type
Value = int | float | bool | str


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=False)


class Variable(_Model):
    name: str
    type: VarType = VarType.NUMBER
    initial: bool | int | float | str = 0
    min: int | float | str | None = None
    max: int | float | str | None = None
    label: str = ""

    @property
    def display_label(self) -> str:
        return self.label or self.name.replace("_", " ").capitalize()


class Item(_Model):
    id: str
    name: str = ""
    description: str = ""
    stackable: bool = False

    @property
    def display_name(self) -> str:
        return self.name or self.id.replace("_", " ").capitalize()


class Rule(_Model):
    id: str = ""
    name: str = ""
    condition: str = ""
    effects: str = ""
    goto: str | None = None


class Chapter(_Model):
    id: str
    title: str = ""
    color: str | None = None


class EndingKind(StrEnum):
    DEATH = "death"
    VICTORY = "victory"
    NEUTRAL = "neutral"


class Ending(_Model):
    kind: EndingKind = EndingKind.NEUTRAL
    title: str = ""


class LockedMode(StrEnum):
    HIDE = "hide"
    SHOW = "show"


class Choice(_Model):
    id: str = ""
    text: str = ""
    target: str = ""
    condition: str = ""
    when_locked: LockedMode = LockedMode.HIDE
    hint: str = ""
    effects: str = ""
    once: bool = False


class Scene(_Model):
    id: str
    title: str = ""
    chapter: str | None = None
    text: str = ""
    art: str = ""
    on_enter: str = ""
    choices: list[Choice] = Field(default_factory=list)
    ending: Ending | None = None
    tags: list[str] = Field(default_factory=list)
    # Author-only fields: kept in project exports, stripped from player exports.
    notes: str = ""
    position: tuple[float, float] | None = None


class Settings(_Model):
    title_art: str = ""
    intro: str = ""
    accent_color: str = "cyan"
    status_format: str = ""
    show_scene_titles: bool = False
    text_width: int = Field(default=80, ge=40, le=200)
    typewriter: bool = False


class Game(_Model):
    format: int = FORMAT_VERSION
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str = "Untitled"
    author: str = ""
    description: str = ""
    version: str = "1.0"
    start_scene: str = ""
    settings: Settings = Field(default_factory=Settings)
    variables: list[Variable] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)

    @model_validator(mode="after")
    def _assign_missing_ids(self) -> Game:
        """Give choices and rules stable ids when a hand-written file omits them."""
        for scene in self.scenes:
            taken = {c.id for c in scene.choices if c.id}
            for i, choice in enumerate(scene.choices, start=1):
                if not choice.id:
                    candidate = f"c{i}"
                    while candidate in taken:
                        candidate += "_"
                    choice.id = candidate
                    taken.add(candidate)
        taken = {r.id for r in self.rules if r.id}
        for i, rule in enumerate(self.rules, start=1):
            if not rule.id:
                candidate = f"r{i}"
                while candidate in taken:
                    candidate += "_"
                rule.id = candidate
                taken.add(candidate)
        return self

    def scene(self, scene_id: str) -> Scene | None:
        return next((s for s in self.scenes if s.id == scene_id), None)

    def to_player_dict(self) -> dict[str, Any]:
        """The game as shipped to players: author notes and graph positions removed."""
        data = self.model_dump(mode="json")
        for scene in data["scenes"]:
            scene.pop("notes", None)
            scene.pop("position", None)
        return data

    def to_project_dict(self) -> dict[str, Any]:
        """Everything, for backups and moving a game between dashboards."""
        return self.model_dump(mode="json")


class GameFileError(Exception):
    """The file isn't a readable game."""


def _format_validation_error(error: ValidationError) -> str:
    lines = []
    for err in error.errors()[:10]:
        where = ".".join(str(p) for p in err["loc"]) or "(top level)"
        lines.append(f"  {where}: {err['msg']}")
    more = len(error.errors()) - 10
    if more > 0:
        lines.append(f"  ... and {more} more")
    return "\n".join(lines)


def game_from_dict(data: Any) -> Game:
    if not isinstance(data, dict):
        raise GameFileError("not a game file: expected a JSON object")
    fmt = data.get("format", FORMAT_VERSION)
    if isinstance(fmt, int) and fmt > FORMAT_VERSION:
        raise GameFileError(
            f"this game was made with a newer version (format {fmt}); please update the player"
        )
    try:
        return Game.model_validate(data)
    except ValidationError as e:
        raise GameFileError(
            "the game file has invalid fields:\n" + _format_validation_error(e)
        ) from e


def game_from_text(text: str, source: str = "the game file") -> Game:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise GameFileError(f"{source} is not valid JSON (line {e.lineno}: {e.msg})") from e
    return game_from_dict(data)


def load_game(path: str | Path) -> Game:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise GameFileError(f"can't read {path}: {e.strerror or e}") from e
    return game_from_text(text, str(path))
