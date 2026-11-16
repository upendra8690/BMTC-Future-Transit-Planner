"""HTTP API end to end: public reads, administrative uploads, device isolation, headers and limits."""

from __future__ import annotations

import csv
import datetime as dt
import io

import pytest
from app import clock
from app.main import create_app
from fastapi.testclient import TestClient

from tests.helpers import (
    ADMIN_KEY,
    CLIENT_A,
    CLIENT_B,
    admin_headers,
    client_headers,
    make_settings,
    synthetic_feed,
    valid_files,
    zip_of,
)

UNVERIFIED = "UNVERIFIED_FEED"
OFFICIAL = "OFFICIAL_VERIFIED"
NO_OFFICIAL = "No officially verified timetable is available for this future year."
# 10:00 on 15 November 2026 in Bengaluru. The 2027 planning years are future years from this date.
FROZEN_NOW = dt.datetime(2026, 11, 15, 4, 30, tzinfo=dt.UTC)


@pytest.fixture
def frozen_api_clock(monkeypatch):
    monkeypatch.setattr(clock, "utc_now", lambda: FROZEN_NOW)


def new_source(client: TestClient, *, kind: str = "SYNTHETIC_DEMO", name: str = "Demo source") -> dict:
    response = client.post(
        "/api/admin/data-sources",
        headers=admin_headers(),
        json={"name": name, "publisher": "Test publisher", "kind": kind, "license": "test"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, source_id: int, data: bytes, *, key: str = ADMIN_KEY, name: str = "feed.zip"):
    return client.post(
        "/api/admin/imports",
        headers=admin_headers(key),
        files={"file": (name, data, "application/zip")},
        data={"data_source_id": str(source_id)},
    )


def load_demo(client: TestClient, *, kind: str = "SYNTHETIC_DEMO") -> dict:
    """Create a source, upload the synthetic demo feed to it and return the import summary."""
    source = new_source(client, kind=kind)
    response = upload(client, source["id"], synthetic_feed())
    assert response.status_code == 201, response.text
    return response.json()["import"]


def demo_route_id(client: TestClient, *, short_name: str = "DEMO-1", classification: str = UNVERIFIED) -> int:
    results = client.get(
        "/api/routes", params={"classification": classification, "year": 2027, "q": short_name}
    ).json()["results"]
    assert len(results) == 1, results
    return results[0]["id"]


def scenario_body(**overrides) -> dict:
    body = {
        "name": "Trial route",
        "year": 2028,
        "route_code": "PROP-1",
        "origin_name": "Demo Central",
        "origin_lat": 12.975,
        "origin_lon": 77.595,
        "destination_name": "Demo Junction",
        "destination_lat": 12.998,
        "destination_lon": 77.624,
        "first_departure": "06:00",
        "last_departure": "22:00",
        "frequency_minutes": 15,
        "operating_days": ["MON", "TUE", "WED", "THU", "FRI"],
        "stops": [{"name": "Demo Market", "lat": 12.979, "lon": 77.600}],
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------- system, years and static files

def test_health_and_meta_describe_the_service(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["planning_years"] == [2027, 2028, 2029, 2030]
    assert set(meta["classifications"]) == {OFFICIAL, UNVERIFIED, "ESTIMATED_SCENARIO"}
    assert meta["admin_enabled"] is True


def test_year_comparison_covers_every_planning_year(client):
    years = client.get("/api/years/compare").json()["years"]
    assert [y["year"] for y in years] == [2027, 2028, 2029, 2030]


def test_planning_year_without_data_shows_the_required_official_message(client, frozen_api_clock):
    body = client.get("/api/years/2029/status").json()
    assert body["is_planning_year"] is True
    assert body["official"]["status"] == "NONE"
    assert body["official"]["message"] == NO_OFFICIAL
    assert body["unverified"]["status"] == "NONE"


def test_a_past_year_without_official_data_is_named_not_called_future(client, frozen_api_clock):
    body = client.get("/api/years/2005/status").json()
    assert body["is_future"] is False
    assert body["official"]["message"] == "No officially verified timetable is available for 2005."


def test_years_outside_the_supported_range_are_refused(client):
    assert client.get("/api/years/1999/status").status_code == 422


def test_dashboard_and_api_docs_are_served(client):
    assert client.get("/api/docs").status_code == 200
    home = client.get("/")
    assert home.status_code == 200
    assert "<html" in home.text.lower()
    assert client.get("/sw.js").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200


def test_security_headers_and_dashboard_policy(client):
    home = client.get("/")
    csp = home.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert home.headers["x-frame-options"] == "DENY"
    assert home.headers["x-content-type-options"] == "nosniff"
    api = client.get("/api/health")
    assert "content-security-policy" not in api.headers
    assert api.headers["x-content-type-options"] == "nosniff"


def test_requests_beyond_the_per_minute_limit_get_429(tmp_path):
    app = create_app(make_settings(tmp_path / "limited", rate_limit_per_minute=3))
    with TestClient(app) as client:
        statuses = [client.get("/api/health").status_code for _ in range(4)]
        assert statuses == [200, 200, 200, 429]
        assert client.get("/api/health").headers["retry-after"] == "60"
    app.state.db.dispose()


# ---------------------------------------------------------------- administration

def test_admin_routes_are_disabled_when_no_key_is_configured(tmp_path):
    app = create_app(make_settings(tmp_path / "no-admin", admin_api_key=""))
    with TestClient(app) as client:
        assert client.get("/api/meta").json()["admin_enabled"] is False
        assert client.get("/api/admin/stats", headers=admin_headers()).status_code == 503
    app.state.db.dispose()


def test_admin_requests_need_the_correct_key(client):
    source = new_source(client)
    assert upload(client, source["id"], synthetic_feed(), key="").status_code == 401
    assert upload(client, source["id"], synthetic_feed(), key="not-the-key").status_code == 401
    assert client.get("/api/admin/stats").status_code == 401


def test_empty_uploads_are_refused(client):
    source = new_source(client)
    assert upload(client, source["id"], b"").status_code == 400


def test_oversized_uploads_are_refused(tmp_path):
    app = create_app(make_settings(tmp_path / "small", max_upload_bytes=2_000))
    with TestClient(app) as client:
        source = new_source(client)
        assert upload(client, source["id"], b"x" * 3_000).status_code == 413
    app.state.db.dispose()


def test_upload_to_an_unknown_source_is_a_404(client):
    assert upload(client, 99_999, synthetic_feed()).status_code == 404


def test_rejected_feed_returns_422_with_reasons_and_no_timetable(client):
    source = new_source(client)
    files = valid_files()
    files["trips.txt"] = files["trips.txt"].replace("R1,WK", "NOPE,WK")
    response = upload(client, source["id"], zip_of(files))
    assert response.status_code == 422
    summary = response.json()["import"]
    assert summary["status"] == "REJECTED"
    assert any("unknown route_id" in message for message in summary["errors"])
    assert client.get("/api/routes", params={"classification": UNVERIFIED, "year": 2027}).json()["results"] == []


def test_only_official_sources_can_be_verified_and_verification_reclassifies(client):
    synthetic = new_source(client, kind="SYNTHETIC_DEMO", name="Synthetic")
    refused = client.post(
        f"/api/admin/data-sources/{synthetic['id']}/verify",
        headers=admin_headers(),
        json={"verified": True, "note": "Not allowed"},
    )
    assert refused.status_code == 400

    official = new_source(client, kind="OFFICIAL", name="Official test feed")
    assert official["classification"] == UNVERIFIED
    assert upload(client, official["id"], synthetic_feed()).status_code == 201
    assert client.get("/api/routes", params={"classification": OFFICIAL, "year": 2027}).json()["results"] == []

    verified = client.post(
        f"/api/admin/data-sources/{official['id']}/verify",
        headers=admin_headers(),
        json={"verified": True, "note": "Confirmed against the publisher's page"},
    )
    assert verified.status_code == 200
    assert verified.json()["reclassified_imports"] == 1
    after = client.get("/api/routes", params={"classification": OFFICIAL, "year": 2027}).json()
    assert len(after["results"]) == 2
    assert after["coverage"]["status"] == "FULL"
    assert client.get("/api/routes", params={"classification": UNVERIFIED, "year": 2027}).json()["results"] == []


def test_admin_actions_are_written_to_the_audit_log(client):
    source = new_source(client)
    upload(client, source["id"], synthetic_feed())
    entries = client.get("/api/admin/audit-logs", headers=admin_headers()).json()["entries"]
    assert {"data_source.create", "gtfs.import"} <= {entry["action"] for entry in entries}


def test_admin_stats_count_imports_by_classification(client):
    load_demo(client)
    stats = client.get("/api/admin/stats", headers=admin_headers()).json()
    assert stats["database"] == "sqlite"
    assert stats["counts"]["routes"] == 2
    assert stats["active_imports_by_classification"][UNVERIFIED] == 1
    assert stats["active_imports_by_classification"][OFFICIAL] == 0


def test_deleting_an_import_removes_its_timetable(client):
    summary = load_demo(client)
    assert client.delete(f"/api/admin/imports/{summary['id']}", headers=admin_headers()).status_code == 204
    assert client.get("/api/routes", params={"classification": UNVERIFIED, "year": 2027}).json()["results"] == []


def test_sqlite_backup_creates_a_copy(client, settings):
    load_demo(client)
    response = client.post("/api/admin/backup", headers=admin_headers())
    assert response.status_code == 200, response.text
    copy = settings.backup_dir / response.json()["file"]
    assert copy.is_file()
    assert copy.stat().st_size > 0


# ---------------------------------------------------------------- public timetables

def test_unverified_upload_is_visible_only_under_its_own_classification(client):
    summary = load_demo(client)
    assert summary["status"] == "COMPLETED"
    assert summary["classification"] == UNVERIFIED
    assert summary["routes"] == 2
    assert summary["trips"] == 192

    unverified = client.get("/api/routes", params={"classification": UNVERIFIED, "year": 2027}).json()
    official = client.get("/api/routes", params={"classification": OFFICIAL, "year": 2027}).json()
    assert len(unverified["results"]) == 2
    assert official["results"] == []
    assert official["coverage"]["status"] == "NONE"


def test_scenario_classification_is_not_a_timetable_classification(client):
    assert client.get("/api/routes", params={"classification": "ESTIMATED_SCENARIO"}).status_code == 400


def test_timetables_and_csv_respect_the_feed_coverage(client):
    load_demo(client)
    route_id = demo_route_id(client)

    covered = client.get(f"/api/routes/{route_id}/timetable", params={"date": "2027-01-11"}).json()
    assert covered["covered"] is True
    assert len(covered["trips"]) == 66

    outside = client.get(f"/api/routes/{route_id}/timetable", params={"date": "2028-01-03"}).json()
    assert outside["covered"] is False
    assert outside["trips"] == []
    assert outside["message"] == "No unverified feed covers this date."

    export = client.get(f"/api/routes/{route_id}/timetable.csv", params={"date": "2027-01-11"})
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "attachment" in export.headers["content-disposition"]
    assert client.get(f"/api/routes/{route_id}/timetable.csv", params={"date": "2028-01-03"}).status_code == 404
    assert client.get("/api/routes/999999").status_code == 404


def test_stop_search_journeys_and_nearby_stops(client, frozen_api_clock):
    load_demo(client)
    stops = client.get(
        "/api/stops", params={"classification": UNVERIFIED, "year": 2027, "q": "junction"}
    ).json()["results"]
    assert [s["name"] for s in stops] == ["Demo Junction"]

    nearby = client.get(
        "/api/stops/nearby",
        params={"lat": 12.975, "lon": 77.595, "radius_m": 400, "classification": UNVERIFIED},
    ).json()
    assert nearby["results"][0]["name"] == "Demo Central"

    journey = client.get(
        "/api/journey",
        params={"origin": "Demo Central", "destination": "Demo Junction", "date": "2027-01-11",
                "classification": UNVERIFIED},
    ).json()
    assert len(journey["journeys"]) == 33
    assert all(j["classification"] == UNVERIFIED for j in journey["journeys"])

    official = client.get(
        "/api/journey",
        params={"origin": "Demo Central", "destination": "Demo Junction", "date": "2027-01-11"},
    ).json()
    assert official["journeys"] == []
    assert official["message"] == NO_OFFICIAL


# ---------------------------------------------------------------- device-scoped data

def test_saved_routes_belong_to_one_device(client):
    load_demo(client)
    body = {"gtfs_route_id": "DR1", "classification": UNVERIFIED, "label": "Home line"}
    assert client.post("/api/saved-routes", json=body).status_code == 400  # no device key

    saved = client.post("/api/saved-routes", headers=client_headers(CLIENT_A), json=body)
    assert saved.status_code == 201
    saved_id = saved.json()["id"]
    mine = client.get("/api/saved-routes", headers=client_headers(CLIENT_A)).json()["saved"]
    assert [r["label"] for r in mine] == ["Home line"]
    assert client.get("/api/saved-routes", headers=client_headers(CLIENT_B)).json()["saved"] == []

    unknown = client.post("/api/saved-routes", headers=client_headers(CLIENT_A), json={**body, "gtfs_route_id": "NOPE"})
    assert unknown.status_code == 404
    assert client.delete(f"/api/saved-routes/{saved_id}", headers=client_headers(CLIENT_B)).status_code == 404
    assert client.delete(f"/api/saved-routes/{saved_id}", headers=client_headers(CLIENT_A)).status_code == 204


def test_preferences_are_device_scoped_and_validated(client):
    assert client.put("/api/preferences", json={"values": {"units": "metric"}}).status_code == 400
    saved = client.put("/api/preferences", headers=client_headers(CLIENT_A), json={"values": {"units": "metric"}})
    assert saved.status_code == 200
    assert saved.json()["values"] == {"units": "metric"}
    assert client.get("/api/preferences", headers=client_headers(CLIENT_B)).json()["values"] == {}
    bad = client.put("/api/preferences", headers=client_headers(CLIENT_A), json={"values": {"Bad-Key": "x"}})
    assert bad.status_code == 422


def test_a_device_keeps_at_most_twenty_preferences(client):
    headers = client_headers(CLIENT_A)
    twenty = {f"pref_{letter}": "on" for letter in "abcdefghijklmnopqrst"}
    assert client.put("/api/preferences", headers=headers, json={"values": twenty}).status_code == 200
    # A stored preference can still be changed. A twenty-first one is refused, and nothing from that request is saved.
    assert client.put("/api/preferences", headers=headers, json={"values": {"pref_a": "off"}}).status_code == 200
    refused = client.put("/api/preferences", headers=headers, json={"values": {"pref_u": "on", "pref_a": "x"}})
    assert refused.status_code == 422
    stored = client.get("/api/preferences", headers=headers).json()["values"]
    assert len(stored) == 20
    assert stored["pref_a"] == "off"
    assert "pref_u" not in stored


def test_a_backup_that_cannot_be_written_returns_a_reason(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file is in the way", encoding="utf-8")
    app = create_app(make_settings(tmp_path, backup_dir=blocker))
    with TestClient(app) as test_client:
        response = test_client.post("/api/admin/backup", headers=admin_headers())
    app.state.db.dispose()
    assert response.status_code == 500
    assert "could not be written" in response.json()["detail"]


# ---------------------------------------------------------------- scenarios

def test_scenarios_are_labelled_estimates_owned_by_one_device(client):
    created = client.post("/api/scenarios", headers=client_headers(CLIENT_A), json=scenario_body())
    assert created.status_code == 201, created.text
    body = created.json()
    scenario_id = body["id"]
    assert body["classification"] == "ESTIMATED_SCENARIO"
    assert "not an official" in body["notice"]
    assert body["estimate"]["classification"] == "ESTIMATED_SCENARIO"
    assert body["estimate"]["departures_per_day"] == 65

    assert client.get("/api/scenarios").json()["scenarios"] == []  # no device key: nothing is shown
    mine = client.get("/api/scenarios", headers=client_headers(CLIENT_A)).json()["scenarios"]
    assert [s["id"] for s in mine] == [scenario_id]
    assert client.get("/api/scenarios", headers=client_headers(CLIENT_B)).json()["scenarios"] == []

    # Another device gets exactly the answer for a missing id, so ids cannot be probed.
    foreign = client.get(f"/api/scenarios/{scenario_id}", headers=client_headers(CLIENT_B))
    missing = client.get("/api/scenarios/999999", headers=client_headers(CLIENT_B))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert client.put(
        f"/api/scenarios/{scenario_id}", headers=client_headers(CLIENT_B), json=scenario_body()
    ).status_code == 404
    assert client.delete(f"/api/scenarios/{scenario_id}", headers=client_headers(CLIENT_B)).status_code == 404
    assert client.get(f"/api/scenarios/{scenario_id}", headers=client_headers(CLIENT_A)).status_code == 200


def test_scenario_writes_need_a_valid_device_key_and_valid_data(client):
    assert client.post("/api/scenarios", json=scenario_body()).status_code == 400
    assert client.post("/api/scenarios", headers=client_headers("short"), json=scenario_body()).status_code == 400
    invalid = client.post("/api/scenarios", headers=client_headers(CLIENT_A), json=scenario_body(year=2031))
    assert invalid.status_code == 422


def test_scenario_can_be_updated_and_deleted_by_its_owner(client):
    scenario_id = client.post("/api/scenarios", headers=client_headers(CLIENT_A), json=scenario_body()).json()["id"]
    updated = client.put(
        f"/api/scenarios/{scenario_id}", headers=client_headers(CLIENT_A), json=scenario_body(frequency_minutes=30)
    )
    assert updated.status_code == 200
    assert updated.json()["frequency_minutes"] == 30
    assert updated.json()["estimate"]["departures_per_day"] == 33
    assert client.delete(f"/api/scenarios/{scenario_id}", headers=client_headers(CLIENT_A)).status_code == 204
    assert client.get(f"/api/scenarios/{scenario_id}", headers=client_headers(CLIENT_A)).status_code == 404


def test_scenario_warns_when_its_route_code_matches_verified_data(client):
    official = new_source(client, kind="OFFICIAL", name="Official test feed")
    assert upload(client, official["id"], synthetic_feed()).status_code == 201
    verified = client.post(
        f"/api/admin/data-sources/{official['id']}/verify",
        headers=admin_headers(),
        json={"verified": True, "note": "test"},
    )
    assert verified.status_code == 200
    created = client.post(
        "/api/scenarios", headers=client_headers(CLIENT_A), json=scenario_body(year=2027, route_code="DEMO-1")
    )
    assert created.status_code == 201
    assert any("does not change that route" in warning for warning in created.json()["warnings"])


def test_scenarios_never_enter_the_timetable_tables(client):
    client.post("/api/scenarios", headers=client_headers(CLIENT_A), json=scenario_body())
    counts = client.get("/api/admin/stats", headers=admin_headers()).json()["counts"]
    assert counts["scenarios"] == 1
    assert counts["routes"] == 0
    assert counts["stop_times"] == 0


def test_compare_and_exports_are_owner_scoped(client):
    first = client.post("/api/scenarios", headers=client_headers(CLIENT_A), json=scenario_body()).json()["id"]
    second = client.post(
        "/api/scenarios",
        headers=client_headers(CLIENT_A),
        json=scenario_body(name="Every thirty", frequency_minutes=30),
    ).json()["id"]
    params = {"a": first, "b": second}

    comparison = client.get("/api/scenarios/compare", headers=client_headers(CLIENT_A), params=params)
    assert comparison.status_code == 200
    assert comparison.json()["difference_b_minus_a"]["departures_per_day"] == 33 - 65
    assert client.get("/api/scenarios/compare", headers=client_headers(CLIENT_B), params=params).status_code == 404

    csv_export = client.get("/api/scenarios/export.csv", headers=client_headers(CLIENT_A))
    assert csv_export.status_code == 200
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert "ESTIMATED_SCENARIO" in csv_export.text

    pdf = client.get(f"/api/scenarios/{first}/export.pdf", headers=client_headers(CLIENT_A))
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-")
    assert client.get(f"/api/scenarios/{first}/export.pdf", headers=client_headers(CLIENT_B)).status_code == 404

    compare_pdf = client.get("/api/scenarios/compare.pdf", headers=client_headers(CLIENT_A), params=params)
    assert compare_pdf.status_code == 200
    assert compare_pdf.content.startswith(b"%PDF-")


def test_csv_export_neutralises_spreadsheet_formulas(client):
    client.post(
        "/api/scenarios",
        headers=client_headers(CLIENT_A),
        json=scenario_body(name='=HYPERLINK("https://example.invalid","open")'),
    )
    body = client.get("/api/scenarios/export.csv", headers=client_headers(CLIENT_A)).text
    rows = list(csv.reader(io.StringIO(body)))
    assert rows[1][1].startswith("'=HYPERLINK")


def test_verifying_a_source_without_evidence_is_refused_and_changes_nothing(client):
    """A verified status needs recorded evidence. Without it the request is refused and the source stays as it was."""
    official = new_source(client, kind="OFFICIAL", name="Needs evidence")
    refused = client.post(
        f"/api/admin/data-sources/{official['id']}/verify",
        headers=admin_headers(),
        json={"verified": True, "note": "   "},
    )
    assert refused.status_code == 400, refused.text
    assert "evidence" in refused.json()["detail"]
    listing = client.get("/api/admin/data-sources", headers=admin_headers()).json()["sources"]
    row = next(item for item in listing if item["id"] == official["id"])
    assert row["verified"] is False

