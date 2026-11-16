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
        )
