"""Service notices: written by an administrator, only from an official source, dated, audited, and never invented."""

from __future__ import annotations

import datetime as dt

import pytest
from app.services.notices import is_official_source

from tests.helpers import admin_headers

OFFICIAL = "https://mybmtc.karnataka.gov.in/info-1/Notices/en"


def today(client) -> dt.date:
    return dt.date.fromisoformat(client.get("/api/notices").json()["today"])


def notice(client, **changes) -> dict:
    start = today(client)
    body = {
        "title": "Route 500D diverted near Silk Board",
        "body": "Buses use the service road while the flyover is repaired.",
        "kind": "DIVERSION",
        "mode": "BUS",
        "source_title": "BMTC notice",
        "source_url": OFFICIAL,
        "starts_on": start.isoformat(),
        "ends_on": (start + dt.timedelta(days=7)).isoformat(),
        "reason": "Copied from the BMTC website",
    }
    body.update(changes)
    return body


def post(client, body, headers=None):
    return client.post("/api/admin/notices", json=body, headers=admin_headers() if headers is None else headers)


def public(client) -> list[dict]:
    return client.get("/api/notices").json()["notices"]


def test_there_are_no_notices_until_an_administrator_posts_one(client):
    data = client.get("/api/notices").json()
    assert data["notices"] == []
    assert data["live_alerts_feed"] is False


def test_an_official_notice_is_shown_with_its_source_and_audited(client):
    created = post(client, notice(client))
    assert created.status_code == 201, created.text
    shown = public(client)
    assert len(shown) == 1
    assert shown[0]["status"] == "ACTIVE"
    assert shown[0]["source"] == {"title": "BMTC notice", "url": OFFICIAL}
    assert shown[0]["written_by_app_administrator"] is True
    audit = client.get("/api/admin/audit-logs", headers=admin_headers()).json()["entries"]
    entry = next(e for e in audit if e["action"] == "notice.create")
    assert "Copied from the BMTC website" in entry["detail"]


@pytest.mark.parametrize(("url", "ok"), [
    ("https://mybmtc.karnataka.gov.in/notice", True),
    ("https://english.bmrc.co.in/press-release/", True),
    ("https://dult.karnataka.gov.in/", True),
    ("https://x.com/BMTC_BENGALURU/status/1", True),
    ("https://twitter.com/OfficialBMRCL/status/2", True),
    ("https://x.com/someone_else/status/3", False),
    ("https://example.com/bmtc", False),
    ("https://gov.in.example.com/", False),
    ("https://evilgov.in/", False),
    ("https://example.com/?next=mybmtc.karnataka.gov.in", False),
    ("http://mybmtc.karnataka.gov.in/", False),
])
def test_only_official_sources_are_accepted(url, ok):
    assert is_official_source(url) is ok


def test_a_notice_from_an_unofficial_site_is_refused(client):
    response = post(client, notice(client, source_url="https://example.com/rumour"))
    assert response.status_code == 422
    assert "official source" in response.json()["detail"]
    assert public(client) == []


def test_plain_http_sources_are_refused_by_the_schema(client):
    assert post(client, notice(client, source_url="http://mybmtc.karnataka.gov.in/")).status_code == 422


def test_dates_are_checked(client):
    start = today(client)
    too_long = notice(client, ends_on=(start + dt.timedelta(days=32)).isoformat())
    assert "at most 31 days" in post(client, too_long).json()["detail"]
    backwards = notice(client, ends_on=(start - dt.timedelta(days=1)).isoformat())
    assert post(client, backwards).status_code == 422
    ended = notice(client, starts_on=(start - dt.timedelta(days=9)).isoformat(),
                   ends_on=(start - dt.timedelta(days=2)).isoformat())
    assert "already past" in post(client, ended).json()["detail"]


def test_a_scheduled_notice_waits_for_its_start_date(client):
    start = today(client) + dt.timedelta(days=3)
    body = notice(client, starts_on=start.isoformat(), ends_on=(start + dt.timedelta(days=2)).isoformat())
    assert post(client, body).status_code == 201
    assert public(client) == []
    admin = client.get("/api/admin/notices", headers=admin_headers()).json()["notices"]
    assert [n["status"] for n in admin] == ["SCHEDULED"]


def test_withdrawing_hides_a_notice_at_once_and_keeps_the_record(client):
    created = post(client, notice(client)).json()
    response = client.patch(f"/api/admin/notices/{created['id']}", headers=admin_headers(),
                            json={"withdrawn": True, "reason": "BMTC lifted the diversion"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "WITHDRAWN"
    assert public(client) == []
    admin = client.get("/api/admin/notices", headers=admin_headers()).json()["notices"]
    assert admin[0]["status"] == "WITHDRAWN"
    actions = [e["action"] for e in client.get("/api/admin/audit-logs", headers=admin_headers()).json()["entries"]]
    assert "notice.withdraw" in actions


def test_an_edit_needs_a_change_and_a_reason(client):
    created = post(client, notice(client)).json()
    path = f"/api/admin/notices/{created['id']}"
    unchanged = client.patch(path, headers=admin_headers(), json={"title": created["title"], "reason": "same"})
    assert unchanged.status_code == 422
    assert client.patch(path, headers=admin_headers(), json={"title": "A new title here"}).status_code == 422
    changed = client.patch(path, headers=admin_headers(), json={"title": "A new title here", "reason": "Typo fixed"})
    assert changed.json()["title"] == "A new title here"
    assert client.patch("/api/admin/notices/9999", headers=admin_headers(),
                        json={"title": "Anything else", "reason": "test"}).status_code == 404


def test_disruptions_are_listed_before_information(client):
    post(client, notice(client, kind="INFORMATION", title="Station lift under maintenance"))
    post(client, notice(client, kind="DISRUPTION", title="Purple Line delays this evening", mode="METRO",
                        source_url="https://english.bmrc.co.in/notice/1"))
    assert [n["kind"] for n in public(client)] == ["DISRUPTION", "INFORMATION"]


def test_notices_need_an_administrator(client):
    assert post(client, notice(client), headers={}).status_code == 401
    assert post(client, notice(client), headers=admin_headers("wrong-key-0123456789abcdef-xyz")).status_code == 401
    assert client.get("/api/admin/notices").status_code == 401
    assert public(client) == []


def test_the_reason_and_title_are_required(client):
    body = notice(client)
    del body["reason"]
    assert post(client, body).status_code == 422
    assert post(client, notice(client, title="Hi")).status_code == 422
