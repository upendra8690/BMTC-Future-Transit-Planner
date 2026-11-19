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
from app.schema_migrations import current_revision, head_revision
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

PROJECT_DIR = Path(__file__).resolve().parents[1]
# Tables that migrations 0002 to 0006 added. Earlier builds never had them, so a simulated old database
# leaves them out.
FARE_TABLES = {"fare_attributes", "fare_rules"}
ANNOUNCEMENT_TABLES = {"transport_announcements", "transport_announcement_changes"}
ACCOUNT_TABLES = {"users", "user_sessions", "user_saved_journeys", "notification_preferences"}
NOTICE_TABLES = {"service_notices"}
COMMERCE_TABLES = {"orders", "payments", "travel_tickets", "refunds", "payment_notifications"}
LATER_TABLES = FARE_TABLES | ANNOUNCEMENT_TABLES | ACCOUNT_TABLES | NOTICE_TABLES | COMMERCE_TABLES


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
        assert db.create_schema() == head_revision()
        assert current_revision(db.engine) == head_revision() == "0006"
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
        assert db.create_schema() == head_revision()
        assert current_revision(db.engine) == head_revision()
    finally:
        db.dispose()
    assert _table_names(path) == tables_before


def test_database_built_before_migrations_is_stamped_and_keeps_its_rows(tmp_path):
    path = tmp_path / "legacy.db"
    engine = create_engine(_url(path), poolclass=NullPool)
    try:
        # What earlier builds did at start-up: the baseline tables only, with no version table.
        baseline_tables = [t for t in Base.metadata.sorted_tables if t.name not in LATER_TABLES]
        Base.metadata.create_all(engine, tables=baseline_tables)
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
        assert db.create_schema() == head_revision()
        assert current_revision(db.engine) == head_revision()
        with db.engine.connect() as connection:
            rows = connection.exec_driver_sql("SELECT COUNT(*) FROM data_sources").scalar()
    finally:
        db.dispose()
    assert rows == 1
    assert _table_names(path) >= LATER_TABLES


def test_a_version_two_database_gains_the_fare_tables_and_keeps_every_row(tmp_path):
    """The real upgrade path: a database at revision 0001 with records in it, then the server starts on the head."""
    path = tmp_path / "v2.db"
    url = _url(path)
    assert _alembic(url, "upgrade", "0001").returncode == 0
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO data_sources (name, publisher, license, kind, verified, created_at) "
            "VALUES ('Kept source', 'Test publisher', 'test', 'UNKNOWN', 0, '2026-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO audit_logs (created_at, actor, action, entity, entity_id, detail, ip) "
            "VALUES ('2026-01-01 00:00:00', 'admin', 'test.kept', 'x', NULL, '{}', NULL)"
        )
        conn.commit()
    finally:
        conn.close()
    assert FARE_TABLES.isdisjoint(_table_names(path))

    db = Database(url)
    try:
        assert db.create_schema() == head_revision() == "0006"
    finally:
        db.dispose()
    assert _table_names(path) >= LATER_TABLES
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM data_sources WHERE name = 'Kept source'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'test.kept'").fetchone()[0] == 1
    finally:
        conn.close()


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
