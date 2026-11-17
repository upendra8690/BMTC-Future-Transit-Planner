"""Provider registry, upcoming-transport registry and data freshness.

PROVIDERS records every outside data source or service the app uses or would need, with its licence and the app's
permission status. Nothing in it is a credential.

UPCOMING holds the upcoming-transport entries checked when this version was written, and validate_upcoming() the
rules every entry must meet. The entries live in the database (services/announcements.py), where administrators
update them without code changes. They are information only: the planner never uses them. A project is "Operating"
only when a dated source reports that passengers can use it.

data_status() reads the loaded feeds and says, for each, whether its calendar still covers today.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KIND_SYNTHETIC, STATUS_COMPLETED, DataSource, GtfsImport

CHECKED = "2026-11-17"

# ---------------------------------------------------------------- providers

# Permission: GRANTED (written permission held), NOT_REQUESTED, REQUESTED, NOT_NEEDED (open licence / own data).
# Integration: CONNECTED, NOT_CONNECTED, BLOCKED (needs an agreement the app does not have).
PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "dult_data_hub",
        "provider": "Directorate of Urban Land Transport (DULT), Government of Karnataka",
        "dataset": "BMTC and BMRCL static GTFS on the Transport Data Hub",
        "url": "https://dult.karnataka.gov.in/",
        "licence": "Not found. DULT's website policy requires prior permission to republish its content.",
        "permission": "NOT_REQUESTED",
        "owner": "DULT / BMTC / BMRCL",
        "update_frequency": "Unknown",
        "integration": "NOT_CONNECTED",
        "limitations": "Draft request letter prepared; not sent. No DULT data is loaded.",
    },
    {
        "id": "bmtc_gtfs",
        "provider": "Bengaluru Metropolitan Transport Corporation (BMTC)",
        "dataset": "Bus routes, stops, timetables and fares",
        "url": "https://mybmtc.karnataka.gov.in/",
        "licence": "Not published for reuse.",
        "permission": "NOT_REQUESTED",
        "owner": "BMTC",
        "update_frequency": "Unknown",
        "integration": "NOT_CONNECTED",
        "limitations": "No BMTC timetable, fare or route data is loaded.",
    },
    {
        "id": "bmtc_realtime",
        "provider": "BMTC",
        "dataset": "Live bus positions and arrival predictions",
        "url": "https://mybmtc.karnataka.gov.in/",
        "licence": "Shared only under an agreement.",
        "permission": "NOT_REQUESTED",
        "owner": "BMTC",
        "update_frequency": "Real time",
        "integration": "BLOCKED",
        "limitations": "Live tracking and ETAs stay disabled until an authorised feed is provided.",
    },
    {
        "id": "bmtc_ticketing",
        "provider": "BMTC",
        "dataset": "Bus tickets and passes",
        "url": "https://mybmtc.karnataka.gov.in/",
        "licence": "Requires a ticketing agreement.",
        "permission": "NOT_REQUESTED",
        "owner": "BMTC",
        "update_frequency": "—",
        "integration": "BLOCKED",
        "limitations": "The app issues no tickets or passes and links to official channels.",
    },
    {
        "id": "bmrcl_data",
        "provider": "Bangalore Metro Rail Corporation Limited (BMRCL)",
        "dataset": "Namma Metro stations, timetables and fares",
        "url": "https://english.bmrc.co.in/",
        "licence": "Website content; reuse needs BMRCL's permission.",
        "permission": "NOT_REQUESTED",
        "owner": "BMRCL",
        "update_frequency": "Unknown",
        "integration": "NOT_CONNECTED",
        "limitations": "No BMRCL timetable or fare data is loaded.",
    },
    {
        "id": "metro_qr_ondc",
        "provider": "BMRCL through ONDC-registered apps",
        "dataset": "Metro QR tickets",
        "url": "https://english.bmrc.co.in/",
        "licence": "Requires ONDC registration and BMRCL approval.",
        "permission": "NOT_REQUESTED",
        "owner": "BMRCL",
        "update_frequency": "—",
        "integration": "BLOCKED",
        "limitations": "The app shows no QR codes and sells no Metro tickets.",
    },
    {
        "id": "payments",
        "provider": "A licensed payment aggregator (UPI, cards, NCMC)",
        "dataset": "Payments, wallet, NCMC",
        "url": None,
        "licence": "Requires a merchant agreement and an operator's ticketing agreement.",
        "permission": "NOT_REQUESTED",
        "owner": "—",
        "update_frequency": "—",
        "integration": "BLOCKED",
        "limitations": "The app takes no payments, keeps no wallet and stores no card or UPI details.",
    },
    {
        "id": "osm_tiles",
        "provider": "OpenStreetMap Foundation",
        "dataset": "Map tiles",
        "url": "https://www.openstreetmap.org/copyright",
        "licence": "Map data ODbL; tile usage policy applies.",
        "permission": "NOT_NEEDED",
        "owner": "OpenStreetMap contributors",
        "update_frequency": "Continuous",
        "integration": "CONNECTED",
        "limitations": "Light use only under the tile usage policy; switch provider before heavy use.",
    },
    {
        "id": "synthetic_demo",
        "provider": "This project",
        "dataset": "Synthetic demo bus and Metro feeds",
        "url": None,
        "licence": "Project's own invented data.",
        "permission": "NOT_NEEDED",
        "owner": "This project",
        "update_frequency": "On deployment",
        "integration": "CONNECTED",
        "limitations": "Invented for demonstration. Never a real service; cannot be marked official.",
    },
]

# Providers whose timetable data would be imported (the others are services the app calls or would call).
DATASET_PROVIDERS = frozenset({"dult_data_hub", "bmtc_gtfs", "bmrcl_data", "synthetic_demo"})

# ---------------------------------------------------------------- upcoming transport

OPERATING, ANNOUNCED, UNDER_CONSTRUCTION = "OPERATING", "ANNOUNCED", "UNDER_CONSTRUCTION"
PLANNED, DELAYED, AWAITING = "PLANNED", "DELAYED", "AWAITING_CONFIRMATION"
PROJECT_STATUSES = (ANNOUNCED, PLANNED, UNDER_CONSTRUCTION, DELAYED, AWAITING, OPERATING)

TRANSPORT_TYPES = ("BUS_ROUTE", "ELECTRIC_BUS", "FEEDER", "METRO_EXTENSION", "METRO_STATION", "SUBURBAN_RAIL",
                   "INTERCHANGE", "INTEGRATED_TICKETING")
# Where a status comes from. Only OFFICIAL (the operator's or government's own announcement) may give an expected
# start date; ESTIMATE and DEMO entries can never be shown as operating.
SRC_OFFICIAL, SRC_PRESS, SRC_SECONDARY, SRC_ESTIMATE, SRC_DEMO = "OFFICIAL", "PRESS", "SECONDARY", "ESTIMATE", "DEMO"
ANNOUNCEMENT_SOURCE_KINDS = (SRC_OFFICIAL, SRC_PRESS, SRC_SECONDARY, SRC_ESTIMATE, SRC_DEMO)
TYPE_MODE = {"BUS_ROUTE": "bus", "ELECTRIC_BUS": "bus", "FEEDER": "bus", "METRO_EXTENSION": "metro",
             "METRO_STATION": "metro", "SUBURBAN_RAIL": "rail"}

# The entries checked when this version was written. They seed the database on first use; after that administrators
# update them through the API (services/announcements.py) and these values are not read again.
UPCOMING: list[dict[str, Any]] = [
    {
        "id": "metro_yellow",
        "name": "Namma Metro Yellow Line",
        "transport_type": "METRO_EXTENSION",
        "location": "RV Road to Bommasandra",
        "announcement": "Opened to passengers in August 2025.",
        "status": OPERATING,
        "source_kind": SRC_SECONDARY,
        "announced_on": None,
        "expected_start": None,
        "opened_on": "2025-08-11",
        "sources": [{"title": "Yellow Line (Namma Metro) — Wikipedia",
                     "url": "https://en.wikipedia.org/wiki/Yellow_Line_(Namma_Metro)"}],
        "verified_on": CHECKED,
        "note": "Secondary source; confirm on BMRCL's website",
    },
    {
        "id": "metro_pink_elevated",
        "name": "Namma Metro Pink Line, elevated section",
        "transport_type": "METRO_EXTENSION",
        "location": "Kalena Agrahara to Tavarekere/SG Palya (six stations)",
        "announcement": "Inaugurated on 13 November 2026; press reports say it opened to the public on 14 November "
                        "2026.",
        "status": OPERATING,
        "source_kind": SRC_PRESS,
        "announced_on": "2026-11-13",
        "expected_start": None,
        "opened_on": "2026-11-14",
        "sources": [
            {"title": "Deccan Herald — PM to open elevated Pink Line on November 13",
             "url": "https://www.deccanherald.com/india/karnataka/bengaluru/pm-modi-to-inaugurate-bengaluru-namma-"
                    "metros-elevated-pink-line-on-november-13-4206469"},
            {"title": "Oneindia — 7.5 km stretch to open on November 13",
             "url": "https://www.oneindia.com/bengaluru/namma-metro-pink-line-7-5-km-stretch-connecting-kalena-"
                    "agrahara-and-tavarekere-to-open-on-november-8248555.html"},
        ],
        "verified_on": CHECKED,
        "note": "Press reports around the opening; confirm on BMRCL's website",
    },
    {
        "id": "metro_pink_underground",
        "name": "Namma Metro Pink Line, underground section",
        "transport_type": "METRO_EXTENSION",
        "location": "Dairy Circle to Nagawara",
        "announcement": "Systems testing reported. Not open.",
        "status": UNDER_CONSTRUCTION,
        "source_kind": SRC_SECONDARY,
        "announced_on": None,
        "expected_start": None,
        "opened_on": None,
        "sources": [{"title": "Pink Line (Namma Metro) — Wikipedia",
                     "url": "https://en.wikipedia.org/wiki/Pink_Line_(Namma_Metro)"}],
        "verified_on": CHECKED,
        "note": "No official opening date. Secondary sources report different targets in 2027",
    },
    {
        "id": "metro_blue",
        "name": "Namma Metro Blue Line",
        "transport_type": "METRO_EXTENSION",
        "location": "Central Silk Board to KR Puram (Phase 2A), KR Puram to the airport (Phase 2B)",
        "announcement": "Under construction. Not open.",
        "status": UNDER_CONSTRUCTION,
        "source_kind": SRC_SECONDARY,
        "announced_on": None,
        "expected_start": None,
        "opened_on": None,
        "sources": [{"title": "Blue Line (Namma Metro) — Wikipedia",
                     "url": "https://en.wikipedia.org/wiki/Blue_Line_(Namma_Metro)"}],
        "verified_on": CHECKED,
        "note": "No official opening date. Published targets conflict",
    },
    {
        "id": "suburban_mallige",
        "name": "Bengaluru Suburban Railway — Mallige line",
        "transport_type": "SUBURBAN_RAIL",
        "location": "Benniganahalli to Chikkabanavara",
        "announcement": "No suburban rail service is operating. Contract and land issues have been reported.",
        "status": UNDER_CONSTRUCTION,
        "source_kind": SRC_SECONDARY,
        "announced_on": None,
        "expected_start": None,
        "opened_on": None,
        "sources": [
            {"title": "Mallige line — Wikipedia", "url": "https://en.wikipedia.org/wiki/Mallige_line"},
            {"title": "Bengaluru Suburban Railway — Wikipedia",
             "url": "https://en.wikipedia.org/wiki/Bengaluru_Suburban_Railway"},
        ],
        "verified_on": CHECKED,
        "note": "No official opening date for passengers; check K-RIDE for the current status",
    },
    {
        "id": "bmtc_pink_feeders",
        "name": "BMTC feeder bus routes for Pink Line stations",
        "transport_type": "FEEDER",
        "location": "Five routes serving the elevated Pink Line stations",
        "announcement": "Reported as 28 buses making 401 trips a day on five new routes. Their timetables are not "
                        "loaded in this app.",
        "status": OPERATING,
        "source_kind": SRC_PRESS,
        "announced_on": None,
        "expected_start": None,
        "opened_on": "2026-11-14",
        "sources": [{"title": "Deccan Herald — five new feeder bus services at Pink Line stations",
                     "url": "https://www.deccanherald.com/india/karnataka/bengaluru/5-new-feeder-bus-services-to-"
                            "start-on-novemer-14-at-bengalurus-pink-line-metro-stations-4217860"}],
        "verified_on": CHECKED,
        "note": "Press report; confirm routes on BMTC's website",
    },
    {
        "id": "bmtc_mini_ac_feeders",
        "name": "BMTC mini AC electric feeder buses (about 200 buses)",
        "transport_type": "ELECTRIC_BUS",
        "location": "Within about 5 km of Metro stations",
        "announcement": "A plan to use about 200 compact AC electric buses as Metro feeders.",
        "status": ANNOUNCED,
        "source_kind": SRC_PRESS,
        "announced_on": "2026-09",
        "expected_start": None,
        "opened_on": None,
        "sources": [{"title": "Channel IAM — Bengaluru Metro mini AC buses (September 2026)",
                     "url": "https://en.channeliam.com/2026/09/09/bengaluru-metro-mini-ac-buses/"}],
        "verified_on": CHECKED,
        "note": "Announcement only; no delivery date published",
    },
]


class RegistryError(ValueError):
    """An upcoming-transport entry that could mislead a traveller."""


def _period_start(value: str, ident: str, label: str) -> dt.date:
    """The first day of a YYYY, YYYY-MM or YYYY-MM-DD value."""
    parts = value.split("-")
    try:
        if len(parts) == 1:
            return dt.date(int(parts[0]), 1, 1)
        if len(parts) == 2:
            return dt.date(int(parts[0]), int(parts[1]), 1)
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise RegistryError(f"{ident}: invalid {label} {value!r}") from exc


def validate_upcoming(entries: list[dict[str, Any]], today: dt.date) -> None:
    """Reject entries that would show a service as running, or a date as official, without a source that says so.

    Every entry needs a known status, type and source kind, at least one https source and a verification date that is
    not in the future. Only OPERATING entries may have an opening date, which may not be in the future or after the
    check. Only an OFFICIAL announcement may give an expected start date, and an estimate or a demonstration entry can
    never be operating.
    """
    seen: set[str] = set()
    for entry in entries:
        ident = entry.get("id", "?")
        if ident in seen:
            raise RegistryError(f"{ident}: duplicate id")
        seen.add(ident)
        status = entry.get("status")
        if status not in PROJECT_STATUSES:
            raise RegistryError(f"{ident}: unknown status {status!r}")
        sources = entry.get("sources") or []
        if not sources or not all(str(s.get("url") or "").startswith("https://") for s in sources):
            raise RegistryError(f"{ident}: needs at least one https source")
        verified = entry.get("verified_on")
        if not verified:
            raise RegistryError(f"{ident}: needs a verification date")
        verified_day = _period_start(verified, ident, "verification date")
        if verified_day > today:
            raise RegistryError(f"{ident}: the verification date is in the future")
        opened = entry.get("opened_on")
        if status == OPERATING:
            if not opened:
                raise RegistryError(f"{ident}: an operating service needs the date it opened")
            opened_day = _period_start(opened, ident, "opening date")
            if opened_day > today or opened_day > verified_day:
                raise RegistryError(f"{ident}: marked operating before its opening date")
        elif opened:
            raise RegistryError(f"{ident}: only an operating service may have an opening date")
        if entry.get("transport_type") not in TRANSPORT_TYPES:
            raise RegistryError(f"{ident}: unknown transport type {entry.get('transport_type')!r}")
        kind = entry.get("source_kind")
        if kind not in ANNOUNCEMENT_SOURCE_KINDS:
            raise RegistryError(f"{ident}: unknown source kind {kind!r}")
        if status == OPERATING and kind in (SRC_ESTIMATE, SRC_DEMO):
            raise RegistryError(f"{ident}: an estimate or a demonstration entry cannot be shown as operating")
        expected = entry.get("expected_start")
        if expected:
            if kind != SRC_OFFICIAL:
                raise RegistryError(f"{ident}: only an official announcement may give an expected start date")
            if status == OPERATING:
                raise RegistryError(f"{ident}: an operating service has an opening date, not an expected start")
            _period_start(expected, ident, "expected start")
        announced = entry.get("announced_on")
        if announced and _period_start(announced, ident, "announcement date") > today:
            raise RegistryError(f"{ident}: the announcement date is in the future")
        if not str(entry.get("name") or "").strip():
            raise RegistryError(f"{ident}: needs a name")


UPCOMING_NOTE = ("Status information only. The journey planner uses loaded timetables, never these entries. "
                 "No official timetable for these services is loaded in this app.")


# ---------------------------------------------------------------- data freshness

CURRENT, EXPIRED, NOT_STARTED, UNKNOWN_DATES = "CURRENT", "EXPIRED", "NOT_STARTED", "UNKNOWN_DATES"
EXPIRING_DAYS = 14


def data_status(db: Session, today: dt.date) -> dict[str, Any]:
    """Each active feed with its calendar coverage on the service's today."""
    rows = db.execute(
        select(GtfsImport, DataSource)
        .join(DataSource, DataSource.id == GtfsImport.data_source_id)
        .where(GtfsImport.status == STATUS_COMPLETED, GtfsImport.is_active.is_(True))
        .order_by(GtfsImport.id)
    ).all()
    feeds = []
    for feed, source in rows:
        start, end = feed.feed_start_date, feed.feed_end_date
        if start is None or end is None:
            state = UNKNOWN_DATES
        elif end < today:
            state = EXPIRED
        elif start > today:
            state = NOT_STARTED
        else:
            state = CURRENT
        feeds.append({
            "import_id": feed.id,
            "source": source.name,
            "publisher": source.publisher,
            "kind": source.kind,
            "demo": source.kind == KIND_SYNTHETIC,
            "classification": feed.classification,
            "feed_start_date": start.isoformat() if start else None,
            "feed_end_date": end.isoformat() if end else None,
            "imported_at": feed.created_at.isoformat() + "Z" if feed.created_at else None,
            "state": state,
            "expires_soon": state == CURRENT and end is not None and (end - today).days < EXPIRING_DAYS,
        })
    return {
        "today": today.isoformat(),
        "realtime": False,
        "live_feed": "NONE",
        "demo_only": bool(feeds) and all(f["demo"] for f in feeds),
        "feeds": feeds,
    }


def providers(db: Session) -> dict[str, Any]:
    latest = db.scalar(
        select(GtfsImport.created_at)
        .join(DataSource, DataSource.id == GtfsImport.data_source_id)
        .where(DataSource.kind == KIND_SYNTHETIC, GtfsImport.status == STATUS_COMPLETED, GtfsImport.is_active.is_(True))
        .order_by(GtfsImport.created_at.desc())
        .limit(1)
    )
    out = []
    for entry in PROVIDERS:
        row = dict(entry)
        row["loads_data"] = entry["id"] in DATASET_PROVIDERS
        row["last_successful_update"] = None
        if entry["id"] == "synthetic_demo" and latest is not None:
            row["last_successful_update"] = latest.isoformat() + "Z"
        out.append(row)
    return {"checked": CHECKED, "providers": out}
