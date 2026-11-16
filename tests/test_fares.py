"""Fares from the optional GTFS fare files: what is shown, what is never added up, and how bad fare files are handled.

A fare is shown only when the feed gives one that applies to the ride with no origin, destination or zone limit.
A journey with changes is never given a total, because the feed's transfer rules are not applied.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from app.gtfs.importer import import_feed
from app.models import CLASS_OFFICIAL, STATUS_COMPLETED, STATUS_REJECTED, FareAttribute, FareRule
from app.services import planner
from sqlalchemy import func, select

from tests.helpers import TODAY, admin_headers, build_transit_feed, load_transit_feed, make_source

PLAN = planner.PlanSettings(min_transfer_seconds=180, max_walk_m=300, walk_speed_mps=4.8 / 3.6)
ATTR_HEADER = "fare_id,price,currency_type,payment_method,transfers\n"
RULE_HEADER = "fare_id,route_id,origin_id,destination_id,contains_id\n"

STOPS = {
    "A": ("Alpha Stop", 12.9734, 77.5916),
    "X": ("Xray Hub", 12.9734, 77.6046),
    "B": ("Beta Stop", 13.0500, 77.7000),
}
ROUTES = {"R1": "101", "R2": "202"}
TRIPS = [
    ("T1", "R1", [("A", "08:00:00"), ("X", "08:10:00")]),
    ("U1", "R2", [("X", "08:20:00"), ("B", "08:40:00")]),
]


def plan(session, origin: str, destination: str):
    return planner.plan_journeys(
        session,
        CLASS_OFFICIAL,
        origin_query=origin,
        destination_query=destination,
        default_zone="Asia/Kolkata",
        plan=PLAN,
        on_date=dt.date(2027, 1, 11),
    )


def fare_feed(attributes: str, rules: str) -> bytes:
    return build_transit_feed(STOPS, ROUTES, TRIPS, fares=(ATTR_HEADER + attributes, RULE_HEADER + rules))


def test_a_route_fare_is_shown_on_a_direct_ride(database, settings):
    data = fare_feed("F1,10.00,INR,0,\n", "F1,R1,,,\n")
    with database.session() as session:
        load_transit_feed(session, settings, data, name="Bus")
        option = plan(session, "alpha", "xray")["options"][0]
    assert option["fare"]["code"] == "IN_FEED"
    assert option["fare"]["total"] == {"price": "10.00", "currency": "INR", "fare_id": "F1"}
    assert option["legs"][0]["fares"][0]["payment"] == "ON_BOARD"


@pytest.mark.parametrize(
    "rule",
    [
        "F2,R2,Z1,Z2,",  # limited by both an origin and a destination zone
        "F2,R2,Z1,,",  # limited by an origin zone only
        "F2,R2,,Z2,",  # limited by a destination zone only
        "F2,R2,,,Z3",  # limited to journeys that pass through a zone
    ],
)
def test_a_zone_limited_fare_is_not_shown_as_the_route_fare(database, settings, rule):
    data = fare_feed("F2,12.00,INR,0,\n", rule + "\n")
    with database.session() as session:
        load_transit_feed(session, settings, data, name="Bus")
        option = plan(session, "xray", "beta")["options"][0]
    assert option["fare"] == {"code": "NOT_IN_FEED", "total": None}


def test_a_fare_with_no_route_applies_to_every_route(database, settings):
    data = fare_feed("F3,5.00,INR,0,\n", "F3,,,,\n")
    with database.session() as session:
        load_transit_feed(session, settings, data, name="Bus")
        first = plan(session, "alpha", "xray")["options"][0]
        second = plan(session, "xray", "beta")["options"][0]
    assert first["fare"]["total"]["price"] == "5.00"
    assert second["fare"]["total"]["price"] == "5.00"


def test_fares_are_never_added_up_across_changes(database, settings):
    data = fare_feed("F1,10.00,INR,0,\nF3,5.00,INR,0,\n", "F1,R1,,,\nF3,,,,\n")
    with database.session() as session:
        load_transit_feed(session, settings, data, name="Bus")
        option = plan(session, "alpha", "beta")["options"][0]
    assert option["changes"] == 1
    assert option["fare"] == {"code": "CHANGES_NOT_PRICED", "total": None}
    assert [len(leg["fares"]) for leg in option["legs"] if leg["type"] == "ride"] == [2, 1]


def test_several_fares_for_one_ride_are_listed_cheapest_first_and_none_is_chosen(database, settings):
    data = fare_feed("F1,10.00,INR,0,\nF4,5.00,INR,1,2\n", "F1,R1,,,\nF4,R1,,,\n")
    with database.session() as session:
        load_transit_feed(session, settings, data, name="Bus")
        option = plan(session, "alpha", "xray")["options"][0]
    assert option["fare"] == {"code": "SEVERAL_IN_FEED", "total": None}
    assert [fare["price"] for fare in option["legs"][0]["fares"]] == ["5.00", "10.00"]
    assert option["legs"][0]["fares"][0]["payment"] == "BEFORE_BOARDING"


def test_a_feed_without_fare_files_still_plans_and_says_not_in_feed(database, settings):
    data = build_transit_feed(STOPS, ROUTES, TRIPS)
    with database.session() as session:
        load_transit_feed(session, settings, data, name="Bus")
        option = plan(session, "alpha", "xray")["options"][0]
    assert option["fare"] == {"code": "NOT_IN_FEED", "total": None}


def _import(session, settings, data: bytes):
    source = make_source(session, kind="OFFICIAL", verified=False, name="Fare test")
    return import_feed(session, data, filename="fares.zip", source=source, settings=settings, today=TODAY)


def test_a_malformed_fare_price_rejects_the_whole_feed(database, settings):
    data = fare_feed("F1,ten,INR,0,\n", "F1,R1,,,\n")
    with database.session() as session:
        imp = _import(session, settings, data)
        stored = session.scalar(select(func.count()).select_from(FareAttribute))
        errors = json.loads(imp.errors)
    assert imp.status == STATUS_REJECTED
    assert stored == 0
    assert any("price must be a plain amount" in message for message in errors)


def test_a_currency_that_is_not_a_three_letter_code_rejects_the_feed(database, settings):
    data = fare_feed("F1,10.00,inr,0,\n", "F1,R1,,,\n")
    with database.session() as session:
        imp = _import(session, settings, data)
    assert imp.status == STATUS_REJECTED
    assert "currency_type must be a three-letter code" in imp.errors


def test_a_payment_method_other_than_0_or_1_rejects_the_feed(database, settings):
    data = fare_feed("F1,10.00,INR,2,\n", "F1,R1,,,\n")
    with database.session() as session:
        imp = _import(session, settings, data)
    assert imp.status == STATUS_REJECTED
    assert "payment_method must be 0" in imp.errors


def test_a_rule_for_an_unknown_fare_or_route_is_skipped_with_a_warning(database, settings):
    data = fare_feed("F1,10.00,INR,0,\n", "F1,R1,,,\nNOPE,R1,,,\nF1,ROUTE-X,,,\n")
    with database.session() as session:
        imp = _import(session, settings, data)
        stored = session.scalars(select(FareRule.fare_id).where(FareRule.import_id == imp.id)).all()
    assert imp.status == STATUS_COMPLETED
    warnings = json.loads(imp.warnings)
    assert any("fare 'NOPE' is not in fare_attributes.txt" in message for message in warnings)
    assert any("route 'ROUTE-X' is not in routes.txt" in message for message in warnings)
    assert list(stored) == ["F1"]


def test_the_admin_import_report_counts_the_fare_prices_each_feed_stored(client):
    """The upload answer and the import list both give the fare count, so a feed without fares shows 0, not a guess."""
    source = client.post(
        "/api/admin/data-sources",
        headers=admin_headers(),
        json={"name": "Fare report", "publisher": "Test publisher", "kind": "COMMUNITY", "license": "test"},
    )
    assert source.status_code == 201, source.text
    source_id = str(source.json()["id"])
    with_fares = fare_feed("F1,10.00,INR,0,\nF2,15.00,INR,0,\n", "F1,R1,,,\nF2,R2,,,\n")
    plain = build_transit_feed(STOPS, ROUTES, TRIPS)

    first = client.post(
        "/api/admin/imports",
        headers=admin_headers(),
        files={"file": ("with-fares.zip", with_fares, "application/zip")},
        data={"data_source_id": source_id},
    )
    assert first.status_code == 201, first.text
    assert first.json()["import"]["fares"] == 2

    second = client.post(
        "/api/admin/imports",
        headers=admin_headers(),
        files={"file": ("no-fares.zip", plain, "application/zip")},
        data={"data_source_id": source_id},
    )
    assert second.status_code == 201, second.text
    assert second.json()["import"]["fares"] == 0

    listing = client.get("/api/admin/imports", headers=admin_headers()).json()["imports"]
    counts = {item["filename"]: item["fares"] for item in listing}
    assert counts == {"with-fares.zip": 2, "no-fares.zip": 0}
