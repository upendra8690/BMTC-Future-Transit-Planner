"""4.0 app shell: the feature-status list, the official services directory and the renamed product.

The rule these tests protect: the app never presents an unavailable capability (live positions, tickets, passes,
payments, NCMC) as working, and it shows Bus or Metro features as available only when that data is really loaded.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from urllib.parse import urlparse

from tests.helpers import admin_headers, valid_files, zip_of
from tests.test_api import load_demo, new_source, upload

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
NEVER_AVAILABLE = {"live_tracking", "bus_tickets", "bus_passes", "metro_tickets", "payments", "ncmc_cards"}
STATES = {"AVAILABLE", "NO_DATA", "UNAVAILABLE", "PLANNED"}
OFFICIAL_HOSTS = {
    "erss.in", "mybmtc.karnataka.gov.in", "english.bmrc.co.in", "indianrailways.gov.in",
    "www.bengaluruairport.com", "btp.karnataka.gov.in", "www.karnatakatourism.org",
}


def features(client) -> dict[str, dict]:
    response = client.get("/api/features")
    assert response.status_code == 200
    body = response.json()
    assert body["version"].startswith("4.0.0")
    return {f["id"]: f for f in body["features"]}


def test_every_feature_has_a_known_state_and_a_reason_unless_available(client):
    for feature_id, feature in features(client).items():
        assert feature["state"] in STATES, feature_id
        if feature["state"] == "AVAILABLE":
            assert feature["reason"] is None, feature_id
        else:
            assert feature["reason"], f"{feature_id} is {feature['state']} without a reason"


def test_unauthorised_capabilities_are_never_reported_as_available(client):
    load_demo(client)
    found = features(client)
    assert set(found) >= NEVER_AVAILABLE
    for feature_id in NEVER_AVAILABLE:
        assert found[feature_id]["state"] == "UNAVAILABLE", feature_id


def test_with_no_feed_the_data_features_say_no_data(client):
    found = features(client)
    for feature_id in ("bus_routes", "bus_timetables", "nearby_stops", "journey_planner", "metro", "fares"):
        assert found[feature_id] == {"id": feature_id, "state": "NO_DATA", "reason": "NO_FEED_LOADED"}


def test_a_bus_feed_makes_bus_features_available_but_not_metro(client):
    load_demo(client)
    found = features(client)
    assert found["bus_routes"]["state"] == "AVAILABLE"
    assert found["journey_planner"]["state"] == "AVAILABLE"
    assert found["metro"]["state"] == "NO_DATA"
    assert found["bus_metro_journeys"] == {
        "id": "bus_metro_journeys", "state": "NO_DATA", "reason": "NEEDS_BUS_AND_METRO_FEEDS",
    }


def test_a_metro_feed_is_recognised_by_its_route_type(client):
    files = valid_files()
    files["routes.txt"] = files["routes.txt"].replace("Test Route,3", "Test Route,1")
    source = new_source(client, name="Metro test source")
    assert upload(client, source["id"], zip_of(files)).status_code == 201
    found = features(client)
    assert found["metro"]["state"] == "AVAILABLE"
    assert found["bus_routes"]["state"] == "NO_DATA"


def test_a_deleted_feed_no_longer_counts(client):
    imported = load_demo(client)
    assert features(client)["bus_routes"]["state"] == "AVAILABLE"
    assert client.delete(f"/api/admin/imports/{imported['id']}", headers=admin_headers()).status_code in (200, 204)
    assert features(client)["bus_routes"]["state"] == "NO_DATA"


def test_the_services_directory_lists_only_official_https_sites_and_plain_phone_numbers(client):
    response = client.get("/api/services")
    assert response.status_code == 200
    body = response.json()
    dt.date.fromisoformat(body["checked"])
    assert body["categories"], "the directory is empty"
    for category in body["categories"]:
        assert re.fullmatch(r"[a-z]+", category["id"])
        assert category["items"]
        for item in category["items"]:
            assert item["name"]
            assert item["source"]
            assert item["url"] or item["tel"], item
            if item["url"]:
                parsed = urlparse(item["url"])
                assert parsed.scheme == "https", item["url"]
                assert parsed.hostname in OFFICIAL_HOSTS, item["url"]
            if item["tel"]:
                assert re.fullmatch(r"[0-9]{3,12}", item["tel"]), item["tel"]


def test_the_emergency_number_112_is_listed(client):
    categories = {c["id"]: c for c in client.get("/api/services").json()["categories"]}
    assert any(item["tel"] == "112" for item in categories["emergency"]["items"])


def test_the_product_is_renamed_and_still_says_it_is_unofficial(client):
    meta = client.get("/api/meta").json()
    assert meta["name"] == "Bengaluru Transit Planner"
    assert meta["unofficial"] is True
    assert meta["live_positions_available"] is False
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    assert "<title>Bengaluru Transit Planner</title>" in html
    assert "Not an official BMTC or BMRCL app" in html


def test_every_menu_link_leads_to_a_page_the_app_can_show():
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    app = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    routes_block = app[app.index("var ROUTES = {"): app.index("};", app.index("var ROUTES = {"))]
    known = set(re.findall(r"^\s*([a-z]+):", routes_block, flags=re.M))
    links = set(re.findall(r'href="#/([a-z]+)"[^>]*data-nav', html))
    assert links, "no menu links found"
    assert links <= known, f"menu links without a page: {sorted(links - known)}"
    for section in ("home", "nearby", "journey", "live", "tickets", "metro", "favourites", "account", "more"):
        assert section in links, f"the menu has no link to {section}"
