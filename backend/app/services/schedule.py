"""Timetable queries over imported GTFS data: year coverage, operating days, search, timetables and direct journeys.

Every query takes one classification, so official and unverified data are never mixed in a result.
Years are filtered by real feed coverage. Nothing is extended into a year the feed does not cover.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..models import (
    CLASS_OFFICIAL,
    STATUS_COMPLETED,
    WEEKDAYS,
    GtfsImport,
    Route,
    ServiceCalendar,
    ServiceException,
    ShapePoint,
    Stop,
    StopTime,
    Trip,
)

EARTH_RADIUS_KM = 6371.0088
NO_OFFICIAL_MESSAGE = "No officially verified timetable is available for this future year."
LIKE_ESCAPE = "\\"


def contains_pattern(text: str) -> str:
    """A LIKE pattern meaning 'contains this text'. Use it with escape=LIKE_ESCAPE.

    % and _ typed by a user are matched literally, not treated as wildcards, so a search for "%" finds
    only names that contain a percent sign.
    """
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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


def year_coverage(session: Session, classification: str, year: int) -> dict[str, Any]:
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
            message = NO_OFFICIAL_MESSAGE
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
    term = query.strip().lower()
    if term:
        like = contains_pattern(term)
        stmt = stmt.where(
            or_(
                func.lower(Route.short_name).like(like, escape=LIKE_ESCAPE),
                func.lower(Route.long_name).like(like, escape=LIKE_ESCAPE),
                func.lower(Route.gtfs_route_id) == term,
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
    term = query.strip().lower()
    stmt = select(Stop).where(Stop.import_id.in_(import_ids))
    if term:
        stmt = stmt.where(
            func.lower(Stop.name).like(contains_pattern(term), escape=LIKE_ESCAPE)
            | (func.lower(Stop.gtfs_stop_id) == term)
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
    }
    services = active_service_ids(session, route.import_id, on_date)
    if not services:
        result["message"] = "No service operates on this date according to the feed."
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
        trip.pop("_sort", None)
    result["trips"] = ordered
    if ordered:
        result["first_departure"] = ordered[0]["first_departure"]
        result["last_arrival"] = max((t["last_arrival"] for t in ordered if t["last_arrival"]), default=None)
    else:
        result["message"] = "The feed lists no trips for this route on this date."
    return result


def direct_journeys(
    session: Session,
    classification: str,
    *,
    origin_query: str,
    destination_query: str,
    on_date: dt.date,
    limit: int = 50,
) -> dict[str, Any]:
    """Direct trips (no transfers) that call at a matching origin stop before a matching destination stop."""
    import_ids = eligible_import_ids(session, classification, on_date=on_date)
    result: dict[str, Any] = {
        "classification": classification,
        "date": on_date.isoformat(),
        "origin_query": origin_query,
        "destination_query": destination_query,
        "journeys": [],
        "message": None,
        "note": "Only direct trips are listed. Trips that need a transfer are not calculated.",
    }
    if not import_ids:
        result["message"] = (
            NO_OFFICIAL_MESSAGE if classification == CLASS_OFFICIAL
            else "No unverified feed covers this date."
        )
        return result

    if not origin_query.strip() or not destination_query.strip():
        result["message"] = "Enter a name for both the origin and the destination."
        return result
    origin_term = contains_pattern(origin_query.strip().lower())
    destination_term = contains_pattern(destination_query.strip().lower())
    journeys: list[dict[str, Any]] = []
    o_stop = aliased(StopTime)
    d_stop = aliased(StopTime)
    o_name = aliased(Stop)
    d_name = aliased(Stop)

    for import_id in import_ids:
        services = active_service_ids(session, import_id, on_date)
        if not services:
            continue
        origin_ids = list(session.scalars(select(Stop.id).where(
            Stop.import_id == import_id, func.lower(Stop.name).like(origin_term, escape=LIKE_ESCAPE))))
        destination_ids = list(session.scalars(select(Stop.id).where(
            Stop.import_id == import_id, func.lower(Stop.name).like(destination_term, escape=LIKE_ESCAPE))))
        if not origin_ids or not destination_ids:
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
            .order_by(o_stop.departure_sec)
            .limit(limit)
        )
        journey_rows = session.execute(stmt)
        for dep, arr, o_seq, d_seq, trip_id, headsign, short, long_name, gtfs_route, o_nm, d_nm in journey_rows:
            journeys.append(
                {
                    "classification": classification,
                    "trip_id": trip_id,
                    "route_number": short or gtfs_route,
                    "route_name": long_name,
                    "headsign": headsign,
                    "origin_stop": o_nm,
                    "destination_stop": d_nm,
                    "departure": fmt_gtfs_time(dep),
                    "arrival": fmt_gtfs_time(arr),
                    "duration_minutes": round((arr - dep) / 60),
                    "intermediate_stops": max(d_seq - o_seq - 1, 0),
                }
            )
    journeys.sort(key=lambda j: (j["departure"] or "", j["route_number"] or ""))
    result["journeys"] = journeys[:limit]
    if not journeys:
        result["message"] = "No direct service found in this classification's timetable for that date."
    return result


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
