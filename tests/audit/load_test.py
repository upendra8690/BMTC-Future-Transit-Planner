"""Concurrent load test against the test server (rate limit raised for this test only). Usage: python load_test.py"""
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE = "http://127.0.0.1:8030"
CLS = {"classification": "UNVERIFIED_FEED"}
c = httpx.Client(base_url=BASE, timeout=60)
route_id = c.get("/api/routes", params={**CLS, "q": "DEMO-1"}).json()["results"][0]["id"]
stop_id = c.get("/api/stops", params={**CLS, "q": "Demo Market"}).json()["results"][0]["id"]

MIX = [
    ("route search", "/api/routes", {**CLS, "q": "DEMO"}),
    ("stop search", "/api/stops", {**CLS, "q": "Demo"}),
    ("route detail", f"/api/routes/{route_id}", CLS),
    ("timetable", f"/api/routes/{route_id}/timetable", {**CLS, "date": "2027-01-04"}),
    ("departures", f"/api/stops/{stop_id}/departures", CLS),
    ("routes at stop", f"/api/stops/{stop_id}/routes", CLS),
    ("metro stations", "/api/metro/stations", CLS),
    ("bus+metro plan", "/api/plan", {**CLS, "origin": "Demo Lake View", "destination": "Demo Metro Hub", "date": "2027-01-04"}),
    ("features", "/api/features", {}),
]


def one(i):
    name, path, params = MIX[i % len(MIX)]
    with httpx.Client(base_url=BASE, timeout=60) as cl:
        t0 = time.perf_counter()
        r = cl.get(path, params=params)
        return name, r.status_code, (time.perf_counter() - t0) * 1000


for workers, total in ((1, 90), (20, 900)):
    order = list(range(total))
    random.Random(7).shuffle(order)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(one, order))
    wall = time.perf_counter() - t0
    errors = [r for r in rows if r[1] != 200]
    lat = sorted(r[2] for r in rows)
    print(f"\n{workers} concurrent users, {total} requests in {wall:.1f}s = {total / wall:.0f} req/s, errors: {len(errors)}")
    print(f"  all: p50 {statistics.median(lat):.0f} ms, p95 {lat[int(len(lat) * 0.95) - 1]:.0f} ms, max {lat[-1]:.0f} ms")
    by = {}
    for name, _, ms in rows:
        by.setdefault(name, []).append(ms)
    for name, values in by.items():
        values.sort()
        print(f"  {name:15} p50 {statistics.median(values):6.0f} ms  p95 {values[int(len(values) * 0.95) - 1]:6.0f} ms")
