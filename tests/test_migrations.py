"""Schema migrations: a new database reaches head and matches the models, the migration can be reversed and
re-applied, and a database built by an earlier version is stamped at the baseline with its rows kept."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.database import Base, Database
from app.schema_migrations import BASELINE_REVISION, current_revision, head_revision
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

PROJECT_DIR = Path(__file__).resolve().parents[1]


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _table_names(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    """Run the real alembic command, as an administrator would from the project folder."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_new_database_reaches_head_and_matches_the_models(tmp_path):
    path = tmp_path / "new.db"
    db = Database(_url(path))
    try:
        assert db.create_schema() == BASELINE_REVISION
        assert current_revision(db.engine) == head_revision() == BASELINE_REVISION
        with db.engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        db.dispose()
    assert differences == [], differences
    assert set(Base.metadata.tables) <= _table_names(path)


def test_running_the_upgrade_again_changes_nothing(tmp_path):
    path = tmp_path / "again.db"
    db = Database(_url(path))
    try:
        db.create_schema()
        tables_before = _table_names(path)
        assert db.create_schema() == BASELINE_REVISION
        assert current_revision(db.engine) == BASELINE_REVISION
    finally:
        db.dispose()
    assert _table_names(path) == tables_before


def test_database_built_before_migrations_is_stamped_and_keeps_its_rows(tmp_path):
    path = tmp_path / "legacy.db"
    engine = create_engine(_url(path), poolclass=NullPool)
    try:
        Base.metadata.create_all(engine)  # what earlier builds did at start-up
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO data_sources (name, publisher, license, kind, verified, created_at) "
                "VALUES ('Legacy source', 'Test publisher', 'test', 'UNKNOWN', 0, '2026-01-01 00:00:00')"
            )
    finally:
        engine.dispose()
    assert "alembic_version" not in _table_names(path)

    db = Database(_url(path))
    try:
        assert db.create_schema() == BASELINE_REVISION
        assert current_revision(db.engine) == BASELINE_REVISION
        with db.engine.connect() as connection:
            rows = connection.exec_driver_sql("SELECT COUNT(*) FROM data_sources").scalar()
    finally:
        db.dispose()
    assert rows == 1


def test_alembic_command_upgrades_downgrades_and_upgrades_again(tmp_path):
    path = tmp_path / "cli.db"
    url = _url(path)

    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    check = _alembic(url, "check")
    assert check.returncode == 0, check.stdout + check.stderr

    down = _alembic(url, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    assert not (set(Base.metadata.tables) & _table_names(path))

    again = _alembic(url, "upgrade", "head")
    assert again.returncode == 0, again.stderr
    assert set(Base.metadata.tables) <= _table_names(path)
