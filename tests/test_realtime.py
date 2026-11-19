"""Live vehicles and arrival estimates (GTFS-Realtime provider adapter).

Every live answer in these tests comes from a feed built in the test, decoded by the app and matched with a small
timetable. Without a configured feed the app says "not connected" and never shows a vehicle.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from app import clock
from app.main import create_app
from app.services import realtime
from app.services.realtime import FeedError, LiveService, parse_feed
from fastapi.testclient import TestClient

from tests import realtime_feed as rt
from tests.helpers import build_transit_feed, load_transit_feed, make_settings

IST = ZoneInfo("Asia/Kolkata")
NOW = dt.datetime(2027, 3, 10, 8, 12, tzinfo=IST).astimezone(dt.UTC)
T = int(NOW.timestamp())
MIDNIGHT = int(dt.datetime(2027, 3, 10, tzinfo=IST).timestamp())
STOPS = {"A": ("Kempegowda Bus Station", 12.977, 77.572), "B": ("Corporation", 12.966, 77.587),
         "C": ("Shanti Nagar", 12.957, 77.597), "D": ("Koramangala", 12.935, 77.624)}
TIMETABLE = build_transit_feed(STOPS, {"R1": "500D"}, [
    ("T1", "R1", [("A", "08:00:00"), ("B", "08:10:00"), ("C", "08:20:00"), ("D", "08:30:00")]),
    ("T2", "R1", [("A", "08:30:00"), ("B", "08:40:00"), ("C", "08:50:00"), ("D", "09:00:00")]),
])


class Stub:
    def __init__(self, data):
        self.data = data
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if isinstance(self.data, Exception):
            raise self.data
        return parse_feed(self.data)


def at(hhmm: str) -> int:
    hours, minutes = map(int, hhmm.split(":"))
    return MIDNIGHT + hours * 3600 + minutes * 60


def standard_feed(**extra) -> bytes:
    entities = [
        rt.vehicle("e1", vehicle_id="KA-01-F-1234", label="Bus 1234", trip_id="T1", route_id="R1",
                   start_date="20270310", lat=12.970, lon=77.580, timestamp=T - 15, stop_sequence=2, status=2,
                   bearing=120.0, speed=5.0),
        rt.trip_update("u1", trip_id="T1", route_id="R1", start_date="20270310", vehicle_label="Bus 1234",
                       timestamp=T - 20, stops=[(2, "B", None, 120, False)]),
    ]
    entities += extra.get("more", [])
    return rt.feed(extra.get("timestamp", T - 10), entities)


@pytest.fixture
def live(tmp_path, monkeypatch):
    """A real-mode server with an official timetable and a feed provider the test controls."""
    monkeypatch.setattr(clock, "utc_now", lambda: NOW)
    settings = make_settings(tmp_path, demo_mode=False)
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.db.session() as session:
            load_transit_feed(session, settings, TIMETABLE, name="Test operator")

        def use(data, **overrides):
            stub = Stub(data)
            app.state.live = LiveService(make_settings(tmp_path, demo_mode=False, **overrides), provider=stub)
            return stub

        client.use = use
        yield client
    app.state.db.dispose()


# ---------------------------------------------------------------- decoding
def test_a_feed_is_decoded_field_by_field():
    feed = parse_feed(standard_feed(more=[rt.trip_update("u2", trip_id="T2", delay=-60, stops=[])]))
    assert feed.timestamp == T - 10
    vehicle = feed.vehicles[0]
    assert (vehicle.vehicle_id, vehicle.label, vehicle.trip_id, vehicle.route_id) == ("KA-01-F-1234", "Bus 1234",
                                                                                    "T1", "R1")
    assert vehicle.lat == pytest.approx(12.970, abs=1e-5)
    assert vehicle.lon == pytest.approx(77.580, abs=1e-5)
    assert (vehicle.stop_sequence, vehicle.status, vehicle.timestamp) == (2, 2, T - 15)
    assert feed.trips[0].stops[0].arrival_delay == 120
    assert feed.trips[1].delay == -60


@pytest.mark.parametrize("data", [b"", b"\xff\xff\xff", b"\x0a\x05abc", b"not a feed at all"])
def test_anything_that_is_not_a_feed_is_refused(data):
    with pytest.raises(FeedError) as caught:
        parse_feed(data)
    assert caught.value.code == "FEED_INVALID"


# ---------------------------------------------------------------- not connected (the public service today)
def test_without_a_feed_nothing_live_is_shown(client):
    status = client.get("/api/live/status").json()
    assert status["available"] is False
    assert status["state"] == "NOT_CONNECTED"
    assert status["reason"] == "NO_AUTHORISED_LIVE_FEED"
    assert "BMTC" in status["needs"]
    assert client.get("/api/live/vehicles").json() == {"available": False, "status": status, "vehicles": [],
                                                       "hidden_old": 0}
    features = {f["id"]: f for f in client.get("/api/features").json()["features"]}
    assert features["live_tracking"] == {"id": "live_tracking", "state": "UNAVAILABLE",
                                         "reason": "NO_AUTHORISED_LIVE_FEED"}
    assert client.get("/api/meta").json()["live_positions_available"] is False
    rows = {r["capability"]: r for r in client.get("/api/integrations").json()["integrations"]}
    assert rows["live_vehicles"]["connected"] is False


def test_a_test_feed_is_refused_on_a_real_server(tmp_path):
    settings = make_settings(tmp_path, demo_mode=False, realtime_vehicles_url="http://127.0.0.1:9/vp",
                             realtime_source_kind="TEST")
    status = LiveService(settings).status(NOW)
    assert (status["available"], status["state"], status["reason"]) == (False, "REFUSED", "TEST_FEED_REFUSED")


@pytest.mark.parametrize(("overrides", "reason"), [
    ({"realtime_vehicles_url": "http://feeds.example.org/vp"}, "BAD_FEED_URL"),
    ({"realtime_vehicles_url": "file:///etc/passwd"}, "BAD_FEED_URL"),
    ({"realtime_vehicles_url": "https://feeds.example.org/vp", "realtime_auth_header": "no colon"}, "BAD_AUTH_HEADER"),
    ({"realtime_vehicles_url": "https://feeds.example.org/vp", "realtime_source_kind": "SCRAPED"}, "BAD_SOURCE_KIND"),
])
def test_unsafe_feed_settings_are_refused(tmp_path, overrides, reason):
    status = LiveService(make_settings(tmp_path, demo_mode=False, **overrides)).status(NOW)
    assert status["available"] is False
    assert status["reason"] == reason


# ---------------------------------------------------------------- vehicles
def test_live_vehicles_are_matched_with_the_timetable(live):
    live.use(standard_feed())
    data = live.get("/api/live/vehicles").json()
    assert data["status"]["state"] == "LIVE"
    assert data["status"]["feed_age_seconds"] == 10
    [bus] = data["vehicles"]
    assert bus["label"] == "Bus 1234"
    assert bus["route"]["number"] == "500D"
    assert bus["headsign"] == "Koramangala"
    assert bus["current_stop"]["name"] == "Kempegowda Bus Station"
    assert bus["next_stop"]["name"] == "Corporation"
    # Half-way from stop 1 to stop 2 of four: 0.5 of 3 stop-to-stop sections.
    assert bus["progress"] == {"stop_number": 2, "stops_total": 4, "percent": 17}
    assert (bus["freshness"], bus["age_seconds"], bus["speed_kmph"], bus["bearing"]) == ("FRESH", 15, 18, 120)
    assert bus["matched_to_timetable"] is True
    features = {f["id"]: f for f in live.get("/api/features").json()["features"]}
    assert features["live_tracking"]["state"] == "AVAILABLE"
    assert live.get("/api/meta").json()["live_positions_available"] is True
    rows = {r["capability"]: r for r in live.get("/api/integrations").json()["integrations"]}
    assert rows["live_vehicles"]["status"] == "CONNECTED"


def test_old_positions_are_hidden_and_late_ones_marked_stale(live):
    live.use(standard_feed(more=[
        rt.vehicle("e2", vehicle_id="V2", label="Bus 2", trip_id="T2", lat=12.97, lon=77.58, timestamp=T - 200),
        rt.vehicle("e3", vehicle_id="V3", label="Bus 3", trip_id="T2", lat=12.97, lon=77.58, timestamp=T - 900),
    ]))
    data = live.get("/api/live/vehicles").json()
    assert {v["label"]: v["freshness"] for v in data["vehicles"]} == {"Bus 1234": "FRESH", "Bus 2": "STALE"}
    assert data["hidden_old"] == 1


def test_vehicles_can_be_filtered_by_route_number(live):
    live.use(standard_feed())
    assert len(live.get("/api/live/vehicles?route=500D").json()["vehicles"]) == 1
    assert live.get("/api/live/vehicles?route=401").json()["vehicles"] == []


def test_a_stopped_vehicle_is_at_its_stop_and_heads_for_the_next(live):
    live.use(rt.feed(T, [rt.vehicle("e1", vehicle_id="V", label="Bus", trip_id="T1", lat=12.96, lon=77.59,
                                    timestamp=T, stop_sequence=3, status=1)]))
    [bus] = live.get("/api/live/vehicles").json()["vehicles"]
    assert (bus["current_stop"]["name"], bus["next_stop"]["name"]) == ("Shanti Nagar", "Koramangala")
    assert bus["progress"]["percent"] == 67


def test_a_vehicle_shows_an_estimate_for_each_stop_ahead(live):
    live.use(standard_feed())
    data = live.get("/api/live/vehicles/KA-01-F-1234").json()
    upcoming = [(u["stop"]["name"], u["scheduled"][11:16], u["estimate"][11:16], u["kind"], u["delay_seconds"])
                for u in data["upcoming"]]
    # The two-minute delay given at Corporation also applies to the later stops (GTFS-Realtime rule).
    assert upcoming == [("Corporation", "08:10", "08:12", "LIVE_ESTIMATE", 120),
                        ("Shanti Nagar", "08:20", "08:22", "LIVE_ESTIMATE", 120),
                        ("Koramangala", "08:30", "08:32", "LIVE_ESTIMATE", 120)]
    assert live.get("/api/live/vehicles/NOT-THERE").status_code == 404


def test_without_a_prediction_a_stop_keeps_its_scheduled_label(live):
    live.use(rt.feed(T, [rt.vehicle("e1", vehicle_id="V", label="Bus", trip_id="T1", start_date="20270310",
                                    lat=12.97, lon=77.58, timestamp=T, stop_sequence=2, status=2)]))
    upcoming = live.get("/api/live/vehicles/V").json()["upcoming"]
    assert {u["kind"] for u in upcoming} == {"SCHEDULED"}
    assert all(u["estimate"] is None for u in upcoming)


def test_a_skipped_stop_is_marked(live):
    live.use(rt.feed(T, [
        rt.vehicle("e1", vehicle_id="V", label="Bus", trip_id="T1", start_date="20270310", lat=12.97, lon=77.58,
                   timestamp=T, stop_sequence=2, status=2),
        rt.trip_update("u1", trip_id="T1", start_date="20270310", timestamp=T,
                       stops=[(2, "B", at("08:13"), None, False), (3, "C", None, None, True)]),
    ]))
    kinds = [(u["stop"]["name"], u["kind"]) for u in live.get("/api/live/vehicles/V").json()["upcoming"]]
    assert kinds == [("Corporation", "LIVE_ESTIMATE"), ("Shanti Nagar", "SKIPPED"), ("Koramangala", "LIVE_ESTIMATE")]


# ---------------------------------------------------------------- stop arrivals
def stop_id(client, name: str) -> int:
    return next(s["id"] for s in client.get("/api/stops?classification=OFFICIAL_VERIFIED&q=" + name).json()["results"]
                if s["name"] == name)


def test_a_stop_lists_live_estimates_in_order(live):
    live.use(standard_feed(more=[
        rt.trip_update("u2", trip_id="T2", start_date="20270310", timestamp=T, stops=[(1, "A", None, 300, False)]),
    ]))
    data = live.get(f"/api/live/stops/{stop_id(live, 'Shanti Nagar')}/arrivals").json()
    rows = [(a["route"]["number"], a["estimate"][11:16], a["minutes"], a["kind"]) for a in data["arrivals"]]
    assert rows == [("500D", "08:22", 10, "LIVE_ESTIMATE"), ("500D", "08:55", 43, "LIVE_ESTIMATE")]
    assert data["arrivals"][0]["vehicle_label"] == "Bus 1234"
    assert data["arrivals"][0]["prediction_age_seconds"] == 20


def test_a_stop_with_no_estimate_lists_nothing_live(live):
    live.use(standard_feed())
    # Kempegowda Bus Station is before the first update, so it has no estimate: no scheduled time is shown as live.
    assert live.get(f"/api/live/stops/{stop_id(live, 'Kempegowda Bus Station')}/arrivals").json()["arrivals"] == []


def test_a_cancelled_trip_gives_no_arrival(live):
    live.use(rt.feed(T, [rt.trip_update("u1", trip_id="T1", start_date="20270310", timestamp=T, canceled=True,
                                        stops=[(3, "C", None, 60, False)])]))
    assert live.get(f"/api/live/stops/{stop_id(live, 'Shanti Nagar')}/arrivals").json()["arrivals"] == []


# ---------------------------------------------------------------- failures, polling, secrets
def test_a_feed_that_cannot_be_read_shows_nothing_and_says_why(live):
    live.use(FeedError("FEED_UNREACHABLE"))
    status = live.get("/api/live/status").json()
    assert (status["available"], status["state"], status["reason"]) == (False, "ERROR", "FEED_UNREACHABLE")
    assert live.get("/api/live/vehicles").json()["vehicles"] == []


def test_an_old_feed_is_reported_stale(live):
    live.use(standard_feed(timestamp=T - 400))
    assert live.get("/api/live/status").json()["state"] == "STALE"


def test_the_feed_is_read_at_most_once_per_poll_interval(tmp_path):
    stub = Stub(standard_feed())
    service = LiveService(make_settings(tmp_path, demo_mode=False), provider=stub)
    service.status(NOW)
    service.status(NOW + dt.timedelta(seconds=5))
    assert stub.calls == 1
    service.status(NOW + dt.timedelta(seconds=21))
    assert stub.calls == 2


def test_the_access_header_is_sent_and_never_shown(tmp_path, monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _n):
            return standard_feed()

    def fake_urlopen(request, timeout):
        seen["key"] = request.get_header("X-api-key")
        seen["url"] = request.full_url
        return Response()

    monkeypatch.setattr(realtime.urllib.request, "urlopen", fake_urlopen)
    settings = make_settings(tmp_path, demo_mode=False, realtime_vehicles_url="https://feeds.example.org/vp",
                             realtime_auth_header="X-Api-Key: s3cret-value")
    status = LiveService(settings).status(NOW)
    assert status["available"] is True
    assert seen == {"key": "s3cret-value", "url": "https://feeds.example.org/vp"}
    assert "s3cret" not in json.dumps(status)


def test_an_oversized_feed_is_refused(tmp_path, monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n):
            return b"x" * n

    monkeypatch.setattr(realtime.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    settings = make_settings(tmp_path, demo_mode=False, realtime_vehicles_url="https://feeds.example.org/vp")
    status = LiveService(settings).status(NOW)
    assert (status["state"], status["reason"]) == ("ERROR", "FEED_TOO_LARGE")
