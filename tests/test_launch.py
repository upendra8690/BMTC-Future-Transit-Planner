"""Launch scenarios for the 4.0 public demo.

Journey modes (bus only, Metro only, bus + Metro), no route, stale data, missing live feed, ticket and payment
integrations without a provider, device isolation, the upcoming-transport registry and the travel assistant.
Everything runs on the SYNTHETIC demo feeds.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.services import assistant, registry

from tests.helpers import CLIENT_A, CLIENT_B, client_headers, synthetic_feed
from tests.test_api import UNVERIFIED, load_demo, new_source, upload
from tests.test_phase2_api import MONDAY, load_metro


def plan(client, origin: str, destination: str, modes: str | None = None) -> dict:
    params = {"origin": origin, "destination": destination, "classification": UNVERIFIED, "date": MONDAY}
    if modes:
        params["modes"] = modes
    response = client.get("/api/plan", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ride_modes(body: dict) -> set[str]:
    return {leg["mode"] for option in body["options"] for leg in option["legs"] if leg["type"] == "ride"}


# ---------------------------------------------------------------- journey modes

def test_bus_only_journey_uses_only_buses(client):
    load_demo(client)
    load_metro(client)
    body = plan(client, "Demo Central", "Demo Junction", "bus")
    assert body["travel_modes"] == "bus"
    assert body["options"], body
    assert ride_modes(body) == {"bus"}
    assert all(option["modes"] == ["bus"] for option in body["options"])


def test_metro_only_journey_uses_only_the_metro(client):
    load_demo(client)
    load_metro(client)
    body = plan(client, "Demo Metro Central", "Demo Metro Tech Park", "metro")
    assert body["options"], body
    assert ride_modes(body) == {"metro"}


def test_bus_and_metro_journey_is_labelled_and_mode_filters_respect_it(client):
    load_demo(client)
    load_metro(client)
    mixed = plan(client, "Demo Lake View", "Demo Metro Hub")
    assert mixed["travel_modes"] == "all"
    labelled = [o for o in mixed["options"] if "BUS_AND_METRO" in o["labels"]]
    assert labelled, mixed
    assert all(set(o["modes"]) == {"bus", "metro"} for o in labelled)
    for modes in ("bus", "metro"):
        body = plan(client, "Demo Lake View", "Demo Metro Hub", modes)
        if body["options"]:
            assert ride_modes(body) == {modes}
        else:
            assert body["message_code"] == "NO_JOURNEY_FOR_MODE"


def test_metro_only_between_bus_stops_finds_nothing_and_says_so(client):
    load_demo(client)
    load_metro(client)
    body = plan(client, "Demo Central", "Demo Junction", "metro")
    assert body["options"] == []
    assert body["message_code"] == "NO_JOURNEY_FOR_MODE"


def test_no_available_route(client):
    load_demo(client)
    body = plan(client, "Nowhere Such Place", "Demo Junction")
    assert body["options"] == []
    assert body["message_code"] == "ORIGIN_NOT_FOUND"


def test_unknown_travel_mode_is_rejected(client):
    load_demo(client)
    response = client.get("/api/plan", params={
        "origin": "Demo Central", "destination": "Demo Junction", "classification": UNVERIFIED, "modes": "taxi",
    })
    assert response.status_code == 422


# ---------------------------------------------------------------- data freshness and live data

def test_an_expired_feed_is_reported_as_expired(client):
    source = new_source(client, name="Old demo source")
    old = synthetic_feed(dt.date(2020, 1, 1), dt.date(2020, 12, 31))
    assert upload(client, source["id"], old, name="old.zip").status_code == 201
    load_demo(client)
    status = client.get("/api/data-status").json()
    states = {f["source"]: f["state"] for f in status["feeds"]}
    assert states["Old demo source"] == "EXPIRED"
    assert states["Demo source"] == "CURRENT"
    assert status["demo_only"] is True
    assert all(f["demo"] for f in status["feeds"])


def test_missing_live_feed_is_stated_and_never_faked(client):
    load_demo(client)
    status = client.get("/api/data-status").json()
    assert status["realtime"] is False
    assert status["live_feed"] == "NONE"
    features = {f["id"]: f for f in client.get("/api/features").json()["features"]}
    assert features["live_tracking"]["state"] == "UNAVAILABLE"
    response = client.post("/api/integrations/live_vehicles/request")
    assert response.status_code == 503
    assert response.json()["code"] == "NO_AUTHORISED_LIVE_FEED"
    body = plan(client, "Demo Central", "Demo Junction")
    assert body["realtime"] is False
    assert {leg["timing"] for o in body["options"] for leg in o["legs"] if leg["type"] == "ride"} == {"scheduled"}


# ---------------------------------------------------------------- integrations without a provider

FORBIDDEN_OUTPUT = {"ticket", "ticket_id", "qr", "qr_code", "receipt", "balance", "payment_id", "transaction_id"}


@pytest.mark.parametrize(("capability", "code"), [
    ("bus_tickets", "NEEDS_TICKETING_AGREEMENT"),
    ("bus_passes", "NEEDS_TICKETING_AGREEMENT"),
    ("metro_qr_tickets", "NEEDS_ONDC_REGISTRATION"),
    ("payments", "NEEDS_PAYMENT_GATEWAY"),
    ("ncmc", "NEEDS_BANK_INTEGRATION"),
])
def test_ticket_and_payment_requests_are_refused_without_a_provider(client, capability, code):
    response = client.post(f"/api/integrations/{capability}/request", json={"amount": 25, "upi": "x@y"})
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == code
    assert not FORBIDDEN_OUTPUT & set(body)


def test_unknown_or_malformed_integration_is_rejected(client):
    assert client.post("/api/integrations/free_tickets/request").status_code == 404
    assert client.post("/api/integrations/DROP%20TABLE/request").status_code == 422


def test_integration_status_lists_every_capability_as_not_connected(client):
    data = client.get("/api/integrations").json()
    caps = {i["capability"]: i for i in data["integrations"]}
    assert set(caps) == {"live_vehicles", "bus_tickets", "bus_passes", "metro_qr_tickets", "payments", "ncmc"}
    assert all(not i["connected"] and i["status"] == "AWAITING_PROVIDER_ACCESS" for i in caps.values())


# ---------------------------------------------------------------- device isolation

def test_one_device_cannot_erase_or_read_another_devices_data(client):
    load_demo(client)
    body = {"gtfs_route_id": "DR1", "classification": UNVERIFIED, "label": "Home line"}
    assert client.post("/api/saved-routes", headers=client_headers(CLIENT_A), json=body).status_code == 201
    erased = client.delete("/api/my-data", headers=client_headers(CLIENT_B)).json()
    assert erased["deleted"]["saved_routes"] == 0
    mine = client.get("/api/saved-routes", headers=client_headers(CLIENT_A)).json()["saved"]
    assert [r["label"] for r in mine] == ["Home line"]
    assert client.get("/api/saved-routes", headers=client_headers(CLIENT_B)).json()["saved"] == []


# ---------------------------------------------------------------- upcoming transport and providers

TODAY = dt.date(2026, 11, 17)


def entry(**changes) -> dict:
    base = {"id": "x", "status": "UNDER_CONSTRUCTION", "opened_on": None,
            "sources": [{"title": "t", "url": "https://example.org/"}], "verified_on": "2026-11-17"}
    base.update(changes)
    return base


def test_registry_entries_are_valid():
    registry.validate_upcoming(registry.UPCOMING, TODAY)


@pytest.mark.parametrize(("bad", "why"), [
    (entry(status="OPERATING"), "needs the date it opened"),
    (entry(status="OPERATING", opened_on="2027-03-01"), "before its opening date"),
    (entry(status="OPERATING", opened_on="2026-11-18", verified_on="2026-11-17"), "before its opening date"),
    (entry(status="PLANNED", opened_on="2026-01-01"), "only an operating service"),
    (entry(status="RUNNING"), "unknown status"),
    (entry(sources=[]), "https source"),
    (entry(sources=[{"title": "t", "url": "http://insecure.example/"}]), "https source"),
    (entry(verified_on=None), "verification date"),
])
def test_a_future_service_cannot_be_marked_operating(bad, why):
    with pytest.raises(registry.RegistryError, match=why):
        registry.validate_upcoming([bad], TODAY)


def test_upcoming_projects_are_never_used_by_the_planner(client):
    data = client.get("/api/upcoming").json()
    assert data["projects"]
    for project in data["projects"]:
        assert project["in_planner"] is False
        assert project["status"] in data["statuses"]
        assert project["sources"]
        assert project["verified_on"]
        if project["status"] != "OPERATING":
            assert project["opened_on"] is None


def test_provider_registry_records_licence_permission_and_status(client):
    load_demo(client)
    data = client.get("/api/providers").json()
    required = {"provider", "dataset", "licence", "permission", "owner", "update_frequency", "integration",
                "limitations", "last_successful_update"}
    for row in data["providers"]:
        assert required <= set(row), row["id"]
        assert row["integration"] in {"CONNECTED", "NOT_CONNECTED", "BLOCKED"}
        assert row["permission"] in {"GRANTED", "NOT_REQUESTED", "REQUESTED", "NOT_NEEDED"}
    rows = {row["id"]: row for row in data["providers"]}
    for blocked in ("bmtc_realtime", "bmtc_ticketing", "metro_qr_ondc", "payments"):
        assert rows[blocked]["integration"] == "BLOCKED"
    assert rows["synthetic_demo"]["last_successful_update"] is not None
    assert rows["bmtc_gtfs"]["last_successful_update"] is None
    assert rows["bmtc_gtfs"]["loads_data"] is True
    assert rows["osm_tiles"]["loads_data"] is False


# ---------------------------------------------------------------- travel assistant

@pytest.mark.parametrize(("question", "intent", "params"), [
    ("How do I go from Majestic to Whitefield?", "journey",
     {"origin": "majestic", "destination": "whitefield", "modes": "all"}),
    ("Demo Central to Demo Junction by bus", "journey",
     {"origin": "demo central", "destination": "demo junction", "modes": "bus"}),
    ("from Indiranagar to MG Road by metro", "journey",
     {"origin": "indiranagar", "destination": "mg road", "modes": "metro"}),
    ("route 500D", "route", {"q": "500D"}),
    ("bus no 335E timings", "route", {"q": "335E"}),
    ("V-500D", "route", {"q": "V-500D"}),
    ("stops near me", "nearby", {}),
    ("bus stop at Hebbal", "stop", {"q": "hebbal"}),
    ("metro stations", "metro", {"q": ""}),
    ("When will my bus arrive?", "live", {"feature": "live_tracking"}),
    ("where is the bus 500D", "live", {"feature": "live_tracking"}),
    ("buy a ticket", "tickets", {"feature": "bus_tickets"}),
    ("pay with UPI", "tickets", {"feature": "bus_tickets"}),
    ("there was an accident, help me", "emergency", {"tel": "112"}),
    ("", "help", {}),
])
def test_assistant_maps_questions_to_data_requests(question, intent, params):
    assert assistant.interpret(question) == {"intent": intent, "params": params}


def test_assistant_endpoint_never_writes_its_own_answer(client):
    data = client.get("/api/assistant", params={"q": "Demo Central to Demo Junction"}).json()
    assert data["engine"] == "rules"
    assert set(data) == {"intent", "params", "engine"}
    assert client.get("/api/assistant", params={"q": "x" * 201}).status_code == 422
