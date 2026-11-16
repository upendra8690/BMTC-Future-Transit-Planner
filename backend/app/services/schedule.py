"""Timetable queries over imported GTFS data: coverage, operating days, search, timetables, departures and journeys.

Every query takes one classification, so official and unverified data are never mixed in a result.
Years are filtered by real feed coverage. Nothing is extended into a year the feed does not cover.
Times are reported two ways: the GTFS time as written in the feed, and the absolute local time in the feed's own
time zone. Live bus positions are never implied; every time shown here is a scheduled time.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from .. import clock
from ..models import (
    CLASS_OFFICIAL,
    STATUS_COMPLETED,
    WEEKDAYS,
    Agency,
    GtfsImport,
    Route,
    ServiceCalendar,
    ServiceException,
    ShapePoint,
    Stop,
    StopTime,
    Trip,
)
from .text import fold

EARTH_RADIUS_KM = 6371.0088
NO_OFFICIAL_MESSAGE = "No officially verified timetable is available for this future year."
LIKE_ESCAPE = "\\"
DEPARTURE_NOTE = "Scheduled times from the timetable. Live bus positions and delays are not available."
JOURNEY_NOTE = "Only direct trips are listed. Trips that need a transfer are not calculated."
FEED_STATES = ("NO_FEED", "COVERS_TODAY", "GAP_TODAY", "EXPIRED", "NOT_STARTED")


def contains_pattern(text: str) -> str:
    """A LIKE pattern meaning 'contains this text'. Use it with escape=LIKE_ESCAPE.

    % and _ typed by a user are matched literally, not treated as wildcards, so a search for "%" finds
    only names that contain a percent sign.
    """
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def fold_column(session: Session, column: Any) -> Any:
    """A case- and form-insensitive view of a text column, for comparing with fold() output.

    SQLite uses the bmtc_fold function registered on each connection. Other databases fall back to lower(), which
    folds ASCII only; PostgreSQL is not tested in this release.
    """
    if session.get_bind().dialect.name == "sqlite":
        return func.bmtc_fold(column)
    return func.lower(column)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def fmt_gtfs_time(seconds: int | None) -> str | None:
    """Format seconds since service-day start as HH:MM:SS. Hours above 24 are kept, as GTFS allows."""
    if seconds is None:
        return None
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def merge_intervals(intervals: Iterable[tuple[dt.date, dt.date]]) -> list[tuple[dt.date, dt.date]]:
    merged: list[tuple[dt.date, dt.date]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + dt.timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def eligible_import_ids(
    session: Session, classification: str, *, year: int | None = None, on_date: dt.date | None = None
) -> list[int]:
    stmt = select(GtfsImport.id).where(
        GtfsImport.classification == classification,
        GtfsImport.status == STATUS_COMPLETED,
        GtfsImport.is_active.is_(True),
    )
    if year is not None:
        stmt = stmt.where(
            GtfsImport.feed_start_date <= dt.date(year, 12, 31),
            GtfsImport.feed_end_date >= dt.date(year, 1, 1),
        )
    if on_date is not None:
        stmt = stmt.where(GtfsImport.feed_start_date <= on_date, GtfsImport.feed_end_date >= on_date)
    return list(session.scalars(stmt))


def default_today() -> dt.date:
    """Today in the default service zone, for callers that do not pass the service's own date."""
    return clock.service_date(clock.zone(clock.DEFAULT_SERVICE_TIMEZONE), clock.utc_now())


def _official_gap(period_year: int, today: dt.date, label: str) -> str:
    """Required wording for a future year. A past or current period is named instead, so it is never 'future'."""
    if period_year > today.year:
        return NO_OFFICIAL_MESSAGE
    return f"No officially verified timetable is available for {label}."


def no_official_year_message(year: int, today: dt.date) -> str:
    return _official_gap(year, today, str(year))


def no_official_date_message(on_date: dt.date, today: dt.date) -> str:
    return _official_gap(on_date.year, today, f"{on_date:%d %b %Y}")


def year_coverage(
    session: Session, classification: str, year: int, *, today: dt.date | None = None
) -> dict[str, Any]:
    year_start, year_end = dt.date(year, 1, 1), dt.date(year, 12, 31)
    rows = session.execute(
        select(GtfsImport.id, GtfsImport.feed_start_date, GtfsImport.feed_end_date).where(
            GtfsImport.classification == classification,
            GtfsImport.status == STATUS_COMPLETED,
            GtfsImport.is_active.is_(True),
            GtfsImport.feed_start_date <= year_end,
            GtfsImport.feed_end_date >= year_start,
        )
    ).all()
    clipped = [(max(start, year_start), min(end, year_end)) for _, start, end in rows]
    merged = merge_intervals(clipped)
    total_days = (year_end - year_start).days + 1
    covered_days = sum((end - start).days + 1 for start, end in merged)

    if not merged:
        status = "NONE"
    elif covered_days >= total_days:
        status = "FULL"
    else:
        status = "PARTIAL"

    if classification == CLASS_OFFICIAL:
        if status == "NONE":
            message = no_official_year_message(year, today or default_today())
        elif status == "PARTIAL":
            message = (
                f"Officially verified timetable data covers {merged[0][0]:%d %b %Y} to {merged[-1][1]:%d %b %Y} "
                "only. Dates outside that range have no verified timetable."
            )
        else:
            message = f"Officially verified timetable data covers all of {year}."
    else:
        message = {
            "NONE": f"No unverified feed covers {year}.",
            "PARTIAL": f"Unverified feed data covers only part of {year}.",
            "FULL": f"Unverified feed data covers all of {year}.",
        }[status]

    return {
        "classification": classification,
        "status": status,
        "covered_from": merged[0][0].isoformat() if merged else None,
        "covered_to": merged[-1][1].isoformat() if merged else None,
        "covered_days": covered_days,
        "days_in_year": total_days,
        "import_ids": [row[0] for row in rows],
        "message": message,
    }


def import_zone(session: Session, import_id: int) -> ZoneInfo:
    """The time zone the feed's agency declares. Imports validate it, so the fallback only covers older rows."""
    name = session.scalar(
        select(Agency.timezone).where(Agency.import_id == import_id).order_by(Agency.id).limit(1)
    )
    return clock.zone_or_none(name) or clock.zone(clock.DEFAULT_SERVICE_TIMEZONE)


def service_zone(session: Session, default_name: str) -> tuple[ZoneInfo, str]:
    """The zone for 'now' across the site: the newest active feed's agency zone, else the configured default."""
    name = session.scalar(
        select(Agency.timezone)
        .join(GtfsImport, GtfsImport.id == Agency.import_id)
        .where(GtfsImport.status == STATUS_COMPLETED, GtfsImport.is_active.is_(True))
        .order_by(GtfsImport.id.desc(), Agency.id)
        .limit(1)
    )
    found = clock.zone_or_none(name)
    if found is not None:
        return found, "feed"
    return clock.zone(default_name), "default"


def feed_status(session: Session, classification: str, today: dt.date) -> dict[str, Any]:
    """Whether the feeds of one classification cover the service's current date."""
    rows = session.execute(
        select(GtfsImport.feed_start_date, GtfsImport.feed_end_date).where(
            GtfsImport.classification == classification,
            GtfsImport.status == STATUS_COMPLETED,
            GtfsImport.is_active.is_(True),
        )
    ).all()
    if not rows:
        state = "NO_FEED"
    elif any(start <= today <= end for start, end in rows):
        state = "COVERS_TODAY"
    elif all(end < today for _, end in rows):
        state = "EXPIRED"
    elif all(start > today for start, _ in rows):
        state = "NOT_STARTED"
    else:
        state = "GAP_TODAY"
    earliest = min((start for start, _ in rows), default=None)
    latest = max((end for _, end in rows), default=None)
    return {
        "classification": classification,
        "state": state,
        "covers_today": state == "COVERS_TODAY",
        "imports": len(rows),
        "earliest_start": earliest.isoformat() if earliest else None,
        "latest_end": latest.isoformat() if latest else None,
    }


def active_service_ids(session: Session, import_id: int, day: dt.date) -> set[str]:
    """Services running on a date: weekday flags within the calendar window, plus calendar_dates exceptions."""
    weekday_column = getattr(ServiceCalendar, WEEKDAYS[day.weekday()])
    active = set(
        session.scalars(
            select(ServiceCalendar.service_id).where(
                ServiceCalendar.import_id == import_id,
                ServiceCalendar.start_date <= day,
                ServiceCalendar.end_date >= day,
                weekday_column == 1,
            )
        )
    )
    exceptions = session.execute(
        select(ServiceException.service_id, ServiceException.exception_type).where(
            ServiceException.import_id == import_id,
            ServiceException.date == day,
        )
    ).all()
    for service_id, exception_type in exceptions:
        if exception_type == 1:
            active.add(service_id)
        elif exception_type == 2:
            active.discard(service_id)
    return active


def route_operating_days(session: Session, route: Route) -> list[str]:
    service_ids = set(session.scalars(select(Trip.service_id).where(Trip.route_id == route.id).distinct()))
    if not service_ids:
        return []
    rows = session.execute(
        select(*(func.max(getattr(ServiceCalendar, day)) for day in WEEKDAYS)).where(
            ServiceCalendar.import_id == route.import_id,
            ServiceCalendar.service_id.in_(service_ids),
        )
    ).one()
    return [code for code, flag in zip(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"), rows, strict=True) if flag]


def search_routes(
    session: Session, classification: str, *, year: int | None, query: str, limit: int
) -> list[dict[str, Any]]:
    import_ids = eligible_import_ids(session, classification, year=year)
    if not import_ids:
        return []
    stmt = select(Route, GtfsImport.feed_start_date, GtfsImport.feed_end_date).join(
        GtfsImport, GtfsImport.id == Route.import_id
    ).where(Route.import_id.in_(import_ids))
    term = fold(query)
    if term:
        like = contains_pattern(term)
        stmt = stmt.where(
            or_(
                fold_column(session, Route.short_name).like(like, escape=LIKE_ESCAPE),
                fold_column(session, Route.long_name).like(like, escape=LIKE_ESCAPE),
                fold_column(session, Route.gtfs_route_id) == term,
            )
        )
    stmt = stmt.order_by(Route.short_name, Route.gtfs_route_id).limit(limit)
    return [
        {
            "id": route.id,
            "import_id": route.import_id,
            "classification": classification,
            "gtfs_route_id": route.gtfs_route_id,
            "short_name": route.short_name,
            "long_name": route.long_name,
            "route_type": route.route_type,
            "feed_start_date": start.isoformat() if start else None,
            "feed_end_date": end.isoformat() if end else None,
        }
        for route, start, end in session.execute(stmt).all()
    ]


def search_stops(
    session: Session, classification: str, *, year: int | None, query: str, limit: int
) -> list[dict[str, Any]]:
    import_ids = eligible_import_ids(session, classification, year=year)
    if not import_ids:
        return []
    term = fold(query)
    stmt = select(Stop).where(Stop.import_id.in_(import_ids))
    if term:
        stmt = stmt.where(
            fold_column(session, Stop.name).like(contains_pattern(term), escape=LIKE_ESCAPE)
            | (fold_column(session, Stop.gtfs_stop_id) == term)
        )
    stmt = stmt.order_by(Stop.name).limit(limit)
    return [stop_dict(stop, classification) for stop in session.scalars(stmt)]


def stop_dict(stop: Stop, classification: str) -> dict[str, Any]:
    return {
        "id": stop.id,
        "import_id": stop.import_id,
        "classification": classification,
        "gtfs_stop_id": stop.gtfs_stop_id,
        "name": stop.name,
        "lat": stop.lat,
        "lon": stop.lon,
    }


def nearby_stops(
    session: Session, classification: str, *, lat: float, lon: float, radius_m: int, limit: int
) -> list[dict[str, Any]]:
    import_ids = eligible_import_ids(session, classification)
    if not import_ids:
        return []
    radius_km = radius_m / 1000.0
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    candidates = session.scalars(
        select(Stop).where(
            Stop.import_id.in_(import_ids),
            Stop.lat.is_not(None),
            Stop.lon.is_not(None),
            Stop.lat.between(lat - dlat, lat + dlat),
            Stop.lon.between(lon - dlon, lon + dlon),
        )
    ).all()
    scored = []
    for stop in candidates:
        distance = haversine_km(lat, lon, stop.lat, stop.lon) * 1000
        if distance <= radius_m:
            item = stop_dict(stop, classification)
            item["distance_m"] = round(distance)
            scored.append(item)
    scored.sort(key=lambda item: item["distance_m"])
    return scored[:limit]


def route_detail(session: Session, route: Route, classification: str) -> dict[str, Any]:
    """Stops for each direction, from the trip with the most stops in that direction.

    The shape is included when the feed provides one.
    """
    counts = session.execute(
        select(Trip.id, Trip.direction_id, Trip.shape_id, Trip.headsign, func.count(StopTime.id))
        .join(StopTime, StopTime.trip_id == Trip.id)
        .where(Trip.route_id == route.id)
        .group_by(Trip.id, Trip.direction_id, Trip.shape_id, Trip.headsign)
    ).all()
    best: dict[Any, tuple[int, int, str | None, str | None]] = {}
    for trip_id, direction, shape_id, headsign, stop_count in counts:
        current = best.get(direction)
        if current is None or stop_count > current[1]:
            best[direction] = (trip_id, stop_count, shape_id, headsign)

    directions = []
    for direction in sorted(best, key=lambda d: (d is None, d)):
        trip_id, stop_count, shape_id, headsign = best[direction]
        rows = session.execute(
            select(
                StopTime.sequence, StopTime.arrival_sec, StopTime.departure_sec,
                Stop.id, Stop.name, Stop.lat, Stop.lon,
            )
            .join(Stop, Stop.id == StopTime.stop_id)
            .where(StopTime.trip_id == trip_id)
            .order_by(StopTime.sequence)
        ).all()
        directions.append(
            {
                "direction_id": direction,
                "headsign": headsign,
                "representative_trip_id": trip_id,
                "stop_count": stop_count,
                "stops": [
                    {
                        "sequence": seq,
                        "stop_id": stop_pk,
                        "name": name,
                        "lat": lat,
                        "lon": lon,
                        "arrival": fmt_gtfs_time(arr),
                        "departure": fmt_gtfs_time(dep),
                    }
                    for seq, arr, dep, stop_pk, name, lat, lon in rows
                ],
                "shape_id": shape_id,
            }
        )

    shape_points = []
    shape_ids = {d["shape_id"] for d in directions if d["shape_id"]}
    for shape_id in shape_ids:
        points = session.execute(
            select(ShapePoint.lat, ShapePoint.lon)
            .where(ShapePoint.import_id == route.import_id, ShapePoint.gtfs_shape_id == shape_id)
            .order_by(ShapePoint.sequence)
        ).all()
        shape_points.append({"shape_id": shape_id, "points": [[lat, lon] for lat, lon in points]})

    return {
        "id": route.id,
        "import_id": route.import_id,
        "classification": classification,
        "gtfs_route_id": route.gtfs_route_id,
        "short_name": route.short_name,
        "long_name": route.long_name,
        "route_type": route.route_type,
        "operating_days": route_operating_days(session, route),
        "directions": directions,
        "shapes": shape_points,
        "geometry_note": (
            "Route path from the feed's shapes.txt. It shows the planned path, not the bus's live position."
            if shape_points
            else "The feed has no shape geometry for this route. Only stop locations are shown."
        ),
    }


def route_timetable(session: Session, route: Route, classification: str, on_date: dt.date) -> dict[str, Any]:
    result: dict[str, Any] = {
        "route_id": route.id,
        "classification": classification,
        "date": on_date.isoformat(),
        "covered": True,
        "trips": [],
        "first_departure": None,
        "last_arrival": None,
        "message": None,
        "message_code": None,
    }
    services = active_service_ids(session, route.import_id, on_date)
    if not services:
        result["message"] = "No service operates on this date according to the feed."
        result["message_code"] = "NO_SERVICE"
        return result

    rows = session.execute(
        select(
            Trip.id, Trip.headsign, Trip.direction_id,
            StopTime.sequence, StopTime.arrival_sec, StopTime.departure_sec, Stop.name,
        )
        .join(StopTime, StopTime.trip_id == Trip.id)
        .join(Stop, Stop.id == StopTime.stop_id)
        .where(Trip.route_id == route.id, Trip.service_id.in_(services))
        .order_by(Trip.id, StopTime.sequence)
    ).all()

    trips: dict[int, dict[str, Any]] = {}
    for trip_id, headsign, direction, seq, arr, dep, name in rows:
        trip = trips.setdefault(
            trip_id,
            {"trip_id": trip_id, "headsign": headsign, "direction_id": direction, "_sort": None, "stops": []},
        )
        first_time = dep if dep is not None else arr
        if trip["_sort"] is None and first_time is not None:
            trip["_sort"] = first_time
        trip["stops"].append(
            {"sequence": seq, "stop": name, "arrival": fmt_gtfs_time(arr), "departure": fmt_gtfs_time(dep)}
        )

    ordered = sorted(trips.values(), key=lambda t: (t["_sort"] if t["_sort"] is not None else 10**9, t["trip_id"]))
    for trip in ordered:
        stops = trip["stops"]
        trip["first_departure"] = stops[0]["departure"] or stops[0]["arrival"]
        trip["last_arrival"] = stops[-1]["arrival"] or stops[-1]["departure"]
        trip["first_departure_seconds"] = trip.pop("_sort")
    result["trips"] = ordered
    if ordered:
        result["first_departure"] = ordered[0]["first_departure"]
        result["last_arrival"] = max((t["last_arrival"] for t in ordered if t["last_arrival"]), default=None)
    else:
        result["message"] = "The feed lists no trips for this route on this date."
        result["message_code"] = "NO_TRIPS"
    return result


def _journey_row(
    *, zone: ZoneInfo, day: dt.date, now: dt.datetime | None, classification: str, values: tuple[Any, ...]
) -> tuple[dt.datetime, dict[str, Any]] | None:
    dep, arr, o_seq, d_seq, trip_id, headsign, short, long_name, gtfs_route, o_nm, d_nm = values
    if arr < dep:  # the feed says the bus arrives before it leaves; never show a negative journey
        return None
    instant = clock.departure_instant(zone, day, dep)
    item = {
        "classification": classification,
        "trip_id": trip_id,
        "route_number": short or gtfs_route,
        "route_name": long_name,
        "headsign": headsign,
        "origin_stop": o_nm,
        "destination_stop": d_nm,
        "service_date": day.isoformat(),
        "departure": fmt_gtfs_time(dep),
        "arrival": fmt_gtfs_time(arr),
        "departure_local": clock.local_time(zone, instant).isoformat(timespec="seconds"),
        "next_day": clock.is_next_day(zone, day, instant),
        "minutes_from_now": None if now is None else clock.whole_minutes_between(now, instant),
        "duration_minutes": round((arr - dep) / 60),
        "intermediate_stops": max(d_seq - o_seq - 1, 0),
    }
    return instant, item


def _no_data_code(classification: str) -> str:
    return "NO_OFFICIAL_DATA" if classification == CLASS_OFFICIAL else "NO_UNVERIFIED_DATA"


def direct_journeys(
    session: Session,
    classification: str,
    *,
    origin_query: str,
    destination_query: str,
    on_date: dt.date | None = None,
    not_before: dt.datetime | None = None,
    today: dt.date | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Direct trips (no transfers) that call at a matching origin stop before a matching destination stop.

    Give on_date to list one service date, or not_before to list trips leaving at or after that moment ("leave now").
    Each result is in the feed's own time zone and carries how many minutes away it leaves.
    """
    if (on_date is None) == (not_before is None):
        raise ValueError("Give either on_date or not_before, not both and not neither.")
    now = clock.as_utc(not_before) if not_before is not None else None
    result: dict[str, Any] = {
        "classification": classification,
        "mode": "date" if now is None else "now",
        "date": on_date.isoformat() if on_date is not None else None,
        "origin_query": origin_query,
        "destination_query": destination_query,
        "journeys": [],
        "message": None,
        "message_code": None,
        "note": JOURNEY_NOTE,
        "skipped_invalid": 0,
    }
    origin_key, destination_key = fold(origin_query), fold(destination_query)
    if not origin_key or not destination_key:
        result["message"] = "Enter a name for both the origin and the destination."
        result["message_code"] = "NEED_BOTH_STOPS"
        return result

    if now is None:
        import_ids = eligible_import_ids(session, classification, on_date=on_date)
    else:
        import_ids = eligible_import_ids(session, classification)
    if not import_ids:
        if now is None:
            result["message"] = (
                no_official_date_message(on_date, today or default_today())
                if classification == CLASS_OFFICIAL
                else "No unverified feed covers this date."
            )
        else:
            result["message"] = (
                "No officially verified timetable is loaded." if classification == CLASS_OFFICIAL
                else "No unverified feed is loaded."
            )
        result["message_code"] = _no_data_code(classification)
        return result

    origin_term = contains_pattern(origin_key)
    destination_term = contains_pattern(destination_key)
    found: list[tuple[dt.datetime, dict[str, Any]]] = []
    o_stop = aliased(StopTime)
    d_stop = aliased(StopTime)
    o_name = aliased(Stop)
    d_name = aliased(Stop)

    for import_id in import_ids:
        zone = import_zone(session, import_id)
        days = [on_date] if now is None else clock.candidate_service_dates(zone, now)
        origin_ids = list(session.scalars(select(Stop.id).where(
            Stop.import_id == import_id, fold_column(session, Stop.name).like(origin_term, escape=LIKE_ESCAPE))))
        destination_ids = list(session.scalars(select(Stop.id).where(
            Stop.import_id == import_id, fold_column(session, Stop.name).like(destination_term, escape=LIKE_ESCAPE))))
        if not origin_ids or not destination_ids:
            continue
        for day in days:
            services = active_service_ids(session, import_id, day)
            if not services:
                continue
            stmt = (
                select(
                    o_stop.departure_sec, d_stop.arrival_sec, o_stop.sequence, d_stop.sequence,
                    Trip.id, Trip.headsign, Route.short_name, Route.long_name, Route.gtfs_route_id,
                    o_name.name, d_name.name,
                )
                .select_from(o_stop)
                .join(d_stop, and_(d_stop.trip_id == o_stop.trip_id, d_stop.sequence > o_stop.sequence))
                .join(Trip, Trip.id == o_stop.trip_id)
                .join(Route, Route.id == Trip.route_id)
                .join(o_name, o_name.id == o_stop.stop_id)
                .join(d_name, d_name.id == d_stop.stop_id)
                .where(
                    o_stop.import_id == import_id,
                    o_stop.stop_id.in_(origin_ids),
                    d_stop.stop_id.in_(destination_ids),
                    Trip.service_id.in_(services),
                    o_stop.departure_sec.is_not(None),
                    d_stop.arrival_sec.is_not(None),
                )
            )
            if now is not None:
                stmt = stmt.where(o_stop.departure_sec >= clock.seconds_into_service_day(zone, day, now))
            stmt = stmt.order_by(o_stop.departure_sec).limit(limit)
            for values in session.execute(stmt).all():
                row = _journey_row(zone=zone, day=day, now=now, classification=classification, values=values)
                if row is None:
                    result["skipped_invalid"] += 1
                else:
                    found.append(row)

    found.sort(key=lambda pair: (pair[0], pair[1]["route_number"] or ""))
    result["journeys"] = [item for _, item in found[:limit]]
    if not result["journeys"]:
        result["message"] = (
            "No direct service found in this classification's timetable for that date."
            if now is None
            else "No direct service is scheduled from this stop pair in the coming service days."
        )
        result["message_code"] = "NO_DIRECT_SERVICE"
    return result


def stop_departures(
    session: Session, stop: Stop, classification: str, *, now: dt.datetime, limit: int = 20
) -> dict[str, Any]:
    """The next scheduled departures from one stop, earliest first.

    The search covers the service days from the lookback to the days ahead (see clock.candidate_service_dates).
    A trip that ends at this stop is not listed, even when the feed gives it a time there.
    """
    zone = import_zone(session, stop.import_id)
    upcoming: list[tuple[dt.datetime, dict[str, Any]]] = []
    later_stop = aliased(StopTime)
    # A stop time with no later stop in its trip is the trip's last stop: the bus ends there and does not leave.
    has_later_stop = (
        select(later_stop.id)
        .where(later_stop.trip_id == StopTime.trip_id, later_stop.sequence > StopTime.sequence)
        .exists()
    )
    for day in clock.candidate_service_dates(zone, now):
        services = active_service_ids(session, stop.import_id, day)
        if not services:
            continue
        rows = session.execute(
            select(
                StopTime.departure_sec, Trip.id, Trip.headsign,
                Route.short_name, Route.long_name, Route.gtfs_route_id,
            )
            .join(Trip, Trip.id == StopTime.trip_id)
            .join(Route, Route.id == Trip.route_id)
            .where(
                StopTime.import_id == stop.import_id,
                StopTime.stop_id == stop.id,
                StopTime.departure_sec.is_not(None),
                StopTime.departure_sec >= clock.seconds_into_service_day(zone, day, now),
                Trip.service_id.in_(services),
                has_later_stop,
            )
            .order_by(StopTime.departure_sec)
            .limit(limit)
        ).all()
        for dep, trip_id, headsign, short, long_name, gtfs_route in rows:
            instant = clock.departure_instant(zone, day, dep)
            upcoming.append((
                instant,
                {
                    "trip_id": trip_id,
                    "route_number": short or gtfs_route,
                    "route_name": long_name,
                    "headsign": headsign,
                    "service_date": day.isoformat(),
                    "gtfs_time": fmt_gtfs_time(dep),
                    "departure_local": clock.local_time(zone, instant).isoformat(timespec="seconds"),
                    "next_day": clock.is_next_day(zone, day, instant),
                    "minutes_from_now": clock.whole_minutes_between(now, instant),
                    "live": False,
                },
            ))
    upcoming.sort(key=lambda pair: (pair[0], pair[1]["route_number"] or ""))
    departures = [item for _, item in upcoming[:limit]]
    return {
        "classification": classification,
        "stop": stop_dict(stop, classification),
        "service_timezone": zone.key,
        "now_local": clock.local_time(zone, now).isoformat(timespec="seconds"),
        "departures": departures,
        "message": None if departures else "No scheduled departures from this stop in the coming service days.",
        "message_code": None if departures else "NO_DEPARTURES",
        "note": DEPARTURE_NOTE,
    }


def stop_has_timetable(session: Session, stop: Stop) -> bool:
    return session.scalar(select(func.count(StopTime.id)).where(StopTime.stop_id == stop.id)) > 0


def database_counts(session: Session) -> dict[str, int]:
    from ..models import AuditLog, DataSource, Scenario

    return {
        "data_sources": session.scalar(select(func.count(DataSource.id))) or 0,
        "imports_completed": (
            session.scalar(select(func.count(GtfsImport.id)).where(GtfsImport.status == STATUS_COMPLETED)) or 0
        ),
        "imports_rejected": (
            session.scalar(select(func.count(GtfsImport.id)).where(GtfsImport.status != STATUS_COMPLETED)) or 0
        ),
        "routes": session.scalar(select(func.count(Route.id))) or 0,
        "stops": session.scalar(select(func.count(Stop.id))) or 0,
        "trips": session.scalar(select(func.count(Trip.id))) or 0,
        "stop_times": session.scalar(select(func.count(StopTime.id))) or 0,
        "shape_points": session.scalar(select(func.count(ShapePoint.id))) or 0,
        "scenarios": session.scalar(select(func.count(Scenario.id))) or 0,
        "audit_entries": session.scalar(select(func.count(AuditLog.id))) or 0,
    }


# ---------------------------------------------------------------- 4.0: routes at a stop, Metro stations

METRO_ROUTE_TYPES = (1, 400, 401, 402, 403, 404, 405)


def stop_routes(session: Session, stop: Stop, classification: str) -> dict[str, Any]:
    """Every route that calls at this stop in the feed, with the directions (headsigns) it runs towards."""
    rows = session.execute(
        select(Route.id, Route.short_name, Route.long_name, Route.gtfs_route_id, Route.route_type, Route.color,
               Trip.headsign)
        .join(Trip, Trip.route_id == Route.id)
        .join(StopTime, StopTime.trip_id == Trip.id)
        .where(StopTime.stop_id == stop.id)
        .distinct()
    ).all()
    routes: dict[int, dict[str, Any]] = {}
    for route_id, short, long_name, gtfs_route, route_type, color, headsign in rows:
        entry = routes.setdefault(route_id, {
            "id": route_id,
            "route_number": short or gtfs_route,
            "route_name": long_name,
            "route_type": route_type,
            "color": color,
            "towards": [],
        })
        if headsign and headsign not in entry["towards"] and headsign != stop.name:
            entry["towards"].append(headsign)
    result = sorted(routes.values(), key=lambda r: (r["route_number"] or "", r["id"]))
    for entry in result:
        entry["towards"].sort()
    return {
        "classification": classification,
        "stop": stop_dict(stop, classification),
        "routes": result,
        "message_code": None if result else "NO_TRIPS",
    }


def metro_stations(session: Session, classification: str, *, query: str, limit: int) -> dict[str, Any]:
    """Stops served by a Metro route (GTFS route_type 1 and the extended urban-rail types), with their lines."""
    import_ids = eligible_import_ids(session, classification)
    if not import_ids:
        return {"classification": classification, "stations": [], "message_code": _no_data_code(classification)}
    stmt = (
        select(Stop, Route.id, Route.short_name, Route.gtfs_route_id, Route.color)
        .join(StopTime, StopTime.stop_id == Stop.id)
        .join(Trip, Trip.id == StopTime.trip_id)
        .join(Route, Route.id == Trip.route_id)
        .where(Stop.import_id.in_(import_ids), Route.route_type.in_(METRO_ROUTE_TYPES))
        .distinct()
        .order_by(Stop.name)
    )
    term = fold(query)
    if term:
        stmt = stmt.where(fold_column(session, Stop.name).like(contains_pattern(term), escape=LIKE_ESCAPE))
    stations: dict[int, dict[str, Any]] = {}
    for stop, route_id, short, gtfs_route, color in session.execute(stmt).all():
        entry = stations.get(stop.id)
        if entry is None:
            if len(stations) >= limit:
                continue
            entry = stations[stop.id] = {**stop_dict(stop, classification), "lines": []}
        if not any(line["id"] == route_id for line in entry["lines"]):
            entry["lines"].append({"id": route_id, "route_number": short or gtfs_route, "color": color})
    result = list(stations.values())
    return {"classification": classification, "stations": result,
            "message_code": None if result else "NO_METRO_STATIONS"}
