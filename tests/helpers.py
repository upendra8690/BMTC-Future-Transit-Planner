"""Shared constants and builders for the test suite. Nothing in this module is a fixture."""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from pathlib import Path

from app.config import Settings
from app.gtfs.importer import import_feed
from app.gtfs.synthetic import build_synthetic_feed
from app.models import KIND_OFFICIAL, KIND_SYNTHETIC, STATUS_COMPLETED, DataSource

ADMIN_KEY = "test-admin-key-0123456789abcdef"
CLIENT_A = "client-a-0123456789abcdef"
CLIENT_B = "client-b-0123456789abcdef"

FEED_START = dt.date(2026, 6, 1)
FEED_END = dt.date(2027, 12, 31)
TODAY = dt.date(2026, 11, 15)  # a fixed "today", so date-dependent rules are repeatable

# Dates inside the synthetic feed's 2027 service window (see app/gtfs/synthetic.py).
MONDAY_2027 = dt.date(2027, 1, 11)
SATURDAY_2027 = dt.date(2027, 1, 9)
HOLIDAY_MONDAY_2027 = dt.date(2027, 1, 4)


def make_settings(tmp_path: Path, **overrides) -> Settings:
    """Settings for an isolated test database, with small limits so hostile-input tests stay fast."""
    base: dict = {
        "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "admin_api_key": ADMIN_KEY,
        "max_upload_bytes": 5 * 1024 * 1024,
        "max_uncompressed_bytes": 50 * 1024 * 1024,
        "max_zip_members": 50,
        "max_compression_ratio": 100,
        "rate_limit_per_minute": 100_000,
        "avg_bus_speed_kmph": 15.0,
        "stop_dwell_minutes": 0.5,
        "detour_factor": 1.3,
        "backup_dir": tmp_path / "backups",
        "log_level": "WARNING",
        "cors_origins": (),
    }
    base.update(overrides)
    return Settings(**base)


def make_source(
    session, *, kind: str = KIND_SYNTHETIC, verified: bool = False, name: str = "Test source"
) -> DataSource:
    """Create and commit a data source, as the admin API would before an upload."""
    source = DataSource(name=name, publisher="Test publisher", kind=kind, verified=verified, license="test")
    session.add(source)
    session.commit()
    return source


def synthetic_feed(start: dt.date = FEED_START, end: dt.date = FEED_END, holiday: dt.date | None = None) -> bytes:
    return build_synthetic_feed(start, end, holiday=holiday)


def zip_of(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def valid_files() -> dict[str, str]:
    """The smallest GTFS feed that passes every check. Tests copy it and break one part on purpose."""
    return {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nT,Test Agency,https://example.invalid,UTC\n",
        "routes.txt": "route_id,route_short_name,route_long_name,route_type\nR1,T-1,Test Route,3\n",
        "stops.txt": (
            "stop_id,stop_name,stop_lat,stop_lon,location_type\n"
            "S1,Alpha,12.97,77.59,0\n"
            "S2,Beta,12.98,77.60,0\n"
        ),
        "trips.txt": "route_id,service_id,trip_id,direction_id\nR1,WK,T1,0\n",
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T1,08:00:00,08:00:00,S1,1\nT1,08:10:00,08:10:00,S2,2\n"
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "WK,1,1,1,1,1,0,0,20270101,20271231\n"
        ),
    }


def admin_headers(key: str = ADMIN_KEY) -> dict[str, str]:
    return {"X-Admin-Key": key}


def client_headers(key: str) -> dict[str, str]:
    return {"X-Client-Key": key}


def build_transit_feed(stops, routes, trips, *, fares=None) -> bytes:
    """A small GTFS ZIP in which one service runs every day of 2027. Every expected time in a test is known exactly.

    stops: {stop_id: (name, lat, lon)}. routes: {route_id: short_name}.
    trips: [(trip_id, route_id, [(stop_id, "HH:MM:SS"), ...])] in calling order. Times may pass 24:00:00.
    fares: optional (fare_attributes.txt text, fare_rules.txt text).
    """
    files = {
        "agency.txt": (
            "agency_id,agency_name,agency_url,agency_timezone\n"
            "T,Test Agency,https://example.invalid,Asia/Kolkata\n"
        ),
        "routes.txt": "route_id,route_short_name,route_long_name,route_type\n" + "".join(
            f"{route_id},{short},Route {short},3\n" for route_id, short in routes.items()
        ),
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,location_type\n" + "".join(
            f"{stop_id},{name},{lat},{lon},0\n" for stop_id, (name, lat, lon) in stops.items()
        ),
        "trips.txt": "route_id,service_id,trip_id,direction_id\n" + "".join(
            f"{route_id},ALL,{trip_id},0\n" for trip_id, route_id, _calls in trips
        ),
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n" + "".join(
            f"{trip_id},{time},{time},{stop_id},{sequence}\n"
            for trip_id, _route, calls in trips
            for sequence, (stop_id, time) in enumerate(calls, start=1)
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "ALL,1,1,1,1,1,1,1,20270101,20271231\n"
        ),
    }
    if fares is not None:
        files["fare_attributes.txt"], files["fare_rules.txt"] = fares
    return zip_of(files)


def load_transit_feed(session, settings, data: bytes, *, name: str, kind: str = KIND_OFFICIAL,
                      verified: bool = True):
    """Store a feed under a new source and return the import. The import must complete."""
    source = make_source(session, kind=kind, verified=verified, name=name)
    imp = import_feed(session, data, filename=f"{name}.zip", source=source, settings=settings, today=TODAY)
    assert imp.status == STATUS_COMPLETED, f"the import was {imp.status}, not {STATUS_COMPLETED}"
    return imp

