"""Application factory. Run with: uvicorn app.main:create_app --factory --app-dir backend"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import DASHBOARD_DIR, Settings
from .database import Database
from .security import RateLimiter, client_ip

LOG = logging.getLogger("bmtc_planner")

DASHBOARD_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://*.tile.openstreetmap.org; "
    "connect-src 'self'; "
    "manifest-src 'self'; "
    "worker-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Only the page itself may ask for the device's location ("near me" search). Other device features are off.
PERMISSIONS_POLICY = "geolocation=(self), camera=(), microphone=(), payment=(), usb=()"


def _apply_security_headers(response: Response, path: str) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
    if not path.startswith("/api/"):
        response.headers.setdefault("Content-Security-Policy", DASHBOARD_CSP)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # The database is opened and migrated before the application exists, so a bad database fails at start-up.
    db = Database(settings.database_url)
    db.create_schema()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        db.dispose()

    app = FastAPI(
        title="BMTC Future Transit Planner API",
        version="1.0.0",
        description=(
            "Verified timetables are shown separately from unverified feeds. "
            "Future scenarios are always labelled ESTIMATED_SCENARIO and are not official announcements."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    limiter = RateLimiter(settings.rate_limit_per_minute)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Content-Type", "X-Client-Key", "X-Admin-Key"],
        )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        started = time.perf_counter()
        path = request.url.path
        if path.startswith("/api/") and not limiter.allow(client_ip(request)):
            response: Response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please wait a minute and try again."},
                headers={"Retry-After": "60"},
            )
        else:
            response = await call_next(request)
        _apply_security_headers(response, path)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if path.startswith("/api/") and request.method != "GET":
            LOG.info("%s %s -> %s (%.1f ms)", request.method, path, response.status_code, elapsed_ms)
        return response

    app.include_router(router, prefix="/api")

    if DASHBOARD_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

    return app
