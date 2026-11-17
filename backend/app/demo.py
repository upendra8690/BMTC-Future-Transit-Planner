"""Demonstration mode: invented (SYNTHETIC_DEMO) timetables are served only by a server started with DEMO_MODE=1.

The public service runs with demonstration mode off. A passenger then sees only real information: official data, or
real services from a clearly labelled community source. Invented data never stands in for missing real data. A
demonstration server, for development and presentations, runs the same code with DEMO_MODE=1 and shows a banner on
every screen.

Middleware in main.py sets the mode for each request. Code that runs outside a request (import scripts, tests that call
services directly) sees no restriction, because no request asked for one.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

from sqlalchemy import select, true
from sqlalchemy.sql.elements import ColumnElement

from .models import KIND_SYNTHETIC, DataSource, GtfsImport

_DEMO: ContextVar[bool | None] = ContextVar("demo_mode", default=None)


def enter(enabled: bool) -> Token:
    """Set the mode for the current request. Pass the returned token to leave() when the request ends."""
    return _DEMO.set(enabled)


def leave(token: Token) -> None:
    _DEMO.reset(token)


def demo_hidden() -> bool:
    """True when the current request comes to a server running with demonstration mode off."""
    return _DEMO.get() is False


def served_imports() -> ColumnElement[bool]:
    """SQL condition on GtfsImport: true for every import the current request may read."""
    if not demo_hidden():
        return true()
    synthetic = select(DataSource.id).where(DataSource.kind == KIND_SYNTHETIC)
    return GtfsImport.data_source_id.not_in(synthetic)
