"""Response headers that limit what other sites and browser features can do, compression, and the admin key check.

These tests read the real responses. The CSP itself is also checked for forbidden sources in test_dashboard_static.py.
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

from tests.helpers import ADMIN_KEY, admin_headers, make_settings


def test_the_dashboard_page_sets_the_full_header_set(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["Cache-Control"] == "no-cache"
    csp = response.headers["Content-Security-Policy"]
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp


def test_api_responses_use_the_api_policy_and_no_dashboard_policy(client: TestClient):
    response = client.get("/api/meta")
    assert response.status_code == 200
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-site"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "Content-Security-Policy" not in response.headers


def test_large_json_is_compressed_when_the_client_accepts_it(client: TestClient):
    compressed = client.get("/api/openapi.json", headers={"Accept-Encoding": "gzip"})
    plain = client.get("/api/openapi.json", headers={"Accept-Encoding": "identity"})
    assert compressed.status_code == plain.status_code == 200
    assert compressed.headers.get("Content-Encoding") == "gzip"
    assert "Content-Encoding" not in plain.headers
    assert compressed.json() == plain.json()


def test_a_short_admin_key_is_warned_about_but_still_works(tmp_path, caplog):
    short_key = "short-test-key-0123"
    settings: Settings = make_settings(tmp_path, admin_api_key=short_key)
    with caplog.at_level(logging.WARNING, logger="bmtc_planner"):
        app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/admin/stats", headers=admin_headers(short_key))
    app.state.db.dispose()
    assert response.status_code == 200
    assert any("ADMIN_API_KEY is shorter than 32 characters" in record.getMessage() for record in caplog.records)


def test_a_long_admin_key_is_not_warned_about(tmp_path, caplog):
    settings = make_settings(tmp_path, admin_api_key=ADMIN_KEY + "0123456789abcdef")
    with caplog.at_level(logging.WARNING, logger="bmtc_planner"):
        app = create_app(settings)
    app.state.db.dispose()
    assert not any("shorter than 32" in record.getMessage() for record in caplog.records)


def test_hsts_is_sent_over_https_and_not_over_plain_http(settings):
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as secure:
        assert secure.get("/api/health").headers["strict-transport-security"] == "max-age=31536000"
        assert secure.get("/").headers["strict-transport-security"] == "max-age=31536000"
    with TestClient(app, base_url="http://testserver") as plain:
        assert "strict-transport-security" not in plain.get("/api/health").headers


def test_the_dashboard_policy_allows_no_inline_styles(client):
    policy = client.get("/").headers["content-security-policy"]
    assert "style-src 'self';" in policy
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy
