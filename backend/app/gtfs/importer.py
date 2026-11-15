"""Validation and import of static GTFS ZIP feeds.

Security and data-quality rules:
* The ZIP is never extracted to disk. Only the GTFS tables are read, in memory or as a stream.
* Member paths are checked for traversal (`..`, absolute paths, drive letters), encryption,
  member counts, total uncompressed size and suspicious compression ratios before anything is read.
* Dates, times, coordinates and every foreign key are validated before a single row is written.
* A feed with any error is stored as REJECTED and nothing from it reaches the timetable tables.
* Feed dates are checked against today. Schedules are never extended into years they do not cover.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import logging
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import (
    CLASS_OFFICIAL,
    CLASS_UNVERIFIED,
    KIND_OFFICIAL,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    WEEKDAYS,
    Agency,
    DataSource,
    GtfsImport,
    Route,
    ServiceCalendar,
    ServiceException,
    ShapePoint,
    Stop,
    StopTime,
    Trip,
    utcnow,
)
from ..services.audit import record_audit

LOG = logging.getLogger(__name__)

REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "agency.txt": ("agency_name", "agency_url", "agency_timezone"),
    "routes.txt": ("route_id", "route_type"),
    "stops.txt": ("stop_id", "stop_name"),
    "trips.txt": ("route_id", "service_id", "trip_id"),
    "stop_times.txt": ("trip_id", "stop_sequence", "stop_id"),
}
# GTFS spells weekday columns out in full. They are stored as mon..sun in the database.
GTFS_WEEKDAY_COLUMNS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
OPTIONAL_FILES: dict[str, tuple[str, ...]] = {
    "calendar.txt": ("service_id", "start_date", "end_date", *GTFS_WEEKDAY_COLUMNS),
    "calendar_dates.txt": ("service_id", "date", "exception_type"),
    "shapes.txt": ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"),
}
KNOWN_FILES = frozenset(REQUIRED_FILES) | frozenset(OPTIONAL_FILES)

MAX_MESSAGES = 200
CHUNK_SIZE = 5000
MIN_YEAR, MAX_YEAR = 2000, 2100
MAX_FEED_SPAN_DAYS = 3 * 366
TIME_RE = re.compile(r"^(\d{1,3}):([0-5]\d):([0-5]\d)$")


class Report:
    """Collects errors and warnings. Storage is capped so one bad feed cannot bloat the database."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self._error_total = 0
        self._warning_total = 0

    def error(self, message: str) -> None:
        self._error_total += 1
        if len(self.errors) < MAX_MESSAGES:
            self.errors.append(message)

    def warn(self, message: str) -> None:
        self._warning_total += 1
        if len(self.warnings) < MAX_MESSAGES:
            self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return self._error_total == 0

    def finalize(self) -> None:
        if self._error_total > len(self.errors):
            self.errors.append(f"... and {self._error_total - len(self.errors)} more error(s).")
        if self._warning_total > len(self.warnings):
            self.warnings.append(f"... and {self._warning_total - len(self.warnings)} more warning(s).")


def parse_gtfs_date(value: str) -> dt.date | None:
    if not re.fullmatch(r"\d{8}", value or ""):
        return None
    try:
        parsed = dt.datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None
    return parsed if MIN_YEAR <= parsed.year <= MAX_YEAR else None


def parse_gtfs_time(value: str) -> int | None:
    """GTFS times may exceed 24:00:00 for trips that run past midnight. Returns seconds since service-day start."""
    match = TIME_RE.match(value or "")
    if not match:
        return None
    hours, minutes, seconds = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _coord(value: str, low: float, high: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


@dataclass
class Archive:
    zf: zipfile.ZipFile
    members: dict[str, zipfile.ZipInfo]

    def close(self) -> None:
        self.zf.close()


def open_archive(data: bytes, settings: Settings, report: Report) -> Archive | None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError):
        report.error("The file is not a readable ZIP archive.")
        return None

    def reject(message: str) -> None:
        report.error(message)
        zf.close()

    infos = [info for info in zf.infolist() if not info.is_dir()]
    if len(infos) > settings.max_zip_members:
        reject(f"The archive contains {len(infos)} files; the limit is {settings.max_zip_members}.")
        return None

    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in infos:
        name = info.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", name):
            reject("The archive contains an unsafe file path, so the whole feed was rejected.")
            return None
        if info.flag_bits & 0x1:
            reject(f"{path.name} is encrypted. Encrypted feeds are not supported.")
            return None
        total += info.file_size
        if info.file_size > settings.max_uncompressed_bytes or total > settings.max_uncompressed_bytes:
            reject("The uncompressed feed is larger than the configured limit.")
            return None
        if (
            info.compress_size
            and info.file_size > 1_000_000
            and info.file_size / info.compress_size > settings.max_compression_ratio
        ):
            reject(f"{path.name} has a suspicious compression ratio and was rejected.")
            return None
        if path.name in KNOWN_FILES:
            if path.name in members:
                reject(f"{path.name} appears more than once in the archive.")
                return None
            members[path.name] = info
    return Archive(zf=zf, members=members)


def _stream_rows(archive: Archive, name: str, report: Report, required: tuple[str, ...]) -> Iterator[dict[str, str]]:
    info = archive.members[name]
    with archive.zf.open(info) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text)
        headers = [header.strip().lower() for header in (reader.fieldnames or [])]
        reader.fieldnames = headers
        if not headers:
            report.error(f"{name} is empty or has no header row.")
            return
        missing = [column for column in required if column not in headers]
        if missing:
            report.error(f"{name} is missing required column(s): {', '.join(missing)}.")
            return
        for row in reader:
            yield {key: (value or "").strip() for key, value in row.items() if key}


@dataclass
class Tables:
    agency: list[dict[str, str]]
    routes: list[dict[str, str]]
    stops: list[dict[str, str]]
    trips: list[dict[str, str]]
    calendars: list[dict[str, str]]
    calendar_dates: list[dict[str, str]]
    shapes: list[dict[str, str]]
    start: dt.date | None = None
    end: dt.date | None = None
    service_ids: set[str] = field(default_factory=set)


def read_tables(archive: Archive, report: Report) -> Tables | None:
    for name in REQUIRED_FILES:
        if name not in archive.members:
            report.error(f"Required file {name} is missing from the archive.")
    if not report.ok:
        return None

    def load(name: str) -> list[dict[str, str]]:
        if name not in archive.members:
            return []
        required = REQUIRED_FILES.get(name) or OPTIONAL_FILES[name]
        return list(_stream_rows(archive, name, report, required))

    return Tables(
        agency=load("agency.txt"),
        routes=load("routes.txt"),
        stops=load("stops.txt"),
        trips=load("trips.txt"),
        calendars=load("calendar.txt"),
        calendar_dates=load("calendar_dates.txt"),
        shapes=load("shapes.txt"),
    )


def _check_agency(rows: list[dict[str, str]], report: Report) -> None:
    if not rows:
        report.error("agency.txt has no rows.")
    for line, row in enumerate(rows, start=2):
        if not row.get("agency_name"):
            report.error(f"agency.txt line {line}: agency_name is empty.")


def _check_routes(rows: list[dict[str, str]], report: Report) -> set[str]:
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        route_id = row.get("route_id", "")
        if not route_id:
            report.error(f"routes.txt line {line}: route_id is empty.")
            continue
        if route_id in seen:
            report.error(f"routes.txt line {line}: duplicate route_id '{route_id}'.")
        seen.add(route_id)
        if not (row.get("route_short_name") or row.get("route_long_name")):
            report.error(f"routes.txt line {line}: route '{route_id}' needs a short or long name.")
        if not row.get("route_type", "").isdigit():
            report.error(f"routes.txt line {line}: route_type must be a whole number.")
    return seen


def _check_stops(rows: list[dict[str, str]], report: Report) -> None:
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        stop_id = row.get("stop_id", "")
        if not stop_id:
            report.error(f"stops.txt line {line}: stop_id is empty.")
            continue
        if stop_id in seen:
            report.error(f"stops.txt line {line}: duplicate stop_id '{stop_id}'.")
        seen.add(stop_id)
        if not row.get("stop_name"):
            report.error(f"stops.txt line {line}: stop '{stop_id}' has no name.")
        location_type = row.get("location_type") or "0"
        if location_type not in {"0", "1", "2", "3", "4"}:
            report.error(f"stops.txt line {line}: location_type must be 0 to 4.")
        if location_type == "0" and (_coord(row.get("stop_lat", ""), -90, 90) is None
                                     or _coord(row.get("stop_lon", ""), -180, 180) is None):
            report.error(f"stops.txt line {line}: stop '{stop_id}' needs valid coordinates.")


def _check_calendars(tables: Tables, report: Report) -> tuple[set[str], list[tuple[dt.date, dt.date]]]:
    services: set[str] = set()
    spans: list[tuple[dt.date, dt.date]] = []
    for line, row in enumerate(tables.calendars, start=2):
        service = row.get("service_id", "")
        if not service:
            report.error(f"calendar.txt line {line}: service_id is empty.")
            continue
        start = parse_gtfs_date(row.get("start_date", ""))
        end = parse_gtfs_date(row.get("end_date", ""))
        if start is None or end is None:
            report.error(f"calendar.txt line {line}: start_date and end_date must be valid YYYYMMDD dates.")
            continue
        if start > end:
            report.error(f"calendar.txt line {line}: start_date is after end_date.")
            continue
        if any(row.get(day, "") not in {"0", "1"} for day in GTFS_WEEKDAY_COLUMNS):
            report.error(f"calendar.txt line {line}: weekday columns must be 0 or 1.")
            continue
        services.add(service)
        spans.append((start, end))
    for line, row in enumerate(tables.calendar_dates, start=2):
        service = row.get("service_id", "")
        day = parse_gtfs_date(row.get("date", ""))
        if not service or day is None:
            report.error(f"calendar_dates.txt line {line}: service_id and a valid YYYYMMDD date are required.")
            continue
        if row.get("exception_type") not in {"1", "2"}:
            report.error(f"calendar_dates.txt line {line}: exception_type must be 1 or 2.")
            continue
        services.add(service)
        spans.append((day, day))
    if not spans:
        report.error("No valid service dates were found in calendar.txt or calendar_dates.txt.")
    return services, spans


def _check_trips(rows: list[dict[str, str]], route_ids: set[str], service_ids: set[str], report: Report) -> None:
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        trip_id = row.get("trip_id", "")
        if not trip_id:
            report.error(f"trips.txt line {line}: trip_id is empty.")
            continue
        if trip_id in seen:
            report.error(f"trips.txt line {line}: duplicate trip_id '{trip_id}'.")
        seen.add(trip_id)
        if row.get("route_id") not in route_ids:
            report.error(f"trips.txt line {line}: trip '{trip_id}' refers to an unknown route_id.")
        if row.get("service_id") not in service_ids:
            report.error(f"trips.txt line {line}: trip '{trip_id}' refers to an unknown service_id.")
        direction = row.get("direction_id", "")
        if direction and direction not in {"0", "1"}:
            report.error(f"trips.txt line {line}: direction_id must be 0 or 1.")


def _check_shapes(rows: list[dict[str, str]], report: Report) -> None:
    for line, row in enumerate(rows, start=2):
        if not row.get("shape_id"):
            report.error(f"shapes.txt line {line}: shape_id is empty.")
        if (
            _coord(row.get("shape_pt_lat", ""), -90, 90) is None
            or _coord(row.get("shape_pt_lon", ""), -180, 180) is None
        ):
            report.error(f"shapes.txt line {line}: shape point has invalid coordinates.")
        if not row.get("shape_pt_sequence", "").isdigit():
            report.error(f"shapes.txt line {line}: shape_pt_sequence must be a whole number.")


def _check_feed_dates(spans: list[tuple[dt.date, dt.date]], today: dt.date, report: Report) -> None:
    if not spans:
        return
    start = min(span[0] for span in spans)
    end = max(span[1] for span in spans)
    if end < today:
        report.warn(
            f"The service dates end on {end.isoformat()}, before today. "
            "The feed is stored for history and will not be shown as current."
        )
    if (end - start).days > MAX_FEED_SPAN_DAYS:
        report.warn("The feed covers more than three years. Check that the publisher intended this range.")


def validate_tables(tables: Tables, today: dt.date, report: Report) -> None:
    _check_agency(tables.agency, report)
    route_ids = _check_routes(tables.routes, report)
    _check_stops(tables.stops, report)
    service_ids, spans = _check_calendars(tables, report)
    _check_trips(tables.trips, route_ids, service_ids, report)
    _check_shapes(tables.shapes, report)
    _check_feed_dates(spans, today, report)
    tables.service_ids = service_ids
    if spans:
        tables.start = min(span[0] for span in spans)
        tables.end = max(span[1] for span in spans)


def _optional_time(value: str, label: str, line: int, report: Report) -> int | None:
    if not value:
        return None
    seconds = parse_gtfs_time(value)
    if seconds is None:
        report.error(f"stop_times.txt line {line}: {label} '{value}' is not HH:MM:SS.")
    return seconds


def validate_stop_times(archive: Archive, tables: Tables, report: Report) -> None:
    trip_ids = {row["trip_id"] for row in tables.trips if row.get("trip_id")}
    stop_ids = {row["stop_id"] for row in tables.stops if row.get("stop_id")}
    last_sequence: dict[str, int] = {}
    seen_trips: set[str] = set()
    rows = 0
    stop_rows = _stream_rows(archive, "stop_times.txt", report, REQUIRED_FILES["stop_times.txt"])
    for line, row in enumerate(stop_rows, start=2):
        trip = row.get("trip_id", "")
        stop = row.get("stop_id", "")
        if trip not in trip_ids:
            report.error(f"stop_times.txt line {line}: unknown trip_id '{trip}'.")
        if stop not in stop_ids:
            report.error(f"stop_times.txt line {line}: unknown stop_id '{stop}'.")
        raw_sequence = row.get("stop_sequence", "")
        if raw_sequence.isdigit():
            sequence = int(raw_sequence)
            previous = last_sequence.get(trip)
            if previous is not None and sequence <= previous:
                report.error(f"stop_times.txt line {line}: stop_sequence must increase within trip '{trip}'.")
            last_sequence[trip] = sequence
        else:
            report.error(f"stop_times.txt line {line}: stop_sequence must be a whole number.")
        arrival = _optional_time(row.get("arrival_time", ""), "arrival_time", line, report)
        departure = _optional_time(row.get("departure_time", ""), "departure_time", line, report)
        if arrival is not None and departure is not None and departure < arrival:
            report.error(f"stop_times.txt line {line}: departure is earlier than arrival.")
        seen_trips.add(trip)
        rows += 1
    if rows == 0:
        report.error("stop_times.txt has no rows, so the timetable would be empty.")
    without_stops = trip_ids - seen_trips
    if without_stops:
        report.warn(f"{len(without_stops)} trip(s) have no stop times and are stored without stops.")


def classification_for_source(source: DataSource) -> str:
    """Only an official source with an explicit verification record can produce OFFICIAL_VERIFIED data."""
    return CLASS_OFFICIAL if source.kind == KIND_OFFICIAL and source.verified else CLASS_UNVERIFIED


def reclassify_source_imports(session: Session, source: DataSource) -> int:
    """Apply a verification or revocation to every import already stored for this source."""
    target = classification_for_source(source)
    changed = 0
    for imp in session.scalars(select(GtfsImport).where(GtfsImport.data_source_id == source.id)):
        if imp.classification != target:
            imp.classification = target
            changed += 1
    return changed


def _new_import(
    *, source: DataSource, filename: str, digest: str, size: int, classification: str, status: str, report: Report
) -> GtfsImport:
    return GtfsImport(
        data_source_id=source.id,
        filename=filename,
        sha256=digest,
        size_bytes=size,
        status=status,
        classification=classification,
        warnings=json.dumps(report.warnings, ensure_ascii=False),
        errors=json.dumps(report.errors, ensure_ascii=False),
        is_active=status == STATUS_COMPLETED,
        created_at=utcnow(),
    )


def _bulk(session: Session, model: type, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), CHUNK_SIZE):
        session.execute(insert(model), rows[start : start + CHUNK_SIZE])


def _overlapping_imports(
    session: Session, classification: str, start: dt.date | None, end: dt.date | None
) -> list[int]:
    if start is None or end is None:
        return []
    return list(
        session.scalars(
            select(GtfsImport.id).where(
                GtfsImport.classification == classification,
                GtfsImport.status == STATUS_COMPLETED,
                GtfsImport.is_active.is_(True),
                GtfsImport.feed_start_date <= end,
                GtfsImport.feed_end_date >= start,
            )
        )
    )


def _insert_feed(session: Session, imp: GtfsImport, archive: Archive, tables: Tables) -> dict[str, int]:
    _bulk(
        session,
        Agency,
        [
            {
                "import_id": imp.id,
                "gtfs_id": row.get("agency_id") or None,
                "name": row["agency_name"][:200],
                "url": row["agency_url"][:500],
                "timezone": row["agency_timezone"][:100],
            }
            for row in tables.agency
        ],
    )
    _bulk(
        session,
        Route,
        [
            {
                "import_id": imp.id,
                "gtfs_route_id": row["route_id"][:100],
                "short_name": (row.get("route_short_name") or None) and row["route_short_name"][:50],
                "long_name": (row.get("route_long_name") or None) and row["route_long_name"][:200],
                "route_type": int(row["route_type"]),
                "color": (row.get("route_color") or None) and row["route_color"][:10],
                "text_color": (row.get("route_text_color") or None) and row["route_text_color"][:10],
            }
            for row in tables.routes
        ],
    )
    route_map = dict(session.execute(select(Route.gtfs_route_id, Route.id).where(Route.import_id == imp.id)).all())

    _bulk(
        session,
        Stop,
        [
            {
                "import_id": imp.id,
                "gtfs_stop_id": row["stop_id"][:100],
                "name": row["stop_name"][:200],
                "lat": _coord(row.get("stop_lat", ""), -90, 90),
                "lon": _coord(row.get("stop_lon", ""), -180, 180),
                "location_type": int(row.get("location_type") or 0),
            }
            for row in tables.stops
        ],
    )
    stop_map = dict(session.execute(select(Stop.gtfs_stop_id, Stop.id).where(Stop.import_id == imp.id)).all())

    _bulk(
        session,
        ServiceCalendar,
        [
            {
                "import_id": imp.id,
                "service_id": row["service_id"][:100],
                **{
                    model_day: int(row[gtfs_day])
                    for gtfs_day, model_day in zip(GTFS_WEEKDAY_COLUMNS, WEEKDAYS, strict=True)
                },
                "start_date": parse_gtfs_date(row["start_date"]),
                "end_date": parse_gtfs_date(row["end_date"]),
            }
            for row in tables.calendars
        ],
    )
    _bulk(
        session,
        ServiceException,
        [
            {
                "import_id": imp.id,
                "service_id": row["service_id"][:100],
                "date": parse_gtfs_date(row["date"]),
                "exception_type": int(row["exception_type"]),
            }
            for row in tables.calendar_dates
        ],
    )

    shape_rows = [
        {
            "import_id": imp.id,
            "gtfs_shape_id": row["shape_id"][:100],
            "sequence": int(row["shape_pt_sequence"]),
            "lat": float(row["shape_pt_lat"]),
            "lon": float(row["shape_pt_lon"]),
        }
        for row in tables.shapes
    ]
    _bulk(session, ShapePoint, shape_rows)

    _bulk(
        session,
        Trip,
        [
            {
                "import_id": imp.id,
                "route_id": route_map[row["route_id"]],
                "gtfs_trip_id": row["trip_id"][:100],
                "gtfs_route_id": row["route_id"][:100],
                "service_id": row["service_id"][:100],
                "headsign": (row.get("trip_headsign") or None) and row["trip_headsign"][:200],
                "direction_id": int(row["direction_id"]) if row.get("direction_id") else None,
                "shape_id": (row.get("shape_id") or None) and row["shape_id"][:100],
            }
            for row in tables.trips
        ],
    )
    trip_map = dict(session.execute(select(Trip.gtfs_trip_id, Trip.id).where(Trip.import_id == imp.id)).all())

    buffer: list[dict[str, Any]] = []
    stop_time_count = 0
    throwaway = Report()  # rows were fully validated before this pass
    for row in _stream_rows(archive, "stop_times.txt", throwaway, REQUIRED_FILES["stop_times.txt"]):
        buffer.append(
            {
                "import_id": imp.id,
                "trip_id": trip_map[row["trip_id"]],
                "stop_id": stop_map[row["stop_id"]],
                "sequence": int(row["stop_sequence"]),
                "arrival_sec": parse_gtfs_time(row.get("arrival_time", "")),
                "departure_sec": parse_gtfs_time(row.get("departure_time", "")),
                "stop_headsign": (row.get("stop_headsign") or None) and row["stop_headsign"][:200],
            }
        )
        if len(buffer) >= CHUNK_SIZE:
            session.execute(insert(StopTime), buffer)
            stop_time_count += len(buffer)
            buffer = []
    if buffer:
        session.execute(insert(StopTime), buffer)
        stop_time_count += len(buffer)

    return {
        "route_count": len(tables.routes),
        "stop_count": len(tables.stops),
        "trip_count": len(tables.trips),
        "stop_time_count": stop_time_count,
        "shape_point_count": len(shape_rows),
    }


def import_feed(
    session: Session,
    data: bytes,
    *,
    filename: str,
    source: DataSource,
    settings: Settings,
    actor: str = "admin",
    ip: str | None = None,
    today: dt.date | None = None,
) -> GtfsImport:
    """Validate and import one GTFS ZIP. Returns the stored import record (COMPLETED or REJECTED)."""
    today = today or dt.date.today()
    report = Report()
    digest = hashlib.sha256(data).hexdigest()
    classification = classification_for_source(source)

    duplicate_of = session.scalar(
        select(GtfsImport.id).where(GtfsImport.sha256 == digest, GtfsImport.status == STATUS_COMPLETED).limit(1)
    )
    if duplicate_of is not None:
        report.warn(f"An identical file was already imported as import #{duplicate_of}.")

    tables: Tables | None = None
    archive = open_archive(data, settings, report)
    if archive is not None:
        try:
            tables = read_tables(archive, report)
            if tables is not None:
                validate_tables(tables, today, report)
                if report.ok:
                    validate_stop_times(archive, tables, report)
        except (UnicodeDecodeError, csv.Error) as exc:
            report.error(f"The feed text could not be read as UTF-8 CSV: {exc}")
        finally:
            archive.close()

    if tables is None or not report.ok:
        report.finalize()
        rejected = _new_import(
            source=source, filename=filename, digest=digest, size=len(data),
            classification=classification, status=STATUS_REJECTED, report=report,
        )
        session.add(rejected)
        session.flush()
        record_audit(
            session, actor=actor, action="gtfs.import_rejected", entity="gtfs_import", entity_id=rejected.id,
            detail={"filename": filename, "errors": len(report.errors), "sha256": digest}, ip=ip,
        )
        session.commit()
        return rejected

    overlaps = _overlapping_imports(session, classification, tables.start, tables.end)
    if overlaps:
        report.warn(
            f"Dates overlap with existing import(s) {overlaps} of the same classification. "
            "Each is kept and searched separately."
        )
    report.finalize()

    imp = _new_import(
        source=source, filename=filename, digest=digest, size=len(data),
        classification=classification, status=STATUS_COMPLETED, report=report,
    )
    imp.feed_start_date = tables.start
    imp.feed_end_date = tables.end
    imp.agency_name = tables.agency[0]["agency_name"][:200] if tables.agency else None
    session.add(imp)

    try:
        session.flush()
        archive = open_archive(data, settings, report)
        if archive is None:
            raise RuntimeError("archive could not be re-opened for import")
        try:
            counts = _insert_feed(session, imp, archive, tables)
        finally:
            archive.close()
        for name, value in counts.items():
            setattr(imp, name, value)
        record_audit(
            session, actor=actor, action="gtfs.import", entity="gtfs_import", entity_id=imp.id,
            detail={"filename": filename, "classification": classification, **counts}, ip=ip,
        )
        session.commit()
        return imp
    except Exception:
        session.rollback()
        LOG.exception("GTFS import failed for %s", filename)
        failed_report = Report()
        failed_report.error("The import failed while writing to the database. See the server log for details.")
        failed = _new_import(
            source=source, filename=filename, digest=digest, size=len(data),
            classification=classification, status=STATUS_REJECTED, report=failed_report,
        )
        session.add(failed)
        session.flush()
        record_audit(
            session, actor=actor, action="gtfs.import_failed", entity="gtfs_import", entity_id=failed.id,
            detail={"filename": filename}, ip=ip,
        )
        session.commit()
        return failed


def import_summary(imp: GtfsImport) -> dict[str, Any]:
    return {
        "id": imp.id,
        "filename": imp.filename,
        "status": imp.status,
        "classification": imp.classification,
        "agency_name": imp.agency_name,
        "feed_start_date": imp.feed_start_date.isoformat() if imp.feed_start_date else None,
        "feed_end_date": imp.feed_end_date.isoformat() if imp.feed_end_date else None,
        "routes": imp.route_count,
        "stops": imp.stop_count,
        "trips": imp.trip_count,
        "stop_times": imp.stop_time_count,
        "shape_points": imp.shape_point_count,
        "is_active": imp.is_active,
        "warnings": json.loads(imp.warnings or "[]"),
        "errors": json.loads(imp.errors or "[]"),
        "sha256": imp.sha256,
        "created_at": imp.created_at.isoformat() if imp.created_at else None,
    }
