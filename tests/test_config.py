"""Start-up settings: safe defaults, .env loading, and clear refusals that name the setting that is wrong."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from app.config import Settings

DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

BAD_VALUES = [
    ("RATE_LIMIT_PER_MINUTE", "0"),
    ("RATE_LIMIT_PER_MINUTE", "1e3"),
    ("RATE_LIMIT_PER_MINUTE", "-5"),
    ("MAX_UPLOAD_MB", "2049"),
    ("MAX_UNCOMPRESSED_MB", "abc"),
    ("MAX_ZIP_MEMBERS", "0"),
    ("AVG_BUS_SPEED_KMPH", "nan"),
    ("AVG_BUS_SPEED_KMPH", "inf"),
    ("AVG_BUS_SPEED_KMPH", "0"),
    ("STOP_DWELL_MINUTES", "-1"),
    ("DETOUR_FACTOR", "0.5"),
    ("SERVICE_TIMEZONE", "Mars/Olympus"),
]


def _load(tmp_path: Path, text: str = "", **env: str) -> Settings:
    """Read settings from a test .env file and only the variables given, never from the developer's environment."""
    env_file = tmp_path / "test.env"
    env_file.write_text(text, encoding="utf-8")
    with patch.dict(os.environ, env, clear=True):
        return Settings.from_env(env_file=env_file)


def test_defaults_are_safe_when_nothing_is_set(tmp_path):
    settings = _load(tmp_path)
    assert settings.admin_api_key == ""  # empty means the admin area is closed (503), never open
    assert settings.service_timezone == "Asia/Kolkata"
    assert settings.pdf_font_path is None
    assert settings.rate_limit_per_minute == 120
    assert settings.log_level == "INFO"
    assert settings.cors_origins == ()
    assert settings.max_upload_bytes == 100 * 1024 * 1024


@pytest.mark.parametrize(("name", "value"), BAD_VALUES)
def test_a_bad_value_stops_start_up_and_names_the_setting(tmp_path, name, value):
    with pytest.raises(ValueError, match=name):
        _load(tmp_path, **{name: value})


def test_a_missing_font_file_stops_start_up(tmp_path):
    with pytest.raises(ValueError, match="PDF_FONT_PATH"):
        _load(tmp_path, PDF_FONT_PATH=str(tmp_path / "missing.ttf"))


def test_a_file_that_is_not_a_truetype_font_stops_start_up(tmp_path):
    fake = tmp_path / "fake.ttf"
    fake.write_text("this is not a font", encoding="utf-8")
    with pytest.raises(ValueError, match="readable TrueType"):
        _load(tmp_path, PDF_FONT_PATH=str(fake))


@pytest.mark.skipif(not DEJAVU.is_file(), reason="DejaVu Sans is not installed on this machine")
def test_a_truetype_font_is_accepted(tmp_path):
    assert _load(tmp_path, PDF_FONT_PATH=str(DEJAVU)).pdf_font_path == DEJAVU


def test_values_from_the_env_file_load_and_real_variables_win(tmp_path):
    text = 'RATE_LIMIT_PER_MINUTE=300\nADMIN_API_KEY="from-file-0123456789abcdef"\n# a comment\nLOG_LEVEL=debug\n'
    settings = _load(tmp_path, text, RATE_LIMIT_PER_MINUTE="50")
    assert settings.rate_limit_per_minute == 50
    assert settings.admin_api_key == "from-file-0123456789abcdef"
    assert settings.log_level == "DEBUG"


def test_a_valid_alternative_zone_name_is_accepted(tmp_path):
    assert _load(tmp_path, SERVICE_TIMEZONE="Asia/Calcutta").service_timezone == "Asia/Calcutta"
