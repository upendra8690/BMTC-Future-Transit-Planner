"""The "now" features through the API: service clock, next departures, leave-now journeys and feed expiry.

The clock is frozen with a fixed instant, so every answer is repeatable. Times are checked in the feed's own zone.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app import clock
from fastapi.testclient import TestClient

from tests.helpers import admin_headers, synthetic_feed, valid_files, zip_of

# Monday 11 January 2027, 08:10 in Bengaluru (02:40 UTC).
MONDAY_0810_IST = dt.datetime(2027, 1, 11, 2, 40, tzinfo=dt.UTC)


@pytest.fixture
def frozen_now(monkeypatch):
    holder = {"now": MONDAY_0810_IST}
    monkeypatch.setattr(clock, "utc_now", lambda: holder["now"])
    return holder


def _kolkata_files() -> dict[str, str]:
    """The minimal valid feed, with its agency in Bengaluru's zone so the clock values read as India time."""
    files = valid_files()
    files["agency.txt"] = (
        "agency_id,agency_name,agency_url,agency_timezone\nT,Test Agency,https://example.invalid,Asia/Kolkata\n"
    )
    return files


def _upload(client: TestClient, data: bytes, kind: str = "SYNTHETIC_DEMO") -> dict:
    source = client.post(
        "/api/admin/data-sources",
        json={"name": "Feed", "publisher": "Test", "kind": kind, "license": "test"},
        headers=admin_headers(),
    ).json()
    response = client.post(
        "/api/admin/imports",
        files={"file": ("feed.zip", data, "application/zip")},
        data={"data_source_id": str(source["id"])},
        headers=admin_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()["import"]


def _stop_id(client: TestClient, name: str, classification: str = "UNVERIFIED_FEED") -> int:
    found = client.get(
        "/api/stops", params={"classification": classification, "year": 2027, "q": name, "limit": 5}
    ).json()["results"]
    assert found, f"no stop named {name}"
    return found[0]["id"]


@pytest.fixture
def demo_client(client: TestClient, frozen_now) -> TestClient:
    _upload(client, synthetic_feed())
    return client


def test_clock_reports_bengaluru_time_and_the_service_date(demo_client: TestClient):
    body = demo_client.get("/api/clock").json()
    assert body["service_timezone"] == "Asia/Kolkata"
    assert body["timezone_source"] == "feed"
    assert body["now_local"] == "2027-01-11T08:10:00+05:30"
    assert body["service_date"] == "2027-01-11"
    assert body["weekday"] == "MON"
    assert body["now_utc"] == "2027-01-11T02:40:00Z"
    feeds = {feed["classification"]: feed for feed in body["feeds"]}
    assert feeds["UNVERIFIED_FEED"]["state"] == "COVERS_TODAY"
    assert feeds["UNVERIFIED_FEED"]["covers_today"] is True
    assert feeds["OFFICIAL_VERIFIED"]["state"] == "NO_FEED"


def test_clock_says_when_the_feed_has_expired(client: TestClient, frozen_now):
    _upload(client, synthetic_feed())
    frozen_now["now"] = dt.datetime(2028, 2, 1, 3, 0, tzinfo=dt.UTC)
    feeds = {feed["classification"]: feed for feed in client.get("/api/clock").json()["feeds"]}
    assert feeds["UNVERIFIED_FEED"]["state"] == "EXPIRED"
    assert feeds["UNVERIFIED_FEED"]["latest_end"] == "2027-12-31"


def test_next_departures_start_from_now_in_local_time(demo_client: TestClient):
    stop_id = _stop_id(demo_client, "Demo Market")
    body = demo_client.get(f"/api/stops/{stop_id}/departures", params={"classification": "UNVERIFIED_FEED"}).json()
    departures = body["departures"]
    assert departures, body
    # Every listed departure is in the future, earliest first, and says it is scheduled rather than live.
    assert all(d["minutes_from_now"] >= 0 for d in departures)
    assert [d["departure_local"] for d in departures] == sorted(d["departure_local"] for d in departures)
    assert all(d["live"] is False for d in departures)
    # DEMO-2's direction 1 trip reaches Demo Market at 08:12 and ends there, so it is not a departure from it.
    # The next departure leaves at 08:16 (see app/gtfs/synthetic.py).
    assert "2027-01-11T08:12:00+05:30" not in [d["departure_local"] for d in departures]
    first = departures[0]
    assert first["departure_local"] == "2027-01-11T08:16:00+05:30"
    assert first["minutes_from_now"] == 6
    assert first["service_date"] == "2027-01-11"
    assert first["next_day"] is False
    assert all(d["departure_local"] >= "2027-01-11T08:10" for d in departures)


def test_next_departures_roll_forward_as_time_passes(demo_client: TestClient, frozen_now):
    stop_id = _stop_id(demo_client, "Demo Market")
    frozen_now["now"] = dt.datetime(2027, 1, 11, 2, 43, tzinfo=dt.UTC)  # 08:13 local
    departures = demo_client.get(
        f"/api/stops/{stop_id}/departures", params={"classification": "UNVERIFIED_FEED"}
    ).json()["departures"]
    assert departures[0]["departure_local"] == "2027-01-11T08:16:00+05:30"
    assert departures[0]["minutes_from_now"] == 3


def test_departures_are_limited_and_the_limit_is_validated(demo_client: TestClient):
    stop_id = _stop_id(demo_client, "Demo Market")
    short = demo_client.get(
        f"/api/stops/{stop_id}/departures", params={"classification": "UNVERIFIED_FEED", "limit": 3}
    ).json()
    assert len(short["departures"]) == 3
    assert demo_client.get(
        f"/api/stops/{stop_id}/departures", params={"classification": "UNVERIFIED_FEED", "limit": 0}
    ).status_code == 422


def test_a_stop_is_not_found_in_the_wrong_classification(demo_client: TestClient):
    stop_id = _stop_id(demo_client, "Demo Market")
    response = demo_client.get(f"/api/stops/{stop_id}/departures", params={"classification": "OFFICIAL_VERIFIED"})
    assert response.status_code == 404
    assert demo_client.get("/api/stops/999999/departures").status_code == 404
    assert demo_client.get("/api/stops/1/departures", params={"classification": "BOGUS"}).status_code == 400


def test_a_trip_past_midnight_is_listed_on_the_service_day_it_started(client: TestClient, frozen_now):
    """A bus written as 25:10:00 leaves at 01:10 the next morning. At 00:30 that departure is still ahead."""
    files = _kolkata_files()  # service Monday to Friday
    files["stop_times.txt"] = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,25:10:00,25:10:00,S1,1\nT1,25:20:00,25:20:00,S2,2\n"
    )
    _upload(client, zip_of(files))
    frozen_now["now"] = dt.datetime(2027, 1, 11, 19, 0, tzinfo=dt.UTC)  # 00:30 on Tuesday 12 January, IST
    stop_id = _stop_id(client, "Alpha")
    departures = client.get(f"/api/stops/{stop_id}/departures", params={"classification": "UNVERIFIED_FEED"}).json()[
        "departures"
    ]
    first = departures[0]
    assert first["gtfs_time"] == "25:10:00"
    assert first["service_date"] == "2027-01-11"  # the Monday service that started the journey
    assert first["departure_local"] == "2027-01-12T01:10:00+05:30"
    assert first["next_day"] is True
    assert first["minutes_from_now"] == 40


def test_a_past_midnight_trip_disappears_once_it_has_left(client: TestClient, frozen_now):
    files = _kolkata_files()
    files["stop_times.txt"] = (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,25:10:00,25:10:00,S1,1\nT1,25:20:00,25:20:00,S2,2\n"
    )
    _upload(client, zip_of(files))
    frozen_now["now"] = dt.datetime(2027, 1, 11, 19, 50, tzinfo=dt.UTC)  # 01:20 on 12 January IST
    stop_id = _stop_id(client, "Alpha")
    departures = client.get(f"/api/stops/{stop_id}/departures", params={"classification": "UNVERIFIED_FEED"}).json()[
        "departures"
    ]
    assert departures[0]["service_date"] == "2027-01-12"
    assert departures[0]["departure_local"] == "2027-01-13T01:10:00+05:30"


def test_a_trip_is_not_a_departure_from_the_stop_where_it_ends(client: TestClient, frozen_now):
    """T1 ends at Beta. The feed gives it a time there, but no bus leaves Beta on that trip."""
    _upload(client, zip_of(_kolkata_files()))
    frozen_now["now"] = dt.datetime(2027, 1, 11, 2, 0, tzinfo=dt.UTC)  # 07:30 on Monday in Bengaluru
    beta = _stop_id(client, "Beta")
    body = client.get(f"/api/stops/{beta}/departures", params={"classification": "UNVERIFIED_FEED"}).json()
    assert body["departures"] == []
    assert body["message_code"] == "NO_DEPARTURES"


def test_after_the_last_bus_today_the_next_departure_is_on_the_next_service_day(client: TestClient, frozen_now):
    """Alpha's only bus on Monday left at 08:00. Service runs Monday to Friday, so the next one is on Tuesday."""
    _upload(client, zip_of(_kolkata_files()))
    frozen_now["now"] = dt.datetime(2027, 1, 11, 4, 0, tzinfo=dt.UTC)  # 09:30 on Monday in Bengaluru
    alpha = _stop_id(client, "Alpha")
    departures = client.get(f"/api/stops/{alpha}/departures", params={"classification": "UNVERIFIED_FEED"}).json()[
        "departures"
    ]
    assert departures[0]["departure_local"] == "2027-01-12T08:00:00+05:30"
    assert departures[0]["service_date"] == "2027-01-12"
    assert departures[0]["minutes_from_now"] == 22 * 60 + 30


def test_the_next_departure_after_a_friday_skips_the_weekend(client: TestClient, frozen_now):
    _upload(client, zip_of(_kolkata_files()))
    frozen_now["now"] = dt.datetime(2027, 1, 15, 4, 0, tzinfo=dt.UTC)  # 09:30 on Friday in Bengaluru
    alpha = _stop_id(client, "Alpha")
    departures = client.get(f"/api/stops/{alpha}/departures", params={"classification": "UNVERIFIED_FEED"}).json()[
        "departures"
    ]
    assert departures[0]["departure_local"] == "2027-01-18T08:00:00+05:30"


def test_leave_now_finds_the_next_direct_trip_on_a_later_service_day(client: TestClient, frozen_now):
    _upload(client, zip_of(_kolkata_files()))
    frozen_now["now"] = dt.datetime(2027, 1, 11, 4, 0, tzinfo=dt.UTC)  # 09:30 on Monday in Bengaluru
    body = client.get(
        "/api/journey", params={"origin": "Alpha", "destination": "Beta", "classification": "UNVERIFIED_FEED"}
    ).json()
    assert body["journeys"][0]["departure_local"] == "2027-01-12T08:00:00+05:30"


def test_leave_now_lists_only_trips_still_to_come(demo_client: TestClient):
    body = demo_client.get(
        "/api/journey",
        params={"origin": "Demo Central", "destination": "Demo Junction", "classification": "UNVERIFIED_FEED"},
    ).json()
    assert body["mode"] == "now"
    assert body["service_timezone"] == "Asia/Kolkata"
    assert body["journeys"], body
    first = body["journeys"][0]
    assert first["departure_local"] == "2027-01-11T08:30:00+05:30"
    assert first["minutes_from_now"] == 20
    assert all(j["minutes_from_now"] >= 0 for j in body["journeys"])


def test_a_chosen_date_still_lists_the_whole_day(demo_client: TestClient):
    body = demo_client.get(
        "/api/journey",
        params={
            "origin": "Demo Central", "destination": "Demo Junction",
            "date": "2027-01-11", "classification": "UNVERIFIED_FEED",
        },
    ).json()
    assert body["mode"] == "date"
    assert body["journeys"][0]["departure_local"] == "2027-01-11T06:00:00+05:30"
    assert body["journeys"][0]["minutes_from_now"] is None


def test_leave_now_never_invents_trips_after_the_feed_ends(demo_client: TestClient, frozen_now):
    frozen_now["now"] = dt.datetime(2028, 3, 1, 3, 0, tzinfo=dt.UTC)
    body = demo_client.get(
        "/api/journey",
        params={"origin": "Demo Central", "destination": "Demo Junction", "classification": "UNVERIFIED_FEED"},
    ).json()
    assert body["journeys"] == []
    assert body["message_code"] == "NO_DIRECT_SERVICE"


def test_journey_without_both_names_has_a_coded_message(demo_client: TestClient):
    body = demo_client.get(
        "/api/journey", params={"origin": "Demo Central", "destination": "  ", "classification": "UNVERIFIED_FEED"}
    )
    assert body.status_code == 200
    assert body.json()["message_code"] == "NEED_BOTH_STOPS"


def test_official_journeys_say_there_is_no_official_data(demo_client: TestClient):
    body = demo_client.get(
        "/api/journey",
        params={"origin": "Demo Central", "destination": "Demo Junction", "classification": "OFFICIAL_VERIFIED"},
    ).json()
    assert body["journeys"] == []
    assert body["message_code"] == "NO_OFFICIAL_DATA"


def test_year_status_uses_the_service_date_not_the_server_date(client: TestClient, frozen_now):
    # 20:00 UTC on 31 December is already 01:30 on 1 January in Bengaluru, so 2027 has started there.
    frozen_now["now"] = dt.datetime(2026, 12, 31, 20, 0, tzinfo=dt.UTC)
    assert client.get("/api/years/2027/status").json()["is_future"] is False
    assert client.get("/api/years/2028/status").json()["is_future"] is True
    frozen_now["now"] = dt.datetime(2026, 12, 31, 10, 0, tzinfo=dt.UTC)  # 15:30 on 31 December in Bengaluru
    assert client.get("/api/years/2027/status").json()["is_future"] is True


def test_timetable_outside_the_feed_has_a_code(demo_client: TestClient):
    route = demo_client.get(
        "/api/routes", params={"classification": "UNVERIFIED_FEED", "year": 2027, "q": "DEMO-1"}
    ).json()["results"][0]
    body = demo_client.get(f"/api/routes/{route['id']}/timetable", params={"date": "2025-01-01"}).json()
    assert body["covered"] is False
    assert body["message_code"] == "NOT_COVERED"
    covered = demo_client.get(f"/api/routes/{route['id']}/timetable", params={"date": "2027-01-11"}).json()
    assert covered["message_code"] is None
    assert covered["trips"][0]["first_departure_seconds"] == 6 * 3600


def test_meta_reports_the_current_version(client: TestClient):
    assert client.get("/api/meta").json()["version"] == "2.0.0"


def test_the_synthetic_feed_still_covers_the_whole_window(demo_client: TestClient):
    years = demo_client.get("/api/years/compare").json()["years"]
    assert [y["year"] for y in years] == [2027, 2028, 2029, 2030]
    assert years[0]["unverified"]["status"] == "FULL"
