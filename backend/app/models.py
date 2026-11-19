"""ORM models: data sources, GTFS imports and their timetable tables, future scenarios, user data and audit logs."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Three data classifications. They are never mixed in one result set.
CLASS_OFFICIAL = "OFFICIAL_VERIFIED"
CLASS_UNVERIFIED = "UNVERIFIED_FEED"
CLASS_SCENARIO = "ESTIMATED_SCENARIO"
DATA_CLASSIFICATIONS = (CLASS_OFFICIAL, CLASS_UNVERIFIED)

KIND_OFFICIAL = "OFFICIAL"
KIND_COMMUNITY = "COMMUNITY"
KIND_SYNTHETIC = "SYNTHETIC_DEMO"
KIND_UNKNOWN = "UNKNOWN"
SOURCE_KINDS = (KIND_OFFICIAL, KIND_COMMUNITY, KIND_SYNTHETIC, KIND_UNKNOWN)

STATUS_COMPLETED = "COMPLETED"
STATUS_REJECTED = "REJECTED"

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")

# BigInteger for large stop_times tables on PostgreSQL; plain INTEGER on SQLite so autoincrement works.
BIG_ID = BigInteger().with_variant(Integer(), "sqlite")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    publisher: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    license: Mapped[str] = mapped_column(String(200), default="Not specified")
    kind: Mapped[str] = mapped_column(String(30), default=KIND_UNKNOWN)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    imports: Mapped[list[GtfsImport]] = relationship(back_populates="data_source")


class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(20))  # VERIFIED or REVOKED
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class GtfsImport(Base):
    __tablename__ = "gtfs_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), index=True)
    classification: Mapped[str] = mapped_column(String(30), index=True)
    agency_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    feed_start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    feed_end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    route_count: Mapped[int] = mapped_column(Integer, default=0)
    stop_count: Mapped[int] = mapped_column(Integer, default=0)
    trip_count: Mapped[int] = mapped_column(Integer, default=0)
    stop_time_count: Mapped[int] = mapped_column(Integer, default=0)
    shape_point_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    warnings: Mapped[str] = mapped_column(Text, default="[]")
    errors: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    data_source: Mapped[DataSource] = relationship(back_populates="imports")


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    gtfs_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(100))


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    gtfs_route_id: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    long_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    route_type: Mapped[int] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    text_color: Mapped[str | None] = mapped_column(String(10), nullable=True)

    __table_args__ = (Index("ix_routes_import_gtfs", "import_id", "gtfs_route_id"),)


class Stop(Base):
    __tablename__ = "stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    gtfs_stop_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200), index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_type: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("ix_stops_import_gtfs", "import_id", "gtfs_stop_id"),)


class ServiceCalendar(Base):
    __tablename__ = "service_calendars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str] = mapped_column(String(100))
    mon: Mapped[int] = mapped_column(Integer, default=0)
    tue: Mapped[int] = mapped_column(Integer, default=0)
    wed: Mapped[int] = mapped_column(Integer, default=0)
    thu: Mapped[int] = mapped_column(Integer, default=0)
    fri: Mapped[int] = mapped_column(Integer, default=0)
    sat: Mapped[int] = mapped_column(Integer, default=0)
    sun: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date] = mapped_column(Date)

    __table_args__ = (Index("ix_calendar_import_service", "import_id", "service_id"),)


class ServiceException(Base):
    """calendar_dates.txt rows: exception_type 1 adds service on a date, 2 removes it."""

    __tablename__ = "service_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str] = mapped_column(String(100))
    date: Mapped[dt.date] = mapped_column(Date)
    exception_type: Mapped[int] = mapped_column(Integer)

    __table_args__ = (Index("ix_exceptions_import_date", "import_id", "date"),)


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), index=True)
    gtfs_trip_id: Mapped[str] = mapped_column(String(100))
    gtfs_route_id: Mapped[str] = mapped_column(String(100))
    service_id: Mapped[str] = mapped_column(String(100))
    headsign: Mapped[str | None] = mapped_column(String(200), nullable=True)
    direction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shape_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("ix_trips_import_gtfs", "import_id", "gtfs_trip_id"),
        Index("ix_trips_import_service", "import_id", "service_id"),
    )


class StopTime(Base):
    __tablename__ = "stop_times"

    id: Mapped[int] = mapped_column(BIG_ID, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"))
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    stop_id: Mapped[int] = mapped_column(ForeignKey("stops.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    arrival_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    departure_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stop_headsign: Mapped[str | None] = mapped_column(String(200), nullable=True)

    __table_args__ = (
        Index("ix_stop_times_trip_seq", "trip_id", "sequence"),
        Index("ix_stop_times_stop", "stop_id"),
        Index("ix_stop_times_import_stop", "import_id", "stop_id"),
    )


class ShapePoint(Base):
    __tablename__ = "shape_points"

    id: Mapped[int] = mapped_column(BIG_ID, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    gtfs_shape_id: Mapped[str] = mapped_column(String(100))
    sequence: Mapped[int] = mapped_column(Integer)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)

    __table_args__ = (Index("ix_shape_import_shape_seq", "import_id", "gtfs_shape_id", "sequence"),)


class FareAttribute(Base):
    """A row of a GTFS fare_attributes.txt file. The price is kept exactly as the feed wrote it."""

    __tablename__ = "fare_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    fare_id: Mapped[str] = mapped_column(String(100))
    price: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    payment_method: Mapped[int] = mapped_column(Integer)  # 0 = on board, 1 = before boarding
    transfers: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = not stated in the feed

    __table_args__ = (Index("ix_fare_attributes_import_fare", "import_id", "fare_id"),)


class FareRule(Base):
    """A row of a GTFS fare_rules.txt file. Only rules without origin, destination or zone limits give route fares."""

    __tablename__ = "fare_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("gtfs_imports.id", ondelete="CASCADE"), index=True)
    fare_id: Mapped[str] = mapped_column(String(100))
    route_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    origin_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    destination_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contains_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (Index("ix_fare_rules_import_route", "import_id", "route_id"),)


class Scenario(Base):
    """A proposed, illustrative service. Always ESTIMATED_SCENARIO; never an official announcement."""

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_hash: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(120))
    year: Mapped[int] = mapped_column(Integer, index=True)
    route_code: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_name: Mapped[str] = mapped_column(String(200))
    origin_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_name: Mapped[str] = mapped_column(String(200))
    destination_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_departure: Mapped[str] = mapped_column(String(5))
    last_departure: Mapped[str] = mapped_column(String(5))
    frequency_minutes: Mapped[int] = mapped_column(Integer)
    operating_days: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default=CLASS_SCENARIO)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    stops: Mapped[list[ScenarioStop]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="ScenarioStop.sequence",
    )


class ScenarioStop(Base):
    __tablename__ = "scenario_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    scenario: Mapped[Scenario] = relationship(back_populates="stops")


class SavedRoute(Base):
    __tablename__ = "saved_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_hash: Mapped[str] = mapped_column(String(64), index=True)
    classification: Mapped[str] = mapped_column(String(30))
    gtfs_route_id: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("client_hash", "classification", "gtfs_route_id", name="uq_saved_route"),)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_hash: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("client_hash", "key", name="uq_user_pref"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TransportAnnouncement(Base):
    """An upcoming-transport entry: information only, never read by the journey planner.

    Administrators add and update entries through the API, so no code change is needed when a project's status
    changes. Each change is kept in ``changes`` with its reason.
    """

    __tablename__ = "transport_announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    transport_type: Mapped[str] = mapped_column(String(40))
    location: Mapped[str] = mapped_column(String(300), default="")
    announcement: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40))
    source_kind: Mapped[str] = mapped_column(String(20))
    # Partial ISO dates (YYYY, YYYY-MM or YYYY-MM-DD); opened_on is always a full date.
    announced_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    expected_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    opened_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sources_json: Mapped[str] = mapped_column(Text)
    verified_on: Mapped[str] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    changes: Mapped[list[TransportAnnouncementChange]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan",
        order_by="TransportAnnouncementChange.id.desc()",
    )


class TransportAnnouncementChange(Base):
    """One change to an upcoming-transport entry: who, when, why, and each field's old and new value."""

    __tablename__ = "transport_announcement_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    announcement_id: Mapped[int] = mapped_column(
        ForeignKey("transport_announcements.id", ondelete="CASCADE"), index=True
    )
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    changes_json: Mapped[str] = mapped_column(Text)

    announcement: Mapped[TransportAnnouncement] = relationship(back_populates="changes")


# ---------------------------------------------------------------- service notices (written by administrators)
NOTICE_KINDS = ("DISRUPTION", "DIVERSION", "INFORMATION")
NOTICE_MODES = ("BUS", "METRO", "ALL")


class ServiceNotice(Base):
    """A short service notice written by an administrator from an official source, shown until its end date.

    It is information only: the journey planner never reads it. Every notice links to the official source it repeats,
    and ends within a month. Withdrawing a notice hides it at once; it is kept, with the audit log, as a record.
    """

    __tablename__ = "service_notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(10))
    source_title: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))
    starts_on: Mapped[dt.date] = mapped_column(Date)
    ends_on: Mapped[dt.date] = mapped_column(Date, index=True)
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- passenger accounts (off unless storage is permanent)
ROLE_PASSENGER, ROLE_EDITOR, ROLE_ADMIN = "passenger", "editor", "admin"
ROLES = (ROLE_PASSENGER, ROLE_EDITOR, ROLE_ADMIN)


class User(Base):
    """A passenger or staff account. Only a salted scrypt hash of the password is stored, never the password."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_PASSENGER)
    recovery_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class UserSession(Base):
    """A signed-in session. The token is given to the browser once; only its SHA-256 hash is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)


class UserSavedJourney(Base):
    """A journey saved to an account, so it follows the passenger to another device."""

    __tablename__ = "user_saved_journeys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    origin: Mapped[str] = mapped_column(String(80))
    destination: Mapped[str] = mapped_column(String(80))
    modes: Mapped[str] = mapped_column(String(10), default="all")
    classification: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class NotificationPreference(Base):
    """What a passenger would like to be told about. Stored only: no notification is sent (no delivery service)."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    service_notices: Mapped[bool] = mapped_column(Boolean, default=False)
    upcoming_changes: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
