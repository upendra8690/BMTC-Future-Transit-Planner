"""Upcoming-transport announcements are kept in the database and updated by administrators without code changes.

Every change needs the admin key and a reason, passes the same rules as the seeded entries, and is kept in the entry's
public history. No change can show a planned service as operating without an opening date, or give an expected start
date that no official announcement made.
"""

from __future__ import annotations

from typing import get_args

import pytest
from app import schemas
from app.services import registry

from tests.helpers import admin_headers

SOURCE = [{"title": "Operator announcement", "url": "https://example.org/announcement"}]


def projects(client) -> dict[str, dict]:
    return {p["id"]: p for p in client.get("/api/upcoming").json()["projects"]}


def patch(client, key: str, body: dict, headers: dict | None = None):
    return client.patch(f"/api/admin/upcoming/{key}", json=body,
                        headers=admin_headers() if headers is None else headers)


def new_entry(**changes) -> dict:
    body = {"id": "test_interchange", "name": "Test interchange", "transport_type": "INTERCHANGE",
            "location": "Demo station forecourt", "announcement": "A new bus and Metro interchange.",
            "status": "ANNOUNCED", "source_kind": "OFFICIAL", "announced_on": "2026-10",
            "expected_start": "2027-06", "sources": SOURCE, "verified_on": "2026-11-17",
            "reason": "Operator press release checked"}
    body.update(changes)
    return body


def test_schema_choices_match_the_registry():
    assert set(get_args(schemas.ProjectStatus)) == set(registry.PROJECT_STATUSES)
    assert set(get_args(schemas.TransportType)) == set(registry.TRANSPORT_TYPES)
    assert set(get_args(schemas.AnnouncementSourceKind)) == set(registry.ANNOUNCEMENT_SOURCE_KINDS)


def test_entries_are_seeded_once_with_their_first_history_record(client):
    first = projects(client)
    second = projects(client)
    assert set(first) == set(second) == {item["id"] for item in registry.UPCOMING}
    for project in second.values():
        assert project["history"][-1]["actor"] == "system"
        assert project["in_planner"] is False
        assert project["expected_start"] is None  # no seeded entry comes from an official announcement


def test_an_administrator_records_a_delay_with_a_reason(client):
    response = patch(client, "metro_blue", {"status": "DELAYED", "note": "Operator reported a delay",
                                            "reason": "Checked the operator's statement"})
    assert response.status_code == 200, response.text
    project = projects(client)["metro_blue"]
    assert project["status"] == "DELAYED"
    latest = project["history"][0]
    assert latest["reason"] == "Checked the operator's statement"
    assert latest["changes"]["status"] == ["UNDER_CONSTRUCTION", "DELAYED"]
    assert latest["actor"] == "admin"
    assert len(project["history"]) == 2


def test_a_planned_service_cannot_be_made_operating_without_an_opening_date(client):
    response = patch(client, "metro_blue", {"status": "OPERATING", "reason": "Trying without a date"})
    assert response.status_code == 400
    assert "needs the date it opened" in response.json()["detail"]
    assert projects(client)["metro_blue"]["status"] == "UNDER_CONSTRUCTION"


def test_an_expected_start_date_needs_an_official_announcement(client):
    response = patch(client, "metro_blue", {"expected_start": "2027-03", "reason": "Press report says March"})
    assert response.status_code == 400
    assert "only an official announcement" in response.json()["detail"]
    official = patch(client, "metro_blue", {"source_kind": "OFFICIAL", "expected_start": "2027-03",
                                            "sources": SOURCE, "reason": "Operator announced the date"})
    assert official.status_code == 200, official.text
    assert official.json()["official_announcement"] is True


def test_opening_a_service_needs_a_past_opening_date(client):
    future = patch(client, "metro_pink_underground", {"status": "OPERATING", "opened_on": "2099-01-01",
                                                      "reason": "Not yet open"})
    assert future.status_code == 400
    opened = patch(client, "metro_pink_underground", {"status": "OPERATING", "opened_on": "2026-11-16",
                                                      "verified_on": "2026-11-17", "reason": "Opening reported"})
    assert opened.status_code == 200, opened.text
    assert projects(client)["metro_pink_underground"]["opened_on"] == "2026-11-16"


def test_changes_need_the_admin_key_and_a_reason(client):
    assert patch(client, "metro_blue", {"status": "DELAYED", "reason": "x" * 5}, headers={}).status_code == 401
    assert patch(client, "metro_blue", {"status": "DELAYED", "reason": "x" * 5},
                 headers=admin_headers("wrong-key-000000000000")).status_code == 401
    assert patch(client, "metro_blue", {"status": "DELAYED"}).status_code == 422
    assert client.post("/api/admin/upcoming", json=new_entry()).status_code == 401
    assert projects(client)["metro_blue"]["status"] == "UNDER_CONSTRUCTION"


@pytest.mark.parametrize("body", [
    {"status": "RUNNING", "reason": "bad status"},
    {"opened_on": "14 Nov 2026", "reason": "bad date"},
    {"sources": [{"title": "t", "url": "http://insecure.example/"}], "reason": "http source"},
    {"sources": [], "reason": "no source"},
    {"name": None, "reason": "empty name"},
])
def test_invalid_changes_are_refused(client, body):
    assert patch(client, "metro_blue", body).status_code == 422


def test_an_unchanged_entry_is_not_recorded_again(client):
    response = patch(client, "metro_blue", {"status": "UNDER_CONSTRUCTION", "reason": "No change"})
    assert response.status_code == 400
    assert len(projects(client)["metro_blue"]["history"]) == 1


def test_an_unknown_entry_is_not_found(client):
    assert patch(client, "no_such_entry", {"status": "DELAYED", "reason": "x" * 5}).status_code == 404


def test_an_administrator_adds_an_official_announcement(client):
    response = client.post("/api/admin/upcoming", json=new_entry(), headers=admin_headers())
    assert response.status_code == 201, response.text
    created = projects(client)["test_interchange"]
    assert created["official_announcement"] is True
    assert created["expected_start"] == "2027-06"
    assert created["mode"] == "other"
    assert created["history"][0]["reason"] == "Operator press release checked"
    again = client.post("/api/admin/upcoming", json=new_entry(), headers=admin_headers())
    assert again.status_code == 409


def test_an_estimate_cannot_be_added_as_operating(client):
    body = new_entry(id="estimate_line", source_kind="ESTIMATE", status="OPERATING", opened_on="2026-01-01",
                     expected_start=None)
    response = client.post("/api/admin/upcoming", json=body, headers=admin_headers())
    assert response.status_code == 400
    assert "cannot be shown as operating" in response.json()["detail"]


def test_changes_are_written_to_the_audit_log(client):
    patch(client, "metro_blue", {"status": "DELAYED", "reason": "Checked the operator's statement"})
    entries = client.get("/api/admin/audit-logs", headers=admin_headers()).json()["entries"]
    assert any(e["action"] == "upcoming.update" and e["entity_id"] == "metro_blue" for e in entries)
