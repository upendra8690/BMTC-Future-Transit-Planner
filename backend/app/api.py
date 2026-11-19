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
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLES,
    STATUS_COMPLETED,
    WEEKDAY_CODES,
    AuditLog,
    DataSource,
    GtfsImport,
    Route,
    SavedRoute,
    Scenario,
    Stop,
    User,
    UserPreference,
    utcnow,
)
from .schemas import (
    PLANNING_YEARS,
    AccountIn,
    AccountJourneyIn,
    AnnouncementIn,
    AnnouncementUpdateIn,
    DataSourceIn,
    NoticeIn,
    NoticeUpdateIn,
    NotificationIn,
    OrderIn,
    PasswordChangeIn,
    PasswordIn,
    PayIn,
    PreferencesIn,
    QuoteIn,
    RecoverIn,
    RefundIn,
    RoleIn,
    SavedRouteIn,
    ScenarioIn,
    VerificationIn,
)
from .security import (
    bearer_token,
    client_ip,
    optional_client_hash,
    require_admin,
    require_client_key,
    safe_filename,
)
from .services import (
    accounts,
    announcements,
    assistant,
    catalogue,
    commerce,
    integrations,
    notices,
    planner,
    registry,
)
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


# ---------------------------------------------------------------- live vehicles (GTFS-Realtime; off until authorised)

def _live_official(request: Request) -> bool:
    live = request.app.state.live
    return bool(live.official and live.status(clock.utc_now())["available"])


@router.get("/live/status", tags=["live"])
def live_status(request: Request) -> dict[str, Any]:
    """Whether a live feed is connected, how fresh it is, and what is needed when it is not."""
    return request.app.state.live.status(clock.utc_now())


@router.get("/live/vehicles", tags=["live"])
def live_vehicles(request: Request, db: DbSession,
                  route: str = Query("", max_length=40, description="Route number or GTFS route id")) -> dict[str, Any]:
    """Vehicles from the live feed, matched with the timetable. Positions older than 10 minutes are left out."""
    return request.app.state.live.vehicles(db, clock.utc_now(), route)


@router.get("/live/vehicles/{vehicle_id}", tags=["live"])
def live_vehicle(request: Request, db: DbSession,
                 vehicle_id: str = ApiPath(..., min_length=1, max_length=100)) -> dict[str, Any]:
    """One vehicle with its route progress and an estimate for each stop still ahead (or the scheduled time)."""
    found = request.app.state.live.vehicle(db, clock.utc_now(), vehicle_id)
    if found is None:
        raise HTTPException(status_code=404, detail="That vehicle is not in the live feed now.")
    return found


@router.get("/live/stops/{stop_id}/arrivals", tags=["live"])
def live_arrivals(stop_id: int, request: Request, db: DbSession) -> dict[str, Any]:
    """Live arrival estimates at one stop. Scheduled departures stay on their own endpoint, under their own label."""
    stop = db.get(Stop, stop_id)
    if stop is None:
        raise HTTPException(status_code=404, detail="Stop not found.")
    return request.app.state.live.arrivals(db, clock.utc_now(), stop)


# ---------------------------------------------------------------- tickets and payments (no provider connected)

def _commerce(call: Any) -> Any:
    try:
        return call()
    except commerce.CommerceError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc),
                            headers={"X-Error-Code": exc.code}) from exc


@router.get("/commerce/status", tags=["tickets"])
def commerce_status(request: Request) -> dict[str, Any]:
    """Which products can be bought, which payment methods exist, and what each missing one needs."""
    return request.app.state.commerce.status()


@router.post("/commerce/quotes", tags=["tickets"])
def commerce_quote(data: QuoteIn, request: Request) -> dict[str, Any]:
    """The official fare from the ticketing provider. 503 while no provider is connected."""
    return _commerce(lambda: request.app.state.commerce.quote(data.product, data.details))


@router.post("/commerce/orders", status_code=201, tags=["tickets"])
def commerce_order(data: OrderIn, request: Request, db: DbSession) -> dict[str, Any]:
    shop = request.app.state.commerce
    _commerce(lambda: shop.require(data.product))
    user = _signed_in(request, db)
    return _commerce(lambda: shop.create_order(db, user, data.product, data.details, data.idempotency_key))


@router.post("/commerce/orders/{order_id}/pay", tags=["tickets"])
def commerce_pay(order_id: int, data: PayIn, request: Request, db: DbSession) -> dict[str, Any]:
    """Starts a payment with the payment provider and returns where to pay. The app never takes card or UPI secrets."""
    user = _signed_in(request, db)
    return _commerce(lambda: request.app.state.commerce.pay(db, user, order_id, data.method))


@router.post("/commerce/orders/{order_id}/verify", tags=["tickets"])
def commerce_verify(order_id: int, request: Request, db: DbSession) -> dict[str, Any]:
    """Asks the payment provider, server to server, whether the payment arrived. The only way an order becomes paid
    apart from the provider's signed webhook: returning from a UPI app or a browser redirect proves nothing."""
    user = _signed_in(request, db)
    return _commerce(lambda: request.app.state.commerce.verify(db, user, order_id))


@router.post("/admin/payments/reconcile", tags=["admin"])
def admin_reconcile_payments(request: Request, db: DbSession) -> dict[str, Any]:
    """Checks every pending payment with the provider, for example after a restart."""
    require_admin(request)
    result = request.app.state.commerce.reconcile_pending(db)
    record_audit(db, actor=request.state.admin_actor, action="payments.reconcile", entity="payments",
                 detail=result, ip=client_ip(request))
    db.commit()
    return result


@router.post("/commerce/orders/{order_id}/refund", tags=["tickets"])
def commerce_refund(order_id: int, data: RefundIn, request: Request, db: DbSession) -> dict[str, Any]:
    user = _signed_in(request, db)
    return _commerce(lambda: request.app.state.commerce.request_refund(db, user, order_id, data.reason))


@router.get("/commerce/orders", tags=["tickets"])
def commerce_history(request: Request, db: DbSession) -> dict[str, Any]:
    """The signed-in passenger's orders with their payments, tickets and refunds. Empty while nothing can be sold."""
    user = _signed_in(request, db)
    return {"orders": request.app.state.commerce.history(db, user)}


@router.get("/commerce/orders/{order_id}", tags=["tickets"])
def commerce_order_detail(order_id: int, request: Request, db: DbSession) -> dict[str, Any]:
    user = _signed_in(request, db)
    return _commerce(lambda: request.app.state.commerce.order(db, user, order_id))


@router.get("/commerce/orders/{order_id}/receipt", tags=["tickets"])
def commerce_receipt(order_id: int, request: Request, db: DbSession) -> dict[str, Any]:
    """A record of a payment the provider confirmed. Not a tax invoice and not a ticket."""
    user = _signed_in(request, db)
    return _commerce(lambda: request.app.state.commerce.receipt(db, user, order_id))


@router.post("/commerce/notifications/{provider}", tags=["tickets"])
async def commerce_notification(request: Request,
                                provider: str = ApiPath(..., pattern="^[a-z0-9-]{2,50}$")) -> dict[str, Any]:
    """Signed notifications from the payment provider. The signature is checked by the provider's class."""
    body = await request.body()
    if len(body) > 64 * 1024:
        raise HTTPException(status_code=413, detail="Notification too large.")
    headers = {k.lower(): v for k, v in request.headers.items()}
    with request.app.state.db.session() as db:
        return _commerce(lambda: request.app.state.commerce.notification(db, provider, headers, body))


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
        "live_positions_available": _live_official(request),
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
    """What works right now. States: AVAILABLE, NO_DATA, UNAVAILABLE (needs an authorisation), PLANNED.

    `server_storage_persistent` is false when items saved on the server are lost on restart (free hosting), so the
    app can say so next to them.
    """
    settings = request.app.state.settings
    return {"version": APP_VERSION, "demo_mode": settings.demo_mode,
            "server_storage_persistent": not settings.ephemeral_storage,
            "features": catalogue.feature_states(db, accounts_running=request.app.state.accounts_reason is None,
                                                 live=request.app.state.live.status(clock.utc_now()))}


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
    require_admin(request, roles=(ROLE_ADMIN, ROLE_EDITOR))
    values = data.model_dump(exclude={"id", "reason"})
    try:
        return announcements.create(db, data.id, values, reason=data.reason, actor=request.state.admin_actor,
                                    ip=client_ip(request),
                                    today=_service_today(request, db))
    except announcements.AnnouncementError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.patch("/admin/upcoming/{key}", tags=["admin"])
def admin_update_upcoming(
    key: Annotated[str, ApiPath(pattern=r"^[a-z0-9_]{2,60}$")], data: AnnouncementUpdateIn, request: Request,
    db: DbSession,
) -> dict[str, Any]:
    require_admin(request, roles=(ROLE_ADMIN, ROLE_EDITOR))
    changes: dict[str, Any] = {}
    for field in sorted(data.model_fields_set - {"reason"}):
        value = getattr(data, field)
        if value is None and field in _REQUIRED_WHEN_SENT:
            raise HTTPException(status_code=422, detail=f"{field} cannot be empty.")
        if field == "sources":
            value = [source.model_dump() for source in data.sources or []]
        changes[field] = "" if value is None and field in ("location", "announcement", "note") else value
    try:
        return announcements.update(db, key, changes, reason=data.reason, actor=request.state.admin_actor,
                                    ip=client_ip(request),
                                    today=_service_today(request, db))
    except announcements.AnnouncementError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/notices", tags=["system"])
def service_notices(request: Request, db: DbSession) -> dict[str, Any]:
    """Service notices running today. Each repeats an official source, which it links to; there is no live alerts
    feed, so this list is empty unless an administrator has posted a notice."""
    return notices.list_active(db, _service_today(request, db))


@router.get("/admin/notices", tags=["admin"])
def admin_list_notices(request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request, roles=(ROLE_ADMIN, ROLE_EDITOR))
    return notices.list_for_admin(db, _service_today(request, db))


@router.post("/admin/notices", status_code=201, tags=["admin"])
def admin_create_notice(data: NoticeIn, request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request, roles=(ROLE_ADMIN, ROLE_EDITOR))
    values = data.model_dump(exclude={"reason"})
    values["title"], values["body"] = values["title"].strip(), values["body"].strip()
    try:
        return notices.create(db, values, reason=data.reason, actor=request.state.admin_actor, ip=client_ip(request),
                              today=_service_today(request, db))
    except notices.NoticeError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.patch("/admin/notices/{notice_id}", tags=["admin"])
def admin_update_notice(notice_id: Annotated[int, ApiPath(ge=1)], data: NoticeUpdateIn, request: Request,
                        db: DbSession) -> dict[str, Any]:
    require_admin(request, roles=(ROLE_ADMIN, ROLE_EDITOR))
    changes: dict[str, Any] = {}
    for field in sorted(data.model_fields_set - {"reason"}):
        value = getattr(data, field)
        if value is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be empty.")
        changes[field] = value.strip() if isinstance(value, str) else value
    try:
        return notices.update(db, notice_id, changes, reason=data.reason, actor=request.state.admin_actor,
                              ip=client_ip(request), today=_service_today(request, db))
    except notices.NoticeError as exc:
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
def integration_status(request: Request) -> dict[str, Any]:
    """Provider integrations (live vehicles, tickets, passes, Metro QR, payments, NCMC) and what each one needs."""
    return integrations.status(live_connected=_live_official(request))


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
    record_audit(db, actor=request.state.admin_actor, action="data_source.create", entity="data_source",
                 entity_id=source.id,
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
        changed = set_verification(db, source, verified=data.verified, note=data.note, actor=request.state.admin_actor,
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
            imp = import_feed(session, data, filename=name, source=source, settings=settings,
                              actor=request.state.admin_actor, ip=ip)
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
    record_audit(db, actor=request.state.admin_actor, action="gtfs.delete", entity="gtfs_import", entity_id=import_id,
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
    record_audit(db, actor=request.state.admin_actor, action="database.backup", entity="database",
                 entity_id=report["file"],
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




# ---------------------------------------------------------------- passenger accounts (off unless storage is permanent)

def _accounts_on(request: Request) -> None:
    reason = request.app.state.accounts_reason
    if reason == accounts.DISABLED:
        raise HTTPException(status_code=503, detail="Passenger accounts are switched off on this server.")
    if reason:
        raise HTTPException(status_code=503, detail="Passenger accounts are not available on this server: they need "
                                                    "a permanent database.")


def _signed_in(request: Request, db: Session) -> Any:
    _accounts_on(request)
    user = accounts.user_for_token(db, bearer_token(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in first.")
    return user


def _account_call(call: Any) -> Any:
    try:
        return call()
    except accounts.AccountError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/account/status", tags=["account"])
def account_status(request: Request) -> dict[str, Any]:
    reason = request.app.state.accounts_reason
    return {"available": reason is None, "reason": reason, "notification_delivery": "NOT_AVAILABLE",
            "roles": list(ROLES), "staff_session_hours": accounts.STAFF_SESSION_HOURS,
            "passenger_session_days": accounts.SESSION_DAYS}


@router.post("/account/register", status_code=201, tags=["account"])
def account_register(data: AccountIn, request: Request, db: DbSession) -> dict[str, Any]:
    _accounts_on(request)
    user, code = _account_call(lambda: accounts.register(db, data.email, data.password))
    return {"user": accounts.public_user(user), "recovery_code": code,
            "recovery_note": "Keep this code safe. It is shown only once and is the only way to reset the password."}


@router.post("/account/sign-in", tags=["account"])
def account_sign_in(data: AccountIn, request: Request, db: DbSession) -> dict[str, Any]:
    _accounts_on(request)
    user, token, expires = _account_call(lambda: accounts.sign_in(db, data.email, data.password))
    if user.role in accounts.STAFF_ROLES:
        record_audit(db, actor=f"user:{user.id}", action="account.sign_in", entity="user", entity_id=user.id,
                     detail={"role": user.role}, ip=client_ip(request))
        db.commit()
    return {"user": accounts.public_user(user), "token": token,
            "expires_at": expires.isoformat(timespec="seconds") + "Z"}


@router.post("/account/sign-out", tags=["account"])
def account_sign_out(request: Request, db: DbSession) -> dict[str, Any]:
    _signed_in(request, db)
    accounts.sign_out(db, bearer_token(request))
    return {"signed_out": True}


@router.get("/account/me", tags=["account"])
def account_me(request: Request, db: DbSession) -> dict[str, Any]:
    return {"user": accounts.public_user(_signed_in(request, db))}


@router.post("/account/password", tags=["account"])
def account_password(data: PasswordChangeIn, request: Request, db: DbSession) -> dict[str, Any]:
    user = _signed_in(request, db)
    _account_call(lambda: accounts.change_password(db, user, data.current_password, data.new_password))
    return {"changed": True, "note": "Every session was signed out. Sign in again."}


@router.post("/account/recover", tags=["account"])
def account_recover(data: RecoverIn, request: Request, db: DbSession) -> dict[str, Any]:
    _accounts_on(request)
    code = _account_call(lambda: accounts.recover(db, data.email, data.recovery_code, data.new_password))
    return {"recovery_code": code, "recovery_note": "The old code no longer works. Keep this new one safe."}


@router.get("/account/export", tags=["account"])
def account_export(request: Request, db: DbSession) -> dict[str, Any]:
    user = _signed_in(request, db)
    return {**accounts.export(db, user), "orders": request.app.state.commerce.history(db, user)}


@router.post("/account/delete", tags=["account"])
def account_delete(data: PasswordIn, request: Request, db: DbSession) -> dict[str, Any]:
    user = _signed_in(request, db)
    _account_call(lambda: accounts.delete_account(db, user, data.password))
    return {"deleted": True}


@router.get("/account/journeys", tags=["account"])
def account_journeys(request: Request, db: DbSession) -> dict[str, Any]:
    return {"journeys": accounts.journeys(db, _signed_in(request, db))}


@router.post("/account/journeys", status_code=201, tags=["account"])
def account_add_journey(data: AccountJourneyIn, request: Request, db: DbSession) -> dict[str, Any]:
    user = _signed_in(request, db)
    return _account_call(lambda: accounts.add_journey(db, user, data.model_dump()))


@router.delete("/account/journeys/{journey_id}", tags=["account"])
def account_remove_journey(journey_id: int, request: Request, db: DbSession) -> dict[str, Any]:
    user = _signed_in(request, db)
    _account_call(lambda: accounts.remove_journey(db, user, journey_id))
    return {"removed": True}


@router.get("/account/notifications", tags=["account"])
def account_notifications(request: Request, db: DbSession) -> dict[str, Any]:
    return accounts.preferences(db, _signed_in(request, db))


@router.put("/account/notifications", tags=["account"])
def account_set_notifications(data: NotificationIn, request: Request, db: DbSession) -> dict[str, Any]:
    return accounts.set_preferences(db, _signed_in(request, db), data.model_dump())


@router.get("/admin/users", tags=["admin"])
def admin_users(request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request, bootstrap=True)
    _accounts_on(request)
    return {"users": [accounts.public_user(u) for u in db.scalars(select(User).order_by(User.id))]}


@router.put("/admin/users/{user_id}/role", tags=["admin"])
def admin_set_role(user_id: int, data: RoleIn, request: Request, db: DbSession) -> dict[str, Any]:
    require_admin(request, bootstrap=True)
    _accounts_on(request)
    user = _account_call(lambda: accounts.set_role(db, user_id, data.role))
    record_audit(db, actor=request.state.admin_actor, action="user.role", entity="user", entity_id=user_id,
                 detail={"role": data.role}, ip=client_ip(request))
    db.commit()
    return {"user": accounts.public_user(user)}
