"""Command-line importer: exit codes, refusal rules, the verification round trip and the audit trail.

Every database here is a temporary file. The OFFICIAL source is a test fixture only. Its name says so, and it exists
just long enough to exercise the verification path. Nothing it creates leaves the test.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from app.database import Database
from app.models import (
    CLASS_OFFICIAL,
    CLASS_UNVERIFIED,
    KIND_OFFICIAL,
    KIND_UNKNOWN,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    AuditLog,
    DataSource,
    GtfsImport,
    VerificationRecord,
)
from sqlalchemy import select

from tests.helpers import valid_files, zip_of

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_gtfs.py"
EXIT_OK, EXIT_USAGE, EXIT_REJECTED, EXIT_REFUSED = 0, 1, 2, 3


@pytest.fixture
def cli(tmp_path, monkeypatch) -> tuple[ModuleType, str]:
    url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    spec = importlib.util.spec_from_file_location("import_gtfs_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, url


@pytest.fixture
def feed_path(tmp_path) -> Path:
    path = tmp_path / "feed.zip"
    path.write_bytes(zip_of(valid_files()))
    return path


def _query(url: str, fn):
    db = Database(url)
    try:
        with db.session() as session:
            return fn(session)
    finally:
        db.dispose()


def _only_source_id(url: str) -> int:
    return _query(url, lambda s: s.scalars(select(DataSource.id)).one())


# ---------------------------------------------------------------- imports

def test_valid_feed_is_imported_as_unverified_data(cli, feed_path, capsys):
    module, url = cli
    code = module.main(["--file", str(feed_path), "--new-source", "Test publisher", "--name", "TEST feed"])
    assert code == EXIT_OK
    output = json.loads(capsys.readouterr().out)
    assert output["import"]["status"] == STATUS_COMPLETED
    assert output["import"]["classification"] == CLASS_UNVERIFIED
    assert output["import"]["routes"] == 1
    actions = _query(url, lambda s: [row.action for row in s.scalars(select(AuditLog))])
    assert "data_source.create" in actions
    assert "gtfs.import" in actions


def test_new_source_records_the_command_line_as_its_actor(cli, feed_path):
    module, url = cli
    module.main(["--file", str(feed_path), "--new-source", "Test publisher", "--name", "TEST feed",
                 "--kind", KIND_UNKNOWN])
    source = _query(url, lambda s: s.scalars(select(DataSource)).one())
    assert source.name == "TEST feed"
    assert source.kind == KIND_UNKNOWN
    assert source.verified is False
    actors = _query(url, lambda s: [
        row.actor for row in s.scalars(select(AuditLog).where(AuditLog.action == "data_source.create"))
    ])
    assert actors == ["cli"]


def test_a_file_that_is_not_a_zip_is_rejected_with_exit_2(cli, tmp_path, capsys):
    module, url = cli
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"this is plainly not a zip archive")
    code = module.main(["--file", str(bad), "--new-source", "Test publisher"])
    assert code == EXIT_REJECTED
    output = json.loads(capsys.readouterr().out)
    assert output["import"]["status"] == STATUS_REJECTED
    assert output["import"]["errors"]
    rejected = _query(url, lambda s: s.scalars(select(GtfsImport).where(GtfsImport.status == STATUS_REJECTED)).all())
    assert len(rejected) == 1


# ---------------------------------------------------------------- usage errors exit with 1

@pytest.mark.parametrize(
    "extra",
    [
        ["--new-source", "Test publisher", "--verify"],
        ["--source-id", "1", "--verify", "--revoke"],
        ["--new-source", "Test publisher", "--source-url", "ftp://example.org/feed.zip"],
        ["--new-source", "Test publisher", "--license", "x" * 201],
        ["--new-source", "Test publisher", "--name", "x" * 201],
        ["--new-source", "   "],
        ["--source-id", "999"],
    ],
    ids=[
        "verify-with-new-source",
        "verify-and-revoke",
        "non-http-source-url",
        "licence-too-long",
        "name-too-long",
        "blank-publisher",
        "unknown-source-id",
    ],
)
def test_usage_mistakes_exit_with_1(cli, feed_path, extra):
    module, _ = cli
    assert module.main(["--file", str(feed_path), *extra]) == EXIT_USAGE


def test_missing_file_exits_with_1(cli, tmp_path, capsys):
    module, _ = cli
    assert module.main(["--file", str(tmp_path / "absent.zip"), "--new-source", "Test publisher"]) == EXIT_USAGE
    assert "file not found" in capsys.readouterr().err


def test_no_target_or_nothing_to_do_exits_with_1(cli, feed_path):
    module, _ = cli
    assert module.main(["--file", str(feed_path)]) == EXIT_USAGE
    assert module.main(["--source-id", "1"]) == EXIT_USAGE


def test_help_exits_with_0(cli):
    module, _ = cli
    assert module.main(["--help"]) == EXIT_OK


# ---------------------------------------------------------------- verification

def test_verify_is_refused_for_a_source_that_is_not_official(cli, feed_path, capsys):
    module, url = cli
    module.main(["--file", str(feed_path), "--new-source", "Test publisher", "--kind", KIND_UNKNOWN])
    capsys.readouterr()
    code = module.main(["--source-id", str(_only_source_id(url)), "--verify", "--note", "attempt"])
    assert code == EXIT_REFUSED
    assert "only sources of kind OFFICIAL" in capsys.readouterr().err
    assert _query(url, lambda s: s.scalar(select(DataSource.verified))) is False
    assert _query(url, lambda s: s.scalars(select(VerificationRecord)).all()) == []


def test_official_test_fixture_round_trip_moves_its_imports(cli, feed_path, capsys):
    module, url = cli
    code = module.main([
        "--file", str(feed_path), "--new-source", "TEST ONLY publisher",
        "--kind", KIND_OFFICIAL, "--name", "TEST ONLY official fixture",
    ])
    assert code == EXIT_OK
    created = json.loads(capsys.readouterr().out)["import"]
    assert created["classification"] == CLASS_UNVERIFIED  # not verified yet, so never official
    source_id = _only_source_id(url)

    code = module.main(["--source-id", str(source_id), "--verify", "--note", "TEST ONLY: verification path"])
    assert code == EXIT_OK
    verified = json.loads(capsys.readouterr().out)["verification"]
    assert verified["verified"] is True
    assert verified["reclassified_imports"] == 1
    assert verified["classification_of_source"] == CLASS_OFFICIAL
    assert _query(url, lambda s: s.scalar(select(GtfsImport.classification))) == CLASS_OFFICIAL

    code = module.main(["--source-id", str(source_id), "--revoke"])
    assert code == EXIT_OK
    revoked = json.loads(capsys.readouterr().out)["verification"]
    assert revoked["verified"] is False
    assert _query(url, lambda s: s.scalar(select(GtfsImport.classification))) == CLASS_UNVERIFIED

    actions = _query(url, lambda s: [
        row.action for row in s.scalars(select(VerificationRecord).order_by(VerificationRecord.id))
    ])
    assert actions == ["VERIFIED", "REVOKED"]
    audited = _query(url, lambda s: [
        row.actor for row in s.scalars(select(AuditLog).where(AuditLog.action == "data_source.verify"))
    ])
    assert audited == ["cli", "cli"]
