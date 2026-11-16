"""The /api/plan endpoint: parameters and their limits, the response shape, classification handling, and the notice that
live positions are not available."""

from __future__ import annotations

from fastapi.testclient import TestClient
from freezegun import freeze_time

from tests.helpers import ADMIN_KEY, admin_headers, build_transit_feed

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


def feed() -> bytes:
    return build_transit_feed(STOPS, ROUTES, TRIPS)


def new_source(client: TestClient, *, kind: str, name: str) -> dict:
    response = client.post(
        "/api/admin/data-sources",
        headers=admin_headers(),
        json={"name": name, "publisher": "Test publisher", "kind": kind, "license": "test"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def upload(client: TestClient, source_id: int, data: bytes):
    return client.post(
        "/api/admin/imports",
        headers=admin_headers(ADMIN_KEY),
        files={"file": ("feed.zip", data, "application/zip")},
        data={"data_source_id": str(source_id)},
    )


def verify(client: TestClient, source_id: int) -> None:
    response = client.post(
        f"/api/admin/data-sources/{source_id}/verify",
        headers=admin_headers(),
        json={"verified": True, "note": "Confirmed in a test"},
    )
    assert response.status_code == 200, response.text


def plan(client: TestClient, **params):
    return client.get("/api/plan", params=params)


def test_a_verified_official_feed_is_planned_and_labelled(client: TestClient):
    source = new_source(client, kind="OFFICIAL", name="Official test feed")
    assert upload(client, source["id"], feed()).status_code == 201
    verify(client, source["id"])

    response = plan(client, origin="alpha", destination="beta", date="2027-01-11")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["classification"] == "OFFICIAL_VERIFIED"
    assert body["realtime"] is False
    assert "Live bus positions, delays and cancellations are not available" in body["note"]
    assert body["message"] is None
    assert [source["name"] for source in body["sources"]] == ["Official test feed"]
    option = body["options"][0]
    assert option["changes"] == 1
    assert option["departs_at"].startswith("2027-01-11T08:00")
    assert option["arrives_at"].startswith("2027-01-11T08:40")
    assert option["labels"] == ["EARLIEST_ARRIVAL"]
    assert option["legs"][0]["source"]["classification"] == "OFFICIAL_VERIFIED"
    assert option["legs"][0]["route_number"] == "101"
    assert option["fare"] == {"code": "CHANGES_NOT_PRICED", "total": None}


def test_unverified_data_is_only_planned_when_asked_for(client: TestClient):
    source = new_source(client, kind="UNKNOWN", name="Community feed")
    assert upload(client, source["id"], feed()).status_code == 201

    official = plan(client, origin="alpha", destination="beta", date="2027-01-11").json()
    assert official["options"] == []
    assert official["message_code"] == "NO_OFFICIAL_DATA"

    unverified = plan(
        client, origin="alpha", destination="beta", date="2027-01-11", classification="UNVERIFIED_FEED"
    ).json()
    assert unverified["classification"] == "UNVERIFIED_FEED"
    assert unverified["options"][0]["legs"][0]["source"]["classification"] == "UNVERIFIED_FEED"


def test_parameters_are_checked_before_any_planning(client: TestClient):
    assert plan(client, origin="a", destination="beta", date="2027-01-11").status_code == 422
    assert plan(client, origin="alpha", date="2027-01-11").status_code == 422
    assert plan(client, origin="alpha", destination="beta", date="2027-02-30").status_code == 422
    assert plan(client, origin="alpha", destination="beta", date="2027-01-11", max_changes=3).status_code == 422
    assert plan(client, origin="alpha", destination="beta", date="2027-01-11", max_changes=-1).status_code == 422
    assert plan(client, origin="alpha", destination="beta", date="2027-01-11", limit=0).status_code == 422
    scenario = plan(
        client, origin="alpha", destination="beta", date="2027-01-11", classification="ESTIMATED_SCENARIO"
    )
    assert scenario.status_code == 400


def test_planning_now_uses_the_service_clock_and_says_so(client: TestClient):
    source = new_source(client, kind="OFFICIAL", name="Official test feed")
    assert upload(client, source["id"], feed()).status_code == 201
    verify(client, source["id"])
    # 07:55 in India on 11 January 2027, so the 08:00 and 08:40 buses are inside the next three hours.
    with freeze_time("2027-01-11T02:25:00Z"):
        body = plan(client, origin="alpha", destination="beta").json()
    assert body["mode"] == "now"
    assert body["date"] is None
    assert body["options"][0]["departs_at"].startswith("2027-01-11T08:00")


def test_the_api_states_that_live_positions_are_not_available(client: TestClient):
    body = client.get("/api/meta").json()
    assert body["version"] == "4.0.0-alpha.3"
    assert body["live_positions_available"] is False
    assert "No verified real-time feed" in body["live_positions_note"]
    assert "Not affiliated with" in body["affiliation"]
    assert body["journey_assumptions"]["max_changes"] == 2
