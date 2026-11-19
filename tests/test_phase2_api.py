"""4.0 Phase 2: routes at a stop, the Metro station directory, and bus + Metro journeys with a mode on every ride.

Everything here runs on the SYNTHETIC demo feeds (invented buses and one invented Metro line).
"""

from __future__ import annotations

from app.gtfs.synthetic import build_synthetic_metro_feed

from tests.helpers import FEED_END, FEED_START
from tests.test_api import UNVERIFIED, load_demo, new_source, upload

MONDAY = "2027-01-04"


def load_metro(client) -> dict:
    source = new_source(client, name="Demo Metro source")
    response = upload(client, source["id"], build_synthetic_metro_feed(FEED_START, FEED_END), name="metro.zip")
    assert response.status_code == 201, response.text
    return response.json()["import"]


def stop_id(client, name: str) -> int:
    results = client.get("/api/stops", params={"classification": UNVERIFIED, "q": name}).json()["results"]
    match = [s for s in results if s["name"] == name]
    assert len(match) == 1, results
    return match[0]["id"]


def test_routes_at_a_stop_lists_every_route_and_its_directions(client):
    load_demo(client)
    market = stop_id(client, "Demo Market")
    body = client.get(f"/api/stops/{market}/routes", params={"classification": UNVERIFIED}).json()
    numbers = [r["route_number"] for r in body["routes"]]
    assert numbers == ["DEMO-1", "DEMO-2"]
    demo1 = body["routes"][0]
    assert demo1["route_type"] == 3
    assert demo1["towards"] == ["Demo Central", "Demo Junction"]
    assert body["message_code"] is None


def test_routes_at_a_stop_respect_the_classification(client):
    load_demo(client)
    sid = stop_id(client, "Demo Market")
    response = client.get(f"/api/stops/{sid}/routes", params={"classification": "OFFICIAL_VERIFIED"})
    assert response.status_code == 404
    assert client.get("/api/stops/999999/routes", params={"classification": UNVERIFIED}).status_code == 404


def test_metro_stations_are_empty_and_say_why_without_a_metro_feed(client):
    load_demo(client)
    body = client.get("/api/metro/stations", params={"classification": UNVERIFIED}).json()
    assert body["stations"] == []
    assert body["message_code"] == "NO_METRO_STATIONS"


def test_metro_stations_come_only_from_metro_routes(client):
    load_demo(client)
    load_metro(client)
    body = client.get("/api/metro/stations", params={"classification": UNVERIFIED}).json()
    names = [s["name"] for s in body["stations"]]
    assert names == ["Demo Metro Central", "Demo Metro East", "Demo Metro Hub", "Demo Metro Tech Park"]
    for station in body["stations"]:
        assert station["lines"] == [{"id": station["lines"][0]["id"], "route_number": "DEMO-M1", "color": "7C3AED"}]
    filtered = client.get("/api/metro/stations", params={"classification": UNVERIFIED, "q": "tech"}).json()
    assert [s["name"] for s in filtered["stations"]] == ["Demo Metro Tech Park"]


def test_a_bus_and_metro_journey_names_the_mode_of_every_ride(client):
    load_demo(client)
    load_metro(client)
    body = client.get("/api/plan", params={
        "origin": "Demo Lake View", "destination": "Demo Metro Hub", "classification": UNVERIFIED, "date": MONDAY,
    }).json()
    assert body["options"], body
    for option in body["options"]:
        for leg in option["legs"]:
            if leg["type"] == "ride":
                assert leg["mode"] in {"bus", "metro"}
                assert leg["timing"] == "scheduled"
    mixed = [
        option for option in body["options"]
        if {leg.get("mode") for leg in option["legs"] if leg["type"] == "ride"} == {"bus", "metro"}
    ]
    assert mixed, "expected at least one option that uses both a bus and the Metro"
    legs = mixed[0]["legs"]
    assert any(leg["type"] == "walk" for leg in legs), "a change between bus stop and Metro station is a walk"
    sources = {leg["source"]["name"] for leg in legs if leg["type"] == "ride"}
    assert len(sources) == 2, "each ride names the feed it comes from"


def test_bus_only_rides_are_labelled_bus(client):
    load_demo(client)
    body = client.get("/api/plan", params={
        "origin": "Demo Central", "destination": "Demo Junction", "classification": UNVERIFIED, "date": MONDAY,
    }).json()
    rides = [leg for option in body["options"] for leg in option["legs"] if leg["type"] == "ride"]
    assert rides
    assert {leg["mode"] for leg in rides} == {"bus"}


def test_bus_and_metro_journeys_become_available_when_both_feeds_are_loaded(client):
    load_demo(client)
    load_metro(client)
    features = {f["id"]: f for f in client.get("/api/features").json()["features"]}
    assert features["metro"]["state"] == "AVAILABLE"
    assert features["bus_metro_journeys"]["state"] == "AVAILABLE"


def test_a_device_can_erase_everything_the_server_holds_for_it(client):
    from tests.helpers import CLIENT_A, CLIENT_B, client_headers

    load_demo(client)
    route = client.get("/api/routes", params={"classification": UNVERIFIED, "q": "DEMO-1"}).json()["results"][0]
    for key in (CLIENT_A, CLIENT_B):
        response = client.post("/api/saved-routes", headers=client_headers(key), json={
            "gtfs_route_id": route["gtfs_route_id"], "classification": UNVERIFIED, "label": "mine",
        })
        assert response.status_code == 201
    saved_pref = client.put("/api/preferences", headers=client_headers(CLIENT_A), json={"values": {"theme": "dark"}})
    assert saved_pref.status_code == 200, saved_pref.text
    erased = client.delete("/api/my-data", headers=client_headers(CLIENT_A))
    assert erased.status_code == 200
    assert erased.json()["deleted"] == {"scenarios": 0, "saved_routes": 1, "preferences": 1}
    assert client.get("/api/preferences", headers=client_headers(CLIENT_A)).json()["values"] == {}
    assert client.get("/api/saved-routes", headers=client_headers(CLIENT_A)).json()["saved"] == []
    assert len(client.get("/api/saved-routes", headers=client_headers(CLIENT_B)).json()["saved"]) == 1


def test_erasing_needs_a_device_key(client):
    assert client.delete("/api/my-data").status_code == 400
