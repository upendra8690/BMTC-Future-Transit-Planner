"""Runtime configuration from environment variables, with an optional .env file at the project root.

Every value is checked when the settings are read. A bad value stops the start-up with a message that names the
setting, instead of failing later in the middle of a request.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from reportlab.pdfbase.ttfonts import TTFont

from .clock import DEFAULT_SERVICE_TIMEZONE, zone

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
DASHBOARD_DIR = PROJECT_DIR / "dashboard"
_WHOLE_NUMBER = re.compile(r"[0-9]{1,12}")
_HEADER_NAME = re.compile(r"[A-Za-z0-9-]{1,64}")


def _header_name(name: str) -> str:
    """An HTTP header name, or empty. A malformed value stops the start-up instead of being ignored silently."""
    raw = os.environ.get(name, "").strip()
    if raw and not _HEADER_NAME.fullmatch(raw):
        raise ValueError(f"{name} must be an HTTP header name such as CF-Connecting-IP. Found '{raw}'.")
    return raw.lower()


def _read_dotenv(path: Path) -> None:
    """Load KEY=VALUE pairs without overriding variables already set in the environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _get_int(name: str, default: int, *, low: int = 1, high: int = 10**9) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    if not _WHOLE_NUMBER.fullmatch(raw):
        raise ValueError(f"{name} must be a whole number, for example {default}. Found '{raw}'.")
    value = int(raw)
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}. Found {value}.")
    return value


def _get_float(name: str, default: float, *, low: float, high: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, for example {default}. Found '{raw}'.") from exc
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be a finite number between {low} and {high}. Found '{raw}'.")
    return value


def _check_font_file(path: Path) -> None:
    """The font must exist and be a TrueType file that ReportLab can read, so a bad file stops the start-up."""
    if not path.is_file():
        raise ValueError(f"PDF_FONT_PATH does not point to a font file: {path}")
    try:
        TTFont("PlannerFontCheck", str(path))
    except Exception as exc:
        raise ValueError(f"PDF_FONT_PATH is not a readable TrueType (.ttf) font: {path}") from exc


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_api_key: str
    max_upload_bytes: int
    max_uncompressed_bytes: int
    max_zip_members: int
    max_compression_ratio: int
    rate_limit_per_minute: int
    avg_bus_speed_kmph: float
    stop_dwell_minutes: float
    detour_factor: float
    backup_dir: Path
    log_level: str
    cors_origins: tuple[str, ...] = ()
    # Used for "now" only when no imported feed names a time zone. Imported feeds always supply their own.
    service_timezone: str = DEFAULT_SERVICE_TIMEZONE
    # Optional TrueType font for estimated-scenario PDFs. Without it, PDFs use a standard Latin font.
    pdf_font_path: Path | None = None
    # Planning assumptions for journeys with changes. They are estimates, and every answer states them.
    min_transfer_minutes: float = 3.0
    max_transfer_walk_m: int = 300
    walk_speed_kmph: float = 4.8
    # Demonstration mode serves the invented SYNTHETIC_DEMO feeds. Off by default, so the public service shows only
    # real information; a demonstration server sets DEMO_MODE=1 (see app/demo.py).
    demo_mode: bool = False
    # Passenger accounts run only when switched on AND the database is permanent (PostgreSQL). ACCOUNTS_ALLOW_SQLITE
    # is for local development and tests only: on a hosting service's temporary disk every account would be lost.
    accounts_enabled: bool = False
    accounts_allow_sqlite: bool = False
    # A header that the hosting provider's edge sets to the visitor's address and that a visitor cannot set, such as
    # CF-Connecting-IP behind Cloudflare. Empty: the address uvicorn reports is used. It counts visitors for the rate
    # limit; X-Forwarded-For is not used for that, because its first entry can be written by the visitor.
    client_ip_header: str = ""
    # True on hosting whose disk is erased on every restart (Render's free plan with SQLite). The app then tells
    # passengers that items saved on the server can be lost, and points them to what is kept on their own device.
    ephemeral_storage: bool = False
    # Live vehicles and arrival estimates (GTFS-Realtime). Empty URLs: not connected, which is the case until BMTC
    # authorises access. See app/services/realtime.py. REALTIME_AUTH_HEADER is a secret and is never returned.
    realtime_vehicles_url: str = ""
    realtime_trip_updates_url: str = ""
    realtime_auth_header: str = ""
    realtime_source_kind: str = "OFFICIAL"
    realtime_classification: str = "OFFICIAL_VERIFIED"
    realtime_poll_seconds: int = 20
    realtime_stale_seconds: int = 120
    # Payments and ticketing (app/services/payment_providers.py). Empty: nothing can be bought. Key secrets and the
    # webhook secret are secrets: set them in the hosting dashboard, never in GitHub.
    payment_provider: str = ""
    payment_environment: str = "production"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    public_base_url: str = ""
    merchant_name: str = "Bengaluru Transit Planner"
    ticketing_provider: str = ""
    payment_sandbox_state: Path = DATA_DIR / "payment_sandbox.json"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        _read_dotenv(env_file or PROJECT_DIR / ".env")
        default_db = DATA_DIR / "planner.db"
        origins = os.environ.get("CORS_ORIGINS", "")
        service_timezone = os.environ.get("SERVICE_TIMEZONE", "").strip() or DEFAULT_SERVICE_TIMEZONE
        try:
            zone(service_timezone)
        except ValueError as exc:
            raise ValueError(
                f"SERVICE_TIMEZONE must be an IANA time zone name, such as {DEFAULT_SERVICE_TIMEZONE}. "
                f"Found '{service_timezone}'."
            ) from exc
        font_raw = os.environ.get("PDF_FONT_PATH", "").strip()
        font_path = Path(font_raw) if font_raw else None
        if font_path is not None:
            _check_font_file(font_path)
        log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        return cls(
            database_url=os.environ.get("DATABASE_URL") or f"sqlite:///{default_db.as_posix()}",
            admin_api_key=os.environ.get("ADMIN_API_KEY", "").strip(),
            max_upload_bytes=_get_int("MAX_UPLOAD_MB", 100, high=2048) * 1024 * 1024,
            max_uncompressed_bytes=_get_int("MAX_UNCOMPRESSED_MB", 500, high=8192) * 1024 * 1024,
            max_zip_members=_get_int("MAX_ZIP_MEMBERS", 50, high=10_000),
            max_compression_ratio=_get_int("MAX_COMPRESSION_RATIO", 100, high=10_000),
            rate_limit_per_minute=_get_int("RATE_LIMIT_PER_MINUTE", 120, high=1_000_000),
            avg_bus_speed_kmph=_get_float("AVG_BUS_SPEED_KMPH", 15.0, low=1.0, high=200.0),
            stop_dwell_minutes=_get_float("STOP_DWELL_MINUTES", 0.5, low=0.0, high=30.0),
            detour_factor=_get_float("DETOUR_FACTOR", 1.3, low=1.0, high=3.0),
            backup_dir=Path(os.environ.get("BACKUP_DIR") or (DATA_DIR / "backups")),
            log_level=log_level,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
            service_timezone=service_timezone,
            pdf_font_path=font_path,
            min_transfer_minutes=_get_float("MIN_TRANSFER_MINUTES", 3.0, low=0.0, high=60.0),
            max_transfer_walk_m=_get_int("MAX_TRANSFER_WALK_M", 300, low=0, high=1000),
            walk_speed_kmph=_get_float("WALK_SPEED_KMPH", 4.8, low=1.0, high=10.0),
            demo_mode=_flag("DEMO_MODE"),
            accounts_enabled=_flag("ACCOUNTS_ENABLED"),
            accounts_allow_sqlite=_flag("ACCOUNTS_ALLOW_SQLITE"),
            client_ip_header=_header_name("CLIENT_IP_HEADER"),
            ephemeral_storage=_flag("EPHEMERAL_STORAGE"),
            realtime_vehicles_url=os.environ.get("REALTIME_VEHICLES_URL", "").strip(),
            realtime_trip_updates_url=os.environ.get("REALTIME_TRIP_UPDATES_URL", "").strip(),
            realtime_auth_header=os.environ.get("REALTIME_AUTH_HEADER", "").strip(),
            realtime_source_kind=os.environ.get("REALTIME_SOURCE_KIND", "OFFICIAL").strip().upper() or "OFFICIAL",
            realtime_classification=(os.environ.get("REALTIME_CLASSIFICATION", "").strip()
                                     or "OFFICIAL_VERIFIED"),
            realtime_poll_seconds=_get_int("REALTIME_POLL_SECONDS", 20, low=5, high=600),
            realtime_stale_seconds=_get_int("REALTIME_STALE_SECONDS", 120, low=30, high=600),
            payment_provider=os.environ.get("PAYMENT_PROVIDER", "").strip().lower(),
            payment_environment=os.environ.get("PAYMENT_ENVIRONMENT", "production").strip().lower() or "production",
            razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID", "").strip(),
            razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET", "").strip(),
            razorpay_webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip(),
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "").strip(),
            merchant_name=os.environ.get("MERCHANT_NAME", "").strip() or "Bengaluru Transit Planner",
            ticketing_provider=os.environ.get("TICKETING_PROVIDER", "").strip().lower(),
            payment_sandbox_state=Path(os.environ.get("PAYMENT_SANDBOX_STATE") or (DATA_DIR / "payment_sandbox.json")),
        )
