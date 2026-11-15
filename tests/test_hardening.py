"""Hardening: strict input validation, security headers on every response, and lifespan-based start-up and shutdown."""

from __future__ import annotations

import typing

from app.main import create_app
from app.models import SOURCE_KINDS
from app.schemas import DataSourceIn
from fastapi.testclient import TestClient

from tests.helpers import admin_headers, make_settings


def test_allowed_data_source_kinds_match_the_models():
    allowed = typing.get_args(DataSourceIn.model_fields["kind"].annotation)
    assert set(allowed) == set(SOURCE_KINDS)


def test_unknown_data_source_kind_is_a_validation_error_not_a_server_error(client):
    response = client.post(
        "/api/admin/data-sources",
        headers=admin_headers(),
        json={"name": "Odd source", "publisher": "Test publisher", "kind": "FAKE"},
    )
    assert response.status_code == 422


def test_every_response_declares_a_permissions_policy(client):
    for path in ("/", "/api/health"):
        policy = client.get(path).headers["permissions-policy"]
        assert "geolocation=(self)" in policy
        assert "camera=()" in policy
        assert "microphone=()" in policy


def test_rate_limited_responses_keep_the_security_headers(tmp_path):
    app = create_app(make_settings(tmp_path / "limited", rate_limit_per_minute=1))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        blocked = client.get("/api/health")
        assert blocked.status_code == 429
        assert blocked.headers["x-content-type-options"] == "nosniff"
        assert blocked.headers["x-frame-options"] == "DENY"
        assert "geolocation=(self)" in blocked.headers["permissions-policy"]
    app.state.db.dispose()


def test_start_up_and_shutdown_use_lifespan_not_deprecated_hooks(client):
    assert client.app.router.on_startup == []
    assert client.app.router.on_shutdown == []
