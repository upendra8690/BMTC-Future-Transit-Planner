"""Measure the journey planner on a generated feed, and print the timings as JSON.

Run from the project folder:
    python scripts/bench_planner.py [STOPS ROUTES TRIPS_PER_ROUTE STOPS_PER_TRIP QUERIES]

The default is 2000 stops, 300 routes, 5 trips per route, 30 stops per trip and 40 queries. The feed is invented: its
stops are random points in a box near Bengaluru. It is loaded into a temporary database that is deleted afterwards, and
the project's own data is not touched. The timings describe this machine and this feed only. They are not a guarantee
for a real city.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.database import Database  # noqa: E402
from app.gtfs.importer import import_feed  # noqa: E402
from app.models import KIND_OFFICIAL, DataSource  # noqa: E402
from app.services import planner  # noqa: E402

from tests.helpers import TODAY, make_settings, zip_of  # noqa: E402

DEFAULTS = (2000, 300, 5, 30, 40)


def read_sizes() -> tuple[int, int, int, int, int]:
    if len(sys.argv) == 1:
        return DEFAULTS
    try:
        values = [int(value) for value in sys.argv[1:]]
    except ValueError:
        values = []
    if len(values) != 5 or min(values) < 1:
        raise SystemExit(
            "usage: bench_planner.py STOPS ROUTES TRIPS_PER_ROUTE STOPS_PER_TRIP QUERIES (each at least 1)"
        )
    return values[0], values[1], values[2], values[3], values[4]


N_STOPS, N_ROUTES, TRIPS_PER_ROUTE, STOPS_PER_TRIP, QUERIES = read_sizes()

# Benchmark data only: a fixed seed makes the feed repeatable. Nothing here is security-sensitive.
rng = random.Random(20261115)  # noqa: S311  # nosec B311

# Stops in a 0.2 x 0.2 degree box (about 22 km square), a little larger than central Bengaluru.
stops = [(12.85 + rng.random() * 0.2, 77.50 + rng.random() * 0.2) for _ in range(N_STOPS)]
t0 = time.perf_counter()
neighbours = []
for i, (lat_i, lon_i) in enumerate(stops):
    dists = sorted(
        ((lat_i - lat) ** 2 + ((lon_i - lon) * math.cos(math.radians(lat_i))) ** 2, j)
        for j, (lat, lon) in enumerate(stops)
        if j != i
    )
    neighbours.append([j for _, j in dists[:20]])
gen_neighbours_s = time.perf_counter() - t0

routes_rows, trips_rows, stop_times_rows = [], [], []
stop_rows = [f"{i},Stop {i:05d},{lat:.6f},{lon:.6f},0" for i, (lat, lon) in enumerate(stops)]
for r in range(N_ROUTES):
    route_id = f"R{r:04d}"
    routes_rows.append(f"{route_id},{r + 1},Route {r + 1},3")
    walk = [rng.randrange(N_STOPS)]
    while len(walk) < STOPS_PER_TRIP:
        options = [j for j in neighbours[walk[-1]] if j not in walk]
        if not options:
            break
        walk.append(rng.choice(options))
    for k in range(TRIPS_PER_ROUTE):
        trip_id = f"{route_id}T{k}"
        trips_rows.append(f"{route_id},ALL,{trip_id},0")
        clock_s = 5 * 3600 + rng.randrange(0, 17 * 3600)
        for seq, stop in enumerate(walk, start=1):
            hh, rem = divmod(clock_s, 3600)
            mm, ss = divmod(rem, 60)
            stamp = f"{hh:02d}:{mm:02d}:{ss:02d}"
            stop_times_rows.append(f"{trip_id},{stamp},{stamp},{stop},{seq}")
            clock_s += rng.randrange(90, 240)

files = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nT,Bench Agency,https://example.invalid,Asia/Kolkata\n",
    "routes.txt": "route_id,route_short_name,route_long_name,route_type\n" + "\n".join(routes_rows) + "\n",
    "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,location_type\n" + "\n".join(stop_rows) + "\n",
    "trips.txt": "route_id,service_id,trip_id,direction_id\n" + "\n".join(trips_rows) + "\n",
    "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n" + "\n".join(stop_times_rows) + "\n",
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "ALL,1,1,1,1,1,1,1,20270101,20271231\n"
    ),
}
data = zip_of(files)

tmp = Path(tempfile.mkdtemp(prefix="bench_"))
settings = make_settings(tmp)
db = Database(settings.database_url)
db.create_schema()
session = db.session()
source = DataSource(name="Bench", publisher="Bench", kind=KIND_OFFICIAL, verified=True, license="test")
session.add(source)
session.commit()

t0 = time.perf_counter()
imp = import_feed(session, data, filename="bench.zip", source=source, settings=settings, today=TODAY)
import_s = time.perf_counter() - t0
if imp.status != "COMPLETED":
    raise SystemExit(f"The benchmark feed was not accepted: {imp.errors}")

plan = planner.PlanSettings(min_transfer_seconds=180, max_walk_m=300, walk_speed_mps=4.8 / 3.6)
# Benchmark data only: a fixed seed chooses the queries. Nothing here is security-sensitive.
rng2 = random.Random(7)  # noqa: S311  # nosec B311
pairs = [
    (f"Stop {rng2.randrange(N_STOPS):05d}", f"Stop {rng2.randrange(N_STOPS):05d}")
    for _ in range(QUERIES)
]
pairs = [(a, b) for a, b in pairs if a != b]


def run(day: dt.date, max_changes: int) -> list[float]:
    timings = []
    for origin, destination in pairs:
        t = time.perf_counter()
        planner.plan_journeys(
            session, "OFFICIAL_VERIFIED", origin_query=origin, destination_query=destination,
            default_zone="Asia/Kolkata", plan=plan, max_changes=max_changes, on_date=day,
        )
        timings.append(time.perf_counter() - t)
    return timings


def stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min_ms": round(ordered[0] * 1000, 1),
        "median_ms": round(ordered[len(ordered) // 2] * 1000, 1),
        "max_ms": round(ordered[-1] * 1000, 1),
    }


planner.clear_network_cache()
cold = run(dt.date(2027, 1, 11), 2)  # the first query builds the network; the rest reuse it
warm = run(dt.date(2027, 1, 11), 2)
other_day = run(dt.date(2027, 1, 12), 2)  # a different date needs its own network
zero_changes = run(dt.date(2027, 1, 11), 0)

options_found = sum(
    1
    for a, b in pairs[:5]
    if planner.plan_journeys(
        session, "OFFICIAL_VERIFIED", origin_query=a, destination_query=b,
        default_zone="Asia/Kolkata", plan=plan, on_date=dt.date(2027, 1, 11),
    )["options"]
)

print(json.dumps({
    "stops": N_STOPS,
    "routes": N_ROUTES,
    "trips": N_ROUTES * TRIPS_PER_ROUTE,
    "stop_time_rows": len(stop_times_rows),
    "zip_bytes": len(data),
    "generate_neighbours_s": round(gen_neighbours_s, 2),
    "import_s": round(import_s, 2),
    "first_query_ms": stats(cold),
    "repeat_same_date_ms": stats(warm),
    "new_date_ms": stats(other_day),
    "zero_changes_ms": stats(zero_changes),
    "options_found": options_found,
}, indent=2))

session.close()
db.dispose()
shutil.rmtree(tmp, ignore_errors=True)
