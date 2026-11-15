#!/usr/bin/env python3
"""Check the database without changing it.

Run from the project folder, with the same .env the server uses:

  python scripts/check_database.py

Prints a JSON report: integrity, foreign-key violations, migration revision, table row counts and any problems.
It never creates or changes the database. Exit codes: 0 everything is in order, 1 a problem was found.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.services.maintenance import check_database  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    try:
        report = check_database(settings.database_url)
    except Exception as exc:
        report = {"ok": False, "problems": [f"The database could not be opened: {exc}"]}
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
