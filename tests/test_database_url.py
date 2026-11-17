"""Hosting providers hand out postgres:// and postgresql:// addresses; the app must use its installed psycopg driver."""

from __future__ import annotations

import pytest
from app.database import normalise_url


@pytest.mark.parametrize(("given", "expected"), [
    ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ("postgresql://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("sqlite:///data/planner.db", "sqlite:///data/planner.db"),
])
def test_database_addresses_use_the_installed_driver(given, expected):
    assert normalise_url(given) == expected


def test_the_postgresql_driver_is_a_declared_dependency():
    from pathlib import Path

    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert "psycopg[binary]" in requirements
