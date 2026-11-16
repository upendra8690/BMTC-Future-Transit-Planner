#!/usr/bin/env python3
"""Load the SYNTHETIC demo feed into an empty database, so a fresh public demo has something to show.

  python scripts/seed_demo_feed.py

Does nothing if any GTFS import (completed or rejected) is already recorded, so it is safe to run on every start.
The feed is invented demonstration data, imported as kind SYNTHETIC_DEMO, and is never official BMTC timetable data.
Exit codes: 0 seeded or nothing to do, other values come from the importer.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.config import Settings  # noqa: E402
from app.database import Database  # noqa: E402
from app.models import GtfsImport  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    db = Database(settings.database_url)
    db.create_schema()
    with db.session() as session:
        existing = session.scalar(select(func.count()).select_from(GtfsImport))
    db.dispose()
    if existing:
        print(f"seed_demo_feed: {existing} import(s) already recorded, nothing to do")
        return 0

    import import_gtfs
    import make_synthetic_gtfs

    with tempfile.TemporaryDirectory() as tmp:
        feed = Path(tmp) / "demo_feed.zip"
        make_synthetic_gtfs.main(["--out", str(feed)])
        code = import_gtfs.main(["--file", str(feed), "--new-source", "Synthetic demo", "--kind", "SYNTHETIC_DEMO",
                                 "--name", "demo_feed.zip"])
    print("seed_demo_feed: demo feed imported" if code == 0 else f"seed_demo_feed: importer exited with {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
