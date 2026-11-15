"""Authentication for administrative routes, per-device keys, input-safe filenames and rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

CLIENT_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{16,128}$")


def client_hash(client_key: str) -> str:
    """Store only a SHA-256 of a device key, so the raw key never sits in the database."""
    return hashlib.sha256(client_key.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str:
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


def require_admin(request: Request) -> str:
    """Fail closed: administrative routes are disabled unless ADMIN_API_KEY is configured."""
    expected = request.app.state.settings.admin_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Administrative functions are disabled: ADMIN_API_KEY is not set.")
    supplied = request.headers.get("x-admin-key", "")
    if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key.")
    return "admin"


def safe_filename(name: str | None) -> str:
    base = (name or "upload.zip").replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:120]
    return cleaned or "upload.zip"


class RateLimiter:
    """Sliding-window limiter per client IP. Suitable for one process; use a shared store behind several workers."""

    def __init__(self, per_minute: int, window_seconds: float = 60.0) -> None:
        self.per_minute = per_minute
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._hits) > 10_000:
                self._hits.clear()
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True
