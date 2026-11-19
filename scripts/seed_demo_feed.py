#!/usr/bin/env python3
"""Load the SYNTHETIC demo feeds (demo buses and one demo Metro line) into an empty database.

  python scripts/seed_demo_feed.py

Does nothing if a demonstration import (completed or rejected) is already recorded, so it is safe to run on every
start. Only a demonstration server (DEMO_MODE=1) serves these feeds; see backend/app/demo.py.
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
from app.models import KIND_SYNTHETIC, DataSource, GtfsImport  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    db = Database(settings.database_url)
    db.create_schema()
    with db.session() as session:
        existing = session.scalar(
            select(func.count()).select_from(GtfsImport)
            .join(DataSource, DataSource.id == GtfsImport.data_source_id)
            .where(DataSource.kind == KIND_SYNTHETIC)
        )
    db.dispose()
    if existing:
        print(f"seed_demo_feed: {existing} demonstration import(s) already recorded, nothing to do")
        return 0

    import datetime as dt

    import import_gtfs
    import make_synthetic_gtfs
    from app.gtfs.synthetic import build_synthetic_metro_feed

    with tempfile.TemporaryDirectory() as tmp:
        feed = Path(tmp) / "demo_feed.zip"
        make_synthetic_gtfs.main(["--out", str(feed)])
        code = import_gtfs.main(["--file", str(feed), "--new-source", "Synthetic demo", "--kind", "SYNTHETIC_DEMO",
                                 "--name", "demo_feed.zip"])
        if code == 0:
            metro = Path(tmp) / "demo_metro_feed.zip"
            metro.write_bytes(build_synthetic_metro_feed(dt.date(2026, 6, 1), dt.date(2027, 12, 31)))
            code = import_gtfs.main(["--file", str(metro), "--new-source", "Synthetic demo Metro",
                                     "--kind", "SYNTHETIC_DEMO", "--name", "demo_metro_feed.zip"])
    print("seed_demo_feed: demo feeds imported" if code == 0 else f"seed_demo_feed: importer exited with {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
