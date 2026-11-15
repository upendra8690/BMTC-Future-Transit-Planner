#!/usr/bin/env python3
"""Write the SYNTHETIC demo GTFS feed to a ZIP file. Every stop, route and trip in it is invented.

  python scripts/make_synthetic_gtfs.py --out data/demo_feed.zip
  python scripts/make_synthetic_gtfs.py --out data/demo_feed.zip --holiday 2027-01-26

Import it with --kind SYNTHETIC_DEMO. It is demonstration data only and is never official BMTC timetable data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.gtfs.synthetic import build_synthetic_feed  # noqa: E402


def parse_date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {text!r}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the SYNTHETIC demo GTFS feed.")
    parser.add_argument("--out", type=Path, required=True, help="Where to write the ZIP")
    parser.add_argument("--start", type=parse_date, default=dt.date(2026, 6, 1), help="First service date")
    parser.add_argument("--end", type=parse_date, default=dt.date(2027, 12, 31), help="Last service date")
    parser.add_argument("--holiday", type=parse_date, help="A weekday on which weekday service is removed")
    args = parser.parse_args(argv)
    if args.end < args.start:
        parser.error("--end must not be earlier than --start")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(build_synthetic_feed(args.start, args.end, holiday=args.holiday))
    print(f"Wrote {args.out} ({args.start} to {args.end}). SYNTHETIC_DEMO data, not BMTC timetables.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
