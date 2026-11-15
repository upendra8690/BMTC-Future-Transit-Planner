"""Client addresses behind a reverse proxy.

The rate limit counts each client by the address the server sees. Behind a proxy that address is the proxy itself, so
uvicorn reads X-Forwarded-For, but only when the connection comes from a trusted proxy address. These tests check that a
forwarded address is believed from the trusted proxy and ignored from anyone else.
"""

from __future__ import annotations

from pathlib import Path

from app.main import create_app
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from tests.helpers import make_settings

PROXY_IP = "10.0.0.2"


def _behind_proxy(root: Path, trusted: list[str]):
    """Return the application and the same application wrapped as uvicorn wraps it with --proxy-headers."""
    root.mkdir(parents=True, exist_ok=True)
    inner = create_app(make_settings(root, rate_limit_per_minute=2))
    return inner, ProxyHeadersMiddleware(inner, trusted_hosts=trusted)


def test_a_forwarded_address_gets_its_own_budget_when_the_proxy_is_trusted(tmp_path):
    inner, app = _behind_proxy(tmp_path / "trusted", trusted=[PROXY_IP])
    try:
        with TestClient(app, client=(PROXY_IP, 40000)) as client:
            for _ in range(2):
                assert client.get("/api/meta", headers={"X-Forwarded-For": "203.0.113.10"}).status_code == 200
            blocked = client.get("/api/meta", headers={"X-Forwarded-For": "203.0.113.10"})
            assert blocked.status_code == 429
            assert blocked.headers["retry-after"] == "60"
            assert client.get("/api/meta", headers={"X-Forwarded-For": "203.0.113.11"}).status_code == 200
    finally:
        inner.state.db.dispose()


def test_a_forwarded_address_is_ignored_when_the_connection_is_not_from_a_trusted_proxy(tmp_path):
    inner, app = _behind_proxy(tmp_path / "untrusted", trusted=["127.0.0.1"])
    try:
        with TestClient(app, client=(PROXY_IP, 40000)) as client:
            assert client.get("/api/meta", headers={"X-Forwarded-For": "203.0.113.10"}).status_code == 200
            assert client.get("/api/meta", headers={"X-Forwarded-For": "203.0.113.11"}).status_code == 200
            # The real peer is one client, whatever addresses it claims in the header.
            assert client.get("/api/meta", headers={"X-Forwarded-For": "203.0.113.12"}).status_code == 429
    finally:
        inner.state.db.dispose()
