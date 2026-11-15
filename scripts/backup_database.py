#!/usr/bin/env python3
"""Back up the SQLite database, then verify the copy.

Run from the project folder, with the same .env the server uses:

  python scripts/backup_database.py
  python scripts/backup_database.py --out "D:\\BMTC-backups"

It works while the server is running (SQLite's online backup API). Each copy is checked for integrity and for
its migration revision before the script reports success.

To restore: stop the server, copy a verified backup over the database file (data/planner.db by default),
then start the server again. Exit codes: 0 a verified backup was written, 1 an error occurred.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.maintenance import MaintenanceError, backup_and_verify, sqlite_file  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Back up the planner database and verify the copy.")
    parser.add_argument("--out", type=Path, help="Folder for the backup (default: BACKUP_DIR, or data/backups)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings.from_env()
    source = sqlite_file(settings.database_url)
    if source is None:
        print(
            "error: this script backs up SQLite databases only. Use the database's own backup tools.",
            file=sys.stderr,
        )
        return 1
    folder = (args.out or settings.backup_dir).resolve()
    try:
        report = backup_and_verify(source, folder, when=dt.datetime.now(dt.UTC).replace(tzinfo=None))
    except MaintenanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
