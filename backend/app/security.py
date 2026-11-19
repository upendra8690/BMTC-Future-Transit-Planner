"""Authentication for administrative routes, per-device keys, input-safe filenames and rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

CLIENT_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{16,128}$")


def client_hash(client_key: str) -> str:
    """Store only a SHA-256 of a device key, so the raw key never sits in the database."""
    return hashlib.sha256(client_key.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str:
    """The visitor's address, used only to count requests for the rate limit.

    With CLIENT_IP_HEADER set (for example CF-Connecting-IP on Render, whose Cloudflare edge overwrites that header),
    the address comes from it. Otherwise, or if the header is missing or is not an IP address, the address uvicorn
    reports is used: the peer, or the X-Forwarded-For entry chosen under FORWARDED_ALLOW_IPS.
    """
    settings = getattr(request.app.state, "settings", None)
    header = getattr(settings, "client_ip_header", "")
    if header:
        value = request.headers.get(header, "").strip()
        if value:
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                pass
    return request.client.host if request.client else "unknown"


def require_client_key(request: Request) -> str:
    """Return the hashed device key. Used to scope a user's own scenarios and saved items."""
    key = request.headers.get("x-client-key", "")
    if not CLIENT_KEY_RE.fullmatch(key):
        raise HTTPException(status_code=400, detail="A valid X-Client-Key header is required for this action.")
    return client_hash(key)


def optional_client_hash(request: Request) -> str | None:
    key = request.headers.get("x-client-key", "")
    return client_hash(key) if CLIENT_KEY_RE.fullmatch(key) else None


def bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def require_admin(request: Request, roles: tuple[str, ...] = ("admin",), bootstrap: bool = False) -> str:
    """Fail closed. Returns who acted, and keeps it in request.state.admin_actor for the audit log.

    With accounts running (a permanent database), administration uses individual accounts: a signed-in account whose
    role is in ``roles`` is accepted and recorded as "user:<id>". The shared ADMIN_API_KEY then works only on the
    routes marked ``bootstrap`` (listing accounts and assigning roles), so it can create the first administrator but
    cannot be used for day-to-day changes.

    Without accounts, the ADMIN_API_KEY holder is accepted and recorded as "admin"; without that key configured,
    administrative routes are disabled.
    """
    token = bearer_token(request)
    accounts_running = getattr(request.app.state, "accounts_reason", "off") is None
    if accounts_running and not token and not request.headers.get("x-admin-key"):
        raise HTTPException(status_code=401, detail="Sign in with an administrator or editor account.")
    if token and accounts_running:
        from .services import accounts  # imported here: the account service is optional

        with request.app.state.db.session() as session:
            user = accounts.user_for_token(session, token)
            if user is None:
                raise HTTPException(status_code=401, detail="Your session has ended. Sign in again.")
            if user.role not in roles:
                raise HTTPException(status_code=403, detail="Your account does not have permission for this action.")
            actor = f"user:{user.id}"
    else:
        expected = request.app.state.settings.admin_api_key
        if not expected:
            raise HTTPException(status_code=503,
                                detail="Administrative functions are disabled: ADMIN_API_KEY is not set.")
        supplied = request.headers.get("x-admin-key", "")
        if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Invalid or missing admin key.")
        if accounts_running and not bootstrap:
            raise HTTPException(status_code=403, detail=(
                "Administrator accounts are running on this server, so sign in with your own account. The shared "
                "admin key can only list accounts and assign roles."))
        actor = "admin"
    request.state.admin_actor = actor
    return actor


def safe_filename(name: str | None) -> str:
    base = (name or "upload.zip").replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120]
    return cleaned or "upload.zip"


class RateLimiter:
    """Sliding-window limiter per client IP. Suitable for one process; use a shared store behind several workers."""

    def __init__(self, per_minute: int, window_seconds: float = 60.0, max_clients: int = 10_000) -> None:
        self.per_minute = per_minute
        self.window = window_seconds
        self.max_clients = max_clients
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _forget_idle(self, now: float) -> None:
        """Drop clients with no hit inside the window, so the table only holds clients that are active."""
        idle = [key for key, hits in self._hits.items() if not hits or now - hits[-1] > self.window]
        for key in idle:
            del self._hits[key]

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self.max_clients:
                    self._forget_idle(now)
                if len(self._hits) >= self.max_clients:
                    # Too many distinct clients are active at once. New clients are refused. Existing counts are kept,
                    # because clearing them would let a flood of addresses reset everyone's budget.
                    return False
                hits = self._hits[key] = deque()
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True
