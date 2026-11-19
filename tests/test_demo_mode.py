"""Real mode and demonstration mode, community data, and exact stop names.

The public service runs with DEMO_MODE off: invented (SYNTHETIC_DEMO) feeds are never served, even if one is loaded,
so missing real data is never filled with invented data. A community feed is served as unverified real data: its
times are marked approximate and its fares are never shown as prices.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

from tests.helpers import build_transit_feed, make_settings, synthetic_feed
from tests.test_api import new_source, upload

U = "UNVERIFIED_FEED"
DAY = "2027-01-11"
FARES = ("fare_id,price,currency_type,payment_method,transfers\nF1,10.00,INR,0,\n",
         "fare_id,route_id,origin_id,destination_id,contains_id\nF1,R1,,,\n")
STOPS = {
    "J": ("Jayanagar", 12.9300, 77.5800),
    "V": ("Vijayanagar", 12.9700, 77.5300),
    "K": ("Kengeri", 12.9100, 77.4800),
}
ROUTES = {"R1": "101"}
TRIPS = [("T1", "R1", [("K", "08:00:00"), ("V", "08:15:00"), ("J", "08:40:00")])]


def server(tmp_path: Path, *, demo: bool) -> TestClient:
    return TestClient(create_app(make_settings(tmp_path, demo_mode=demo)))


def load(client: TestClient, kind: str, data: bytes) -> None:
    source = new_source(client, kind=kind, name=f"{kind} source")
    response = upload(client, source["id"], data)
    assert response.status_code == 201, response.text


def demo_journey(client: TestClient) -> dict:
    return client.get("/api/plan", params={"origin": "Demo Central", "destination": "Demo Junction",
                                           "classification": U, "date": DAY}).json()


# ---------------------------------------------------------------- real mode hides invented data

def test_a_real_mode_server_never_serves_an_invented_feed(tmp_path):
    with server(tmp_path, demo=False) as client:
        load(client, "SYNTHETIC_DEMO", synthetic_feed())
        status = client.get("/api/data-status").json()
        assert status["demo_mode"] is False
        assert status["feeds"] == []
        assert status["demo_only"] is False
        assert client.get("/api/routes", params={"classification": U}).json()["results"] == []
        assert client.get("/api/stops", params={"classification": U, "q": "Demo"}).json()["results"] == []
        journey = demo_journey(client)
        assert journey["options"] == []
        assert journey["message_code"] in ("NO_UNVERIFIED_DATA", "ORIGIN_NOT_FOUND")


def test_a_demonstration_server_serves_the_invented_feed_and_says_so(tmp_path):
    with server(tmp_path, demo=True) as client:
        load(client, "SYNTHETIC_DEMO", synthetic_feed())
        status = client.get("/api/data-status").json()
        assert status["demo_mode"] is True
        assert status["demo_only"] is True
        assert demo_journey(client)["options"]


def test_real_mode_still_serves_real_feeds_next_to_a_hidden_demo_feed(tmp_path):
    with server(tmp_path, demo=False) as client:
        load(client, "SYNTHETIC_DEMO", synthetic_feed())
        load(client, "COMMUNITY", build_transit_feed(STOPS, ROUTES, TRIPS))
        feeds = client.get("/api/data-status").json()["feeds"]
        assert [f["kind"] for f in feeds] == ["COMMUNITY"]
        assert client.get("/api/plan", params={"origin": "Kengeri", "destination": "Jayanagar",
                                               "classification": U, "date": DAY}).json()["options"]


def test_demo_mode_is_off_unless_the_environment_turns_it_on(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'env.db').as_posix()}")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    no_dotenv = tmp_path / "none.env"
    assert Settings.from_env(no_dotenv).demo_mode is False
    monkeypatch.setenv("DEMO_MODE", "1")
    assert Settings.from_env(no_dotenv).demo_mode is True
    monkeypatch.setenv("DEMO_MODE", "0")
    assert Settings.from_env(no_dotenv).demo_mode is False


# ---------------------------------------------------------------- community data

def test_community_times_are_approximate_and_their_fares_are_never_shown(tmp_path):
    with server(tmp_path, demo=False) as client:
        load(client, "COMMUNITY", build_transit_feed(STOPS, ROUTES, TRIPS, fares=FARES))
        option = client.get("/api/plan", params={"origin": "Kengeri", "destination": "Jayanagar",
                                                 "classification": U, "date": DAY}).json()["options"][0]
        ride = option["legs"][0]
        assert ride["timing"] == "approximate"
        assert ride["fares"] == []
        assert option["fare"] == {"code": "NOT_VERIFIED", "total": None}


def test_demo_fares_are_still_shown_on_a_demonstration_server(tmp_path):
    with server(tmp_path, demo=True) as client:
        load(client, "SYNTHETIC_DEMO", build_transit_feed(STOPS, ROUTES, TRIPS, fares=FARES))
        option = client.get("/api/plan", params={"origin": "Kengeri", "destination": "Jayanagar",
                                                 "classification": U, "date": DAY}).json()["options"][0]
        assert option["legs"][0]["timing"] == "scheduled"
        assert option["fare"]["code"] == "IN_FEED"


# ---------------------------------------------------------------- exact names win over partial ones

def test_the_planner_takes_an_exact_stop_name_over_a_longer_name_that_contains_it(tmp_path):
    # Before the fix, "Jayanagar" also matched "Vijayanagar", and the planner answered with a trip to Vijayanagar.
    with server(tmp_path, demo=False) as client:
        load(client, "COMMUNITY", build_transit_feed(STOPS, ROUTES, TRIPS))
        options = client.get("/api/plan", params={"origin": "Kengeri", "destination": "Jayanagar",
                                                  "classification": U, "date": DAY}).json()["options"]
        assert options
        for option in options:
            rides = [leg for leg in option["legs"] if leg["type"] == "ride"]
            assert rides[-1]["to"]["name"] == "Jayanagar"


def test_direct_journeys_take_an_exact_stop_name_over_a_longer_name_that_contains_it(tmp_path):
    with server(tmp_path, demo=False) as client:
        load(client, "COMMUNITY", build_transit_feed(STOPS, ROUTES, TRIPS))
        journeys = client.get("/api/journey", params={"origin": "Kengeri", "destination": "Jayanagar",
                                                      "classification": U, "date": DAY}).json()["journeys"]
        assert journeys
        assert {j["destination_stop"] for j in journeys} == {"Jayanagar"}


def test_a_partial_name_still_finds_every_stop_that_contains_it(tmp_path):
    with server(tmp_path, demo=False) as client:
        load(client, "COMMUNITY", build_transit_feed(STOPS, ROUTES, TRIPS))
        body = client.get("/api/plan", params={"origin": "Kengeri", "destination": "jaya",
                                               "classification": U, "date": DAY}).json()
        destinations = {leg["to"]["name"] for o in body["options"] for leg in o["legs"] if leg["type"] == "ride"}
        assert destinations <= {"Jayanagar", "Vijayanagar"}
        assert destinations


# ---------------------------------------------------------------- the real community Metro feed

def _loader():
    path = Path(__file__).resolve().parents[1] / "scripts" / "load_community_metro.py"
    spec = importlib.util.spec_from_file_location("load_community_metro", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_community_metro_feed_loads_once_as_unverified_real_data(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'metro.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    loader = _loader()
    assert loader.main() == 0
    assert loader.main() == 0  # already loaded: nothing happens
    settings = make_settings(tmp_path, database_url=url, demo_mode=False)
    with TestClient(create_app(settings)) as client:
        feeds = client.get("/api/data-status").json()["feeds"]
        assert len(feeds) == 1
        assert feeds[0]["kind"] == "COMMUNITY"
        assert feeds[0]["classification"] == U
        assert "ODbL" in feeds[0]["license"]
        stations = client.get("/api/metro/stations", params={"classification": U, "q": "Indiranagar"}).json()
        assert [s["name"] for s in stations["stations"]] == ["Indiranagar"]
        assert len(stations["stations"][0]["stop_ids"]) == 2  # two platforms shown as one station
        option = client.get("/api/plan", params={
            "origin": "Whitefield (Kadugodi)", "destination": "Electronic City", "classification": U,
            "date": "2026-11-23", "modes": "metro"}).json()["options"][0]
        lines = [leg["route_number"] for leg in option["legs"] if leg["type"] == "ride"]
        assert lines == ["Purple", "Green", "Yellow"]
        assert all(leg["timing"] == "approximate" for leg in option["legs"] if leg["type"] == "ride")
        assert client.get("/api/plan", params={"origin": "Indiranagar", "destination": "Jayanagar",
                                               "date": "2026-11-23"}).json()["options"] == []  # not official


def test_the_loader_refuses_a_file_whose_checksum_does_not_match(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'bad.db').as_posix()}")
    loader = _loader()
    fake = tmp_path / "feed.zip"
    fake.write_bytes(b"not the recorded feed")
    monkeypatch.setattr(loader, "FEED", fake)
    assert loader.main() == 2
