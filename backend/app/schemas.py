"""Request bodies with input validation for the scenario, data-source and user-data endpoints."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


# ---------------------------------------------------------------- upcoming-transport announcements
# The Literals must match registry.PROJECT_STATUSES, TRANSPORT_TYPES and ANNOUNCEMENT_SOURCE_KINDS (a test checks).
PARTIAL_DATE = r"^\d{4}(-\d{2}(-\d{2})?)?$"
FULL_DATE = r"^\d{4}-\d{2}-\d{2}$"
ProjectStatus = Literal["ANNOUNCED", "PLANNED", "UNDER_CONSTRUCTION", "DELAYED", "AWAITING_CONFIRMATION", "OPERATING"]
TransportType = Literal["BUS_ROUTE", "ELECTRIC_BUS", "FEEDER", "METRO_EXTENSION", "METRO_STATION", "SUBURBAN_RAIL",
                        "INTERCHANGE", "INTEGRATED_TICKETING"]
AnnouncementSourceKind = Literal["OFFICIAL", "PRESS", "SECONDARY", "ESTIMATE", "DEMO"]


class AnnouncementSourceIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=500, pattern=r"^https://\S+$")


class AnnouncementIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{2,60}$")
    name: str = Field(min_length=3, max_length=200)
    transport_type: TransportType
    location: str = Field(default="", max_length=300)
    announcement: str = Field(default="", max_length=2000)
    status: ProjectStatus
    source_kind: AnnouncementSourceKind
    announced_on: str | None = Field(default=None, pattern=PARTIAL_DATE)
    expected_start: str | None = Field(default=None, pattern=PARTIAL_DATE)
    opened_on: str | None = Field(default=None, pattern=FULL_DATE)
    sources: list[AnnouncementSourceIn] = Field(min_length=1, max_length=5)
    verified_on: str = Field(pattern=FULL_DATE)
    note: str = Field(default="", max_length=300)
    reason: str = Field(min_length=3, max_length=500)


class AnnouncementUpdateIn(BaseModel):
    """Only the fields that are sent change. Send null to clear an optional date."""

    name: str | None = Field(default=None, min_length=3, max_length=200)
    transport_type: TransportType | None = None
    location: str | None = Field(default=None, max_length=300)
    announcement: str | None = Field(default=None, max_length=2000)
    status: ProjectStatus | None = None
    source_kind: AnnouncementSourceKind | None = None
    announced_on: str | None = Field(default=None, pattern=PARTIAL_DATE)
    expected_start: str | None = Field(default=None, pattern=PARTIAL_DATE)
    opened_on: str | None = Field(default=None, pattern=FULL_DATE)
    sources: list[AnnouncementSourceIn] | None = Field(default=None, min_length=1, max_length=5)
    verified_on: str | None = Field(default=None, pattern=FULL_DATE)
    note: str | None = Field(default=None, max_length=300)
    reason: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------- passenger accounts
class AccountIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class RecoverIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    recovery_code: str = Field(min_length=1, max_length=40)
    new_password: str = Field(min_length=1, max_length=128)


class AccountJourneyIn(BaseModel):
    origin: str = Field(min_length=2, max_length=80)
    destination: str = Field(min_length=2, max_length=80)
    modes: Literal["all", "bus", "metro"] = "all"
    classification: Literal["OFFICIAL_VERIFIED", "UNVERIFIED_FEED"]
    label: str = Field(min_length=1, max_length=100)


class NotificationIn(BaseModel):
    service_notices: bool = False
    upcoming_changes: bool = False


class RoleIn(BaseModel):
    role: Literal["passenger", "editor", "admin"]


# ---------------------------------------------------------------- service notices
NoticeKind = Literal["DISRUPTION", "DIVERSION", "INFORMATION"]
NoticeMode = Literal["BUS", "METRO", "ALL"]


class NoticeIn(BaseModel):
    """A service notice copied from an official source. The source rules are checked in services/notices.py."""

    title: str = Field(min_length=5, max_length=120)
    body: str = Field(default="", max_length=600)
    kind: NoticeKind
    mode: NoticeMode
    source_title: str = Field(min_length=3, max_length=200)
    source_url: str = Field(max_length=500, pattern=r"^https://\S+$")
    starts_on: dt.date
    ends_on: dt.date
    reason: str = Field(min_length=3, max_length=500)


class NoticeUpdateIn(BaseModel):
    """Only the fields that are sent change. Set withdrawn to true to hide a notice at once."""

    title: str | None = Field(default=None, min_length=5, max_length=120)
    body: str | None = Field(default=None, max_length=600)
    kind: NoticeKind | None = None
    mode: NoticeMode | None = None
    source_title: str | None = Field(default=None, min_length=3, max_length=200)
    source_url: str | None = Field(default=None, max_length=500, pattern=r"^https://\S+$")
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None
    withdrawn: bool | None = None
    reason: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------- tickets and payments
# Words that would mean payment secrets. A request containing any of them is refused: this app never takes a card
# number, CVV, UPI PIN, OTP or password for a payment. Payment happens on the provider's page or in the UPI app.
SECRET_WORDS = ("pin", "cvv", "card", "otp", "password", "passcode")


def _no_secrets(value: object, depth: int = 0) -> None:
    if depth > 4:
        raise ValueError("details are nested too deeply")
    if isinstance(value, dict):
        for key, item in value.items():
            if any(word in str(key).lower() for word in SECRET_WORDS):
                raise ValueError("payment secrets are never accepted here")
            _no_secrets(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _no_secrets(item, depth + 1)


class QuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: Literal["BUS_TICKET", "BUS_PASS", "METRO_QR", "COMBINED"]
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def _small_and_secret_free(cls, value: dict[str, Any]) -> dict[str, Any]:
        _no_secrets(value)
        if len(json.dumps(value)) > 2000:
            raise ValueError("details are too long")
        return value


class OrderIn(QuoteIn):
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


class PayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["UPI", "CARD", "NETBANKING"]


class RefundIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=300)
