"""What the app can do right now, and where to go for what it cannot.

Feature states drive the interface, so a feature that is not available explains itself instead of failing:
  AVAILABLE    works with the data that is loaded
  NO_DATA      the code works, but no feed with the needed data is loaded
  UNAVAILABLE  needs an authorisation, agreement or credential the app does not have
  PLANNED      not built yet; scheduled for a later phase of 4.0

The services directory lists official websites and public helplines only. Every web link was opened and its page
title checked on the date in `checked`. Nothing here is a business listing, price, timetable or opening hour.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .. import demo
from ..models import STATUS_COMPLETED, DataSource, FareAttribute, GtfsImport, Route
from .planner import FARE_SOURCE_KINDS

AVAILABLE, NO_DATA, UNAVAILABLE, PLANNED = "AVAILABLE", "NO_DATA", "UNAVAILABLE", "PLANNED"

# GTFS route_type values: 0 tram/light rail, 1 subway/metro, 2 rail, 3 bus (plus extended 7xx bus, 4xx urban rail).
METRO_ROUTE_TYPES = (1, 400, 401, 402)
BUS_ROUTE_TYPES = (3, 700, 701, 702, 704, 715)

CHECKED = "2026-11-16"


def _has_routes(db: Session, route_types: tuple[int, ...]) -> bool:
    query = select(
        exists().where(
            Route.route_type.in_(route_types),
            Route.import_id == GtfsImport.id,
            GtfsImport.is_active.is_(True),
            GtfsImport.status == STATUS_COMPLETED,
            demo.served_imports(),
        )
    )
    return bool(db.scalar(query))


def _has_shown_fares(db: Session) -> bool:
    """True only if a served feed has fares the planner will show: those of an OFFICIAL source (or, on a
    demonstration server, the invented demo source). Community fares are estimates and are never shown."""
    query = select(
        exists().where(
            FareAttribute.import_id == GtfsImport.id,
            GtfsImport.is_active.is_(True),
            GtfsImport.status == STATUS_COMPLETED,
            GtfsImport.data_source_id == DataSource.id,
            DataSource.kind.in_(FARE_SOURCE_KINDS),
            demo.served_imports(),
        )
    )
    return bool(db.scalar(query))


def feature_states(db: Session) -> list[dict[str, Any]]:
    """Each feature with its state and a reason code. Reason codes are translated by the app."""
    bus = _has_routes(db, BUS_ROUTE_TYPES)
    metro = _has_routes(db, METRO_ROUTE_TYPES)
    any_data = bus or metro

    def data_state(present: bool) -> tuple[str, str | None]:
        return (AVAILABLE, None) if present else (NO_DATA, "NO_FEED_LOADED")

    rows: list[tuple[str, tuple[str, str | None]]] = [
        ("bus_routes", data_state(bus)),
        ("bus_timetables", data_state(bus)),
        ("nearby_stops", data_state(any_data)),
        ("journey_planner", data_state(any_data)),
        ("metro", data_state(metro)),
        ("bus_metro_journeys", (AVAILABLE, None) if bus and metro else (NO_DATA, "NEEDS_BUS_AND_METRO_FEEDS")),
        ("fares", (AVAILABLE, None) if _has_shown_fares(db)
         else (NO_DATA, "NO_VERIFIED_FARES") if any_data else (NO_DATA, "NO_FEED_LOADED")),
        ("favourites", (AVAILABLE, None)),
        ("offline", (AVAILABLE, None)),
        ("sos_call", (AVAILABLE, None)),
        ("official_links", (AVAILABLE, None)),
        ("live_tracking", (UNAVAILABLE, "NO_AUTHORISED_LIVE_FEED")),
        ("bus_tickets", (UNAVAILABLE, "NEEDS_TICKETING_AGREEMENT")),
        ("bus_passes", (UNAVAILABLE, "NEEDS_TICKETING_AGREEMENT")),
        ("metro_tickets", (UNAVAILABLE, "NEEDS_ONDC_REGISTRATION")),
        ("payments", (UNAVAILABLE, "NEEDS_PAYMENT_GATEWAY")),
        ("ncmc_cards", (UNAVAILABLE, "NEEDS_BANK_INTEGRATION")),
        # Accounts are built but stay off unless the server has a permanent database (ACCOUNTS_ENABLED with
        # PostgreSQL); notifications also need a delivery service. See docs/launch/ACCOUNTS_AND_ROLES.md.
        ("accounts", (PLANNED, "NEEDS_PERSISTENT_DATABASE")),
        ("notifications", (PLANNED, "NEEDS_DELIVERY_SERVICE")),
        ("upcoming_transport", (AVAILABLE, None)),
        ("facilities", (PLANNED, "NEEDS_LICENSED_DATA")),
        ("ai_assistant", (AVAILABLE, None)),
    ]
    return [{"id": key, "state": state, "reason": reason} for key, (state, reason) in rows]


# Categories are translated by the app ("svc.cat.<id>"). Names are the organisations' own names.
SERVICES: list[dict[str, Any]] = [
    {
        "id": "emergency",
        "items": [
            {"name": "112 Emergency (police, fire, ambulance)", "tel": "112",
             "url": "https://erss.in/", "source": "Emergency Response Support System, Government of India"},
            {"name": "108 Ambulance", "tel": "108", "url": None, "source": "Public emergency number"},
            {"name": "101 Fire", "tel": "101", "url": None, "source": "Public emergency number"},
            {"name": "1098 Childline", "tel": "1098", "url": None, "source": "Public helpline number"},
        ],
    },
    {
        "id": "bus",
        "items": [
            {"name": "BMTC official website", "tel": None, "url": "https://mybmtc.karnataka.gov.in/",
             "source": "Bengaluru Metropolitan Transport Corporation"},
        ],
    },
    {
        "id": "metro",
        "items": [
            {"name": "Namma Metro (BMRCL) official website", "tel": None, "url": "https://english.bmrc.co.in/",
             "source": "Bangalore Metro Rail Corporation Limited"},
        ],
    },
    {
        "id": "rail",
        "items": [
            {"name": "Indian Railways", "tel": "139", "url": "https://indianrailways.gov.in/",
             "source": "Ministry of Railways; 139 is the railway enquiry line"},
        ],
    },
    {
        "id": "airport",
        "items": [
            {"name": "Kempegowda International Airport Bengaluru", "tel": None,
             "url": "https://www.bengaluruairport.com/", "source": "Airport operator's official website"},
        ],
    },
    {
        "id": "traffic",
        "items": [
            {"name": "Bengaluru Traffic Police", "tel": None, "url": "https://btp.karnataka.gov.in/",
             "source": "Bengaluru Traffic Police official website"},
        ],
    },
    {
        "id": "tourism",
        "items": [
            {"name": "Karnataka Tourism", "tel": None, "url": "https://www.karnatakatourism.org/",
             "source": "Karnataka Tourism official website"},
        ],
    },
]


def services_directory() -> dict[str, Any]:
    return {
        "checked": CHECKED,
        "note": "Official websites and public helplines only. Links open the operator's own site; "
                "this app does not book, sell or confirm anything on their behalf.",
        "categories": SERVICES,
    }
