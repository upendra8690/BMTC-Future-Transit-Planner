"""Database maintenance: read-only health checks, consistent SQLite backups and backup verification.

The admin backup endpoint and the scripts in scripts/ share these functions. SQLite is supported in full. For other
databases (PostgreSQL is untested in this build) only the connection and migration checks run, and backups should use
that database's own tools such as pg_dump.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Any

from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from .. import models  # noqa: F401  (registers every table on Base.metadata)
from ..database import Base, normalise_url
from ..models import utcnow
from ..schema_migrations import head_revision


class MaintenanceError(RuntimeError):
    """A maintenance step could not be completed. The message is safe to show to an administrator."""


def sqlite_file(database_url: str) -> Path | None:
    """The database file behind a SQLite URL. None for other databases and for in-memory databases."""
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database).resolve()


def expected_tables() -> list[str]:
    return sorted(Base.metadata.tables)


def _read_only_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _sqlite_revision(conn: sqlite3.Connection) -> str | None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'").fetchone() is None:
        return None
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row else None


def _count_statement(name: str) -> str:
    """SQL that counts one planner table. SQLAlchemy builds it from the model metadata, so the name is quoted."""
    table = Base.metadata.tables[name]
    return str(select(func.count()).select_from(table).compile(dialect=sqlite_dialect.dialect()))


def _sqlite_counts(conn: sqlite3.Connection) -> dict[str, int | None]:
    """Row count per planner table. None means the table is missing."""
    present = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    counts: dict[str, int | None] = {}
    for name in expected_tables():
        if name in present:
            counts[name] = conn.execute(_count_statement(name)).fetchone()[0]
        else:
            counts[name] = None
    return counts


def _free_name(folder: Path, stem: str) -> Path:
    candidate = folder / f"{stem}.db"
    number = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{number}.db"
        number += 1
    return candidate


def backup_sqlite(source: Path, backup_dir: Path, *, when: dt.datetime) -> Path:
    """Copy a live SQLite database with SQLite's online backup API. Safe while the server is running.

    The copy is written as one self-contained file (journal mode DELETE), so copying that file is enough to keep it.
    A copy that fails part-way is removed and reported as MaintenanceError, whether SQLite or the file system failed.
    """
    if not source.is_file():
        raise MaintenanceError(f"Database file not found: {source.name}")
    target: Path | None = None
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = _free_name(backup_dir, f"planner_backup_{when:%Y%m%d_%H%M%S}")
        src = sqlite3.connect(_read_only_uri(source), uri=True)
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
                dst.execute("PRAGMA journal_mode=DELETE").fetchall()
            finally:
                dst.close()
        finally:
            src.close()
    except (sqlite3.Error, OSError) as exc:
        if target is not None:
            target.unlink(missing_ok=True)
        raise MaintenanceError(f"The backup could not be written: {exc}") from exc
    return target


def verify_backup(path: Path) -> dict[str, Any]:
    """Open a backup read-only and confirm it is intact and complete. Raises MaintenanceError when it is not."""
    if not path.is_file():
        raise MaintenanceError(f"Backup file not found: {path.name}")
    try:
        conn = sqlite3.connect(_read_only_uri(path), uri=True)
        try:
            integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
            counts = _sqlite_counts(conn)
            revision = _sqlite_revision(conn)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise MaintenanceError(f"Backup {path.name} is not a readable SQLite database.") from exc
    if integrity != ["ok"]:
        raise MaintenanceError(f"Backup {path.name} failed the integrity check.")
    missing = [name for name, count in counts.items() if count is None]
    if missing:
        raise MaintenanceError(f"Backup {path.name} is missing tables: {', '.join(missing)}")
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "integrity": "ok",
        "revision": revision,
        "row_counts": counts,
    }


def backup_and_verify(source: Path, backup_dir: Path, *, when: dt.datetime | None = None) -> dict[str, Any]:
    """Back up, then verify the copy. A copy that fails verification is deleted and the error is raised."""
    target = backup_sqlite(source, backup_dir, when=when or utcnow())
    try:
        report = verify_backup(target)
    except MaintenanceError:
        target.unlink(missing_ok=True)
        raise
    report["path"] = str(target)
    report["directory"] = str(backup_dir)
    return report


def check_database(database_url: str) -> dict[str, Any]:
    """Read-only health check. It never writes to the database, and it never creates a missing SQLite file.

    The report's "ok" field is True only when "problems" is empty.
    """
    backend = make_url(database_url).get_backend_name()
    report: dict[str, Any] = {
        "backend": backend,
        "checked_at": utcnow().isoformat() + "Z",
        "problems": [],
        "notes": [],
    }
    path = sqlite_file(database_url)
    if path is not None:
        report["file"] = path.name
        if not path.is_file():
            report["problems"].append("The database file does not exist yet. Run scripts/migrate_database.py first.")
            report["ok"] = False
            return report
        conn = sqlite3.connect(_read_only_uri(path), uri=True)
        try:
            integrity = [row[0] for row in conn.execute("PRAGMA integrity_check")]
            foreign_key_problems = conn.execute("PRAGMA foreign_key_check").fetchall()
            revision = _sqlite_revision(conn)
            counts = _sqlite_counts(conn)
        finally:
            conn.close()
        report["integrity"] = integrity
        report["foreign_key_violations"] = len(foreign_key_problems)
        report["row_counts"] = counts
        missing = [name for name, count in counts.items() if count is None]
        if integrity != ["ok"]:
            report["problems"].append("The integrity check reported errors. Restore from a verified backup.")
        if foreign_key_problems:
            report["problems"].append(f"{len(foreign_key_problems)} foreign key violation(s) found.")
        if missing:
            report["problems"].append("Tables are missing: " + ", ".join(missing))
    else:
        engine = create_engine(normalise_url(database_url), poolclass=NullPool)
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
                revision = MigrationContext.configure(connection).get_current_revision()
                existing = set(inspect(connection).get_table_names())
        finally:
            engine.dispose()
        missing = [name for name in expected_tables() if name not in existing]
        if missing:
            report["problems"].append("Tables are missing: " + ", ".join(missing))
        report["notes"].append(
            "Only the connection and migration checks run for this database. This build tests SQLite only."
        )

    head = head_revision()
    report["head_revision"] = head
    report["revision"] = revision
    if revision is None:
        report["problems"].append("No migration version is recorded. Run scripts/migrate_database.py.")
    elif revision != head:
        report["problems"].append(
            f"The schema is at revision {revision} but the code expects {head}. Run scripts/migrate_database.py."
        )
    report["ok"] = not report["problems"]
    return report
