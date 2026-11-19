"""Load the community Namma Metro timetable (bmrcl-gtfs, ODbL) as an UNVERIFIED community source, once.

    python scripts/load_community_metro.py

The feed describes the real Purple, Green and Yellow lines. A community project reconstructed it from the timetables
BMRCL publishes on its website and from OpenStreetMap. It is not BMRCL data and is never verified as official:
- it is imported with kind COMMUNITY, so its classification is always UNVERIFIED_FEED;
- the planner marks its times "approximate", because the published timetables give no intermediate-station times;
- the planner never shows its fares, which the project's build script estimated.

The file is checked against its recorded SHA-256 before import. Nothing happens if this source already has a completed
import, so the script is safe to run on every start. See reference_data/namma_metro_community/README.md.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.config import Settings  # noqa: E402
from app.database import Database  # noqa: E402
from app.models import STATUS_COMPLETED, DataSource, GtfsImport  # noqa: E402
from sqlalchemy import select  # noqa: E402

FEED = ROOT / "reference_data" / "namma_metro_community" / "bmrcl-gtfs-f402c4c.zip"
SHA256 = "c19f56f32ad53525c71191125409dc8dded12dd2cebfc576ad9a4db23a62b8a7"
SOURCE_NAME = "Namma Metro timetable, community reconstruction (bmrcl-gtfs)"
PUBLISHER = "bmrcl-gtfs community project (unofficial), from BMRCL's published timetables and OpenStreetMap"
SOURCE_URL = "https://github.com/Vonter/bmrcl-gtfs/tree/f402c4c69a5d314320024f84620fa83e909c4188"
LICENSE = "ODbL-1.0; contains OpenStreetMap data (c) OpenStreetMap contributors"


def already_loaded(settings: Settings) -> bool:
    db = Database(settings.database_url)
    try:
        db.create_schema()
        with db.session() as session:
            return session.scalar(
                select(GtfsImport.id)
                .join(DataSource, DataSource.id == GtfsImport.data_source_id)
                .where(DataSource.name == SOURCE_NAME, GtfsImport.status == STATUS_COMPLETED)
                .limit(1)
            ) is not None
    finally:
        db.dispose()


def main() -> int:
    digest = hashlib.sha256(FEED.read_bytes()).hexdigest()
    if digest != SHA256:
        print(f"load_community_metro: {FEED.name} has SHA-256 {digest}, expected {SHA256}; not imported")
        return 2
    if already_loaded(Settings.from_env()):
        print("load_community_metro: already imported, nothing to do")
        return 0
    import import_gtfs

    code = import_gtfs.main([
        "--file", str(FEED), "--new-source", PUBLISHER, "--name", SOURCE_NAME, "--kind", "COMMUNITY",
        "--license", LICENSE, "--source-url", SOURCE_URL,
    ])
    print("load_community_metro: imported" if code == 0 else f"load_community_metro: importer exited with {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
