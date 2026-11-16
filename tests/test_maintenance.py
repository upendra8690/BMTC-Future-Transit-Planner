"""Database maintenance: read-only checks, verified SQLite backups and the scripts that wrap them."""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.database import Base, Database
from app.schema_migrations import head_revision
from app.services import maintenance
from app.services.maintenance import (
    MaintenanceError,
    backup_and_verify,
    backup_sqlite,
    check_database,
    sqlite_file,
    verify_backup,
)
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_DIR / "scripts"
WHEN = dt.datetime(2026, 11, 15, 10, 0, 0)


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def planner_db(tmp_path) -> Path:
    """A migrated database with two rows, so that a backup has something real to copy."""
    path = tmp_path / "planner.db"
    db = Database(_url(path))
    try:
        db.create_schema()
    finally:
        db.dispose()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO data_sources (name, publisher, license, kind, verified, created_at) "
            "VALUES ('Source A', 'Publisher', 'test', 'UNKNOWN', 0, '2026-11-15 10:00:00')"
        )
        conn.execute(
            "INSERT INTO audit_logs (created_at, actor, action, entity) "
            "VALUES ('2026-11-15 10:00:00', 'test', 'seed', 'data_source')"
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _script(name: str, database_url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        cwd=PROJECT_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


# ---------------------------------------------------------------- checks

def test_check_passes_for_a_migrated_database(planner_db):
    report = check_database(_url(planner_db))
    assert report["ok"] is True, report["problems"]
    assert report["revision"] == report["head_revision"] == head_revision()
    assert report["integrity"] == ["ok"]
    assert report["foreign_key_violations"] == 0
    assert report["row_counts"]["data_sources"] == 1


def test_check_never_creates_a_missing_database(tmp_path):
    path = tmp_path / "absent.db"
    report = check_database(_url(path))
    assert report["ok"] is False
    assert any("does not exist" in problem for problem in report["problems"])
    assert not path.exists()


def test_check_flags_a_database_built_without_migrations(tmp_path):
    path = tmp_path / "unstamped.db"
    engine = create_engine(_url(path), poolclass=NullPool)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    report = check_database(_url(path))
    assert report["ok"] is False
    assert any("No migration version" in problem for problem in report["problems"])


def test_check_reports_a_foreign_key_violation(planner_db):
    conn = sqlite3.connect(planner_db)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO routes (import_id, gtfs_route_id, route_type) VALUES (999, 'ORPHAN', 3)")
        conn.commit()
    finally:
        conn.close()
    report = check_database(_url(planner_db))
    assert report["ok"] is False
    assert report["foreign_key_violations"] == 1


def test_sqlite_file_recognises_only_file_databases(tmp_path):
    assert sqlite_file(_url(tmp_path / "a.db")) == (tmp_path / "a.db").resolve()
    assert sqlite_file("sqlite:///:memory:") is None
    assert sqlite_file("postgresql+psycopg://user:secret@localhost/planner") is None


# ---------------------------------------------------------------- backups

def test_backup_copies_every_table_and_is_verified(planner_db, tmp_path):
    folder = tmp_path / "backups"
    report = backup_and_verify(planner_db, folder, when=WHEN)
    target = folder / report["file"]
    assert target.name == "planner_backup_20261115_100000.db"
    assert target.is_file()
    assert report["integrity"] == "ok"
    assert report["revision"] == head_revision()
    assert report["row_counts"] == check_database(_url(planner_db))["row_counts"]
    assert report["row_counts"]["data_sources"] == 1
    assert report["row_counts"]["audit_logs"] == 1


def test_backup_is_one_self_contained_file(planner_db, tmp_path):
    target = backup_sqlite(planner_db, tmp_path / "backups", when=WHEN)
    conn = sqlite3.connect(target)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode == "delete"


def test_second_backup_in_the_same_second_gets_its_own_file(planner_db, tmp_path):
    folder = tmp_path / "backups"
    first = backup_sqlite(planner_db, folder, when=WHEN)
    second = backup_sqlite(planner_db, folder, when=WHEN)
    assert first != second
    assert first.is_file()
    assert second.is_file()
    assert second.name.endswith("_2.db")


def test_a_copy_that_fails_verification_is_deleted(planner_db, tmp_path, monkeypatch):
    folder = tmp_path / "backups"

    def refuse(_path):
        raise MaintenanceError("simulated verification failure")

    monkeypatch.setattr(maintenance, "verify_backup", refuse)
    with pytest.raises(MaintenanceError, match="simulated"):
        backup_and_verify(planner_db, folder, when=WHEN)
    assert list(folder.glob("*.db")) == []


def test_a_file_that_is_not_a_database_is_refused(tmp_path):
    fake = tmp_path / "fake.db"
    fake.write_text("this is not a database", encoding="utf-8")
    with pytest.raises(MaintenanceError, match="not a readable SQLite database"):
        verify_backup(fake)


def test_backup_of_a_missing_database_is_refused(tmp_path):
    with pytest.raises(MaintenanceError, match="not found"):
        backup_sqlite(tmp_path / "none.db", tmp_path / "backups", when=WHEN)


def test_a_backup_folder_that_is_a_file_is_reported_and_the_file_is_kept(planner_db, tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file is in the way", encoding="utf-8")
    with pytest.raises(MaintenanceError, match="could not be written"):
        backup_sqlite(planner_db, blocker, when=WHEN)
    assert blocker.read_text(encoding="utf-8") == "a file is in the way"


# ---------------------------------------------------------------- scripts and their exit codes

def test_check_script_exits_0_when_ok_and_1_when_not(planner_db, tmp_path):
    good = _script("check_database.py", _url(planner_db))
    assert good.returncode == 0, good.stdout + good.stderr
    assert json.loads(good.stdout)["ok"] is True

    missing = _script("check_database.py", _url(tmp_path / "missing.db"))
    assert missing.returncode == 1
    assert json.loads(missing.stdout)["ok"] is False


def test_migrate_script_creates_the_database_and_reports_head(tmp_path):
    path = tmp_path / "scripted.db"
    result = _script("migrate_database.py", _url(path))
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["revision_after"] == head_revision()
    assert summary["up_to_date"] is True
    assert _script("check_database.py", _url(path)).returncode == 0


def test_backup_script_writes_a_verified_copy_to_the_chosen_folder(planner_db, tmp_path):
    folder = tmp_path / "chosen"
    result = _script("backup_database.py", _url(planner_db), "--out", str(folder))
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["integrity"] == "ok"
    assert (folder / report["file"]).is_file()


def test_backup_script_refuses_a_missing_database(tmp_path):
    result = _script("backup_database.py", _url(tmp_path / "none.db"), "--out", str(tmp_path / "x"))
    assert result.returncode == 1
    assert "not found" in result.stderr
