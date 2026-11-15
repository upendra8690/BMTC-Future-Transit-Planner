"""Runtime configuration from environment variables, with an optional .env file at the project root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
DASHBOARD_DIR = PROJECT_DIR / "dashboard"


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


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() else default


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


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

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        _read_dotenv(env_file or PROJECT_DIR / ".env")
        default_db = DATA_DIR / "planner.db"
        origins = os.environ.get("CORS_ORIGINS", "")
        return cls(
            database_url=os.environ.get("DATABASE_URL") or f"sqlite:///{default_db.as_posix()}",
            admin_api_key=os.environ.get("ADMIN_API_KEY", "").strip(),
            max_upload_bytes=_get_int("MAX_UPLOAD_MB", 100) * 1024 * 1024,
            max_uncompressed_bytes=_get_int("MAX_UNCOMPRESSED_MB", 500) * 1024 * 1024,
            max_zip_members=_get_int("MAX_ZIP_MEMBERS", 50),
            max_compression_ratio=_get_int("MAX_COMPRESSION_RATIO", 100),
            rate_limit_per_minute=_get_int("RATE_LIMIT_PER_MINUTE", 120),
            avg_bus_speed_kmph=_get_float("AVG_BUS_SPEED_KMPH", 15.0),
            stop_dwell_minutes=_get_float("STOP_DWELL_MINUTES", 0.5),
            detour_factor=_get_float("DETOUR_FACTOR", 1.3),
            backup_dir=Path(os.environ.get("BACKUP_DIR") or (DATA_DIR / "backups")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )
