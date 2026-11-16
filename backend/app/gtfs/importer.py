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
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from .. import clock
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
    FareAttribute,
    FareRule,
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
from ..services.text import normalise

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
    "fare_attributes.txt": ("fare_id", "price", "currency_type", "payment_method"),
    "fare_rules.txt": ("fare_id",),
}
KNOWN_FILES = frozenset(REQUIRED_FILES) | frozenset(OPTIONAL_FILES)

MAX_MESSAGES = 200
CHUNK_SIZE = 5000
MIN_YEAR, MAX_YEAR = 2000, 2100
MAX_FEED_SPAN_DAYS = 3 * 366
# The database keeps identifiers in 100-character columns. A longer identifier would be cut short and then no longer
# match its own references, so such a feed is refused with a clear reason.
MAX_ID_LENGTH = 100
# ASCII only. Python's \d and str.isdigit() also accept other scripts' digits and characters such as superscript two,
# which int() cannot read, so every number in a feed is checked against these instead.
TIME_RE = re.compile(r"^([0-9]{1,3}):([0-5][0-9]):([0-5][0-9])$")
ASCII_INT_RE = re.compile(r"[0-9]+")


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


def is_ascii_int(value: str) -> bool:
    """True only for plain 0 to 9 digits."""
    return bool(ASCII_INT_RE.fullmatch(value or ""))


def parse_gtfs_date(value: str) -> dt.date | None:
    if not re.fullmatch(r"[0-9]{8}", value or ""):
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


class FeedTooLargeError(ValueError):
    """The decompressed feed is over the limit. Checked while reading, because ZIP headers can understate the size."""


class _ReadBudget:
    """Counts the bytes actually decompressed from the archive, shared by every table in one pass."""

    def __init__(self, limit: int) -> None:
        self.remaining = limit

    def spend(self, count: int) -> None:
        self.remaining -= count
        if self.remaining < 0:
            raise FeedTooLargeError("The uncompressed feed is larger than the configured limit.")


class _BudgetedReader(io.RawIOBase):
    def __init__(self, raw: Any, budget: _ReadBudget) -> None:
        super().__init__()
        self._raw = raw
        self._budget = budget

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        chunk = self._raw.read(len(buffer))
        self._budget.spend(len(chunk))
        buffer[: len(chunk)] = chunk
        return len(chunk)

    def close(self) -> None:
        self._raw.close()
        super().close()


@dataclass
class Archive:
    zf: zipfile.ZipFile
    members: dict[str, zipfile.ZipInfo]
    budget: _ReadBudget

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
    return Archive(zf=zf, members=members, budget=_ReadBudget(settings.max_uncompressed_bytes))


def _stream_rows(archive: Archive, name: str, report: Report, required: tuple[str, ...]) -> Iterator[dict[str, str]]:
    info = archive.members[name]
    with archive.zf.open(info) as raw:
        buffered = io.BufferedReader(_BudgetedReader(raw, archive.budget))
        text = io.TextIOWrapper(buffered, encoding="utf-8-sig", newline="")
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
    fare_attributes: list[dict[str, str]] = field(default_factory=list)
    fare_rules: list[dict[str, str]] = field(default_factory=list)
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
        fare_attributes=load("fare_attributes.txt"),
        fare_rules=load("fare_rules.txt"),
    )


def _check_agency(rows: list[dict[str, str]], report: Report) -> str | None:
    """Every agency needs a name and a known IANA time zone. GTFS requires one zone for the whole feed."""
    if not rows:
        report.error("agency.txt has no rows.")
    zones: set[str] = set()
    for line, row in enumerate(rows, start=2):
        if not row.get("agency_name"):
            report.error(f"agency.txt line {line}: agency_name is empty.")
        timezone_name = row.get("agency_timezone", "")
        if clock.zone_or_none(timezone_name) is None:
            report.error(
                f"agency.txt line {line}: agency_timezone '{timezone_name}' is not a known IANA time zone, "
                "such as Asia/Kolkata."
            )
        else:
            zones.add(timezone_name)
    if len(zones) > 1:
        report.error("agency.txt gives more than one agency_timezone. All agencies in one feed must share one zone.")
    return next(iter(zones)) if len(zones) == 1 else None


def _feed_zone(tables: Tables, settings: Settings) -> ZoneInfo:
    """The feed's own time zone, which decides what 'today' means for its dates. Falls back to the configured zone."""
    name = tables.agency[0].get("agency_timezone", "") if tables.agency else ""
    return clock.zone_or_none(name) or clock.zone(settings.service_timezone)


def _too_long(value: str, label: str, file_name: str, line: int, report: Report) -> bool:
    if len(value) <= MAX_ID_LENGTH:
        return False
    report.error(f"{file_name} line {line}: {label} is longer than {MAX_ID_LENGTH} characters.")
    return True


def _check_routes(rows: list[dict[str, str]], report: Report) -> set[str]:
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        route_id = row.get("route_id", "")
        if not route_id:
            report.error(f"routes.txt line {line}: route_id is empty.")
            continue
        if _too_long(route_id, "route_id", "routes.txt", line, report):
            continue
        if route_id in seen:
            report.error(f"routes.txt line {line}: duplicate route_id '{route_id}'.")
        seen.add(route_id)
        if not (row.get("route_short_name") or row.get("route_long_name")):
            report.error(f"routes.txt line {line}: route '{route_id}' needs a short or long name.")
        if not is_ascii_int(row.get("route_type", "")):
            report.error(f"routes.txt line {line}: route_type must be a whole number.")
    return seen


def _check_stops(rows: list[dict[str, str]], report: Report) -> None:
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        stop_id = row.get("stop_id", "")
        if not stop_id:
            report.error(f"stops.txt line {line}: stop_id is empty.")
            continue
        if _too_long(stop_id, "stop_id", "stops.txt", line, report):
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
        if _too_long(service, "service_id", "calendar.txt", line, report):
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
        if _too_long(service, "service_id", "calendar_dates.txt", line, report):
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
        if _too_long(trip_id, "trip_id", "trips.txt", line, report):
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
        else:
            _too_long(row["shape_id"], "shape_id", "shapes.txt", line, report)
        if (
            _coord(row.get("shape_pt_lat", ""), -90, 90) is None
            or _coord(row.get("shape_pt_lon", ""), -180, 180) is None
        ):
            report.error(f"shapes.txt line {line}: shape point has invalid coordinates.")
        if not is_ascii_int(row.get("shape_pt_sequence", "")):
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


FARE_PRICE_RE = re.compile(r"^[0-9]{1,9}(\.[0-9]{1,2})?$")
FARE_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def _check_fares(tables: Tables, route_ids: set[str], report: Report) -> None:
    """Fares are optional, but a wrong fare is worse than none, so a malformed fare stops the import.

    A fare rule that names an unknown fare or route is skipped with a warning, because the rest of the feed is still
    usable. Rules that name a zone or stop are kept by the importer but never used for route fares.
    """
    fare_ids: set[str] = set()
    for line, row in enumerate(tables.fare_attributes, start=2):
        fare_id = row.get("fare_id", "")
        if not fare_id:
            report.error(f"fare_attributes.txt line {line}: fare_id is empty.")
            continue
        if _too_long(fare_id, "fare_id", "fare_attributes.txt", line, report):
            continue
        if fare_id in fare_ids:
            report.error(f"fare_attributes.txt line {line}: duplicate fare_id '{fare_id}'.")
            continue
        fare_ids.add(fare_id)
        if not FARE_PRICE_RE.fullmatch(row.get("price", "")):
            report.error(f"fare_attributes.txt line {line}: price must be a plain amount such as 10 or 10.50.")
        if not FARE_CURRENCY_RE.fullmatch(row.get("currency_type", "")):
            report.error(f"fare_attributes.txt line {line}: currency_type must be a three-letter code such as INR.")
        if row.get("payment_method", "") not in ("0", "1"):
            report.error(
                f"fare_attributes.txt line {line}: payment_method must be 0 (on board) or 1 (before boarding)."
            )
        if row.get("transfers", "") not in ("", "0", "1", "2"):
            report.error(f"fare_attributes.txt line {line}: transfers must be empty, 0, 1 or 2.")
    for line, row in enumerate(tables.fare_rules, start=2):
        fare_id = row.get("fare_id", "")
        if fare_id not in fare_ids:
            report.warn(
                f"fare_rules.txt line {line}: fare '{fare_id}' is not in fare_attributes.txt, so the rule is skipped."
            )
            continue
        for column in ("route_id", "origin_id", "destination_id", "contains_id"):
            _too_long(row.get(column, ""), column, "fare_rules.txt", line, report)
        route = row.get("route_id", "")
        if route and route not in route_ids:
            report.warn(
                f"fare_rules.txt line {line}: route '{route}' is not in routes.txt, so the rule is skipped."
            )


def validate_tables(tables: Tables, today: dt.date, report: Report) -> None:
    _check_agency(tables.agency, report)
    route_ids = _check_routes(tables.routes, report)
    _check_stops(tables.stops, report)
    service_ids, spans = _check_calendars(tables, report)
    _check_trips(tables.trips, route_ids, service_ids, report)
    _check_shapes(tables.shapes, report)
    _check_fares(tables, route_ids, report)
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
    last_time: dict[str, int] = {}
    seen_trips: set[str] = set()
    backwards = 0
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
        if is_ascii_int(raw_sequence):
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
        if arrival is not None and last_time.get(trip) is not None and arrival < last_time[trip]:
            backwards += 1
        latest = departure if departure is not None else arrival
        if latest is not None:
            last_time[trip] = latest
        seen_trips.add(trip)
        rows += 1
    if rows == 0:
        report.error("stop_times.txt has no rows, so the timetable would be empty.")
    without_stops = trip_ids - seen_trips
    if without_stops:
        report.warn(f"{len(without_stops)} trip(s) have no stop times and are stored without stops.")
    if backwards:
        report.warn(
            f"{backwards} stop time(s) are earlier than the stop before them in the same trip. "
            "Journeys that would arrive before they leave are not shown."
        )


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
                "name": normalise(row["agency_name"])[:200],
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
                "short_name": (row.get("route_short_name") or None) and normalise(row["route_short_name"])[:50],
                "long_name": (row.get("route_long_name") or None) and normalise(row["route_long_name"])[:200],
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
                "name": normalise(row["stop_name"])[:200],
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
                "headsign": (row.get("trip_headsign") or None) and normalise(row["trip_headsign"])[:200],
                "direction_id": int(row["direction_id"]) if row.get("direction_id") else None,
                "shape_id": (row.get("shape_id") or None) and row["shape_id"][:100],
            }
            for row in tables.trips
        ],
    )
    trip_map = dict(session.execute(select(Trip.gtfs_trip_id, Trip.id).where(Trip.import_id == imp.id)).all())

    _bulk(
        session,
        FareAttribute,
        [
            {
                "import_id": imp.id,
                "fare_id": row["fare_id"][:100],
                "price": row["price"],
                "currency": row["currency_type"],
                "payment_method": int(row["payment_method"]),
                "transfers": int(row["transfers"]) if row.get("transfers") else None,
            }
            for row in tables.fare_attributes
        ],
    )
    fare_ids = {row["fare_id"] for row in tables.fare_attributes}
    _bulk(
        session,
        FareRule,
        [
            {
                "import_id": imp.id,
                "fare_id": row["fare_id"][:100],
                "route_id": (row.get("route_id") or None) and row["route_id"][:100],
                "origin_id": (row.get("origin_id") or None) and row["origin_id"][:100],
                "destination_id": (row.get("destination_id") or None) and row["destination_id"][:100],
                "contains_id": (row.get("contains_id") or None) and row["contains_id"][:100],
            }
            for row in tables.fare_rules
            if row["fare_id"] in fare_ids and (not row.get("route_id") or row["route_id"] in route_map)
        ],
    )

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
                "stop_headsign": (row.get("stop_headsign") or None) and normalise(row["stop_headsign"])[:200],
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
                # "Today" is the date in the feed's own time zone, never the date on the server.
                feed_today = today or clock.service_date(_feed_zone(tables, settings), clock.utc_now())
                validate_tables(tables, feed_today, report)
                if report.ok:
                    validate_stop_times(archive, tables, report)
        except FeedTooLargeError as exc:
            report.error(str(exc))
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
            "Each is kept and searched together. If two feeds list the same trips, a journey can repeat them."
        )
    report.finalize()

    imp = _new_import(
        source=source, filename=filename, digest=digest, size=len(data),
        classification=classification, status=STATUS_COMPLETED, report=report,
    )
    imp.feed_start_date = tables.start
    imp.feed_end_date = tables.end
    imp.agency_name = normalise(tables.agency[0]["agency_name"])[:200] if tables.agency else None
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


def fare_counts(session: Session, import_ids: list[int]) -> dict[int, int]:
    """How many fare prices each import stored. Imports that stored none are missing from the result."""
    if not import_ids:
        return {}
    rows = session.execute(
        select(FareAttribute.import_id, func.count())
        .where(FareAttribute.import_id.in_(import_ids))
        .group_by(FareAttribute.import_id)
    ).all()
    return {int(import_id): int(count) for import_id, count in rows}


def import_summary(imp: GtfsImport, fares: int) -> dict[str, Any]:
    """The admin view of one import. fares is the number of fare prices stored from this feed."""
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
        "fares": fares,
        "is_active": imp.is_active,
        "warnings": json.loads(imp.warnings or "[]"),
        "errors": json.loads(imp.errors or "[]"),
        "sha256": imp.sha256,
        "created_at": imp.created_at.isoformat() if imp.created_at else None,
    }
