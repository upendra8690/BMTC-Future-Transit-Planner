"""Journey planning: direct, one-change and two-change journeys, walks, the minimum change time, midnight rollover,
trips that overtake each other, cross-feed walks, classification separation and removal of an import.

Every feed is built inside the test, so each expected time is known exactly.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from app.models import CLASS_OFFICIAL, CLASS_UNVERIFIED, KIND_UNKNOWN, GtfsImport
from app.services import planner

from tests.helpers import build_transit_feed as build_feed
from tests.helpers import load_transit_feed as load

IST = ZoneInfo("Asia/Kolkata")
MONDAY = dt.date(2027, 1, 11)
# Central Bengaluru. At this latitude one degree of longitude is about 108.5 km, so 0.0019 degrees is about 206 m,
# 0.0030 degrees is about 325 m, and 0.0100 degrees is about 1.09 km. The origin is 325 m west of Papa, which is just
# outside the 300 m walking limit, so the origin cannot walk to Papa or Quebec and skip the journey being tested.
HERE = (12.9734, 77.5916)
ELSEWHERE = (13.0500, 77.7000)
PAPA = (12.9734, 77.5946)
QUEBEC_NEAR = (12.9734, 77.5965)  # about 206 m east of Papa
QUEBEC_FAR = (12.9734, 77.6046)  # about 1.09 km east of Papa, and about 1.4 km from HERE

PLAN = planner.PlanSettings(min_transfer_seconds=180, max_walk_m=300, walk_speed_mps=4.8 / 3.6)


@pytest.fixture(autouse=True)
def fresh_network_cache():
    planner.clear_network_cache()
    yield
    planner.clear_network_cache()


def plan(session, origin: str, destination: str, *, day=MONDAY, max_changes=2, settings=PLAN,
         classification=CLASS_OFFICIAL):
    return planner.plan_journeys(
        session,
        classification,
        origin_query=origin,
        destination_query=destination,
        default_zone="Asia/Kolkata",
        plan=settings,
        max_changes=max_changes,
        on_date=day,
    )


def clock_of(iso: str) -> str:
    """'2027-01-11T08:20+05:30' -> '08:20'."""
    return iso[11:16]


def ride_legs(option: dict) -> list[dict]:
    return [leg for leg in option["legs"] if leg["type"] == "ride"]


def walk_legs(option: dict) -> list[dict]:
    return [leg for leg in option["legs"] if leg["type"] == "walk"]


# ----------------------------------------------------------------------------------------- direct journeys

def test_a_direct_journey_is_one_ride_labelled_earliest(database, settings):
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("B", "08:20:00")]),
            ("T2", "R1", [("A", "08:30:00"), ("B", "08:50:00")]),
        ],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta")
    assert result["message"] is None
    assert result["classification"] == CLASS_OFFICIAL
    assert result["realtime"] is False
    assert len(result["options"]) == 1
    option = result["options"][0]
    assert option["rides"] == 1
    assert option["changes"] == 0
    assert clock_of(option["departs_at"]) == "08:00"
    assert clock_of(option["arrives_at"]) == "08:20"
    assert option["labels"] == ["EARLIEST_ARRIVAL"]
    leg = ride_legs(option)[0]
    assert leg["route_number"] == "101"
    assert leg["timing"] == "scheduled"
    assert leg["source"]["classification"] == CLASS_OFFICIAL
    assert leg["from"]["name"] == "Alpha Stop"
    assert leg["to"]["name"] == "Beta Stop"
    assert option["fare"]["code"] == "NOT_IN_FEED"
    assert result["sources"][0]["name"] == "Bus"


# ------------------------------------------------------------------------------------------ changes

def test_one_change_waits_for_the_minimum_change_time(database, settings):
    """The first connection leaves two minutes after the bus arrives, which is less than the three-minute minimum."""
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "X": ("Xray Hub", *QUEBEC_FAR), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101", "R2": "202"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("X", "08:10:00")]),
            ("U1", "R2", [("X", "08:12:00"), ("B", "08:30:00")]),
            ("U2", "R2", [("X", "08:15:00"), ("B", "08:35:00")]),
        ],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta")
    assert len(result["options"]) == 1
    option = result["options"][0]
    assert option["changes"] == 1
    assert clock_of(option["arrives_at"]) == "08:35"
    rides = ride_legs(option)
    assert [leg["route_number"] for leg in rides] == ["101", "202"]
    assert clock_of(rides[1]["departs_at"]) == "08:15"


def test_a_zero_minute_change_time_takes_the_earlier_connection(database, settings):
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "X": ("Xray Hub", *QUEBEC_FAR), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101", "R2": "202"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("X", "08:10:00")]),
            ("U1", "R2", [("X", "08:12:00"), ("B", "08:30:00")]),
            ("U2", "R2", [("X", "08:15:00"), ("B", "08:35:00")]),
        ],
    )
    no_minimum = planner.PlanSettings(min_transfer_seconds=0, max_walk_m=300, walk_speed_mps=4.8 / 3.6)
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta", settings=no_minimum)
    assert clock_of(result["options"][0]["arrives_at"]) == "08:30"


def test_two_changes_are_found_and_max_changes_is_respected(database, settings):
    data = build_feed(
        {
            "A": ("Alpha Stop", *HERE),
            "X": ("Xray Hub", *QUEBEC_FAR),
            "Y": ("Yankee Hub", *ELSEWHERE),
            "B": ("Beta Stop", 13.1000, 77.8000),
        },
        {"R1": "101", "R2": "202", "R3": "303"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("X", "08:10:00")]),
            ("T2", "R2", [("X", "08:20:00"), ("Y", "08:30:00")]),
            ("T3", "R3", [("Y", "08:40:00"), ("B", "08:50:00")]),
        ],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        found = plan(session, "alpha", "beta", max_changes=2)
        one_change = plan(session, "alpha", "beta", max_changes=1)
        no_change = plan(session, "alpha", "beta", max_changes=0)
    assert len(found["options"]) == 1
    option = found["options"][0]
    assert option["rides"] == 3
    assert option["changes"] == 2
    assert clock_of(option["arrives_at"]) == "08:50"
    assert [leg["route_number"] for leg in ride_legs(option)] == ["101", "202", "303"]
    assert one_change["options"] == []
    assert one_change["message_code"] == "NO_PLANNED_JOURNEY"
    assert no_change["options"] == []
    assert no_change["message_code"] == "NO_PLANNED_JOURNEY"


def test_the_fewest_changes_and_earliest_arrival_can_be_two_different_options(database, settings):
    """A direct bus leaves at 08:00 and arrives at 09:00. A bus with one change arrives at 08:40."""
    data = build_feed(
        {
            "A": ("Alpha Stop", *HERE),
            "X": ("Xray Hub", *QUEBEC_FAR),
            "B": ("Beta Stop", *ELSEWHERE),
        },
        {"R1": "101", "R2": "202", "R3": "303"},
        [
            ("SLOW", "R3", [("A", "08:00:00"), ("B", "09:00:00")]),
            ("T1", "R1", [("A", "08:00:00"), ("X", "08:10:00")]),
            ("U1", "R2", [("X", "08:20:00"), ("B", "08:40:00")]),
        ],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta")
    options = result["options"]
    assert [option["changes"] for option in options] == [1, 0]
    by_changes = {option["changes"]: option for option in options}
    assert clock_of(by_changes[1]["arrives_at"]) == "08:40"
    assert clock_of(by_changes[0]["arrives_at"]) == "09:00"
    assert by_changes[1]["labels"] == ["EARLIEST_ARRIVAL"]
    assert by_changes[0]["labels"] == ["FEWEST_CHANGES"]


# ------------------------------------------------------------------------------------------- walks

def test_a_walk_between_stops_about_200_metres_apart_joins_two_routes(database, settings):
    """Papa and Quebec are about 200 m apart. The walk takes about 2.5 minutes, so the 08:20 bus can still be caught."""
    data = build_feed(
        {
            "A": ("Alpha Stop", *HERE),
            "P": ("Papa Stop", *PAPA),
            "Q": ("Quebec Stop", *QUEBEC_NEAR),
            "B": ("Beta Stop", *ELSEWHERE),
        },
        {"R1": "101", "R2": "202"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("P", "08:10:00")]),
            ("U1", "R2", [("Q", "08:20:00"), ("B", "08:40:00")]),
        ],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta")
    option = result["options"][0]
    assert option["changes"] == 1
    assert clock_of(option["arrives_at"]) == "08:40"
    assert [leg["type"] for leg in option["legs"]] == ["ride", "walk", "ride"]
    walk = walk_legs(option)[0]
    assert 190 <= walk["distance_m"] <= 215
    assert walk["estimated"] is True
    assert walk["from"]["name"] == "Papa Stop"
    assert walk["to"]["name"] == "Quebec Stop"


def test_stops_about_a_kilometre_apart_are_not_joined_by_a_walk(database, settings):
    data = build_feed(
        {
            "A": ("Alpha Stop", *HERE),
            "P": ("Papa Stop", *PAPA),
            "Q": ("Quebec Stop", *QUEBEC_FAR),
            "B": ("Beta Stop", *ELSEWHERE),
        },
        {"R1": "101", "R2": "202"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("P", "08:10:00")]),
            ("U1", "R2", [("Q", "08:20:00"), ("B", "08:40:00")]),
        ],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta")
    assert result["options"] == []
    assert result["message_code"] == "NO_PLANNED_JOURNEY"


def test_walking_can_be_switched_off(database, settings):
    data = build_feed(
        {
            "A": ("Alpha Stop", *HERE),
            "P": ("Papa Stop", *PAPA),
            "Q": ("Quebec Stop", *QUEBEC_NEAR),
            "B": ("Beta Stop", *ELSEWHERE),
        },
        {"R1": "101", "R2": "202"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("P", "08:10:00")]),
            ("U1", "R2", [("Q", "08:20:00"), ("B", "08:40:00")]),
        ],
    )
    no_walks = planner.PlanSettings(min_transfer_seconds=180, max_walk_m=0, walk_speed_mps=4.8 / 3.6)
    with database.session() as session:
        load(session, settings, data, name="Bus")
        assert plan(session, "alpha", "beta", settings=no_walks)["options"] == []


# ----------------------------------------------------------------------------------- service days

def test_a_trip_after_midnight_is_found_on_the_date_it_arrives(database, settings):
    """A trip of the previous service day that runs past 24:00 leaves at 00:50 on the requested date."""
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("N1", "R1", [("A", "24:50:00"), ("B", "25:20:00")])],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta", day=MONDAY)
    option = result["options"][0]
    assert clock_of(option["departs_at"]) == "00:50"
    assert clock_of(option["arrives_at"]) == "01:20"
    assert option["departs_at"].startswith("2027-01-11T")
    assert ride_legs(option)[0]["service_date"] == "2027-01-10"


def test_planning_now_uses_the_next_three_hours(database, settings):
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("B", "08:20:00")]),
            ("T2", "R1", [("A", "12:00:00"), ("B", "12:20:00")]),
        ],
    )
    now = dt.datetime(2027, 1, 11, 7, 55, tzinfo=IST)
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = planner.plan_journeys(
            session,
            CLASS_OFFICIAL,
            origin_query="alpha",
            destination_query="beta",
            default_zone="Asia/Kolkata",
            plan=PLAN,
            now=now,
        )
    assert result["mode"] == "now"
    assert [clock_of(option["departs_at"]) for option in result["options"]] == ["08:00"]


# ------------------------------------------------------------------------------- overtaking trips

def test_a_faster_trip_that_departs_later_is_not_missed(database, settings):
    """The 08:00 trip is slow. The 08:05 trip overtakes it, so it must still be found and used."""
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [
            ("SLOW", "R1", [("A", "08:00:00"), ("B", "08:30:00")]),
            ("FAST", "R1", [("A", "08:05:00"), ("B", "08:15:00")]),
        ],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta")
    option = result["options"][0]
    assert clock_of(option["departs_at"]) == "08:05"
    assert clock_of(option["arrives_at"]) == "08:15"


# ------------------------------------------------------------------------------ no path and inputs

def test_disconnected_stops_have_no_journey(database, settings):
    data = build_feed(
        {
            "A": ("Alpha Stop", *HERE),
            "C": ("Charlie Stop", 12.9900, 77.6200),
            "D": ("Delta Stop", 13.0100, 77.6400),
            "B": ("Beta Stop", *ELSEWHERE),
        },
        {"R1": "101", "R2": "202"},
        [
            ("T1", "R1", [("A", "08:00:00"), ("C", "08:10:00")]),
            ("U1", "R2", [("D", "08:20:00"), ("B", "08:40:00")]),
        ],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta")
    assert result["options"] == []
    assert result["message_code"] == "NO_PLANNED_JOURNEY"


def test_an_unknown_origin_and_the_same_stop_are_refused(database, settings):
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("T1", "R1", [("A", "08:00:00"), ("B", "08:20:00")])],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        unknown = plan(session, "nowhere", "beta")
        same = plan(session, "alpha", "ALPHA")
        blank = plan(session, "  ", "beta")
    assert unknown["message_code"] == "ORIGIN_NOT_FOUND"
    assert same["message_code"] == "SAME_STOP"
    assert blank["message_code"] == "NEED_BOTH_STOPS"


def test_a_date_with_no_covering_feed_says_so(database, settings):
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("T1", "R1", [("A", "08:00:00"), ("B", "08:20:00")])],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "alpha", "beta", day=dt.date(2031, 6, 1))
    assert result["options"] == []
    assert result["message_code"] == "NO_OFFICIAL_DATA"


def test_a_wrong_max_changes_is_rejected_by_the_planner(database):
    with database.session() as session, pytest.raises(ValueError):
        plan(session, "alpha", "beta", max_changes=3)


# ----------------------------------------------------------------------------- feeds and classes

def test_two_official_feeds_are_joined_by_a_walk_and_both_are_named(database, settings):
    bus = build_feed(
        {"A": ("Alpha Stop", *HERE), "P": ("Papa Stop", *PAPA)},
        {"R1": "101"},
        [("T1", "R1", [("A", "08:00:00"), ("P", "08:10:00")])],
    )
    metro = build_feed(
        {
            "Q": ("Quebec Stop", *QUEBEC_NEAR),
            "B": ("Beta Stop", *ELSEWHERE),
        },
        {"M1": "Green"},
        [("G1", "M1", [("Q", "08:20:00"), ("B", "08:40:00")])],
    )
    with database.session() as session:
        load(session, settings, bus, name="Bus source")
        load(session, settings, metro, name="Metro source")
        result = plan(session, "alpha", "beta")
    option = result["options"][0]
    assert option["changes"] == 1
    rides = ride_legs(option)
    assert rides[0]["source"]["name"] == "Bus source"
    assert rides[1]["source"]["name"] == "Metro source"
    assert {source["name"] for source in result["sources"]} == {"Bus source", "Metro source"}


def test_the_official_plan_never_uses_unverified_data(database, settings):
    official = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("T1", "R1", [("A", "08:00:00"), ("B", "08:20:00")])],
    )
    unverified = build_feed(
        {"G": ("Gamma Stop", 12.9900, 77.6200), "D": ("Delta Stop", 13.0100, 77.6400)},
        {"X1": "909"},
        [("V1", "X1", [("G", "09:00:00"), ("D", "09:20:00")])],
    )
    with database.session() as session:
        load(session, settings, official, name="Bus")
        load(session, settings, unverified, name="Community", kind=KIND_UNKNOWN, verified=False)
        hidden = plan(session, "gamma", "delta")
        shown = plan(session, "gamma", "delta", classification=CLASS_UNVERIFIED)
    assert hidden["message_code"] == "ORIGIN_NOT_FOUND"
    assert hidden["classification"] == CLASS_OFFICIAL
    option = shown["options"][0]
    assert ride_legs(option)[0]["source"]["classification"] == CLASS_UNVERIFIED


def test_deleting_an_import_removes_its_journeys(database, settings):
    data = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("T1", "R1", [("A", "08:00:00"), ("B", "08:20:00")])],
    )
    with database.session() as session:
        imp = load(session, settings, data, name="Bus")
        assert plan(session, "alpha", "beta")["options"]
        session.delete(session.get(GtfsImport, imp.id))
        session.commit()
        after = plan(session, "alpha", "beta")
    assert after["options"] == []
    assert after["message_code"] == "NO_OFFICIAL_DATA"


def test_replacing_an_import_changes_the_answer_even_after_a_query_has_cached_it(database, settings):
    """Query the first timetable so its network is cached. After it is replaced, the answer must use the new one."""
    first = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("T1", "R1", [("A", "08:00:00"), ("B", "08:20:00")])],
    )
    second = build_feed(
        {"A": ("Alpha Stop", *HERE), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("T1", "R1", [("A", "09:00:00"), ("B", "09:20:00")])],
    )
    with database.session() as session:
        imp = load(session, settings, first, name="Bus")
        assert clock_of(plan(session, "alpha", "beta")["options"][0]["departs_at"]) == "08:00"
        session.delete(session.get(GtfsImport, imp.id))
        session.commit()
        load(session, settings, second, name="Bus replacement")
        replaced = plan(session, "alpha", "beta")
    assert clock_of(replaced["options"][0]["departs_at"]) == "09:00"
    assert clock_of(replaced["options"][0]["arrives_at"]) == "09:20"


def test_on_a_date_a_journey_that_starts_with_a_walk_leaves_just_in_time(database, settings):
    """Walking first: the traveller should set off so as to reach the bus as it leaves, not at midnight."""
    data = build_feed(
        {"Q": ("Quebec Near Stop", *QUEBEC_NEAR), "P": ("Papa Stop", *PAPA), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("T1", "R1", [("P", "08:20:00"), ("B", "08:50:00")])],
    )
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = plan(session, "quebec near", "beta")
    option = result["options"][0]
    walk = option["legs"][0]
    assert walk["type"] == "walk"
    assert clock_of(walk["arrives_at"]) == "08:20"
    assert clock_of(walk["starts_at"]) == "08:17"  # about 155 seconds of walking for 206 metres
    assert clock_of(option["departs_at"]) == "08:17"
    assert option["legs"][1]["departs_at"] == walk["arrives_at"]
    assert option["wait_minutes"] is None  # a wait counted from midnight would be meaningless


def test_planning_now_with_a_walk_first_waits_only_after_the_walk(database, settings):
    data = build_feed(
        {"Q": ("Quebec Near Stop", *QUEBEC_NEAR), "P": ("Papa Stop", *PAPA), "B": ("Beta Stop", *ELSEWHERE)},
        {"R1": "101"},
        [("T1", "R1", [("P", "08:20:00"), ("B", "08:50:00")])],
    )
    now = dt.datetime(2027, 1, 11, 8, 0, tzinfo=IST)
    with database.session() as session:
        load(session, settings, data, name="Bus")
        result = planner.plan_journeys(
            session, CLASS_OFFICIAL, origin_query="quebec near", destination_query="beta",
            default_zone="Asia/Kolkata", plan=PLAN, now=now,
        )
    option = result["options"][0]
    assert clock_of(option["departs_at"]) == "08:00"
    assert clock_of(option["legs"][0]["arrives_at"]) == "08:02"
    assert option["wait_minutes"] == 17  # 20 minutes to the bus, less the walk of about 2.5 minutes
