"""Live vehicles and arrival estimates from an operator's GTFS-Realtime feed: the provider adapter.

Nothing live is shown unless an operator's feed is configured. Until BMTC provides authorised access, every live answer
says "not connected", and the app keeps showing scheduled times under their own label. A scheduled time is never
presented as a live one.

Configuration (environment only; the access header is never logged, stored or returned):
- ``REALTIME_VEHICLES_URL``: a GTFS-Realtime VehiclePositions feed (https).
- ``REALTIME_TRIP_UPDATES_URL``: a GTFS-Realtime TripUpdates feed (https).
- ``REALTIME_AUTH_HEADER``: ``Header-Name: value`` sent with both requests, if the operator requires one.
- ``REALTIME_SOURCE_KIND``: ``OFFICIAL`` (default) or ``TEST``. A test feed is refused unless the server is a
  demonstration server (``DEMO_MODE=1``), and every screen then says the vehicles are not real.
- ``REALTIME_CLASSIFICATION``: the static timetable the feed belongs to (``OFFICIAL_VERIFIED`` by default). Trip,
  route and stop ids are matched against it.
- ``REALTIME_POLL_SECONDS`` (20) and ``REALTIME_STALE_SECONDS`` (120).

Connecting BMTC's feed later needs only those settings: a different feed format would need one new provider class
with a ``fetch() -> Feed`` method, and nothing else changes.

The feed is decoded here, without a protobuf library, for exactly the GTFS-Realtime fields the app uses.
"""

from __future__ import annotations

import datetime as dt
import logging
import struct
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import Route, Stop, StopTime, Trip
from . import schedule as sched

LOG = logging.getLogger("bmtc_planner")

KIND_OFFICIAL, KIND_TEST = "OFFICIAL", "TEST"
SOURCE_KINDS = (KIND_OFFICIAL, KIND_TEST)
MAX_FEED_BYTES = 8 * 1024 * 1024
MAX_POSITION_AGE_SECONDS = 600  # an older position is not shown at all
ARRIVAL_WINDOW_SECONDS = 2 * 3600
NEEDS = ("GTFS-Realtime VehiclePositions and TripUpdates from BMTC, matching its official static timetable, under a "
         "data-sharing agreement")

STATUS_INCOMING, STATUS_STOPPED, STATUS_IN_TRANSIT = 0, 1, 2
STATUS_NAMES = {STATUS_INCOMING: "INCOMING_AT", STATUS_STOPPED: "STOPPED_AT", STATUS_IN_TRANSIT: "IN_TRANSIT_TO"}
TRIP_CANCELED = 3
STOP_SKIPPED, STOP_NO_DATA = 1, 2


class FeedError(Exception):
    """The feed could not be read or decoded. ``code`` is shown to administrators and in the status."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------- protobuf wire format (GTFS-Realtime subset)
_VARINT, _FIXED64, _LENGTH, _FIXED32 = 0, 1, 2, 5


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if pos >= len(buf):
            raise FeedError("FEED_INVALID")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise FeedError("FEED_INVALID")


def _fields(buf: bytes) -> Iterator[tuple[int, int, Any]]:
    pos = 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise FeedError("FEED_INVALID")
        if wire == _VARINT:
            value, pos = _varint(buf, pos)
        elif wire in (_FIXED64, _FIXED32):
            size = 8 if wire == _FIXED64 else 4
            if pos + size > len(buf):
                raise FeedError("FEED_INVALID")
            value, pos = buf[pos:pos + size], pos + size
        elif wire == _LENGTH:
            length, pos = _varint(buf, pos)
            if pos + length > len(buf):
                raise FeedError("FEED_INVALID")
            value, pos = buf[pos:pos + length], pos + length
        else:
            raise FeedError("FEED_INVALID")
        yield number, wire, value


def _signed(value: int) -> int:
    return value - (1 << 64) if value >= 1 << 63 else value


def _text(value: bytes) -> str:
    return value.decode("utf-8", "replace").strip()[:200]


def _float(wire: int, value: bytes) -> float | None:
    if wire == _FIXED32:
        number = struct.unpack("<f", value)[0]
    elif wire == _FIXED64:
        number = struct.unpack("<d", value)[0]
    else:
        return None
    return number if number == number else None  # NaN is treated as missing


@dataclass
class StopUpdate:
    sequence: int | None = None
    stop_id: str = ""
    arrival_time: int | None = None
    arrival_delay: int | None = None
    departure_time: int | None = None
    departure_delay: int | None = None
    uncertainty: int | None = None
    relationship: int = 0


@dataclass
class TripUpdate:
    trip_id: str = ""
    route_id: str = ""
    direction_id: int | None = None
    start_date: str = ""
    relationship: int = 0
    vehicle_id: str = ""
    vehicle_label: str = ""
    timestamp: int | None = None
    delay: int | None = None
    stops: list[StopUpdate] = field(default_factory=list)


@dataclass
class Vehicle:
    entity_id: str = ""
    vehicle_id: str = ""
    label: str = ""
    trip_id: str = ""
    route_id: str = ""
    direction_id: int | None = None
    start_date: str = ""
    lat: float | None = None
    lon: float | None = None
    bearing: float | None = None
    speed: float | None = None
    stop_sequence: int | None = None
    stop_id: str = ""
    status: int = STATUS_IN_TRANSIT
    timestamp: int | None = None


@dataclass
class Feed:
    timestamp: int | None = None
    vehicles: list[Vehicle] = field(default_factory=list)
    trips: list[TripUpdate] = field(default_factory=list)


def _trip_descriptor(buf: bytes, into: Vehicle | TripUpdate) -> None:
    for number, wire, value in _fields(buf):
        if wire == _LENGTH and number == 1:
            into.trip_id = _text(value)
        elif wire == _LENGTH and number == 3:
            into.start_date = _text(value)
        elif wire == _VARINT and number == 4 and isinstance(into, TripUpdate):
            into.relationship = value
        elif wire == _LENGTH and number == 5:
            into.route_id = _text(value)
        elif wire == _VARINT and number == 6:
            into.direction_id = value


def _vehicle_descriptor(buf: bytes) -> tuple[str, str]:
    vid = label = ""
    for number, wire, value in _fields(buf):
        if wire == _LENGTH and number == 1:
            vid = _text(value)
        elif wire == _LENGTH and number == 2:
            label = _text(value)
    return vid, label


def _vehicle(buf: bytes, entity_id: str) -> Vehicle:
    vehicle = Vehicle(entity_id=entity_id)
    for number, wire, value in _fields(buf):
        if wire == _LENGTH and number == 1:
            _trip_descriptor(value, vehicle)
        elif wire == _LENGTH and number == 2:
            for n, w, v in _fields(value):
                number_value = _float(w, v)
                if n == 1:
                    vehicle.lat = number_value
                elif n == 2:
                    vehicle.lon = number_value
                elif n == 3:
                    vehicle.bearing = number_value
                elif n == 5:
                    vehicle.speed = number_value
        elif wire == _VARINT and number == 3:
            vehicle.stop_sequence = value
        elif wire == _VARINT and number == 4:
            vehicle.status = value
        elif wire == _VARINT and number == 5:
            vehicle.timestamp = value
        elif wire == _LENGTH and number == 7:
            vehicle.stop_id = _text(value)
        elif wire == _LENGTH and number == 8:
            vehicle.vehicle_id, vehicle.label = _vehicle_descriptor(value)
    return vehicle


def _stop_time_event(buf: bytes) -> tuple[int | None, int | None, int | None]:
    delay = time = uncertainty = None
    for number, wire, value in _fields(buf):
        if wire != _VARINT:
            continue
        if number == 1:
            delay = _signed(value)
        elif number == 2:
            time = _signed(value)
        elif number == 3:
            uncertainty = _signed(value)
    return delay, time, uncertainty


def _trip_update(buf: bytes) -> TripUpdate:
    trip = TripUpdate()
    for number, wire, value in _fields(buf):
        if wire == _LENGTH and number == 1:
            _trip_descriptor(value, trip)
        elif wire == _LENGTH and number == 2:
            update = StopUpdate()
            for n, w, v in _fields(value):
                if w == _VARINT and n == 1:
                    update.sequence = v
                elif w == _LENGTH and n == 2:
                    update.arrival_delay, update.arrival_time, update.uncertainty = _stop_time_event(v)
                elif w == _LENGTH and n == 3:
                    update.departure_delay, update.departure_time, _ = _stop_time_event(v)
                elif w == _LENGTH and n == 4:
                    update.stop_id = _text(v)
                elif w == _VARINT and n == 5:
                    update.relationship = v
            trip.stops.append(update)
        elif wire == _LENGTH and number == 3:
            trip.vehicle_id, trip.vehicle_label = _vehicle_descriptor(value)
        elif wire == _VARINT and number == 4:
            trip.timestamp = value
        elif wire == _VARINT and number == 5:
            trip.delay = _signed(value)
    return trip


def parse_feed(data: bytes) -> Feed:
    """Decode a GTFS-Realtime FeedMessage. Raises FeedError("FEED_INVALID") for anything that is not one."""
    feed = Feed()
    saw_header = False
    try:
        for number, wire, value in _fields(data):
            if number == 1 and wire == _LENGTH:
                saw_header = True
                for n, w, v in _fields(value):
                    if n == 3 and w == _VARINT:
                        feed.timestamp = v
            elif number == 2 and wire == _LENGTH:
                entity_id, deleted = "", False
                parts: list[tuple[int, bytes]] = []
                for n, w, v in _fields(value):
                    if n == 1 and w == _LENGTH:
                        entity_id = _text(v)
                    elif n == 2 and w == _VARINT:
                        deleted = bool(v)
                    elif n in (3, 4) and w == _LENGTH:
                        parts.append((n, v))
                if deleted:
                    continue
                for n, v in parts:
                    if n == 3:
                        feed.trips.append(_trip_update(v))
                    else:
                        feed.vehicles.append(_vehicle(v, entity_id))
    except (struct.error, UnicodeError) as exc:
        raise FeedError("FEED_INVALID") from exc
    if not saw_header:
        raise FeedError("FEED_INVALID")
    return feed


# ---------------------------------------------------------------- providers
class Provider(Protocol):
    def fetch(self) -> Feed: ...


def feed_url_allowed(url: str, kind: str) -> bool:
    """An official feed must use https. A test feed may also use http on this computer."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return True
    return kind == KIND_TEST and parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")


def auth_header(raw: str) -> dict[str, str]:
    name, sep, value = raw.partition(":")
    name, value = name.strip(), value.strip()
    if not sep or not name or not value or any(c in name for c in " \r\n") or any(c in value for c in "\r\n"):
        return {}
    return {name: value}


class GtfsRealtimeHttp:
    """Reads one or two GTFS-Realtime feeds over HTTPS and merges them."""

    def __init__(self, vehicles_url: str, trip_updates_url: str, headers: dict[str, str], timeout: float = 10.0):
        self.urls = [url for url in (vehicles_url, trip_updates_url) if url]
        self.headers = headers
        self.timeout = timeout

    def _get(self, url: str) -> bytes:
        # The scheme was checked by feed_url_allowed when the service started: https, or http on this computer.
        request = urllib.request.Request(url, headers={"User-Agent": "BengaluruTransitPlanner/4 realtime",  # noqa: S310
                                                       "Accept": "application/x-protobuf", **self.headers})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 # nosec B310
                data = response.read(MAX_FEED_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FeedError("FEED_UNREACHABLE") from exc
        if len(data) > MAX_FEED_BYTES:
            raise FeedError("FEED_TOO_LARGE")
        return data

    def fetch(self) -> Feed:
        merged = Feed()
        for url in self.urls:
            part = parse_feed(self._get(url))
            # The older header time is kept, so freshness is never overstated.
            if part.timestamp is not None:
                merged.timestamp = part.timestamp if merged.timestamp is None else min(merged.timestamp, part.timestamp)
            merged.vehicles.extend(part.vehicles)
            merged.trips.extend(part.trips)
        return merged


# ---------------------------------------------------------------- matching with the static timetable
class _Static:
    """Look-ups in the static timetable the feed belongs to, cached for one request."""

    def __init__(self, session: Session, classification: str) -> None:
        self.session = session
        self.import_ids = sched.eligible_import_ids(session, classification)
        self._trips: dict[str, Trip | None] = {}
        self._routes: dict[str, Route | None] = {}
        self._stops: dict[int, list[tuple[StopTime, Stop]]] = {}
        self._zones: dict[int, Any] = {}

    def trip(self, gtfs_id: str) -> Trip | None:
        if not gtfs_id or not self.import_ids:
            return None
        if gtfs_id not in self._trips:
            self._trips[gtfs_id] = self.session.scalars(
                select(Trip).where(Trip.gtfs_trip_id == gtfs_id, Trip.import_id.in_(self.import_ids))
                .order_by(Trip.import_id.desc())).first()
        return self._trips[gtfs_id]

    def route(self, gtfs_id: str) -> Route | None:
        if not gtfs_id or not self.import_ids:
            return None
        if gtfs_id not in self._routes:
            self._routes[gtfs_id] = self.session.scalars(
                select(Route).where(Route.gtfs_route_id == gtfs_id, Route.import_id.in_(self.import_ids))
                .order_by(Route.import_id.desc())).first()
        return self._routes[gtfs_id]

    def stops(self, trip: Trip) -> list[tuple[StopTime, Stop]]:
        if trip.id not in self._stops:
            rows = self.session.execute(
                select(StopTime, Stop).join(Stop, Stop.id == StopTime.stop_id)
                .where(StopTime.trip_id == trip.id).order_by(StopTime.sequence)).all()
            self._stops[trip.id] = [(row[0], row[1]) for row in rows]
        return self._stops[trip.id]

    def stop(self, gtfs_id: str) -> Stop | None:
        if not gtfs_id or not self.import_ids:
            return None
        return self.session.scalars(select(Stop).where(Stop.gtfs_stop_id == gtfs_id,
                                                       Stop.import_id.in_(self.import_ids))).first()

    def zone(self, import_id: int) -> Any:
        if import_id not in self._zones:
            self._zones[import_id] = sched.import_zone(self.session, import_id)
        return self._zones[import_id]


def _iso(epoch: int | float, zone: Any = None) -> str:
    moment = dt.datetime.fromtimestamp(epoch, dt.UTC)
    if zone is None:
        return moment.isoformat(timespec="seconds").replace("+00:00", "Z")
    return moment.astimezone(zone).isoformat(timespec="minutes")


def _service_day(start_date: str, zone: Any, now: dt.datetime) -> dt.date:
    try:
        return dt.datetime.strptime(start_date, "%Y%m%d").date()
    except ValueError:
        return clock.local_time(zone, now).date()


def _route_dict(route: Route | None) -> dict[str, Any] | None:
    if route is None:
        return None
    return {"id": route.id, "gtfs_route_id": route.gtfs_route_id, "number": route.short_name or route.gtfs_route_id,
            "name": route.long_name, "color": route.color, "route_type": route.route_type}


def _stop_index(stops: list[tuple[StopTime, Stop]], sequence: int | None, stop_id: str) -> int | None:
    for i, (stop_time, _stop) in enumerate(stops):
        if sequence is not None and stop_time.sequence == sequence:
            return i
    for i, (_stop_time, stop) in enumerate(stops):
        if stop_id and stop.gtfs_stop_id == stop_id:
            return i
    return None


def _estimates(trip_update: TripUpdate | None, stops: list[tuple[StopTime, Stop]], midnight: float
               ) -> list[tuple[int | None, int | None, str]]:
    """For each stop of the trip: (scheduled epoch, estimate epoch, kind).

    GTFS-Realtime rule: a delay given at one stop also applies to the later stops until the next update. Stops before
    the first update have no estimate and stay SCHEDULED.
    """
    by_sequence = {u.sequence: u for u in (trip_update.stops if trip_update else []) if u.sequence is not None}
    by_stop = {u.stop_id: u for u in (trip_update.stops if trip_update else []) if u.stop_id}
    delay = trip_update.delay if trip_update and trip_update.delay is not None and not trip_update.stops else None
    out: list[tuple[int | None, int | None, str]] = []
    for stop_time, stop in stops:
        seconds = stop_time.arrival_sec if stop_time.arrival_sec is not None else stop_time.departure_sec
        scheduled = int(midnight + seconds) if seconds is not None else None
        update = by_sequence.get(stop_time.sequence) or by_stop.get(stop.gtfs_stop_id)
        if update is not None:
            if update.relationship == STOP_SKIPPED:
                out.append((scheduled, None, "SKIPPED"))
                continue
            if update.relationship == STOP_NO_DATA:
                delay = None
            elif update.arrival_time is not None or update.departure_time is not None:
                when = update.arrival_time if update.arrival_time is not None else update.departure_time
                delay = when - scheduled if scheduled is not None else None
                out.append((scheduled, when, "LIVE_ESTIMATE"))
                continue
            elif update.arrival_delay is not None or update.departure_delay is not None:
                delay = update.arrival_delay if update.arrival_delay is not None else update.departure_delay
        if delay is not None and scheduled is not None:
            out.append((scheduled, scheduled + delay, "LIVE_ESTIMATE"))
        else:
            out.append((scheduled, None, "SCHEDULED"))
    return out


# ---------------------------------------------------------------- the service
class LiveService:
    def __init__(self, settings: Any, provider: Provider | None = None) -> None:
        self.kind = (settings.realtime_source_kind or KIND_OFFICIAL).upper()
        self.classification = settings.realtime_classification
        self.poll_seconds = settings.realtime_poll_seconds
        self.stale_seconds = settings.realtime_stale_seconds
        urls = [u for u in (settings.realtime_vehicles_url, settings.realtime_trip_updates_url) if u]
        self.reason: str | None = None
        self.provider: Provider | None = None
        if provider is None and not urls:
            self.reason = "NO_AUTHORISED_LIVE_FEED"
        elif self.kind not in SOURCE_KINDS:
            self.reason = "BAD_SOURCE_KIND"
        elif self.kind == KIND_TEST and not settings.demo_mode:
            self.reason = "TEST_FEED_REFUSED"
        elif provider is None and not all(feed_url_allowed(u, self.kind) for u in urls):
            self.reason = "BAD_FEED_URL"
        elif provider is None and settings.realtime_auth_header and not auth_header(settings.realtime_auth_header):
            self.reason = "BAD_AUTH_HEADER"
        else:
            self.provider = provider or GtfsRealtimeHttp(settings.realtime_vehicles_url,
                                                         settings.realtime_trip_updates_url,
                                                         auth_header(settings.realtime_auth_header))
        if self.reason and self.reason != "NO_AUTHORISED_LIVE_FEED":
            LOG.warning("The live feed is not used: %s", self.reason)
        self._lock = threading.Lock()
        self._feed: Feed | None = None
        self._fetched_at: dt.datetime | None = None
        self._tried_at: dt.datetime | None = None
        self._error: str | None = None

    @property
    def official(self) -> bool:
        return self.kind == KIND_OFFICIAL

    def snapshot(self, now: dt.datetime) -> Feed | None:
        if self.provider is None:
            return None
        with self._lock:
            if self._tried_at is None or (now - self._tried_at).total_seconds() >= self.poll_seconds:
                self._tried_at = now
                try:
                    self._feed = self.provider.fetch()
                    self._fetched_at = now
                    self._error = None
                except FeedError as exc:
                    self._error = exc.code
                    LOG.warning("The live feed could not be read: %s", exc.code)
            return self._feed

    def status(self, now: dt.datetime) -> dict[str, Any]:
        feed = self.snapshot(now)
        age = None
        if feed is not None and feed.timestamp is not None:
            age = max(0, int(now.timestamp()) - feed.timestamp)
        if self.reason == "NO_AUTHORISED_LIVE_FEED":
            state = "NOT_CONNECTED"
        elif self.reason:
            state = "REFUSED"
        elif feed is None:
            state = "ERROR"
        elif age is None or age > self.stale_seconds:
            state = "STALE"
        else:
            state = "LIVE"
        return {
            "available": feed is not None and self.reason is None,
            "state": state,
            "reason": self.reason or self._error,
            "source_kind": self.kind,
            "official": self.official,
            "classification": self.classification,
            "feed_time": _iso(feed.timestamp) if feed is not None and feed.timestamp else None,
            "feed_age_seconds": age,
            "fetched_at": self._fetched_at.isoformat(timespec="seconds").replace("+00:00", "Z")
            if self._fetched_at else None,
            "poll_seconds": self.poll_seconds,
            "stale_seconds": self.stale_seconds,
            "max_position_age_seconds": MAX_POSITION_AGE_SECONDS,
            "needs": None if self.official and feed is not None else NEEDS,
        }

    # ------------------------------------------------------------ vehicles
    def _item(self, static: _Static, vehicle: Vehicle, feed: Feed, now: dt.datetime) -> dict[str, Any] | None:
        stamp = vehicle.timestamp or feed.timestamp
        if stamp is None or vehicle.lat is None or vehicle.lon is None:
            return None
        if not (-90 <= vehicle.lat <= 90 and -180 <= vehicle.lon <= 180):
            return None
        age = max(0, int(now.timestamp()) - stamp)
        if age > MAX_POSITION_AGE_SECONDS:
            return None
        trip = static.trip(vehicle.trip_id)
        route = static.session.get(Route, trip.route_id) if trip else static.route(vehicle.route_id)
        current = following = progress = None
        headsign = trip.headsign if trip else None
        if trip is not None:
            stops = static.stops(trip)
            index = _stop_index(stops, vehicle.stop_sequence, vehicle.stop_id)
            if stops and not headsign:
                headsign = stops[-1][1].name
            if index is not None:
                if vehicle.status == STATUS_STOPPED:
                    current = stops[index][1]
                    following = stops[index + 1][1] if index + 1 < len(stops) else None
                    done = float(index)
                else:
                    current = stops[index - 1][1] if index > 0 else None
                    following = stops[index][1]
                    done = max(0.0, index - 0.5)
                span = max(1, len(stops) - 1)
                progress = {"stop_number": index + 1, "stops_total": len(stops),
                            "percent": max(0, min(100, round(100 * done / span)))}
        elif vehicle.stop_id:
            following = static.stop(vehicle.stop_id)
        return {
            "vehicle_id": vehicle.vehicle_id or vehicle.entity_id,
            "label": vehicle.label or vehicle.vehicle_id or vehicle.entity_id,
            "route": _route_dict(route),
            "trip_id": vehicle.trip_id or None,
            "headsign": headsign,
            "direction_id": vehicle.direction_id if vehicle.direction_id is not None
            else (trip.direction_id if trip else None),
            "lat": round(vehicle.lat, 6),
            "lon": round(vehicle.lon, 6),
            "bearing": round(vehicle.bearing) if vehicle.bearing is not None else None,
            "speed_kmph": round(vehicle.speed * 3.6) if vehicle.speed is not None else None,
            "status": STATUS_NAMES.get(vehicle.status, "IN_TRANSIT_TO"),
            "current_stop": {"id": current.id, "name": current.name} if current else None,
            "next_stop": {"id": following.id, "name": following.name} if following else None,
            "progress": progress,
            "matched_to_timetable": trip is not None,
            "updated_at": _iso(stamp),
            "age_seconds": age,
            "freshness": "FRESH" if age <= self.stale_seconds else "STALE",
        }

    def vehicles(self, session: Session, now: dt.datetime, route: str = "") -> dict[str, Any]:
        status = self.status(now)
        if not status["available"]:
            return {"available": False, "status": status, "vehicles": [], "hidden_old": 0}
        feed = self._feed or Feed()
        static = _Static(session, self.classification)
        wanted = route.strip().lower()
        items, hidden = [], 0
        for vehicle in feed.vehicles:
            item = self._item(static, vehicle, feed, now)
            if item is None:
                hidden += 1
                continue
            if wanted:
                info = item["route"] or {}
                keys = {str(info.get("number", "")).lower(), str(info.get("gtfs_route_id", "")).lower(),
                        str(info.get("id", "")), vehicle.route_id.lower()}
                if wanted not in keys:
                    continue
            items.append(item)
        items.sort(key=lambda i: (str((i["route"] or {}).get("number", "~")), i["age_seconds"]))
        return {"available": True, "status": status, "vehicles": items, "hidden_old": hidden}

    def vehicle(self, session: Session, now: dt.datetime, vehicle_id: str) -> dict[str, Any] | None:
        status = self.status(now)
        if not status["available"]:
            return {"available": False, "status": status}
        feed = self._feed or Feed()
        static = _Static(session, self.classification)
        for vehicle in feed.vehicles:
            if vehicle_id not in (vehicle.vehicle_id, vehicle.entity_id):
                continue
            item = self._item(static, vehicle, feed, now)
            if item is None:
                return None
            trip = static.trip(vehicle.trip_id)
            upcoming: list[dict[str, Any]] = []
            if trip is not None:
                stops = static.stops(trip)
                zone = static.zone(trip.import_id)
                day = _service_day(vehicle.start_date, zone, now)
                midnight = dt.datetime.combine(day, dt.time(0), zone).timestamp()
                update = next((t for t in feed.trips if t.trip_id == vehicle.trip_id), None)
                estimates = _estimates(update, stops, midnight)
                start = _stop_index(stops, vehicle.stop_sequence, vehicle.stop_id) or 0
                if vehicle.status == STATUS_STOPPED:
                    start += 1
                for (stop_time, stop), (scheduled, estimate, kind) in list(zip(stops, estimates, strict=True))[start:]:
                    upcoming.append({
                        "stop": {"id": stop.id, "name": stop.name}, "sequence": stop_time.sequence,
                        "scheduled": _iso(scheduled, zone) if scheduled is not None else None,
                        "estimate": _iso(estimate, zone) if estimate is not None else None,
                        "delay_seconds": (estimate - scheduled
                                          if estimate is not None and scheduled is not None else None),
                        "kind": kind,
                    })
            return {"available": True, "status": status, "vehicle": item, "upcoming": upcoming}
        return None

    # ------------------------------------------------------------ stop arrivals
    def arrivals(self, session: Session, now: dt.datetime, stop: Stop, limit: int = 20) -> dict[str, Any]:
        status = self.status(now)
        if not status["available"]:
            return {"available": False, "status": status, "arrivals": []}
        feed = self._feed or Feed()
        static = _Static(session, self.classification)
        now_s = int(now.timestamp())
        found: list[dict[str, Any]] = []
        for update in feed.trips:
            if update.relationship == TRIP_CANCELED:
                continue
            trip = static.trip(update.trip_id)
            if trip is None or trip.import_id != stop.import_id:
                continue
            stops = static.stops(trip)
            zone = static.zone(trip.import_id)
            day = _service_day(update.start_date, zone, now)
            midnight = dt.datetime.combine(day, dt.time(0), zone).timestamp()
            for (stop_time, call), (scheduled, estimate, kind) in zip(stops, _estimates(update, stops, midnight),
                                                                      strict=True):
                if call.id != stop.id or kind != "LIVE_ESTIMATE" or estimate is None:
                    continue
                if not now_s - 60 <= estimate <= now_s + ARRIVAL_WINDOW_SECONDS:
                    continue
                vehicle = next((v for v in feed.vehicles if v.trip_id == update.trip_id), None)
                found.append({
                    "route": _route_dict(session.get(Route, trip.route_id)),
                    "headsign": trip.headsign or (stops[-1][1].name if stops else None),
                    "trip_id": update.trip_id,
                    "vehicle_label": update.vehicle_label or (vehicle.label if vehicle else "") or None,
                    "estimate": _iso(estimate, zone),
                    "scheduled": _iso(scheduled, zone) if scheduled is not None else None,
                    "minutes": max(0, round((estimate - now_s) / 60)),
                    "delay_seconds": estimate - scheduled if scheduled is not None else None,
                    "prediction_age_seconds": max(0, now_s - update.timestamp) if update.timestamp else None,
                    "kind": kind,
                    "sequence": stop_time.sequence,
                })
        found.sort(key=lambda a: a["estimate"])
        return {"available": True, "status": status, "stop": {"id": stop.id, "name": stop.name},
                "arrivals": found[:limit]}
