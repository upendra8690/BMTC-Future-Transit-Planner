"""Provider registry, upcoming-transport registry and data freshness.

PROVIDERS records every outside data source or service the app uses or would need, with its licence and the app's
permission status. Nothing in it is a credential.

UPCOMING records transport projects with a status, the source the status comes from, and the date that source was
checked. These entries are information only: the planner never uses them, because it plans only from loaded
timetable feeds. A project is "Operating" only when a dated source reports that passengers can use it.

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
PLANNED, AWAITING, UNAVAILABLE = "PLANNED", "AWAITING_CONFIRMATION", "UNAVAILABLE"
PROJECT_STATUSES = (OPERATING, ANNOUNCED, UNDER_CONSTRUCTION, PLANNED, AWAITING, UNAVAILABLE)

UPCOMING: list[dict[str, Any]] = [
    {
        "id": "metro_yellow",
        "mode": "metro",
        "name": "Namma Metro Yellow Line (RV Road to Bommasandra)",
        "status": OPERATING,
        "opened_on": "2025-08-11",
        "expected": None,
        "announced_on": None,
        "detail": "Opened to passengers in August 2025.",
        "sources": [{"title": "Yellow Line (Namma Metro) — Wikipedia",
                     "url": "https://en.wikipedia.org/wiki/Yellow_Line_(Namma_Metro)"}],
        "verified_on": CHECKED,
        "confidence": "Secondary source; confirm on BMRCL's website",
    },
    {
        "id": "metro_pink_elevated",
        "mode": "metro",
        "name": "Namma Metro Pink Line, elevated section (Kalena Agrahara to Tavarekere/SG Palya)",
        "status": OPERATING,
        "opened_on": "2026-11-14",
        "expected": None,
        "announced_on": "2026-11-13",
        "detail": "Inaugurated on 13 November 2026; press reports say it opened to the public on 14 November 2026 "
                  "with six stations.",
        "sources": [
            {"title": "Deccan Herald — PM to open elevated Pink Line on November 13",
             "url": "https://www.deccanherald.com/india/karnataka/bengaluru/pm-modi-to-inaugurate-bengaluru-namma-"
                    "metros-elevated-pink-line-on-november-13-4206469"},
            {"title": "Oneindia — 7.5 km stretch to open on November 13",
             "url": "https://www.oneindia.com/bengaluru/namma-metro-pink-line-7-5-km-stretch-connecting-kalena-"
                    "agrahara-and-tavarekere-to-open-on-november-8248555.html"},
        ],
        "verified_on": CHECKED,
        "confidence": "Press reports around the opening; confirm on BMRCL's website",
    },
    {
        "id": "metro_pink_underground",
        "mode": "metro",
        "name": "Namma Metro Pink Line, underground section (Dairy Circle to Nagawara)",
        "status": UNDER_CONSTRUCTION,
        "opened_on": None,
        "expected": "2027 (reports differ: March or May 2027)",
        "announced_on": None,
        "detail": "Systems testing reported. Not open.",
        "sources": [{"title": "Pink Line (Namma Metro) — Wikipedia",
                     "url": "https://en.wikipedia.org/wiki/Pink_Line_(Namma_Metro)"}],
        "verified_on": CHECKED,
        "confidence": "Dates differ between sources",
    },
    {
        "id": "metro_blue",
        "mode": "metro",
        "name": "Namma Metro Blue Line (Central Silk Board to KR Puram to Airport)",
        "status": UNDER_CONSTRUCTION,
        "opened_on": None,
        "expected": "Not confirmed (published targets range from late 2026 to 2028)",
        "announced_on": None,
        "detail": "Phase 2A Silk Board to KR Puram and Phase 2B KR Puram to airport. Not open.",
        "sources": [{"title": "Blue Line (Namma Metro) — Wikipedia",
                     "url": "https://en.wikipedia.org/wiki/Blue_Line_(Namma_Metro)"}],
        "verified_on": CHECKED,
        "confidence": "Dates conflict between sources",
    },
    {
        "id": "suburban_mallige",
        "mode": "rail",
        "name": "Bengaluru Suburban Railway — Mallige line (Benniganahalli to Chikkabanavara)",
        "status": UNDER_CONSTRUCTION,
        "opened_on": None,
        "expected": "Not confirmed (overall project deadline reported as March 2030)",
        "announced_on": None,
        "detail": "No suburban rail service is operating. Contract and land issues have been reported.",
        "sources": [
            {"title": "Mallige line — Wikipedia", "url": "https://en.wikipedia.org/wiki/Mallige_line"},
            {"title": "Bengaluru Suburban Railway — Wikipedia",
             "url": "https://en.wikipedia.org/wiki/Bengaluru_Suburban_Railway"},
        ],
        "verified_on": CHECKED,
        "confidence": "Secondary sources; check K-RIDE for current status",
    },
    {
        "id": "bmtc_pink_feeders",
        "mode": "bus",
        "name": "BMTC feeder bus routes for Pink Line stations (5 routes)",
        "status": OPERATING,
        "opened_on": "2026-11-14",
        "expected": None,
        "announced_on": None,
        "detail": "Reported as 28 buses making 401 trips a day on five new routes. Their timetables are not loaded "
                  "in this app.",
        "sources": [{"title": "Deccan Herald — five new feeder bus services at Pink Line stations",
                     "url": "https://www.deccanherald.com/india/karnataka/bengaluru/5-new-feeder-bus-services-to-"
                            "start-on-novemer-14-at-bengalurus-pink-line-metro-stations-4217860"}],
        "verified_on": CHECKED,
        "confidence": "Press report; confirm routes on BMTC's website",
    },
    {
        "id": "bmtc_mini_ac_feeders",
        "mode": "bus",
        "name": "BMTC mini AC electric feeder buses near Metro stations (200 buses)",
        "status": ANNOUNCED,
        "opened_on": None,
        "expected": "No delivery date published",
        "announced_on": "2026-09",
        "detail": "A plan to use about 200 compact AC electric buses within about 5 km of Metro stations.",
        "sources": [{"title": "Channel IAM — Bengaluru Metro mini AC buses (September 2026)",
                     "url": "https://en.channeliam.com/2026/09/09/bengaluru-metro-mini-ac-buses/"}],
        "verified_on": CHECKED,
        "confidence": "Announcement only",
    },
]


class RegistryError(ValueError):
    """An upcoming-transport entry that could mislead a traveller."""


def validate_upcoming(entries: list[dict[str, Any]], today: dt.date) -> None:
    """Reject entries that would show a service as running when no dated source says it is.

    Every entry needs a known status, at least one source URL and a verification date. Only OPERATING entries may have
    an opening date, and that date may not be in the future or after the date the source was checked.
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
        verified_day = dt.date.fromisoformat(verified)
        opened = entry.get("opened_on")
        if status == OPERATING:
            if not opened:
                raise RegistryError(f"{ident}: an operating service needs the date it opened")
            opened_day = dt.date.fromisoformat(opened)
            if opened_day > today or opened_day > verified_day:
                raise RegistryError(f"{ident}: marked operating before its opening date")
        elif opened:
            raise RegistryError(f"{ident}: only an operating service may have an opening date")


def upcoming(today: dt.date) -> dict[str, Any]:
    validate_upcoming(UPCOMING, today)
    return {
        "checked": CHECKED,
        "statuses": list(PROJECT_STATUSES),
        "note": "Status information only. The journey planner uses loaded timetables, never these entries. "
                "No official timetable for these services is loaded in this app.",
        "projects": [dict(entry, in_planner=False) for entry in UPCOMING],
    }


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
