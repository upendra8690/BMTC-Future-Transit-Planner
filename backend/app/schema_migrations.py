"""Keeps the database schema in step with the code, using the Alembic migrations in migrations/.

The server calls upgrade_to_head on every start-up. When the database is already current, that does nothing.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

PROJECT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_DIR / "alembic.ini"
MIGRATIONS_DIR = PROJECT_DIR / "migrations"

# The first migration describes the schema that earlier builds created with create_all.
BASELINE_REVISION = "0001"
# A table every earlier build created. Its presence without a version table means "built before migrations".
LEGACY_MARKER_TABLE = "data_sources"


def _config(connection: Connection | None = None) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def head_revision() -> str:
    head = ScriptDirectory.from_config(_config()).get_current_head()
    if head is None:
        raise RuntimeError("No migration scripts were found in the migrations/versions folder.")
    return head


def current_revision(engine: Engine) -> str | None:
    """The revision the database is at, or None when no migration has been applied."""
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def upgrade_to_head(engine: Engine) -> str:
    """Apply every migration the database has not run yet. Returns the head revision.

    A database built by an earlier version has the application tables but no version table. Those tables
    match the baseline, so the database is stamped at the baseline first and only later migrations run.
    """
    with engine.begin() as connection:
        existing = set(inspect(connection).get_table_names())
        cfg = _config(connection)
        if "alembic_version" not in existing and LEGACY_MARKER_TABLE in existing:
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
    return head_revision()
