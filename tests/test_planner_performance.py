"""Timing guards for journey planning and stop search on a generated feed of 2,000 stops.

The limits are deliberately generous, so a slow machine does not fail them. They catch a change that makes the common
case several times slower. Measured values are in docs/TEST_RESULTS.md, from scripts/bench_planner.py.
"""

from __future__ import annotations

import datetime as dt
import random
import statistics
import time

from app.models import CLASS_OFFICIAL
from app.services import planner
from app.services import schedule as sched

from tests.helpers import build_transit_feed, load_transit_feed

COLD_LIMIT_S = 5.0  # the first query for a date builds that date's network
WARM_MEDIAN_LIMIT_S = 0.25  # later queries for the same date reuse the network
SEARCH_LIMIT_S = 0.5  # one stop-name search over 2,000 stops
DAY = dt.date(2027, 1, 11)
PLAN = planner.PlanSettings(min_transfer_seconds=180, max_walk_m=300, walk_speed_mps=4.8 / 3.6)


def generated_feed(
    stops: int = 2000, routes: int = 60, trips_per_route: int = 4, stops_per_trip: int = 20
) -> tuple[bytes, list[str]]:
    """The feed, and the names of the stops that its trips serve. Random numbers here only shape test data."""
    rng = random.Random(11)  # noqa: S311 - reproducible test data, not used for anything security-related
    coordinates = {
        f"S{i:05d}": (f"Stop {i:05d}", 12.85 + rng.random() * 0.2, 77.50 + rng.random() * 0.2) for i in range(stops)
    }
    ids = list(coordinates)
    route_ids = {f"R{r:03d}": str(r + 1) for r in range(routes)}
    trips = []
    for route in route_ids:
        visited: list[str] = []
        while len(visited) < stops_per_trip:
            candidate = rng.choice(ids)
            if candidate not in visited:
                visited.append(candidate)
        for k in range(trips_per_route):
            clock = 5 * 3600 + rng.randrange(0, 16 * 3600)
            calls = []
            for stop in visited:
                hours, remainder = divmod(clock, 3600)
                minutes, seconds = divmod(remainder, 60)
                calls.append((stop, f"{hours:02d}:{minutes:02d}:{seconds:02d}"))
                clock += rng.randrange(90, 240)
            trips.append((f"{route}-T{k}", route, calls))
    served = sorted({coordinates[stop][0] for _, _, calls in trips for stop, _ in calls})
    return build_transit_feed(coordinates, route_ids, trips), served


def test_planning_and_stop_search_stay_within_their_timing_limits(database, settings):
    data, served = generated_feed()
    # Pairs of stops that the trips serve, so every query runs the full search and none stops early.
    pairs = [(served[i], served[-1 - i]) for i in range(21)]
    with database.session() as session:
        load_transit_feed(session, settings, data, name="Generated")

        origin, destination = pairs[0]
        start = time.perf_counter()
        first = planner.plan_journeys(
            session, CLASS_OFFICIAL, origin_query=origin, destination_query=destination,
            default_zone="Asia/Kolkata", plan=PLAN, on_date=DAY,
        )
        cold = time.perf_counter() - start
        assert first["message_code"] in (None, "NO_PLANNED_JOURNEY")
        assert cold < COLD_LIMIT_S, f"the first planning query took {cold:.2f} s"

        warm = []
        for origin, destination in pairs[1:]:
            start = time.perf_counter()
            planner.plan_journeys(
                session, CLASS_OFFICIAL, origin_query=origin, destination_query=destination,
                default_zone="Asia/Kolkata", plan=PLAN, on_date=DAY,
            )
            warm.append(time.perf_counter() - start)
        median = statistics.median(warm)
        assert median < WARM_MEDIAN_LIMIT_S, f"the median planning query took {median:.3f} s"

        start = time.perf_counter()
        found = sched.search_stops(session, CLASS_OFFICIAL, year=2027, query="stop 0", limit=20)
        search = time.perf_counter() - start
        assert found
        assert search < SEARCH_LIMIT_S, f"the stop search took {search:.3f} s"
