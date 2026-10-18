"""FastAPI dependencies shared by the routers."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from .config import Config
from .db import Database


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_db(request: Request) -> Iterator[Session]:
    yield from get_database(request).session()
