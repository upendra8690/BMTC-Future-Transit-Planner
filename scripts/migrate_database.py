#!/usr/bin/env python3
"""Create the database if needed, then apply every migration it has not run yet.

Run from the project folder, with the same .env the server uses:

  python scripts/migrate_database.py

The server does the same on every start-up, so this is only needed to prepare the database before the first
start, or to see the revision it is at. Exit codes: 0 success, 1 error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.database import Database  # noqa: E402
from app.schema_migrations import current_revision, head_revision  # noqa: E402
from app.services.maintenance import sqlite_file  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    db = Database(settings.database_url)
    try:
        before = current_revision(db.engine)
        db.create_schema()
        after = current_revision(db.engine)
        path = sqlite_file(settings.database_url)
        print(json.dumps({
            "database": db.engine.dialect.name,
            "file": str(path) if path else None,
            "revision_before": before,
            "revision_after": after,
            "head_revision": head_revision(),
            "up_to_date": after == head_revision(),
        }, indent=2))
        return 0 if after == head_revision() else 1
    except Exception as exc:
        print(f"error: the database could not be migrated: {exc}", file=sys.stderr)
        return 1
    finally:
        db.dispose()


if __name__ == "__main__":
    sys.exit(main())
