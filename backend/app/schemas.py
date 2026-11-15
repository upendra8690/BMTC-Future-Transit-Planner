"""Request bodies with input validation for the scenario, data-source and user-data endpoints."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import KIND_UNKNOWN, WEEKDAY_CODES

HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
HHMM_RE = re.compile(HHMM_PATTERN)
PLANNING_YEARS = (2027, 2028, 2029, 2030)


def minutes_of_day(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _check_pair(label: str, lat: float | None, lon: float | None) -> None:
    if (lat is None) != (lon is None):
        raise ValueError(f"{label}: give both latitude and longitude, or neither")


class ScenarioStopIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _pair(self) -> ScenarioStopIn:
        _check_pair(f"stop '{self.name}'", self.lat, self.lon)
        return self


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=2027, le=2030)
    route_code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9][A-Za-z0-9\-_ ]*$")
    description: str | None = Field(default=None, max_length=1000)
    origin_name: str = Field(min_length=1, max_length=200)
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lon: float | None = Field(default=None, ge=-180, le=180)
    destination_name: str = Field(min_length=1, max_length=200)
    destination_lat: float | None = Field(default=None, ge=-90, le=90)
    destination_lon: float | None = Field(default=None, ge=-180, le=180)
    first_departure: str = Field(pattern=HHMM_PATTERN)
    last_departure: str = Field(pattern=HHMM_PATTERN)
    frequency_minutes: int = Field(ge=1, le=240)
    operating_days: list[str] = Field(min_length=1, max_length=7)
    stops: list[ScenarioStopIn] = Field(default_factory=list, max_length=30)

    @field_validator("operating_days")
    @classmethod
    def _days(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in value:
            day = raw.strip().upper()
            if day not in WEEKDAY_CODES:
                raise ValueError(f"unknown operating day '{raw}'")
            if day not in cleaned:
                cleaned.append(day)
        return cleaned

    @model_validator(mode="after")
    def _consistent(self) -> ScenarioIn:
        if minutes_of_day(self.last_departure) < minutes_of_day(self.first_departure):
            raise ValueError("last_departure must not be earlier than first_departure")
        _check_pair("origin", self.origin_lat, self.origin_lon)
        _check_pair("destination", self.destination_lat, self.destination_lon)
        return self


class DataSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=500, pattern=r"^https?://\S+$")
    license: str = Field(default="Not specified", max_length=200)
    # The Literal enforces the allowed kinds (422 otherwise). Tests check it matches models.SOURCE_KINDS.
    kind: Literal["OFFICIAL", "COMMUNITY", "SYNTHETIC_DEMO", "UNKNOWN"] = KIND_UNKNOWN


class VerificationIn(BaseModel):
    verified: bool
    note: str = Field(default="", max_length=500)


class SavedRouteIn(BaseModel):
    gtfs_route_id: str = Field(min_length=1, max_length=100)
    classification: Literal["OFFICIAL_VERIFIED", "UNVERIFIED_FEED"]
    label: str = Field(min_length=1, max_length=200)


class PreferencesIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict, max_length=20)

    @field_validator("values")
    @classmethod
    def _sizes(cls, value: dict[str, str]) -> dict[str, str]:
        for key, val in value.items():
            if not re.fullmatch(r"[a-z_]{1,50}", key) or len(val) > 500:
                raise ValueError(f"invalid preference '{key}'")
        return value
