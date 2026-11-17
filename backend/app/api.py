"""REST API.

Public, read-only:      timetables, routes, stops, journeys, year coverage, data sources.
Owner-scoped (device):  scenarios, saved routes, preferences. Identified by an X-Client-Key header.
Administrative:         data sources and verification, GTFS upload, imports, stats, backups, audit log.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi import Path as ApiPath
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from . import clock
from .gtfs.importer import classification_for_source, fare_counts, import_feed, import_summary
from .models import (
    CLASS_OFFICIAL,
    CLASS_SCENARIO,
    CLASS_UNVERIFIED,
    DATA_CLASSIFICATIONS,
    STATUS_COMPLETED,
    WEEKDAY_CODES,
    AuditLog,
    DataSource,
    GtfsImport,
    Route,
    SavedRoute,
    Scenario,
    Stop,
    UserPreference,
    utcnow,
)
from .schemas import (
    PLANNING_YEARS,
    AnnouncementIn,
    AnnouncementUpdateIn,
    DataSourceIn,
    PreferencesIn,
    SavedRouteIn,
    ScenarioIn,
    VerificationIn,
)
from .security import client_ip, optional_client_hash, require_admin, require_client_key, safe_filename
from .services import announcements, assistant, catalogue, integrations, planner, registry
from .services import scenarios as scn
from .services import schedule as sched
from .services.audit import record_audit
from .services.exports import comparison_pdf, scenario_pdf, scenarios_csv, timetable_csv
from .services.maintenance import MaintenanceError, backup_and_verify, sqlite_file
from .services.verification import VerificationError, set_verification

router = APIRouter()

APP_VERSION = "4.0.0-beta.1"


def get_db(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.db.session()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]
YearQuery = Annotated[int | None, Query(ge=2000, le=2100)]


def _classification(value: str) -> str:
    if value not in DATA_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail="classification must be OFFICIAL_VERIFIED or UNVERIFIED_FEED. Scenarios use their own endpoints.",
        )
    return value


def _active_import(db: Session, import_id: int) -> GtfsImport | None:
    imp = db.get(GtfsImport, import_id)
    if imp is None or imp.status != STATUS_COMPLETED or not imp.is_active:
        return None
    return imp


def _route_or_404(db: Session, route_id: int) -> tuple[Route, GtfsImport]:
    route = db.get(Route, route_id)
    imp = _active_import(db, route.import_id) if route is not None else None
    if route is None or imp is None:
        raise HTTPException(status_code=404, detail="Route not found.")
    return route, imp


def _no_timetable_message(classification: str, on_date: dt.date, today: dt.date) -> str:
    if classification == CLASS_OFFICIAL:
        return sched.no_official_date_message(on_date, today)
    return "No unverified feed covers this date."


def _service_today(request: Request, db: Session) -> dt.date:
    """The service's own calendar date. The timetable means this when it says 'today'."""
    zone, _source = sched.service_zone(db, request.app.state.settings.service_timezone)
    return clock.service_date(zone, clock.utc_now())


def _public_source(db: Session, source: DataSource) -> dict[str, Any]:
    completed = db.scalar(
        select(func.count(GtfsImport.id)).where(
            GtfsImport.data_source_id == source.id, GtfsImport.status == STATUS_COMPLETED
        )
    )
    return {
        "id": source.id,
        "name": source.name,
        "publisher": source.publisher,
        "source_url": source.source_url,
        "license": source.license,
        "kind": source.kind,
        "verified": source.verified,
        "verified_at": source.verified_at.isoformat() if source.verified_at else None,
        "classification": classification_for_source(source),
        "completed_imports": completed or 0,
    }


def _scenario_response(scenario: Scenario, request: Request, warnings: list[str] | None = None) -> dict[str, Any]:
    settings = request.app.state.settings
    payload = scn.scenario_payload(scenario)
    body = {**payload, "estimate": scn.settings_estimate(payload, settings)}
    if warnings:
        body["warnings"] = warnings
    return body


# ---------------------------------------------------------------- health and metadata

@router.get("/health", tags=["system"])
def health(db: DbSession) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok", "time_utc": utcnow().isoformat() + "Z"}


@router.get("/clock", tags=["system"])
def service_clock(request: Request, db: DbSession) -> dict[str, Any]:
    """The service area's local time, its service date, and whether each kind of feed covers that date.

    The time zone comes from the imported feed's agency, so the same code serves any GTFS feed in the world.
    """
    settings = request.app.state.settings
    now = clock.utc_now()
    zone, source = sched.service_zone(db, settings.service_timezone)
    local = clock.local_time(zone, now)
    today = local.date()
    return {
        "now_utc": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "service_timezone": zone.key,
        "timezone_source": source,
        "now_local": local.isoformat(timespec="seconds"),
        "service_date": today.isoformat(),
        "weekday": WEEKDAY_CODES[today.weekday()],
        "feeds": [sched.feed_status(db, cls, today) for cls in DATA_CLASSIFICATIONS],
        "note": "Scheduled times only. Live bus positions and delays are not available.",
    }


@router.get("/meta", tags=["system"])
def meta(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "name": "Bengaluru Transit Planner",
        "version": APP_VERSION,
        "unofficial": True,
        "affiliation": (
            "Not affiliated with, endorsed by or authorised by BMTC, BMRCL, Namma Metro or any transport operator."
        ),
        "live_positions_available": False,
        "live_positions_note": (
            "No verified real-time feed is connected, so no live bus or train positions are shown. "
            "Every time is scheduled."
        ),
        "journey_assumptions": {
            "min_change_minutes": settings.min_transfer_minutes,
            "max_walk_m": settings.max_transfer_walk_m,
            "walk_speed_kmph": settings.walk_speed_kmph,
            "max_changes": planner.MAX_CHANGES_LIMIT,
        },
        "planning_years": list(PLANNING_YEARS),
        "classifications": {
            CLASS_OFFICIAL: "Data confirmed through an authoritative source and verified by an administrator.",
            CLASS_UNVERIFIED: "Data from a third-party, community or unverified feed.",
            CLASS_SCENARIO: "Proposed or simulated future services. Not officially confirmed.",
        },
        "scenario_notice": scn.SCENARIO_NOTICE,
        "estimate_assumptions": {
            "average_bus_speed_kmph": settings.avg_bus_speed_kmph,
            "stop_dwell_minutes": settings.stop_dwell_minutes,
            "road_detour_factor": settings.detour_factor,
        },
        "admin_enabled": bool(settings.admin_api_key),
    }


@router.get("/features", tags=["system"])
def features(request: Request, db: DbSession) -> dict[str, Any]:
    """What works right now. States: AVAILABLE, NO_DATA, UNAVAILABLE (needs an authorisation), PLANNED."""
    return {"version": APP_VERSION, "demo_mode": request.app.state.settings.demo_mode,
            "features": catalogue.feature_states(db)}


@router.get("/services", tags=["system"])
def services() -> dict[str, Any]:
    """Official websites and public helplines, each checked on the stated date. Links only; nothing is booked here."""
    return catalogue.services_directory()


@router.get("/upcoming", tags=["system"])
def upcoming_transport(db: DbSession) -> dict[str, Any]:
    """Upcoming transport: status information only, kept in the database and updated by administrators."""
    return announcements.list_entries(db)


_REQUIRED_WHEN_SENT = ("name", "transport_type", "status", "source_kind", "sources", "verified_on")


@router.post("/admin/upcoming", status_code=201, tags=["admin"])
def admin_create_upcoming(data: AnnouncementIn, request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request)
    values = data.model_dump(exclude={"id", "reason"})
    try:
        return announcements.create(db, data.id, values, reason=data.reason, actor="admin", ip=client_ip(request),
                                    today=_service_today(request, db))
    except announcements.AnnouncementError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.patch("/admin/upcoming/{key}", tags=["admin"])
def admin_update_upcoming(
    key: Annotated[str, ApiPath(pattern=r"^[a-z0-9_]{2,60}$")], data: AnnouncementUpdateIn, request: Request,
    db: DbSession,
) -> dict[str, Any]:
    require_admin(request)
    changes: dict[str, Any] = {}
    for field in sorted(data.model_fields_set - {"reason"}):
        value = getattr(data, field)
        if value is None and field in _REQUIRED_WHEN_SENT:
            raise HTTPException(status_code=422, detail=f"{field} cannot be empty.")
        if field == "sources":
            value = [source.model_dump() for source in data.sources or []]
        changes[field] = "" if value is None and field in ("location", "announcement", "note") else value
    try:
        return announcements.update(db, key, changes, reason=data.reason, actor="admin", ip=client_ip(request),
                                    today=_service_today(request, db))
    except announcements.AnnouncementError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/providers", tags=["system"])
def provider_registry(db: DbSession) -> dict[str, Any]:
    """Every outside data source or service: licence, permission status, integration status and limitations."""
    return registry.providers(db)


@router.get("/data-status", tags=["system"])
def data_freshness(request: Request, db: DbSession) -> dict[str, Any]:
    """Each active feed and whether its calendar covers today (CURRENT, EXPIRED, NOT_STARTED, UNKNOWN_DATES)."""
    return registry.data_status(db, _service_today(request, db))


@router.get("/integrations", tags=["system"])
def integration_status() -> dict[str, Any]:
    """Provider integrations (live vehicles, tickets, passes, Metro QR, payments, NCMC) and what each one needs."""
    return integrations.status()


@router.post("/integrations/{capability}/request", tags=["system"])
def integration_request(capability: str = ApiPath(..., pattern="^[a-z_]{2,40}$")) -> JSONResponse:
    """The single entry point for provider actions. With no authorised provider it always refuses with 503 and the
    official channel; it never returns a ticket, QR code, receipt, balance, payment result or vehicle position."""
    try:
        integrations.adapter(capability).request()
    except integrations.IntegrationUnavailableError as err:
        status_code = 404 if err.code == "UNKNOWN_CAPABILITY" else 503
        return JSONResponse(
            status_code=status_code,
            content={"detail": "This feature needs an authorised provider that is not connected.",
                     "capability": err.capability, "code": err.code, "official_url": err.official_url},
        )
    raise HTTPException(status_code=500, detail="Integration adapter returned without refusing.")


@router.get("/assistant", tags=["system"])
def assistant_interpret(q: str = Query(..., min_length=1, max_length=assistant.MAX_QUESTION)) -> dict[str, Any]:
    """Which of the app's own data requests answers a typed question. Rule-based; it never writes an answer."""
    result = assistant.interpret(q)
    result["engine"] = "rules"
    return result


# ---------------------------------------------------------------- years

@router.get("/years/compare", tags=["years"])
def compare_years(request: Request, db: DbSession) -> dict[str, Any]:
    owner = optional_client_hash(request)
    today = _service_today(request, db)
    years = []
    for year in PLANNING_YEARS:
        own = 0
        if owner:
            own = (
                db.scalar(
                    select(func.count(Scenario.id)).where(Scenario.year == year, Scenario.owner_hash == owner)
                )
                or 0
            )
        years.append(
            {
                "year": year,
                "official": sched.year_coverage(db, CLASS_OFFICIAL, year, today=today),
                "unverified": sched.year_coverage(db, CLASS_UNVERIFIED, year, today=today),
                "your_scenarios": own,
            }
        )
    return {"years": years, "scenario_notice": scn.SCENARIO_NOTICE}


@router.get("/years/{year}/status", tags=["years"])
def year_status(year: Annotated[int, ApiPath(ge=2000, le=2100)], request: Request, db: DbSession) -> dict[str, Any]:
    today = _service_today(request, db)
    return {
        "year": year,
        "is_planning_year": year in PLANNING_YEARS,
        "is_future": year > today.year,
        "official": sched.year_coverage(db, CLASS_OFFICIAL, year, today=today),
        "unverified": sched.year_coverage(db, CLASS_UNVERIFIED, year, today=today),
    }


# ---------------------------------------------------------------- routes, stops, timetables, journeys

@router.get("/routes", tags=["timetables"])
def search_routes(
    request: Request,
    db: DbSession,
    classification: str = Query(CLASS_OFFICIAL),
    year: YearQuery = None,
    q: str = Query("", max_length=80),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    cls = _classification(classification)
    return {
        "classification": cls,
        "year": year,
        "coverage": sched.year_coverage(db, cls, year, today=_service_today(request, db)) if year else None,
        "results": sched.search_routes(db, cls, year=year, query=q, limit=limit),
    }


@router.get("/routes/{route_id}", tags=["timetables"])
def route_detail(route_id: int, db: DbSession) -> dict[str, Any]:
    route, imp = _route_or_404(db, route_id)
    return sched.route_detail(db, route, imp.classification)


@router.get("/routes/{route_id}/timetable", tags=["timetables"])
def route_timetable(
    route_id: int, request: Request, db: DbSession, on_date: dt.date = Query(..., alias="date")
) -> dict[str, Any]:
    route, imp = _route_or_404(db, route_id)
    result = sched.route_timetable(db, route, imp.classification, on_date)
    covered = bool(imp.feed_start_date and imp.feed_end_date and imp.feed_start_date <= on_date <= imp.feed_end_date)
    result["covered"] = covered
    result["coverage_from"] = imp.feed_start_date.isoformat() if imp.feed_start_date else None
    result["coverage_to"] = imp.feed_end_date.isoformat() if imp.feed_end_date else None
    if not covered:
        result["message"] = _no_timetable_message(imp.classification, on_date, _service_today(request, db))
        result["message_code"] = "NOT_COVERED"
        result["trips"] = []
    return result


@router.get("/routes/{route_id}/timetable.csv", tags=["timetables"])
def route_timetable_csv(
    route_id: int, request: Request, db: DbSession, on_date: dt.date = Query(..., alias="date")
) -> Response:
    route, imp = _route_or_404(db, route_id)
    timetable = sched.route_timetable(db, route, imp.classification, on_date)
    if not (imp.feed_start_date and imp.feed_end_date and imp.feed_start_date <= on_date <= imp.feed_end_date):
        raise HTTPException(
            status_code=404,
            detail=_no_timetable_message(imp.classification, on_date, _service_today(request, db)),
        )
    body = timetable_csv({"short_name": route.short_name, "gtfs_route_id": route.gtfs_route_id}, timetable)
    filename = f"timetable_{route.short_name or route.gtfs_route_id}_{on_date.isoformat()}_{imp.classification}.csv"
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename(filename)}"'},
    )


@router.get("/stops", tags=["timetables"])
def search_stops(
    db: DbSession,
    classification: str = Query(CLASS_OFFICIAL),
    year: YearQuery = None,
    q: str = Query("", max_length=80),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    cls = _classification(classification)
    stops_found = sched.search_stops(db, cls, year=year, query=q, limit=limit)
    return {"classification": cls, "year": year, "results": stops_found}


@router.get("/stops/nearby", tags=["timetables"])
def nearby(
    db: DbSession,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(800, ge=50, le=5000),
    classification: str = Query(CLASS_OFFICIAL),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    cls = _classification(classification)
    return {
        "classification": cls,
        "origin": {"lat": lat, "lon": lon},
        "radius_m": radius_m,
        "results": sched.nearby_stops(db, cls, lat=lat, lon=lon, radius_m=radius_m, limit=limit),
    }


@router.get("/stops/{stop_id}/departures", tags=["timetables"])
def stop_departures(
    stop_id: int,
    db: DbSession,
    classification: str = Query(CLASS_OFFICIAL),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """The next scheduled departures from one stop, from the current moment in the feed's time zone."""
    cls = _classification(classification)
    stop = db.get(Stop, stop_id)
    imp = _active_import(db, stop.import_id) if stop is not None else None
    if stop is None or imp is None or imp.classification != cls:
        raise HTTPException(status_code=404, detail="Stop not found in this classification's data.")
    return sched.stop_departures(db, stop, cls, now=clock.utc_now(), limit=limit)


@router.get("/stops/{stop_id}/routes", tags=["timetables"])
def stop_routes(
    stop_id: int,
    db: DbSession,
    classification: str = Query(CLASS_OFFICIAL),
) -> dict[str, Any]:
    """Every route that calls at this stop, with the places it runs towards."""
    cls = _classification(classification)
    stop = db.get(Stop, stop_id)
    imp = _active_import(db, stop.import_id) if stop is not None else None
    if stop is None or imp is None or imp.classification != cls:
        raise HTTPException(status_code=404, detail="Stop not found in this classification's data.")
    return sched.stop_routes(db, stop, cls)


@router.get("/metro/stations", tags=["timetables"])
def metro_stations(
    db: DbSession,
    classification: str = Query(CLASS_OFFICIAL),
    q: str = Query("", max_length=80),
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    """Stations served by Metro routes (GTFS route_type 1 and urban-rail types), with the lines at each."""
    return sched.metro_stations(db, _classification(classification), query=q, limit=limit)


@router.get("/journey", tags=["timetables"])
def journey(
    request: Request,
    db: DbSession,
    origin: str = Query(..., min_length=2, max_length=80),
    destination: str = Query(..., min_length=2, max_length=80),
    on_date: dt.date | None = Query(None, alias="date", description="Leave out to list trips leaving from now."),
    classification: str = Query(CLASS_OFFICIAL),
) -> dict[str, Any]:
    cls = _classification(classification)
    today = _service_today(request, db)
    if on_date is None:
        result = sched.direct_journeys(
            db, cls, origin_query=origin, destination_query=destination, not_before=clock.utc_now(), today=today
        )
    else:
        result = sched.direct_journeys(
            db, cls, origin_query=origin, destination_query=destination, on_date=on_date, today=today
        )
    zone, source = sched.service_zone(db, request.app.state.settings.service_timezone)
    result["service_timezone"] = zone.key
    result["timezone_source"] = source
    return result


@router.get("/plan", tags=["timetables"])
def plan_journey(
    request: Request,
    db: DbSession,
    origin: str = Query(..., min_length=2, max_length=80),
    destination: str = Query(..., min_length=2, max_length=80),
    on_date: dt.date | None = Query(None, alias="date", description="Leave out to plan the next three hours from now."),
    classification: str = Query(CLASS_OFFICIAL),
    max_changes: int = Query(planner.DEFAULT_MAX_CHANGES, ge=0, le=planner.MAX_CHANGES_LIMIT),
    limit: int = Query(5, ge=1, le=10),
    modes: str = Query("all", pattern="^(all|bus|metro)$", description="all, bus (buses only) or metro (Metro only)."),
) -> dict[str, Any]:
    """Journey options with up to two changes, across every feed of one classification.

    Each option lists its legs in order: rides with their route, stops and times, and walks between stops. Every ride
    names the feed it comes from. Times are scheduled times; live positions are never shown.
    """
    cls = _classification(classification)
    settings = request.app.state.settings
    return planner.plan_journeys(
        db,
        cls,
        origin_query=origin,
        destination_query=destination,
        default_zone=settings.service_timezone,
        plan=planner.PlanSettings.from_settings(settings),
        max_changes=max_changes,
        limit=limit,
        on_date=on_date,
        now=None if on_date is not None else clock.utc_now(),
        travel_modes=modes,
    )


@router.get("/data-sources", tags=["sources"])
def public_data_sources(db: DbSession) -> dict[str, Any]:
    sources = db.scalars(select(DataSource).order_by(DataSource.id)).all()
    return {"sources": [_public_source(db, source) for source in sources]}


# ---------------------------------------------------------------- scenarios (owner-scoped)

@router.get("/scenarios", tags=["scenarios"])
def list_scenarios(
    request: Request, db: DbSession, year: Annotated[int | None, Query(ge=2027, le=2030)] = None
) -> dict[str, Any]:
    owner = optional_client_hash(request)
    if owner is None:
        return {
            "scenarios": [],
            "message": "Send your X-Client-Key header to see your scenarios.",
            "notice": scn.SCENARIO_NOTICE,
        }
    scenarios = scn.list_owned(db, owner, year)
    return {"scenarios": [_scenario_response(s, request) for s in scenarios], "notice": scn.SCENARIO_NOTICE}


@router.post("/scenarios", status_code=201, tags=["scenarios"])
def create_scenario(data: ScenarioIn, request: Request, db: DbSession) -> dict[str, Any]:
    owner = require_client_key(request)
    scenario = scn.create_scenario(db, data, owner)
    warning = scn.official_route_warning(db, data.route_code, data.year)
    record_audit(db, actor=f"device:{owner[:12]}", action="scenario.create", entity="scenario",
                 entity_id=scenario.id, detail={"year": data.year, "route_code": data.route_code},
                 ip=client_ip(request))
    db.commit()
    return _scenario_response(scenario, request, [warning] if warning else None)


@router.get("/scenarios/compare", tags=["scenarios"])
def compare_two(
    request: Request,
    db: DbSession,
    a: int = Query(...),
    b: int = Query(...),
) -> dict[str, Any]:
    owner = require_client_key(request)
    first = scn.get_owned(db, a, owner)
    second = scn.get_owned(db, b, owner)
    settings = request.app.state.settings
    p_a, p_b = scn.scenario_payload(first), scn.scenario_payload(second)
    e_a = scn.settings_estimate(p_a, settings)
    e_b = scn.settings_estimate(p_b, settings)
    return scn.compare_payloads(p_a, e_a, p_b, e_b)


@router.get("/scenarios/export.csv", tags=["scenarios"])
def export_scenarios_csv(
    request: Request, db: DbSession, year: Annotated[int | None, Query(ge=2027, le=2030)] = None
) -> Response:
    owner = require_client_key(request)
    rows = []
    for scenario in scn.list_owned(db, owner, year):
        payload = scn.scenario_payload(scenario)
        rows.append((payload, scn.settings_estimate(payload, request.app.state.settings)))
    body = scenarios_csv(rows)
    filename = f"estimated_scenarios_{year or 'all'}.csv"
    return Response(content=body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/scenarios/compare.pdf", tags=["scenarios"])
def export_compare_pdf(request: Request, db: DbSession, a: int = Query(...), b: int = Query(...)) -> Response:
    owner = require_client_key(request)
    settings = request.app.state.settings
    p_a = scn.scenario_payload(scn.get_owned(db, a, owner))
    p_b = scn.scenario_payload(scn.get_owned(db, b, owner))
    comparison = scn.compare_payloads(
        p_a, scn.settings_estimate(p_a, settings), p_b, scn.settings_estimate(p_b, settings)
    )
    return Response(content=comparison_pdf(comparison, font_path=settings.pdf_font_path), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="estimated_scenario_comparison.pdf"'})


@router.get("/scenarios/{scenario_id}", tags=["scenarios"])
def get_scenario(scenario_id: int, request: Request, db: DbSession) -> dict[str, Any]:
    owner = require_client_key(request)
    return _scenario_response(scn.get_owned(db, scenario_id, owner), request)


@router.put("/scenarios/{scenario_id}", tags=["scenarios"])
def update_scenario(scenario_id: int, data: ScenarioIn, request: Request, db: DbSession) -> dict[str, Any]:
    owner = require_client_key(request)
    scenario = scn.get_owned(db, scenario_id, owner)
    scn.update_scenario(db, scenario, data)
    warning = scn.official_route_warning(db, data.route_code, data.year)
    record_audit(db, actor=f"device:{owner[:12]}", action="scenario.update", entity="scenario",
                 entity_id=scenario.id, detail={"year": data.year, "route_code": data.route_code},
                 ip=client_ip(request))
    db.commit()
    return _scenario_response(scenario, request, [warning] if warning else None)


@router.delete("/scenarios/{scenario_id}", status_code=204, tags=["scenarios"])
def delete_scenario(scenario_id: int, request: Request, db: DbSession) -> Response:
    owner = require_client_key(request)
    scenario = scn.get_owned(db, scenario_id, owner)
    db.delete(scenario)
    record_audit(db, actor=f"device:{owner[:12]}", action="scenario.delete", entity="scenario",
                 entity_id=scenario_id, ip=client_ip(request))
    db.commit()
    return Response(status_code=204)


@router.get("/scenarios/{scenario_id}/export.pdf", tags=["scenarios"])
def export_scenario_pdf(scenario_id: int, request: Request, db: DbSession) -> Response:
    owner = require_client_key(request)
    payload = scn.scenario_payload(scn.get_owned(db, scenario_id, owner))
    estimate = scn.settings_estimate(payload, request.app.state.settings)
    return Response(content=scenario_pdf(payload, estimate, font_path=request.app.state.settings.pdf_font_path),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="estimated_scenario_{scenario_id}.pdf"'})


# ---------------------------------------------------------------- saved routes and preferences (device-scoped)

@router.delete("/my-data", tags=["user"])
def erase_device_data(request: Request, db: DbSession) -> dict[str, Any]:
    """Delete everything the server holds for this device: scenarios, saved routes and preferences.

    The audit entry records only the counts and a short hash prefix, never the IP address, so the erasure itself
    leaves no new personal data behind.
    """
    owner = require_client_key(request)
    scenarios = db.scalars(select(Scenario).where(Scenario.owner_hash == owner)).all()
    for scenario in scenarios:
        db.delete(scenario)
    saved = db.execute(delete(SavedRoute).where(SavedRoute.client_hash == owner)).rowcount
    prefs = db.execute(delete(UserPreference).where(UserPreference.client_hash == owner)).rowcount
    counts = {"scenarios": len(scenarios), "saved_routes": saved, "preferences": prefs}
    record_audit(db, actor=f"device:{owner[:12]}", action="device.erase", entity="device", detail=counts)
    db.commit()
    return {"deleted": counts}


@router.get("/saved-routes", tags=["user"])
def list_saved_routes(request: Request, db: DbSession) -> dict[str, Any]:
    owner = optional_client_hash(request)
    if owner is None:
        return {"saved": []}
    rows = db.scalars(select(SavedRoute).where(SavedRoute.client_hash == owner).order_by(SavedRoute.label)).all()
    return {"saved": [
        {"id": r.id, "classification": r.classification, "gtfs_route_id": r.gtfs_route_id, "label": r.label}
        for r in rows
    ]}


@router.post("/saved-routes", status_code=201, tags=["user"])
def save_route(data: SavedRouteIn, request: Request, db: DbSession) -> dict[str, Any]:
    owner = require_client_key(request)
    exists = db.scalar(
        select(Route.id)
        .join(GtfsImport, GtfsImport.id == Route.import_id)
        .where(
            Route.gtfs_route_id == data.gtfs_route_id,
            GtfsImport.classification == data.classification,
            GtfsImport.status == STATUS_COMPLETED,
            GtfsImport.is_active.is_(True),
        )
        .limit(1)
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="That route is not in this classification's data.")
    existing = db.scalar(
        select(SavedRoute).where(
            SavedRoute.client_hash == owner,
            SavedRoute.classification == data.classification,
            SavedRoute.gtfs_route_id == data.gtfs_route_id,
        )
    )
    if existing is None:
        existing = SavedRoute(client_hash=owner, classification=data.classification,
                              gtfs_route_id=data.gtfs_route_id, label=data.label.strip())
        db.add(existing)
    else:
        existing.label = data.label.strip()
    db.commit()
    return {"id": existing.id, "classification": existing.classification,
            "gtfs_route_id": existing.gtfs_route_id, "label": existing.label}


@router.delete("/saved-routes/{saved_id}", status_code=204, tags=["user"])
def delete_saved_route(saved_id: int, request: Request, db: DbSession) -> Response:
    owner = require_client_key(request)
    row = db.get(SavedRoute, saved_id)
    if row is None or row.client_hash != owner:
        raise HTTPException(status_code=404, detail="Saved route not found.")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/preferences", tags=["user"])
def get_preferences(request: Request, db: DbSession) -> dict[str, Any]:
    owner = optional_client_hash(request)
    if owner is None:
        return {"values": {}}
    rows = db.scalars(select(UserPreference).where(UserPreference.client_hash == owner)).all()
    return {"values": {r.key: r.value for r in rows}}


MAX_PREFERENCES_PER_DEVICE = 20


@router.put("/preferences", tags=["user"])
def put_preferences(data: PreferencesIn, request: Request, db: DbSession) -> dict[str, Any]:
    """Add or change the given preferences. The device's other preferences are kept."""
    owner = require_client_key(request)
    stored = {row.key: row for row in db.scalars(select(UserPreference).where(UserPreference.client_hash == owner))}
    new_keys = [key for key in data.values if key not in stored]
    if len(stored) + len(new_keys) > MAX_PREFERENCES_PER_DEVICE:
        raise HTTPException(
            status_code=422, detail=f"A device can keep at most {MAX_PREFERENCES_PER_DEVICE} preferences."
        )
    for key, value in data.values.items():
        row = stored.get(key)
        if row is None:
            db.add(UserPreference(client_hash=owner, key=key, value=value))
        else:
            row.value = value
    db.commit()
    return get_preferences(request, db)


# ---------------------------------------------------------------- administration

@router.get("/admin/data-sources", tags=["admin"])
def admin_list_sources(request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request)
    sources = db.scalars(select(DataSource).order_by(DataSource.id)).all()
    return {"sources": [_public_source(db, s) | {"admin_note": s.verification_note, "verified_by": s.verified_by}
                        for s in sources]}


@router.post("/admin/data-sources", status_code=201, tags=["admin"])
def admin_create_source(data: DataSourceIn, request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request)
    source = DataSource(name=data.name.strip(), publisher=data.publisher.strip(),
                        source_url=data.source_url, license=data.license.strip(), kind=data.kind,
                        verified=False)
    db.add(source)
    db.flush()
    record_audit(db, actor="admin", action="data_source.create", entity="data_source", entity_id=source.id,
                 detail={"name": source.name, "kind": source.kind}, ip=client_ip(request))
    db.commit()
    return _public_source(db, source)


@router.post("/admin/data-sources/{source_id}/verify", tags=["admin"])
def admin_verify_source(source_id: int, data: VerificationIn, request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request)
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found.")
    try:
        changed = set_verification(db, source, verified=data.verified, note=data.note, actor="admin",
                                   ip=client_ip(request))
    except VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"source": _public_source(db, source), "reclassified_imports": changed}


@router.get("/admin/imports", tags=["admin"])
def admin_list_imports(request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request)
    imports = db.scalars(select(GtfsImport).order_by(GtfsImport.id.desc()).limit(200)).all()
    counts = fare_counts(db, [i.id for i in imports])
    return {"imports": [import_summary(i, counts.get(i.id, 0)) for i in imports]}


@router.post(
    "/admin/imports",
    status_code=201,
    tags=["admin"],
    responses={
        422: {
            "description": (
                "The feed was checked and rejected, and nothing was stored. The body holds the import summary under "
                "'import'."
            )
        }
    },
)
async def admin_upload_import(
    request: Request,
    file: UploadFile = File(...),
    data_source_id: int = Form(...),
) -> JSONResponse:
    require_admin(request)
    settings = request.app.state.settings
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="The file is larger than the upload limit.")
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    name = safe_filename(file.filename)
    ip = client_ip(request)

    def work() -> tuple[int, dict[str, Any]]:
        session = request.app.state.db.session()
        try:
            source = session.get(DataSource, data_source_id)
            if source is None:
                raise HTTPException(status_code=404, detail="Data source not found.")
            imp = import_feed(session, data, filename=name, source=source, settings=settings, actor="admin", ip=ip)
            fares = fare_counts(session, [imp.id]).get(imp.id, 0)
            return (201 if imp.status == STATUS_COMPLETED else 422), import_summary(imp, fares)
        finally:
            session.close()

    status_code, summary = await run_in_threadpool(work)
    return JSONResponse(status_code=status_code, content={"import": summary})


@router.delete("/admin/imports/{import_id}", status_code=204, tags=["admin"])
def admin_delete_import(import_id: int, request: Request, db: DbSession) -> Response:
    require_admin(request)
    imp = db.get(GtfsImport, import_id)
    if imp is None:
        raise HTTPException(status_code=404, detail="Import not found.")
    record_audit(db, actor="admin", action="gtfs.delete", entity="gtfs_import", entity_id=import_id,
                 detail={"filename": imp.filename, "classification": imp.classification}, ip=client_ip(request))
    db.delete(imp)
    db.commit()
    return Response(status_code=204)


@router.get("/admin/stats", tags=["admin"])
def admin_stats(request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request)
    counts = sched.database_counts(db)
    per_class = {
        cls: db.scalar(select(func.count(GtfsImport.id)).where(GtfsImport.classification == cls,
                                                               GtfsImport.status == STATUS_COMPLETED,
                                                               GtfsImport.is_active.is_(True))) or 0
        for cls in DATA_CLASSIFICATIONS
    }
    return {"counts": counts, "active_imports_by_classification": per_class,
            "database": make_url(request.app.state.settings.database_url).get_backend_name()}


@router.post("/admin/backup", tags=["admin"])
def admin_backup(request: Request, db: DbSession) -> dict[str, Any]:
    """Copy the live SQLite database to BACKUP_DIR, then check the copy before reporting success."""
    require_admin(request)
    settings = request.app.state.settings
    source = sqlite_file(settings.database_url)
    if source is None:
        raise HTTPException(
            status_code=501, detail="Automatic backup is available for SQLite only. Use pg_dump for PostgreSQL."
        )
    try:
        report = backup_and_verify(source, settings.backup_dir)
    except MaintenanceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    record_audit(db, actor="admin", action="database.backup", entity="database", entity_id=report["file"],
                 detail={"bytes": report["bytes"], "revision": report["revision"]}, ip=client_ip(request))
    db.commit()
    return {"file": report["file"], "bytes": report["bytes"], "directory": report["directory"],
            "verified": True, "revision": report["revision"]}


@router.get("/admin/audit-logs", tags=["admin"])
def admin_audit_logs(request: Request, db: DbSession, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    require_admin(request)
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return {"entries": [
        {"id": r.id, "time": r.created_at.isoformat(), "actor": r.actor, "action": r.action,
         "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail, "ip": r.ip}
        for r in rows
    ]}

