"""Passenger accounts, sessions, roles, account-saved journeys and notification preferences.

Accounts are off by default and refuse to run on a database that is not permanent. These tests switch them on with
ACCOUNTS_ALLOW_SQLITE (allowed for tests and local development only).
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.main import create_app
from app.models import User
from app.services import accounts
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.helpers import admin_headers, make_settings

PASSWORD = "correct horse battery"


@pytest.fixture
def app_client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, accounts_enabled=True, accounts_allow_sqlite=True))) as client:
        yield client


def register(client, email="asha@example.org", password=PASSWORD) -> dict:
    response = client.post("/api/account/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def sign_in(client, email="asha@example.org", password=PASSWORD) -> dict:
    response = client.post("/api/account/sign-in", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def journey(**changes) -> dict:
    body = {"origin": "Indiranagar", "destination": "Jayanagar", "modes": "metro",
            "classification": "UNVERIFIED_FEED", "label": "Work"}
    body.update(changes)
    return body


# ---------------------------------------------------------------- off unless storage is permanent

def test_accounts_are_off_by_default(client):
    status = client.get("/api/account/status").json()
    assert status == {"available": False, "reason": "ACCOUNTS_DISABLED", "notification_delivery": "NOT_AVAILABLE",
                      "roles": ["passenger", "editor", "admin"]}
    refused = client.post("/api/account/register", json={"email": "a@example.org", "password": PASSWORD})
    assert refused.status_code == 503


def test_accounts_refuse_to_run_on_a_temporary_database(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, accounts_enabled=True))) as client:
        assert client.get("/api/account/status").json()["reason"] == "NEEDS_PERSISTENT_DATABASE"
        assert client.post("/api/account/register",
                           json={"email": "a@example.org", "password": PASSWORD}).status_code == 503
        features = {f["id"]: f for f in client.get("/api/features").json()["features"]}
        assert features["accounts"] == {"id": "accounts", "state": "PLANNED", "reason": "NEEDS_PERSISTENT_DATABASE"}
        assert features["notifications"]["reason"] == "NEEDS_DELIVERY_SERVICE"


@pytest.mark.parametrize(("enabled", "allow_sqlite", "url", "reason"), [
    (True, False, "postgresql://u:p@db.example/planner", None),
    (True, False, "postgres://u:p@db.example/planner", None),
    (True, False, "sqlite:///data/planner.db", "NEEDS_PERSISTENT_DATABASE"),
    (True, True, "sqlite:///data/planner.db", None),
    (False, True, "postgresql://u:p@db.example/planner", "ACCOUNTS_DISABLED"),
])
def test_accounts_run_only_with_a_permanent_database(enabled, allow_sqlite, url, reason):
    assert accounts.availability(enabled, allow_sqlite, url) == reason


# ---------------------------------------------------------------- registration, sign-in, sessions

def test_register_sign_in_and_sign_out(app_client):
    created = register(app_client)
    assert created["user"]["role"] == "passenger"
    assert len(created["recovery_code"]) >= 20
    headers = sign_in(app_client)
    assert app_client.get("/api/account/me", headers=headers).json()["user"]["email"] == "asha@example.org"
    assert app_client.post("/api/account/sign-out", headers=headers).status_code == 200
    assert app_client.get("/api/account/me", headers=headers).status_code == 401


def test_passwords_and_recovery_codes_are_stored_only_as_hashes(app_client):
    created = register(app_client)
    db = app_client.app.state.db
    with db.session() as session:
        user = session.scalar(select(User))
        assert user.password_hash.startswith("scrypt$")
        assert PASSWORD not in user.password_hash
        assert created["recovery_code"] not in (user.recovery_hash or "")
    export = app_client.get("/api/account/export", headers=sign_in(app_client)).json()
    assert "hash" not in str(export)


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(app_client):
    register(app_client)
    wrong = app_client.post("/api/account/sign-in", json={"email": "asha@example.org", "password": "x" * 12})
    unknown = app_client.post("/api/account/sign-in", json={"email": "nobody@example.org", "password": "x" * 12})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_repeated_wrong_passwords_lock_the_account(app_client):
    register(app_client)
    for _ in range(accounts.MAX_FAILED_LOGINS):
        app_client.post("/api/account/sign-in", json={"email": "asha@example.org", "password": "x" * 12})
    locked = app_client.post("/api/account/sign-in", json={"email": "asha@example.org", "password": PASSWORD})
    assert locked.status_code == 429


@pytest.mark.parametrize(("email", "password", "status"), [
    ("not-an-email", PASSWORD, 422),
    ("short@example.org", "too short", 422),
])
def test_invalid_registrations_are_refused(app_client, email, password, status):
    assert app_client.post("/api/account/register", json={"email": email, "password": password}).status_code == status


def test_an_email_address_can_register_only_once(app_client):
    register(app_client)
    again = app_client.post("/api/account/register", json={"email": "ASHA@example.org", "password": PASSWORD})
    assert again.status_code == 409


def test_an_expired_session_is_refused(app_client):
    register(app_client)
    db = app_client.app.state.db
    with db.session() as session:
        user = session.scalar(select(User))
        _, token, _ = accounts.sign_in(session, user.email, PASSWORD,
                                       now=dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(days=31))
    assert app_client.get("/api/account/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# ---------------------------------------------------------------- password change and recovery

def test_changing_the_password_signs_out_every_session(app_client):
    register(app_client)
    headers = sign_in(app_client)
    changed = app_client.post("/api/account/password", headers=headers,
                              json={"current_password": PASSWORD, "new_password": "a new long password"})
    assert changed.status_code == 200
    assert app_client.get("/api/account/me", headers=headers).status_code == 401
    sign_in(app_client, password="a new long password")


def test_the_recovery_code_resets_the_password_once(app_client):
    code = register(app_client)["recovery_code"]
    headers = sign_in(app_client)
    body = {"email": "asha@example.org", "recovery_code": code, "new_password": "recovered password 1"}
    first = app_client.post("/api/account/recover", json=body)
    assert first.status_code == 200
    assert first.json()["recovery_code"] != code
    assert app_client.get("/api/account/me", headers=headers).status_code == 401  # old sessions are gone
    assert app_client.post("/api/account/recover", json=body).status_code == 401  # the old code is spent
    sign_in(app_client, password="recovered password 1")


# ---------------------------------------------------------------- saved journeys, preferences, export, deletion

def test_saved_journeys_belong_to_one_account(app_client):
    register(app_client)
    register(app_client, email="ravi@example.org")
    asha, ravi = sign_in(app_client), sign_in(app_client, email="ravi@example.org")
    saved = app_client.post("/api/account/journeys", headers=asha, json=journey())
    assert saved.status_code == 201
    assert [j["label"] for j in app_client.get("/api/account/journeys", headers=asha).json()["journeys"]] == ["Work"]
    assert app_client.get("/api/account/journeys", headers=ravi).json()["journeys"] == []
    assert app_client.delete(f"/api/account/journeys/{saved.json()['id']}", headers=ravi).status_code == 404
    assert app_client.delete(f"/api/account/journeys/{saved.json()['id']}", headers=asha).status_code == 200


def test_a_saved_journey_is_validated(app_client):
    register(app_client)
    headers = sign_in(app_client)
    assert app_client.post("/api/account/journeys", headers=headers,
                           json=journey(modes="ferry")).status_code == 422
    assert app_client.post("/api/account/journeys", json=journey()).status_code == 401


def test_notification_preferences_are_stored_but_nothing_is_sent(app_client):
    register(app_client)
    headers = sign_in(app_client)
    saved = app_client.put("/api/account/notifications", headers=headers,
                           json={"service_notices": True, "upcoming_changes": False}).json()
    assert saved == {"service_notices": True, "upcoming_changes": False, "delivery": "NOT_AVAILABLE"}


def test_deleting_an_account_needs_the_password_and_removes_everything(app_client):
    register(app_client)
    headers = sign_in(app_client)
    app_client.post("/api/account/journeys", headers=headers, json=journey())
    refused = app_client.post("/api/account/delete", headers=headers, json={"password": "wrong password"})
    assert refused.status_code == 401
    assert app_client.post("/api/account/delete", headers=headers, json={"password": PASSWORD}).status_code == 200
    assert app_client.post("/api/account/sign-in",
                           json={"email": "asha@example.org", "password": PASSWORD}).status_code == 401
    with app_client.app.state.db.session() as session:
        assert session.scalar(select(User)) is None


# ---------------------------------------------------------------- roles

def make_role(client, email: str, role: str) -> dict:
    register(client, email=email)
    user_id = client.get("/api/admin/users", headers=admin_headers()).json()["users"][-1]["id"]
    changed = client.put(f"/api/admin/users/{user_id}/role", headers=admin_headers(), json={"role": role})
    assert changed.status_code == 200
    return sign_in(client, email=email)


def test_a_passenger_cannot_use_administration(app_client):
    register(app_client)
    headers = sign_in(app_client)
    assert app_client.get("/api/admin/data-sources", headers=headers).status_code == 403
    assert app_client.get("/api/admin/users", headers=headers).status_code == 403


def test_an_editor_may_update_upcoming_transport_and_is_named_in_its_history(app_client):
    editor = make_role(app_client, "editor@example.org", "editor")
    changed = app_client.patch("/api/admin/upcoming/metro_blue", headers=editor,
                               json={"status": "DELAYED", "reason": "Operator statement checked"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["history"][0]["actor"].startswith("user:")
    assert app_client.post("/api/admin/data-sources", headers=editor,
                           json={"name": "x", "publisher": "y", "kind": "UNKNOWN"}).status_code == 403


def test_an_admin_account_can_manage_data_and_roles(app_client):
    admin = make_role(app_client, "admin@example.org", "admin")
    assert app_client.get("/api/admin/data-sources", headers=admin).status_code == 200
    register(app_client, email="later@example.org")
    users = app_client.get("/api/admin/users", headers=admin).json()["users"]
    target = next(u for u in users if u["email"] == "later@example.org")
    assert app_client.put(f"/api/admin/users/{target['id']}/role", headers=admin,
                          json={"role": "editor"}).status_code == 200
    entries = app_client.get("/api/admin/audit-logs", headers=admin_headers()).json()["entries"]
    assert any(e["action"] == "user.role" and e["actor"].startswith("user:") for e in entries)


def test_an_unknown_role_is_refused(app_client):
    register(app_client)
    assert app_client.put("/api/admin/users/1/role", headers=admin_headers(), json={"role": "owner"}).status_code == 422


def test_the_admin_key_still_works_when_accounts_are_on(app_client):
    assert app_client.get("/api/admin/data-sources", headers=admin_headers()).status_code == 200
