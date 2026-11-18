"""Finding R1 (rate limit behind Render's proxy) and label findings D2 and D3, found on 18 November 2026.

R1: Render keeps an X-Forwarded-For header sent by the visitor, and uvicorn with --forwarded-allow-ips "*" believes
its first entry. A visitor could then pick any address, bypass the per-client limit, and fill the client table. With
CLIENT_IP_HEADER set (CF-Connecting-IP on Render, written by the Cloudflare edge), the limit counts the edge's
address for the visitor instead, whatever X-Forwarded-For says.

D2: the feature list may call fares available only when a fare will actually be shown.
D3: the app is told when items saved on the server are lost on restart.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from tests.helpers import build_transit_feed, make_settings
from tests.test_demo_mode import FARES, ROUTES, STOPS, TRIPS, load

RENDER_PROXY = "10.0.0.2"


def _render_like(root: Path, **overrides):
    """The app wrapped as uvicorn wraps it on Render: --proxy-headers --forwarded-allow-ips "*"."""
    root.mkdir(parents=True, exist_ok=True)
    inner = create_app(make_settings(root, rate_limit_per_minute=2, **overrides))
    return inner, ProxyHeadersMiddleware(inner, trusted_hosts="*")


# ---------------------------------------------------------------- R1: client address for the rate limit

def test_without_the_fix_a_forged_forwarded_address_gets_a_fresh_budget(tmp_path):
    """Documents the weakness: with "*" and no client header, the first X-Forwarded-For entry is believed."""
    inner, app = _render_like(tmp_path / "old")
    try:
        with TestClient(app, client=(RENDER_PROXY, 40000)) as client:
            for forged in ("198.51.100.1", "198.51.100.2", "198.51.100.3"):
                headers = {"X-Forwarded-For": f"{forged}, 203.0.113.50"}
                assert client.get("/api/meta", headers=headers).status_code == 200
    finally:
        inner.state.db.dispose()


def test_the_edge_header_decides_the_budget_whatever_x_forwarded_for_says(tmp_path):
    inner, app = _render_like(tmp_path / "fixed", client_ip_header="cf-connecting-ip")
    try:
        with TestClient(app, client=(RENDER_PROXY, 40000)) as client:
            visitor = {"CF-Connecting-IP": "203.0.113.50"}
            for forged in ("198.51.100.1", "198.51.100.2"):
                headers = {**visitor, "X-Forwarded-For": f"{forged}, 203.0.113.50"}
                assert client.get("/api/meta", headers=headers).status_code == 200
            blocked = client.get("/api/meta", headers={**visitor, "X-Forwarded-For": "198.51.100.3, 203.0.113.50"})
            assert blocked.status_code == 429
            assert blocked.headers["retry-after"] == "60"
            # Another real visitor still has a budget.
            assert client.get("/api/meta", headers={"CF-Connecting-IP": "203.0.113.51"}).status_code == 200
    finally:
        inner.state.db.dispose()


def test_a_missing_or_malformed_edge_header_falls_back_to_the_address_uvicorn_reports(tmp_path):
    inner = create_app(make_settings(tmp_path, rate_limit_per_minute=2, client_ip_header="cf-connecting-ip"))
    try:
        with TestClient(inner) as client:
            assert client.get("/api/meta").status_code == 200
            assert client.get("/api/meta", headers={"CF-Connecting-IP": "not-an-address"}).status_code == 200
            # Both counted for the same peer, so the third request is refused.
            assert client.get("/api/meta", headers={"CF-Connecting-IP": "<script>"}).status_code == 429
    finally:
        inner.state.db.dispose()


def test_the_edge_header_is_ignored_unless_it_is_configured(tmp_path):
    inner = create_app(make_settings(tmp_path, rate_limit_per_minute=2))
    try:
        with TestClient(inner) as client:
            for forged in ("198.51.100.1", "198.51.100.2"):
                assert client.get("/api/meta", headers={"CF-Connecting-IP": forged}).status_code == 200
            assert client.get("/api/meta", headers={"CF-Connecting-IP": "198.51.100.3"}).status_code == 429
    finally:
        inner.state.db.dispose()


def test_client_ip_header_setting_is_validated(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'env.db').as_posix()}")
    no_dotenv = tmp_path / "none.env"
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    assert Settings.from_env(no_dotenv).client_ip_header == ""
    monkeypatch.setenv("CLIENT_IP_HEADER", "CF-Connecting-IP")
    assert Settings.from_env(no_dotenv).client_ip_header == "cf-connecting-ip"
    monkeypatch.setenv("CLIENT_IP_HEADER", "X Forwarded: evil")
    with pytest.raises(ValueError, match="CLIENT_IP_HEADER"):
        Settings.from_env(no_dotenv)


def test_the_render_start_script_sets_the_edge_header_and_temporary_storage():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "container_start.sh").read_text(encoding="utf-8")
    assert 'export CLIENT_IP_HEADER="${CLIENT_IP_HEADER:-CF-Connecting-IP}"' in script
    assert 'export EPHEMERAL_STORAGE="${EPHEMERAL_STORAGE:-1}"' in script
    # Only on Render, and not when a PostgreSQL database is configured.
    assert 'if [ "${RENDER:-}" = "true" ]; then' in script
    assert "postgres*) ;;" in script


# ---------------------------------------------------------------- D2: fares are available only if shown

def _fares_state(client: TestClient) -> dict:
    return {f["id"]: f for f in client.get("/api/features").json()["features"]}["fares"]


def test_community_fares_do_not_make_fares_available(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, demo_mode=False))) as client:
        load(client, "COMMUNITY", build_transit_feed(STOPS, ROUTES, TRIPS, fares=FARES))
        assert _fares_state(client) == {"id": "fares", "state": "NO_DATA", "reason": "NO_VERIFIED_FARES"}


def test_shown_fares_make_fares_available(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, demo_mode=True))) as client:
        load(client, "SYNTHETIC_DEMO", build_transit_feed(STOPS, ROUTES, TRIPS, fares=FARES))
        assert _fares_state(client) == {"id": "fares", "state": "AVAILABLE", "reason": None}


def test_a_feed_without_fares_does_not_make_fares_available(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, demo_mode=True))) as client:
        load(client, "SYNTHETIC_DEMO", build_transit_feed(STOPS, ROUTES, TRIPS))
        assert _fares_state(client)["state"] == "NO_DATA"


# ---------------------------------------------------------------- D3: temporary server storage is reported

def test_server_storage_is_reported_as_temporary_only_when_it_is(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with TestClient(create_app(make_settings(tmp_path / "a", ephemeral_storage=True))) as client:
        assert client.get("/api/features").json()["server_storage_persistent"] is False
    with TestClient(create_app(make_settings(tmp_path / "b"))) as client:
        assert client.get("/api/features").json()["server_storage_persistent"] is True


def test_the_app_shows_the_temporary_storage_notice_and_metro_wording():
    root = Path(__file__).resolve().parents[1] / "dashboard"
    app_js = (root / "app.js").read_text(encoding="utf-8")
    assert "server_storage_persistent" in app_js
    assert "routes.saved_temporary" in app_js
    assert '"journey.wait_metro"' in app_js
    i18n = (root / "i18n.js").read_text(encoding="utf-8")
    for key in ("journey.wait_metro", "journey.wait_other", "routes.saved_temporary",
                "feature.reason.NO_VERIFIED_FARES"):
        assert i18n.count(f'"{key}":') == 4, key
    assert "Bus, Metro and journeys" not in i18n
