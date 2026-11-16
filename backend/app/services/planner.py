"""Journey planning across every active feed of one classification, with up to two changes.

The search is RAPTOR (Delling, Pajor and Werneck, 2012). Round k finds the earliest arrival at every stop using at
most k rides. A change of vehicle needs the minimum change time at that stop. A walk joins two stops within the
walking limit, inside one feed or across two feeds of the same classification.

Times are absolute instants, so feeds in different time zones combine correctly.

What an answer is, and what it is not:
* Only the scheduled times in the feeds are used. There are no live positions, delays or cancellations.
* The walking speed and the minimum change time are planning assumptions. Every answer states them.
* Each option is the earliest arrival with that number of rides. A later departure that arrives at the same time is
  not shown.
* Walking alone is not planned, and walks are never chained: a walk is always followed by a ride or ends the journey.
* Fares are shown only when the feed gives a route fare with no origin, destination or zone limit. A journey with
  changes is never given a total, because transfer rules are not applied.
"""

from __future__ import annotations

import bisect
import datetime as dt
import math
import threading
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import clock
from ..models import (
    CLASS_OFFICIAL,
    Agency,
    DataSource,
    FareAttribute,
    FareRule,
    GtfsImport,
    Route,
    Stop,
    StopTime,
    Trip,
)
from . import schedule as sched
from .text import fold

NEVER = 1 << 62
DEFAULT_MAX_CHANGES = 2
MAX_CHANGES_LIMIT = 2
NOW_WINDOW_SECONDS = 3 * 3600
LOOKBACK_DAYS = 2
MAX_MATCHES = 200
METRES_PER_DEGREE = 111_320.0
CACHE_ENTRIES = 4
ONE_DAY = dt.timedelta(days=1)
PLAN_NOTE = (
    "Scheduled times from the feeds, with up to two changes. Live bus positions, delays and cancellations are not "
    "available. Walking times and the minimum change time are planning estimates."
)
_CACHE: OrderedDict[tuple, _Network] = OrderedDict()
_CACHE_LOCK = threading.Lock()


# GTFS route_type (basic and extended) to the travel mode shown with each ride.
_METRO_TYPES = {1, 400, 401, 402, 403, 404, 405}
_RAIL_TYPES = {2, 100, 101, 102, 103, 106, 109}
_TRAM_TYPES = {0, 900, 901, 902}


def mode_of(route_type: int | None) -> str:
    if route_type in _METRO_TYPES:
        return "metro"
    if route_type in _RAIL_TYPES:
        return "rail"
    if route_type in _TRAM_TYPES:
        return "tram"
    if route_type == 3 or (route_type is not None and 700 <= route_type <= 799):
        return "bus"
    return "other"


@dataclass(frozen=True)
class PlanSettings:
    min_transfer_seconds: int
    max_walk_m: int
    walk_speed_mps: float

    @classmethod
    def from_settings(cls, settings: Any) -> PlanSettings:
        return cls(
            min_transfer_seconds=round(settings.min_transfer_minutes * 60),
            max_walk_m=int(settings.max_transfer_walk_m),
            walk_speed_mps=settings.walk_speed_kmph * 1000.0 / 3600.0,
        )


@dataclass(frozen=True)
class _Feed:
    import_id: int
    source_name: str
    publisher: str
    zone: Any
    agency_name: str | None


class _Network:
    """Scheduled trips of every feed in one classification, for a span of service days.

    A pattern is one route's stop sequence, split into lanes in which no trip overtakes an earlier one. Each lane keeps
    its trips' absolute times in order, so the search finds the first trip after any moment with a binary search.
    """

    def __init__(self) -> None:
        self.feeds: list[_Feed] = []
        self.feed_of_import: dict[int, int] = {}
        self.nodes: list[tuple[int, int, str, str, float | None, float | None]] = []
        self.node_pats: list[list[tuple[int, int]]] = []
        self.foot: list[list[tuple[int, int, int]]] = []
        self.pat_nodes: list[list[int]] = []
        self.pat_feed: list[int] = []
        self.pat_route: list[tuple[int, str | None, str | None, str, int]] = []
        self.pat_trips: list[list[tuple[int, str, str | None, dt.date]]] = []
        self.pat_arr: list[list[list[int]]] = []
        self.pat_dep: list[list[list[int]]] = []
        self.pat_boards: list[list[list[tuple[int, int]]]] = []
        self._node_of: dict[tuple[int, int], int] = {}
        self._raw: dict[tuple[int, int, tuple[int, ...]], list[tuple]] = {}
        self._raw_route: dict[tuple[int, int, tuple[int, ...]], tuple] = {}

    def add_feed(self, feed: _Feed) -> int:
        self.feeds.append(feed)
        index = len(self.feeds) - 1
        self.feed_of_import[feed.import_id] = index
        return index

    def add_node(self, feed: int, stop_id: int, gtfs_id: str, name: str, lat: float | None, lon: float | None) -> None:
        self._node_of[(feed, stop_id)] = len(self.nodes)
        self.nodes.append((feed, stop_id, gtfs_id, name, lat, lon))
        self.node_pats.append([])
        self.foot.append([])

    def node_for(self, feed: int, stop_id: int) -> int | None:
        return self._node_of.get((feed, stop_id))

    def add_trip(
        self,
        feed: int,
        route: tuple[int, str | None, str | None, str],
        meta: tuple[int, str, str | None, dt.date],
        stops: list[tuple[int | None, int | None, int | None]],
        base: int,
    ) -> None:
        """Add one trip. Times are seconds from the service day's start, and base turns them into instants.

        A trip is skipped when a stop is unknown, when its times run backwards, or when it has fewer than two
        timed stops. The importer rejects such feeds, so a skip here only guards the search against a bad row.
        """
        timed: list[tuple[int, int, int]] = []
        for node, arr_s, dep_s in stops:
            if node is None:
                return
            if arr_s is None and dep_s is None:
                continue
            arr_s = dep_s if arr_s is None else arr_s
            dep_s = arr_s if dep_s is None else dep_s
            timed.append((node, arr_s, dep_s))
        if len(timed) < 2:
            return
        previous = None
        for _node, arr_s, dep_s in timed:
            if arr_s > dep_s or (previous is not None and arr_s < previous):
                return
            previous = dep_s
        nodes = tuple(node for node, _, _ in timed)
        key = (feed, route[0], nodes)
        self._raw.setdefault(key, []).append((
            meta,
            [base + arr_s for _, arr_s, _ in timed],
            [base + dep_s for _, _, dep_s in timed],
        ))
        self._raw_route[key] = route

    def finish(self, plan: PlanSettings) -> None:
        """Split every pattern into lanes in which no trip overtakes an earlier one, then build the boarding indexes.

        The search boards the first trip that can be caught at a stop. That is the fastest choice only when later trips
        never pass earlier ones, so trips that do pass each other are put in separate lanes.
        """
        for key, items in self._raw.items():
            feed, _route_id, nodes = key
            items.sort(key=lambda item: item[2][0])
            lanes: list[list[tuple]] = []
            for item in items:
                for lane in lanes:
                    if _no_overtaking(lane[-1], item):
                        lane.append(item)
                        break
                else:
                    lanes.append([item])
            for lane in lanes:
                index = len(self.pat_nodes)
                self.pat_nodes.append(list(nodes))
                self.pat_feed.append(feed)
                self.pat_route.append(self._raw_route[key])
                self.pat_trips.append([meta for meta, _, _ in lane])
                self.pat_arr.append([arr for _, arr, _ in lane])
                self.pat_dep.append([dep for _, _, dep in lane])
                self.pat_boards.append([
                    sorted((self.pat_dep[index][i][pos], i) for i in range(len(lane)))
                    for pos in range(len(nodes))
                ])
                for pos, node in enumerate(nodes):
                    self.node_pats[node].append((index, pos))
        self._raw = {}
        self._raw_route = {}
        self._footpaths(plan)

    def _footpaths(self, plan: PlanSettings) -> None:
        """Walks between stops within the limit. Stops are bucketed in a grid so each stop checks only nearby cells."""
        if plan.max_walk_m <= 0:
            return
        located = [i for i, node in enumerate(self.nodes) if node[4] is not None and node[5] is not None]
        if not located:
            return
        widest_lat = max(abs(self.nodes[i][4]) for i in located)
        cell_lat = plan.max_walk_m / METRES_PER_DEGREE
        cos_ref = max(math.cos(math.radians(min(widest_lat, 89.0))), 0.01)
        cell_lon = cell_lat / cos_ref  # cells are at least max_walk_m wide east-west at every latitude in the data
        grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i in located:
            lat, lon = self.nodes[i][4], self.nodes[i][5]
            grid[(math.floor(lat / cell_lat), math.floor(lon / cell_lon))].append(i)
        for i in located:
            lat, lon = self.nodes[i][4], self.nodes[i][5]
            row, col = math.floor(lat / cell_lat), math.floor(lon / cell_lon)
            for d_row in (-1, 0, 1):
                for d_col in (-1, 0, 1):
                    for j in grid.get((row + d_row, col + d_col), ()):
                        if j == i:
                            continue
                        other = self.nodes[j]
                        metres = sched.haversine_km(lat, lon, other[4], other[5]) * 1000.0
                        if metres <= plan.max_walk_m:
                            self.foot[i].append((j, math.ceil(metres / plan.walk_speed_mps), round(metres)))


def _no_overtaking(earlier: tuple, later: tuple) -> bool:
    """True when the later trip is never ahead of the earlier one, at any stop, on either arrival or departure."""
    return (
        all(a <= b for a, b in zip(earlier[1], later[1], strict=True))
        and all(a <= b for a, b in zip(earlier[2], later[2], strict=True))
    )


def _instant(epoch: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(epoch, dt.UTC)


def _epoch(zone: Any, day: dt.date) -> int:
    """The start of a service day, as the GTFS time base defines it (noon minus twelve hours)."""
    return int(clock.service_day_start(zone, day).timestamp())


def _local_iso(zone: Any, epoch: int) -> str:
    return clock.local_time(zone, _instant(epoch)).isoformat(timespec="minutes")


def _add_import(session: Session, net: _Network, import_id: int, first_day: dt.date, last_day: dt.date) -> None:
    zone = sched.import_zone(session, import_id)
    source_name, publisher = session.execute(
        select(DataSource.name, DataSource.publisher)
        .join(GtfsImport, GtfsImport.data_source_id == DataSource.id)
        .where(GtfsImport.id == import_id)
    ).one()
    agency = session.scalar(select(Agency.name).where(Agency.import_id == import_id).order_by(Agency.id).limit(1))
    feed = net.add_feed(_Feed(import_id, source_name, publisher, zone, agency))
    for stop in session.execute(
        select(Stop.id, Stop.gtfs_stop_id, Stop.name, Stop.lat, Stop.lon)
        .where(Stop.import_id == import_id)
        .order_by(Stop.id)
    ):
        net.add_node(feed, stop.id, stop.gtfs_stop_id, stop.name, stop.lat, stop.lon)
    routes = {
        route.id: (route.id, route.short_name, route.long_name, route.gtfs_route_id, route.route_type)
        for route in session.execute(
            select(Route.id, Route.short_name, Route.long_name, Route.gtfs_route_id, Route.route_type)
            .where(Route.import_id == import_id)
        )
    }
    day = first_day
    while day <= last_day:
        services = sched.active_service_ids(session, import_id, day)
        if services:
            _add_day(session, net, feed, import_id, zone, day, sorted(services), routes)
        day += ONE_DAY


def _add_day(
    session: Session,
    net: _Network,
    feed: int,
    import_id: int,
    zone: Any,
    day: dt.date,
    services: list[str],
    routes: dict[int, tuple[int, str | None, str | None, str]],
) -> None:
    base = _epoch(zone, day)
    rows = session.execute(
        select(
            StopTime.trip_id, StopTime.stop_id, StopTime.arrival_sec, StopTime.departure_sec,
            Trip.route_id, Trip.gtfs_trip_id, Trip.headsign,
        )
        .join(Trip, Trip.id == StopTime.trip_id)
        .where(StopTime.import_id == import_id, Trip.import_id == import_id, Trip.service_id.in_(services))
        .order_by(StopTime.trip_id, StopTime.sequence)
    ).all()
    for trip_id, group in groupby(rows, key=lambda row: row.trip_id):
        trip_rows = list(group)
        first = trip_rows[0]
        route = routes.get(first.route_id)
        if route is None:
            continue
        meta = (trip_id, first.gtfs_trip_id, first.headsign, day)
        stops = [(net.node_for(feed, row.stop_id), row.arrival_sec, row.departure_sec) for row in trip_rows]
        net.add_trip(feed, route, meta, stops, base)


def _network_for(
    session: Session,
    classification: str,
    import_ids: list[int],
    first_day: dt.date,
    last_day: dt.date,
    plan: PlanSettings,
) -> _Network:
    """The network for these feeds and days. Built once, then reused while the imports and days are unchanged.

    Imports are never edited after they complete, so the import identifiers and file hashes are enough to tell when a
    cached network is out of date. Deleting an import changes the identifiers, so its cached network is never used.
    """
    fingerprints = tuple(sorted(
        session.execute(select(GtfsImport.id, GtfsImport.sha256).where(GtfsImport.id.in_(import_ids))).all()
    ))
    key = (str(session.get_bind().url), classification, first_day, last_day, fingerprints, plan)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            return cached
    net = _Network()
    for import_id in import_ids:
        _add_import(session, net, import_id, first_day, last_day)
    net.finish(plan)
    with _CACHE_LOCK:
        _CACHE[key] = net
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_ENTRIES:
            _CACHE.popitem(last=False)
    return net


def clear_network_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


class _Search:
    """The labels of one search: earliest arrivals and boarding times per round, and how each was reached."""

    def __init__(
        self,
        net: _Network,
        arr: list[list[int]],
        arr_par: list[list[Any]],
        brd: list[list[int]],
        brd_par: list[list[Any]],
    ) -> None:
        self.net = net
        self.arr = arr
        self.arr_par = arr_par
        self.brd = brd
        self.brd_par = brd_par

    def trace_arrival(self, k: int, node: int) -> list[tuple]:
        j = k
        while j >= 0 and self.arr_par[j][node] is None:
            j -= 1
        if j < 0:
            raise RuntimeError("planner: an arrival has no recorded route")
        par = self.arr_par[j][node]
        if par[0] == "ride":
            return self._ride(j, par)
        _, walk_s, metres, src, src_ride = par
        return [*self._ride(j, src_ride), ("walk", src, node, walk_s, metres)]

    def _ride(self, k: int, par: tuple) -> list[tuple]:
        _, pat, trip, board_node, board_pos, alight_pos = par
        return [*self.trace_board(k - 1, board_node), ("ride", pat, trip, board_pos, alight_pos)]

    def trace_board(self, k: int, node: int) -> list[tuple]:
        j = k
        while j >= 0 and self.brd_par[j][node] is None:
            j -= 1
        if j < 0:
            raise RuntimeError("planner: a boarding point has no recorded route")
        par = self.brd_par[j][node]
        if par[0] == "origin":
            return []
        if par[0] == "origin_walk":
            _, origin, walk_s, metres = par
            return [("walk", origin, node, walk_s, metres)]
        return self.trace_arrival(j, node)  # ("alight",): the rider got off here and changes


def _search(
    net: _Network, origins: list[int], start: int, horizon_end: int, rounds: int, change_s: int
) -> _Search:
    count = len(net.nodes)
    brd0 = [NEVER] * count
    brd0_par: list[Any] = [None] * count
    for origin in origins:
        brd0[origin] = start
        brd0_par[origin] = ("origin",)
    for origin in origins:
        for other, walk_s, metres in net.foot[origin]:
            if start + walk_s < brd0[other]:
                brd0[other] = start + walk_s
                brd0_par[other] = ("origin_walk", origin, walk_s, metres)
    arr: list[list[int]] = [[NEVER] * count]
    arr_par: list[list[Any]] = [[None] * count]
    brd: list[list[int]] = [brd0]
    brd_par: list[list[Any]] = [brd0_par]
    marked = [node for node in range(count) if brd0[node] < NEVER]

    for _round in range(1, rounds + 1):
        if not marked:
            break
        prev_arr = arr[-1]
        prev_brd = brd[-1]
        scan: dict[int, int] = {}
        for node in marked:
            for pat, pos in net.node_pats[node]:
                current = scan.get(pat)
                if current is None or pos < current:
                    scan[pat] = pos

        candidates: dict[int, tuple[int, tuple]] = {}
        for pat, first in scan.items():
            nodes = net.pat_nodes[pat]
            arrs = net.pat_arr[pat]
            deps = net.pat_dep[pat]
            boards = net.pat_boards[pat]
            trip = -1
            board_pos = -1
            board_node = -1
            for pos in range(first, len(nodes)):
                node = nodes[pos]
                if trip >= 0:
                    arrival = arrs[trip][pos]
                    if arrival < prev_arr[node]:
                        best = candidates.get(node)
                        if best is None or arrival < best[0]:
                            candidates[node] = (arrival, ("ride", pat, trip, board_node, board_pos, pos))
                ready = prev_brd[node]
                if ready < NEVER:
                    options = boards[pos]
                    index = bisect.bisect_left(options, (ready, -1))
                    if index < len(options):
                        departs, candidate_trip = options[index]
                        if departs < horizon_end and (trip < 0 or departs < deps[trip][pos]):
                            trip, board_pos, board_node = candidate_trip, pos, node

        arr_k = list(prev_arr)
        par_k: list[Any] = [None] * count
        ride_time: dict[int, int] = {}
        ride_par: dict[int, tuple] = {}
        for node, (arrival, par) in candidates.items():
            if arrival < arr_k[node]:
                arr_k[node] = arrival
                par_k[node] = par
                ride_time[node] = arrival
                ride_par[node] = par
        walked: list[int] = []
        for node, arrival in ride_time.items():
            for other, walk_s, metres in net.foot[node]:
                reached = arrival + walk_s
                if reached < arr_k[other]:
                    arr_k[other] = reached
                    par_k[other] = ("walk", walk_s, metres, node, ride_par[node])
                    walked.append(other)

        brd_k = list(prev_brd)
        brd_par_k: list[Any] = [None] * count
        for node in set(ride_time) | set(walked):
            ready = arr_k[node] + change_s
            if ready < brd_k[node]:
                brd_k[node] = ready
                brd_par_k[node] = ("alight",)
        marked = [node for node in range(count) if brd_k[node] < prev_brd[node]]
        arr.append(arr_k)
        arr_par.append(par_k)
        brd.append(brd_k)
        brd_par.append(brd_par_k)
    return _Search(net, arr, arr_par, brd, brd_par)


def _fare_map(session: Session, import_ids: list[int]) -> dict[tuple[int, str | None], list[dict[str, Any]]]:
    """Fares a rule gives without an origin, destination or zone limit. A rule with no route applies to every route."""
    rows = session.execute(
        select(
            FareRule.import_id, FareRule.route_id, FareRule.fare_id,
            FareAttribute.price, FareAttribute.currency, FareAttribute.payment_method, FareAttribute.transfers,
        )
        .join(
            FareAttribute,
            (FareAttribute.import_id == FareRule.import_id) & (FareAttribute.fare_id == FareRule.fare_id),
        )
        .where(
            FareRule.import_id.in_(import_ids),
            FareRule.origin_id.is_(None),
            FareRule.destination_id.is_(None),
            FareRule.contains_id.is_(None),
        )
    ).all()
    seen: set[tuple[int, str | None, str]] = set()
    fares: dict[tuple[int, str | None], list[dict[str, Any]]] = defaultdict(list)
    for import_id, route_id, fare_id, price, currency, payment, transfers in rows:
        key = (import_id, route_id, fare_id)
        if key in seen:
            continue
        seen.add(key)
        fares[(import_id, route_id)].append({
            "fare_id": fare_id,
            "price": price,
            "currency": currency,
            "payment": "ON_BOARD" if payment == 0 else "BEFORE_BOARDING",
            "transfers": transfers,
        })
    return fares


def _fares_for(
    fares: dict[tuple[int, str | None], list[dict[str, Any]]], import_id: int, gtfs_route: str
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in [*fares.get((import_id, gtfs_route), []), *fares.get((import_id, None), [])]:
        merged.setdefault(item["fare_id"], item)
    return sorted(merged.values(), key=lambda item: (Decimal(item["price"]), item["fare_id"]))


def _matching_nodes(session: Session, net: _Network, import_ids: list[int], term: str) -> tuple[list[int], bool]:
    """Stops whose names contain the term, or whose stop code equals it.

    Returns the matching nodes and whether the list was cut at MAX_MATCHES.
    """
    rows = session.execute(
        select(Stop.id, Stop.import_id)
        .where(
            Stop.import_id.in_(import_ids),
            or_(
                sched.fold_column(session, Stop.name).like(sched.contains_pattern(term), escape=sched.LIKE_ESCAPE),
                sched.fold_column(session, Stop.gtfs_stop_id) == term,
            ),
        )
        .order_by(Stop.name, Stop.id)
        .limit(MAX_MATCHES + 1)
    ).all()
    nodes = []
    for stop_id, import_id in rows[:MAX_MATCHES]:
        node = net.node_for(net.feed_of_import[import_id], stop_id)
        if node is not None:
            nodes.append(node)
    return nodes, len(rows) > MAX_MATCHES


def _stop_out(net: _Network, node: int) -> dict[str, Any]:
    feed, stop_id, gtfs_id, name, lat, lon = net.nodes[node]
    return {
        "id": stop_id,
        "import_id": net.feeds[feed].import_id,
        "gtfs_stop_id": gtfs_id,
        "name": name,
        "lat": lat,
        "lon": lon,
    }


def _fare_summary(ride_fares: list[list[dict[str, Any]]]) -> dict[str, Any]:
    if len(ride_fares) > 1:
        return {"code": "CHANGES_NOT_PRICED", "total": None}
    only = ride_fares[0]
    if not only:
        return {"code": "NOT_IN_FEED", "total": None}
    if len(only) > 1:
        return {"code": "SEVERAL_IN_FEED", "total": None}
    fare = only[0]
    return {
        "code": "IN_FEED",
        "total": {"price": fare["price"], "currency": fare["currency"], "fare_id": fare["fare_id"]},
    }


def _format_option(
    net: _Network,
    legs: list[tuple],
    start: int,
    classification: str,
    fares: dict[tuple[int, str | None], list[dict[str, Any]]],
    now_mode: bool,
) -> tuple[dict[str, Any], int, list[int]]:
    """One option as the traveller would read it. Returns the option, its arrival instant and the feeds it uses.

    The departure is when the traveller sets off. Walking first in now mode, that is now. Walking first on a date, the
    traveller is taken to set off just in time, so the walk ends as the bus leaves and no wait is shown. Otherwise the
    departure is the bus's departure from the first stop, and any wait before it is shown separately in now mode.
    """
    first_index = next(index for index, leg in enumerate(legs) if leg[0] == "ride")
    _, first_pat, first_trip, first_board, _ = legs[first_index]
    first_departs = net.pat_dep[first_pat][first_trip][first_board]
    pre_walk = sum(leg[3] for leg in legs[:first_index])
    begin = start if now_mode and pre_walk else first_departs - pre_walk
    arrival = begin
    out_legs: list[dict[str, Any]] = []
    first_feed: int | None = None
    last_feed: int | None = None
    ride_fares: list[list[dict[str, Any]]] = []
    feeds_used: list[int] = []
    for leg in legs:
        if leg[0] == "ride":
            _, pat, trip, board_pos, alight_pos = leg
            feed_index = net.pat_feed[pat]
            feed = net.feeds[feed_index]
            _route_db_id, short_name, long_name, gtfs_route, route_type = net.pat_route[pat]
            _trip_db_id, gtfs_trip, headsign, service_day = net.pat_trips[pat][trip]
            departs = net.pat_dep[pat][trip][board_pos]
            arrives = net.pat_arr[pat][trip][alight_pos]
            if first_feed is None:
                first_feed = feed_index
            last_feed = feed_index
            if feed_index not in feeds_used:
                feeds_used.append(feed_index)
            leg_fares = _fares_for(fares, feed.import_id, gtfs_route)
            ride_fares.append(leg_fares)
            arrival = arrives
            out_legs.append({
                "type": "ride",
                "mode": mode_of(route_type),
                "route_type": route_type,
                "timing": "scheduled",
                "source": {
                    "import_id": feed.import_id,
                    "name": feed.source_name,
                    "publisher": feed.publisher,
                    "classification": classification,
                    "agency_name": feed.agency_name,
                    "timezone": feed.zone.key,
                },
                "route_number": short_name or gtfs_route,
                "route_name": long_name,
                "headsign": headsign,
                "trip_id": gtfs_trip,
                "service_date": service_day.isoformat(),
                "from": _stop_out(net, net.pat_nodes[pat][board_pos]),
                "to": _stop_out(net, net.pat_nodes[pat][alight_pos]),
                "departs_at": _local_iso(feed.zone, departs),
                "arrives_at": _local_iso(feed.zone, arrives),
                "duration_minutes": round((arrives - departs) / 60),
                "stops_between": alight_pos - board_pos - 1,
                "fares": leg_fares,
            })
        else:
            _, src, dst, walk_s, metres = leg
            src_zone = net.feeds[net.nodes[src][0]].zone
            walk_start = arrival
            arrival += walk_s
            out_legs.append({
                "type": "walk",
                "estimated": True,
                "from": _stop_out(net, src),
                "to": _stop_out(net, dst),
                "distance_m": metres,
                "starts_at": _local_iso(src_zone, walk_start),
                "arrives_at": _local_iso(src_zone, arrival),
                "duration_minutes": math.ceil(walk_s / 60),
            })
    if first_feed is None or last_feed is None:
        raise RuntimeError("planner: a journey was traced without any ride")
    option = {
        "rides": len(ride_fares),
        "changes": len(ride_fares) - 1,
        "departs_at": _local_iso(net.feeds[first_feed].zone, begin),
        "arrives_at": _local_iso(net.feeds[last_feed].zone, arrival),
        "duration_minutes": round((arrival - begin) / 60),
        "wait_minutes": max(0, (first_departs - start - pre_walk) // 60) if now_mode else None,
        "fare": _fare_summary(ride_fares),
        "labels": [],
        "legs": out_legs,
    }
    return option, arrival, feeds_used


def _options(
    net: _Network,
    search: _Search,
    destinations: list[int],
    start: int,
    classification: str,
    fares: dict[tuple[int, str | None], list[dict[str, Any]]],
    limit: int,
    now_mode: bool,
) -> tuple[list[dict[str, Any]], list[int]]:
    """One option per ride count, kept only when it arrives strictly earlier than every option with fewer rides."""
    formatted: list[tuple[dict[str, Any], int, list[int]]] = []
    best_so_far = NEVER
    for rides in range(1, len(search.arr)):
        reached = [(search.arr[rides][node], node) for node in destinations if search.arr[rides][node] < NEVER]
        if not reached:
            continue
        arrival, node = min(reached)
        if arrival >= best_so_far:
            continue
        best_so_far = arrival
        formatted.append(
            _format_option(net, search.trace_arrival(rides, node), start, classification, fares, now_mode)
        )
    if not formatted:
        return [], []
    earliest = min(range(len(formatted)), key=lambda i: (formatted[i][1], formatted[i][0]["changes"]))
    fewest = min(range(len(formatted)), key=lambda i: (formatted[i][0]["changes"], formatted[i][1]))
    formatted[earliest][0]["labels"].append("EARLIEST_ARRIVAL")
    if fewest != earliest:
        formatted[fewest][0]["labels"].append("FEWEST_CHANGES")
    order = sorted(range(len(formatted)), key=lambda i: (formatted[i][1], formatted[i][0]["changes"]))[:limit]
    used: list[int] = []
    for i in order:
        for feed in formatted[i][2]:
            if feed not in used:
                used.append(feed)
    return [formatted[i][0] for i in order], used


def _sources(net: _Network, used: list[int]) -> list[dict[str, Any]]:
    return [
        {
            "import_id": net.feeds[index].import_id,
            "name": net.feeds[index].source_name,
            "publisher": net.feeds[index].publisher,
            "agency_name": net.feeds[index].agency_name,
        }
        for index in used
    ]


def _no_data_code(classification: str) -> str:
    return "NO_OFFICIAL_DATA" if classification == CLASS_OFFICIAL else "NO_UNVERIFIED_DATA"


def _with_message(result: dict[str, Any], text: str, code: str) -> dict[str, Any]:
    result["message"] = text
    result["message_code"] = code
    return result


def plan_journeys(
    session: Session,
    classification: str,
    *,
    origin_query: str,
    destination_query: str,
    default_zone: str,
    plan: PlanSettings,
    max_changes: int = DEFAULT_MAX_CHANGES,
    limit: int = 5,
    on_date: dt.date | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Options for a journey from a stop matching origin_query to one matching destination_query.

    Give on_date to plan one service date, or now to plan the next three hours from this instant.
    """
    if (on_date is None) == (now is None):
        raise ValueError("Give either on_date or now, not both and not neither.")
    if not 0 <= max_changes <= MAX_CHANGES_LIMIT:
        raise ValueError(f"max_changes must be between 0 and {MAX_CHANGES_LIMIT}.")
    zone, zone_source = sched.service_zone(session, default_zone)
    result: dict[str, Any] = {
        "classification": classification,
        "mode": "date" if on_date is not None else "now",
        "date": on_date.isoformat() if on_date is not None else None,
        "origin_query": origin_query,
        "destination_query": destination_query,
        "max_changes": max_changes,
        "options": [],
        "sources": [],
        "message": None,
        "message_code": None,
        "match_note": None,
        "note": PLAN_NOTE,
        "realtime": False,
        "service_timezone": zone.key,
        "timezone_source": zone_source,
        "assumptions": {
            "min_change_minutes": plan.min_transfer_seconds / 60,
            "max_walk_m": plan.max_walk_m,
            "walk_speed_kmph": round(plan.walk_speed_mps * 3.6, 2),
            "now_window_minutes": NOW_WINDOW_SECONDS // 60,
        },
    }
    origin_key, destination_key = fold(origin_query), fold(destination_query)
    if not origin_key or not destination_key:
        return _with_message(result, "Enter a name for both the origin and the destination.", "NEED_BOTH_STOPS")
    if origin_key == destination_key:
        return _with_message(
            result, "The origin and the destination are the same. Choose two different stops.", "SAME_STOP"
        )

    now_utc = clock.utc_now() if now is None else clock.as_utc(now)
    today = clock.service_date(zone, now_utc)
    if on_date is not None:
        covered_on = on_date
        start = _epoch(zone, on_date)
        horizon_end = _epoch(zone, on_date + ONE_DAY)
        first_day, last_day = on_date - LOOKBACK_DAYS * ONE_DAY, on_date
    else:
        covered_on = today
        start = int(now_utc.timestamp())
        horizon_end = start + NOW_WINDOW_SECONDS
        first_day, last_day = today - LOOKBACK_DAYS * ONE_DAY, today + ONE_DAY

    import_ids = sched.eligible_import_ids(session, classification, on_date=covered_on)
    if not import_ids:
        if classification == CLASS_OFFICIAL:
            text = (
                sched.no_official_date_message(on_date, today)
                if on_date is not None
                else f"No officially verified timetable covers {today.isoformat()}."
            )
        else:
            text = (
                "No unverified feed covers this date."
                if on_date is not None
                else f"No unverified feed covers {today.isoformat()}."
            )
        return _with_message(result, text, _no_data_code(classification))

    net = _network_for(session, classification, import_ids, first_day, last_day, plan)
    origins, origins_cut = _matching_nodes(session, net, import_ids, origin_key)
    destinations, destinations_cut = _matching_nodes(session, net, import_ids, destination_key)
    if origins_cut or destinations_cut:
        result["match_note"] = (
            f"More than {MAX_MATCHES} stops match one of the names. Only the first {MAX_MATCHES} by name are used; "
            "enter a more specific name."
        )
    if not origins:
        return _with_message(result, "No stop matches the origin in this classification's data.", "ORIGIN_NOT_FOUND")
    if not destinations:
        return _with_message(
            result, "No stop matches the destination in this classification's data.", "DESTINATION_NOT_FOUND"
        )
    if not any(net.node_pats[node] or net.foot[node] for node in origins):
        return _with_message(result, "No scheduled trip serves the origin on this date.", "ORIGIN_NOT_SERVED")
    if not any(net.node_pats[node] for node in destinations):
        return _with_message(result, "No scheduled trip serves the destination on this date.", "DESTINATION_NOT_SERVED")

    search = _search(net, origins, start, horizon_end, max_changes + 1, plan.min_transfer_seconds)
    fares = _fare_map(session, import_ids)
    options, used = _options(net, search, destinations, start, classification, fares, limit, now_mode=on_date is None)
    result["options"] = options
    result["sources"] = _sources(net, used)
    if not options:
        if on_date is not None:
            text = f"No journey with up to {max_changes} change(s) was found in this timetable for that date."
        else:
            text = (
                f"No journey with up to {max_changes} change(s) leaves in the next "
                f"{NOW_WINDOW_SECONDS // 3600} hours."
            )
        return _with_message(result, text, "NO_PLANNED_JOURNEY")
    return result
