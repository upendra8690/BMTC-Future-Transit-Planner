"""Future scenario planner: owner-scoped CRUD, a transparent estimate and side-by-side comparison.

A scenario is a proposal. It is always labelled ESTIMATED_SCENARIO and is never written into the
official or unverified timetable tables.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import CLASS_OFFICIAL, CLASS_SCENARIO, Route, Scenario, ScenarioStop
from ..schemas import ScenarioIn, minutes_of_day
from .schedule import eligible_import_ids, haversine_km

SCENARIO_NOTICE = (
    "ESTIMATED SCENARIO: an illustrative proposal only. It is not an official BMTC announcement "
    "and no timetable has been confirmed."
)


def scenario_payload(scenario: Scenario) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "year": scenario.year,
        "route_code": scenario.route_code,
        "description": scenario.description,
        "classification": CLASS_SCENARIO,
        "origin": {"name": scenario.origin_name, "lat": scenario.origin_lat, "lon": scenario.origin_lon},
        "destination": {
            "name": scenario.destination_name,
            "lat": scenario.destination_lat,
            "lon": scenario.destination_lon,
        },
        "stops": [{"sequence": s.sequence, "name": s.name, "lat": s.lat, "lon": s.lon} for s in scenario.stops],
        "first_departure": scenario.first_departure,
        "last_departure": scenario.last_departure,
        "frequency_minutes": scenario.frequency_minutes,
        "operating_days": [d for d in scenario.operating_days.split(",") if d],
        "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
        "updated_at": scenario.updated_at.isoformat() if scenario.updated_at else None,
        "notice": SCENARIO_NOTICE,
    }


def estimate_scenario(
    payload: dict[str, Any], *, avg_speed_kmph: float, dwell_minutes: float, detour_factor: float
) -> dict[str, Any]:
    """Estimate distance, journey time and frequency from the scenario's own numbers and labelled assumptions."""
    chain = [payload["origin"], *payload["stops"], payload["destination"]]
    coords_known = all(point.get("lat") is not None and point.get("lon") is not None for point in chain)

    distance_km: float | None = None
    if coords_known:
        straight = sum(
            haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in pairwise(chain)
        )
        distance_km = round(straight * detour_factor, 2)

    stops_between = len(payload["stops"])
    journey_minutes: int | None = None
    if distance_km is not None and avg_speed_kmph > 0:
        journey_minutes = round(distance_km / avg_speed_kmph * 60 + stops_between * dwell_minutes)

    first = minutes_of_day(payload["first_departure"])
    last = minutes_of_day(payload["last_departure"])
    per_day = (last - first) // payload["frequency_minutes"] + 1
    return {
        "classification": CLASS_SCENARIO,
        "estimated_distance_km": distance_km,
        "estimated_journey_minutes": journey_minutes,
        "stops_between": stops_between,
        "departures_per_day": per_day,
        "departures_per_week": per_day * len(payload["operating_days"]),
        "span_minutes": last - first,
        "assumptions": {
            "average_bus_speed_kmph": avg_speed_kmph,
            "stop_dwell_minutes": dwell_minutes,
            "road_detour_factor": detour_factor,
            "method": (
                "Straight-line distance between the given points, multiplied by the detour factor, "
                "divided by the average speed, plus dwell time per intermediate stop. "
                "These are placeholder assumptions to be calibrated, not measured data."
            ),
        },
        "missing": None
        if coords_known
        else "Add coordinates for the origin, destination and every stop to estimate distance and journey time.",
        "notice": SCENARIO_NOTICE,
    }


def compare_payloads(
    a_payload: dict[str, Any], a_est: dict[str, Any], b_payload: dict[str, Any], b_est: dict[str, Any]
) -> dict[str, Any]:
    def difference(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else round(b - a, 2)

    return {
        "classification": CLASS_SCENARIO,
        "a": {"scenario": a_payload, "estimate": a_est},
        "b": {"scenario": b_payload, "estimate": b_est},
        "difference_b_minus_a": {
            "estimated_distance_km": difference(a_est["estimated_distance_km"], b_est["estimated_distance_km"]),
            "estimated_journey_minutes": difference(
                a_est["estimated_journey_minutes"], b_est["estimated_journey_minutes"]
            ),
            "departures_per_day": difference(a_est["departures_per_day"], b_est["departures_per_day"]),
            "departures_per_week": difference(a_est["departures_per_week"], b_est["departures_per_week"]),
        },
        "notice": SCENARIO_NOTICE,
    }


def _apply(scenario: Scenario, data: ScenarioIn) -> None:
    scenario.name = data.name.strip()
    scenario.year = data.year
    scenario.route_code = data.route_code.strip()
    scenario.description = (data.description or "").strip() or None
    scenario.origin_name = data.origin_name.strip()
    scenario.origin_lat, scenario.origin_lon = data.origin_lat, data.origin_lon
    scenario.destination_name = data.destination_name.strip()
    scenario.destination_lat, scenario.destination_lon = data.destination_lat, data.destination_lon
    scenario.first_departure = data.first_departure
    scenario.last_departure = data.last_departure
    scenario.frequency_minutes = data.frequency_minutes
    scenario.operating_days = ",".join(data.operating_days)
    scenario.stops.clear()
    for number, stop in enumerate(data.stops, start=1):
        scenario.stops.append(ScenarioStop(sequence=number, name=stop.name.strip(), lat=stop.lat, lon=stop.lon))


def create_scenario(session: Session, data: ScenarioIn, owner: str) -> Scenario:
    scenario = Scenario(owner_hash=owner, status=CLASS_SCENARIO)
    _apply(scenario, data)
    session.add(scenario)
    session.flush()
    return scenario


def update_scenario(session: Session, scenario: Scenario, data: ScenarioIn) -> Scenario:
    _apply(scenario, data)
    session.flush()
    return scenario


def get_owned(session: Session, scenario_id: int, owner: str) -> Scenario:
    scenario = session.get(Scenario, scenario_id)
    # Same message for "missing" and "belongs to someone else", so ids cannot be probed.
    if scenario is None or scenario.owner_hash != owner:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return scenario


def list_owned(session: Session, owner: str, year: int | None) -> list[Scenario]:
    stmt = (
        select(Scenario)
        .where(Scenario.owner_hash == owner)
        .order_by(Scenario.year, Scenario.route_code, Scenario.id)
    )
    if year is not None:
        stmt = stmt.where(Scenario.year == year)
    return list(session.scalars(stmt))


def official_route_warning(session: Session, route_code: str, year: int) -> str | None:
    import_ids = eligible_import_ids(session, CLASS_OFFICIAL, year=year)
    if not import_ids:
        return None
    exists = session.scalar(
        select(Route.id)
        .where(Route.import_id.in_(import_ids), func.lower(Route.short_name) == route_code.strip().lower())
        .limit(1)
    )
    if exists is None:
        return None
    return (
        f"A verified route numbered '{route_code}' exists in the {year} official data. "
        "This scenario is a separate proposal and does not change that route."
    )


def settings_estimate(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return estimate_scenario(
        payload,
        avg_speed_kmph=settings.avg_bus_speed_kmph,
        dwell_minutes=settings.stop_dwell_minutes,
        detour_factor=settings.detour_factor,
    )
