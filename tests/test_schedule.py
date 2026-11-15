"""Schedule queries: year coverage, operating days, timetables, journeys and nearby stops."""

from __future__ import annotations

import datetime as dt

from app.gtfs.importer import import_feed, reclassify_source_imports
from app.models import (
    CLASS_OFFICIAL,
    CLASS_UNVERIFIED,
    KIND_OFFICIAL,
    KIND_SYNTHETIC,
    STATUS_COMPLETED,
    DataSource,
    Route,
)
from app.services import schedule as sched
from sqlalchemy import select

from tests.helpers import (
    FEED_END,
    FEED_START,
    HOLIDAY_MONDAY_2027,
    MONDAY_2027,
    SATURDAY_2027,
    TODAY,
    make_source,
    synthetic_feed,
    valid_files,
    zip_of,
)


def load_demo(session, settings, *, start=FEED_START, end=FEED_END, holiday=None):
    """Import the synthetic demo feed as unverified data and return the stored import."""
    source = make_source(session, kind=KIND_SYNTHETIC, name="Demo")
    imp = import_feed(
        session, synthetic_feed(start, end, holiday=holiday), filename="demo.zip",
        source=source, settings=settings, today=TODAY,
    )
    assert imp.status == STATUS_COMPLETED
    return imp


def demo_route(session, short_name: str = "DEMO-1") -> Route:
    return session.scalar(select(Route).where(Route.short_name == short_name))


# ---------------------------------------------------------------- coverage

def test_coverage_is_full_for_2027_and_never_extended_into_2028(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        full = sched.year_coverage(session, CLASS_UNVERIFIED, 2027)
        assert full["status"] == "FULL"
        assert full["covered_days"] == 365
        assert full["days_in_year"] == 365

        beyond = sched.year_coverage(session, CLASS_UNVERIFIED, 2028)
        assert beyond["status"] == "NONE"
        assert beyond["covered_days"] == 0
        assert beyond["covered_from"] is None


def test_partial_coverage_is_reported_exactly(database, settings):
    with database.session() as session:
        load_demo(session, settings, start=dt.date(2026, 6, 1), end=dt.date(2027, 3, 31))
        partial = sched.year_coverage(session, CLASS_UNVERIFIED, 2027)
        assert partial["status"] == "PARTIAL"
        assert partial["covered_from"] == "2027-01-01"
        assert partial["covered_to"] == "2027-03-31"
        assert partial["covered_days"] == 31 + 28 + 31


def test_official_year_without_verified_data_shows_the_required_message(database, settings):
    with database.session() as session:
        load_demo(session, settings)  # unverified data only
        official = sched.year_coverage(session, CLASS_OFFICIAL, 2029)
        assert official["status"] == "NONE"
        assert official["message"] == "No officially verified timetable is available for this future year."


# ---------------------------------------------------------------- operating days and timetables

def test_holiday_exception_removes_weekday_service_only_on_that_date(database, settings):
    with database.session() as session:
        imp = load_demo(session, settings, holiday=HOLIDAY_MONDAY_2027)
        assert "DWKD" in sched.active_service_ids(session, imp.id, MONDAY_2027)
        assert "DWKD" not in sched.active_service_ids(session, imp.id, HOLIDAY_MONDAY_2027)
        assert "DWKE" not in sched.active_service_ids(session, imp.id, MONDAY_2027)
        assert sched.active_service_ids(session, imp.id, SATURDAY_2027) == {"DWKE"}


def test_weekend_timetable_runs_hourly_from_seven(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        timetable = sched.route_timetable(session, demo_route(session), CLASS_UNVERIFIED, SATURDAY_2027)
        # Both directions, 07:00 to 21:00 inclusive, once an hour.
        assert len(timetable["trips"]) == 2 * 15
        assert min(t["first_departure"] for t in timetable["trips"]) == "07:00:00"
        assert max(t["first_departure"] for t in timetable["trips"]) == "21:00:00"


def test_weekday_timetable_runs_every_thirty_minutes(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        timetable = sched.route_timetable(session, demo_route(session), CLASS_UNVERIFIED, MONDAY_2027)
        outbound = [t for t in timetable["trips"] if t["direction_id"] == 0]
        assert len(outbound) == 33  # 06:00 to 22:00 inclusive, every 30 minutes
        assert outbound[0]["first_departure"] == "06:00:00"
        assert outbound[-1]["first_departure"] == "22:00:00"
        assert len(timetable["trips"]) == 66


def test_timetable_outside_the_feed_has_no_trips(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        timetable = sched.route_timetable(session, demo_route(session), CLASS_UNVERIFIED, dt.date(2028, 1, 3))
        assert timetable["trips"] == []
        assert timetable["message"] == "No service operates on this date according to the feed."


def test_minimal_feed_timetable_lists_its_single_trip(database, settings):
    with database.session() as session:
        source = make_source(session)
        imp = import_feed(
            session, zip_of(valid_files()), filename="min.zip", source=source, settings=settings, today=TODAY
        )
        assert imp.status == STATUS_COMPLETED
        route = session.scalar(select(Route).where(Route.import_id == imp.id))
        timetable = sched.route_timetable(session, route, CLASS_UNVERIFIED, MONDAY_2027)
        assert [t["first_departure"] for t in timetable["trips"]] == ["08:00:00"]


# ---------------------------------------------------------------- routes, stops and geometry

def test_route_detail_returns_both_directions_and_planned_shapes(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        detail = sched.route_detail(session, demo_route(session), CLASS_UNVERIFIED)
        assert [d["direction_id"] for d in detail["directions"]] == [0, 1]

        outbound_names = [s["name"] for s in detail["directions"][0]["stops"]]
        assert detail["directions"][0]["stop_count"] == 6
        assert outbound_names[0] == "Demo Central"
        assert outbound_names[-1] == "Demo Junction"
        assert detail["directions"][1]["stops"][0]["name"] == "Demo Junction"

        assert len(detail["shapes"]) == 2
        assert "planned path" in detail["geometry_note"]
        assert detail["operating_days"] == ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def test_nearby_stops_are_closest_first_with_distances(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        results = sched.nearby_stops(session, CLASS_UNVERIFIED, lat=12.9750, lon=77.5950, radius_m=400, limit=10)
        assert results[0]["name"] == "Demo Central"
        assert results[0]["distance_m"] == 0
        distances = [r["distance_m"] for r in results]
        assert distances == sorted(distances)
        assert all(d <= 400 for d in distances)


def test_route_and_stop_search_respect_year_and_classification(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        routes = sched.search_routes(session, CLASS_UNVERIFIED, year=2027, query="demo-2", limit=10)
        assert [r["short_name"] for r in routes] == ["DEMO-2"]
        assert sched.search_routes(session, CLASS_UNVERIFIED, year=2029, query="", limit=10) == []
        assert sched.search_routes(session, CLASS_OFFICIAL, year=2027, query="", limit=10) == []

        stops = sched.search_stops(session, CLASS_UNVERIFIED, year=2027, query="junction", limit=10)
        assert [s["name"] for s in stops] == ["Demo Junction"]


# ---------------------------------------------------------------- direct journeys

def test_direct_journeys_list_departures_in_order_with_durations(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        result = sched.direct_journeys(
            session, CLASS_UNVERIFIED,
            origin_query="Demo Central", destination_query="Demo Junction", on_date=MONDAY_2027,
        )
        journeys = result["journeys"]
        assert result["message"] is None
        assert len(journeys) == 33
        departures = [j["departure"] for j in journeys]
        assert departures == sorted(departures)
        assert departures[0] == "06:00:00"
        assert departures[-1] == "22:00:00"

        first = journeys[0]
        assert first["route_number"] == "DEMO-1"
        assert first["origin_stop"] == "Demo Central"
        assert first["destination_stop"] == "Demo Junction"
        assert first["duration_minutes"] == 20  # five segments of four minutes each
        assert first["intermediate_stops"] == 4


def test_direct_journeys_respect_direction_of_travel(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        reverse = sched.direct_journeys(
            session, CLASS_UNVERIFIED,
            origin_query="Demo Junction", destination_query="Demo Central", on_date=MONDAY_2027,
        )
        assert len(reverse["journeys"]) == 33
        assert all(j["origin_stop"] == "Demo Junction" for j in reverse["journeys"])


def test_journeys_never_cross_classifications(database, settings):
    with database.session() as session:
        load_demo(session, settings)
        official = sched.direct_journeys(
            session, CLASS_OFFICIAL,
            origin_query="Demo Central", destination_query="Demo Junction", on_date=MONDAY_2027,
        )
        assert official["journeys"] == []
        assert official["message"] == sched.NO_OFFICIAL_MESSAGE

        outside = sched.direct_journeys(
            session, CLASS_UNVERIFIED,
            origin_query="Demo Central", destination_query="Demo Junction", on_date=dt.date(2028, 1, 3),
        )
        assert outside["journeys"] == []
        assert outside["message"] == "No unverified feed covers this date."


# ---------------------------------------------------------------- verification flow

def test_official_data_appears_only_after_verification(database, settings):
    with database.session() as session:
        source = DataSource(name="Official feed", publisher="Test", kind=KIND_OFFICIAL, verified=False, license="test")
        session.add(source)
        session.commit()
        import_feed(session, synthetic_feed(), filename="official.zip", source=source, settings=settings, today=TODAY)
        assert sched.year_coverage(session, CLASS_OFFICIAL, 2027)["status"] == "NONE"
        assert sched.year_coverage(session, CLASS_UNVERIFIED, 2027)["status"] == "FULL"

        source.verified = True
        assert reclassify_source_imports(session, source) == 1
        session.commit()
        assert sched.year_coverage(session, CLASS_OFFICIAL, 2027)["status"] == "FULL"
        assert sched.year_coverage(session, CLASS_UNVERIFIED, 2027)["status"] == "NONE"


# ---------------------------------------------------------------- pure helpers

def test_merge_intervals_joins_overlapping_and_adjacent_ranges():
    d = dt.date
    merged = sched.merge_intervals([
        (d(2027, 1, 1), d(2027, 1, 10)),
        (d(2027, 1, 5), d(2027, 1, 8)),
        (d(2027, 1, 11), d(2027, 1, 20)),
        (d(2027, 3, 1), d(2027, 3, 5)),
    ])
    assert merged == [(d(2027, 1, 1), d(2027, 1, 20)), (d(2027, 3, 1), d(2027, 3, 5))]


def test_gtfs_time_formatting_keeps_hours_past_24():
    assert sched.fmt_gtfs_time(25 * 3600 + 5 * 60) == "25:05:00"
    assert sched.fmt_gtfs_time(None) is None


def test_haversine_distance_is_about_right():
    # 0.1 degree of longitude on the equator is about 11.12 km.
    assert 11.1 < sched.haversine_km(0, 0, 0, 0.1) < 11.15
