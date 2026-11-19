"""Browser check of the live-vehicle screens, end to end, with a TEST feed. Never run against the public service.

Usage:  python tests/browser/live_check.py <demo url> <feed port> <real-mode url>

This script serves a GTFS-Realtime test feed on 127.0.0.1:<feed port> (/vp.pb and /tu.pb), built from the pinned
community Metro timetable for the server's own clock: two trains in service, each between two stations, with a
90-second delay. The demonstration server must be started with DEMO_MODE=1, REALTIME_SOURCE_KIND=TEST,
REALTIME_CLASSIFICATION=UNVERIFIED_FEED, REALTIME_POLL_SECONDS=5 and the two feed URLs (see
docs/integrations/LIVE_TRACKING.md). The real-mode server has no feed.

Checks: the TEST label on every live screen, vehicles on the list and the map, the route filter, a vehicle's stops
ahead with live estimates, live arrivals on a stop page, and on the real-mode server "not connected" with no vehicle.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import itertools
import json
import sys
import threading
import time
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests import realtime_feed as rt  # noqa: E402

DEMO = sys.argv[1].rstrip("/") + "/"
PORT = int(sys.argv[2])
REAL = sys.argv[3].rstrip("/") + "/"
ZIP = ROOT / "reference_data" / "namma_metro_community" / "bmrcl-gtfs-f402c4c.zip"
IST = ZoneInfo("Asia/Kolkata")
DELAY = 90
results: list[bool] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f": {str(detail)[:240]}" if not ok else ""))


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - local test servers only
        return json.load(response)


def seconds(text: str) -> int:
    h, m, s = map(int, text.split(":"))
    return h * 3600 + m * 60 + s


def table(z: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig")))


# The server's clock (it may run at a fixed moment), so the feed's times match what the server calls "now".
server_now = dt.datetime.fromisoformat(get_json(DEMO + "api/clock")["now_utc"].replace("Z", "+00:00"))
offset = server_now.timestamp() - time.time()
local = server_now.astimezone(IST)
now_sec = local.hour * 3600 + local.minute * 60 + local.second
midnight = dt.datetime.combine(local.date(), dt.time(0), IST).timestamp()
weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[local.weekday()]
ymd = local.strftime("%Y%m%d")

with zipfile.ZipFile(ZIP) as z:
    services = {c["service_id"] for c in table(z, "calendar.txt")
                if c[weekday] == "1" and c["start_date"] <= ymd <= c["end_date"]}
    trips = {t["trip_id"]: t for t in table(z, "trips.txt") if t["service_id"] in services}
    stops = {s["stop_id"]: s for s in table(z, "stops.txt")}
    calls: dict[str, list[dict[str, str]]] = {}
    for row in table(z, "stop_times.txt"):
        if row["trip_id"] in trips:
            calls.setdefault(row["trip_id"], []).append(row)

chosen = []
seen_routes = set()
for trip_id, rows in sorted(calls.items()):
    rows.sort(key=lambda r: int(r["stop_sequence"]))
    for before, after in itertools.pairwise(rows):
        if seconds(before["departure_time"]) <= now_sec + 60 < seconds(after["arrival_time"]) and \
                trips[trip_id]["route_id"] not in seen_routes and after is not rows[-1]:
            a, b = stops[before["stop_id"]], stops[after["stop_id"]]
            lat = (float(a["stop_lat"]) + float(b["stop_lat"])) / 2
            lon = (float(a["stop_lon"]) + float(b["stop_lon"])) / 2
            chosen.append((trip_id, trips[trip_id]["route_id"], after, lat, lon))
            seen_routes.add(trips[trip_id]["route_id"])
            break
    if len(chosen) == 2:
        break
assert len(chosen) == 2, "no two Metro trains in service at the server's time; start the server during service hours"


def build(kind: str) -> bytes:
    stamp = int(time.time() + offset)
    entities = []
    for n, (trip_id, route_id, nxt, lat, lon) in enumerate(chosen, start=1):
        if kind == "vp":
            entities.append(rt.vehicle(f"v{n}", vehicle_id=f"TEST-{n}", label=f"Test train {n}", trip_id=trip_id,
                                       route_id=route_id, start_date=ymd, lat=lat, lon=lon, timestamp=stamp - 5,
                                       stop_sequence=int(nxt["stop_sequence"]), status=2))
        else:
            entities.append(rt.trip_update(f"u{n}", trip_id=trip_id, route_id=route_id, start_date=ymd,
                                           vehicle_label=f"Test train {n}", timestamp=stamp - 5,
                                           stops=[(int(nxt["stop_sequence"]), nxt["stop_id"], None, DELAY, False)]))
    return rt.feed(stamp, entities)


class Feed(BaseHTTPRequestHandler):
    def do_GET(self):
        body = build("vp" if self.path.startswith("/vp") else "tu")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


feed_server = ThreadingHTTPServer(("127.0.0.1", PORT), Feed)
threading.Thread(target=feed_server.serve_forever, daemon=True).start()


def open_screen(page, base: str, path: str) -> None:
    page.goto("about:blank")
    page.goto(base + "#/" + path, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=20000)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    errors: list[str] = []
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if "Content Security Policy" in msg.text else None)

    api = get_json(DEMO + "api/live/vehicles")
    check("The demonstration server reads the test feed and labels it TEST",
          api["available"] and api["status"]["source_kind"] == "TEST" and len(api["vehicles"]) == 2, api["status"])
    first = api["vehicles"][0]

    open_screen(page, DEMO, "live")
    page.wait_for_selector("#liveList li", timeout=20000)
    check("The live screen says TEST FEED - NOT REAL VEHICLES", "NOT REAL VEHICLES" in page.inner_text("#view"))
    check("Both trains are listed with their route, next station and update age",
          page.locator("#liveList li").count() == 2 and "Next: " in page.inner_text("#liveList")
          and "s ago" in page.inner_text("#liveList"), page.inner_text("#liveList"))
    check("Each train has a progress bar", page.locator("#liveList progress").count() == 2)
    page.wait_for_timeout(800)
    check("Both trains are on the map", page.locator("#liveMap path.leaflet-interactive").count() == 2)
    features = {f["id"]: f for f in get_json(DEMO + "api/features")["features"]}
    check("A test feed never makes live tracking AVAILABLE",
          features["live_tracking"] == {"id": "live_tracking", "state": "UNAVAILABLE", "reason": "TEST_FEED_ONLY"})

    page.fill("#liveFilter [name=route]", first["route"]["number"])
    page.click("#liveFilter button[type=submit]")
    expect(page.locator("#liveList li")).to_have_count(1, timeout=20000)
    check("The route filter keeps only that route", first["route"]["number"] in page.inner_text("#liveList li"))

    page.click("#liveList a:has-text('Details')")
    page.wait_for_selector("#view table", timeout=20000)
    detail = get_json(DEMO + "api/live/vehicles/" + first["vehicle_id"])
    upcoming = detail["upcoming"][0]
    check("Stops ahead show live estimates 90 seconds after the timetable",
          upcoming["kind"] == "LIVE_ESTIMATE" and upcoming["delay_seconds"] == DELAY
          and "Live estimate" in page.inner_text("#view table"), upcoming)
    check("The vehicle page keeps the TEST label and shows the train on a map",
          "NOT REAL VEHICLES" in page.inner_text("#view")
          and page.locator("#liveVehicleMap path.leaflet-interactive").count() == 1)

    page.evaluate("localStorage.setItem('bmtc.classification', 'UNVERIFIED_FEED')")
    open_screen(page, DEMO, f"stops/{first['next_stop']['id']}")
    expect(page.locator("#stopLiveCard")).to_be_visible(timeout=20000)
    live_text = page.inner_text("#stopLiveCard")
    check("The next station's page lists the live arrival, labelled, with the TEST label",
          "Live estimate" in live_text and "NOT REAL VEHICLES" in live_text, live_text)
    check("Scheduled departures on the same page keep their scheduled label",
          "Scheduled times only" in page.inner_text("#view") or "scheduled" in page.inner_text("#view").lower())

    open_screen(page, REAL, "live")
    page.wait_for_selector("text=Not connected", timeout=20000)
    check("On a real-mode server without a feed the screen says Not connected and shows no vehicle",
          page.locator("#liveMap").count() == 0 and page.locator("#liveList").count() == 0)
    page.evaluate("localStorage.setItem('bmtc.classification', 'UNVERIFIED_FEED')")
    open_screen(page, REAL, f"stops/{first['next_stop']['id']}")
    page.wait_for_selector("#stopLiveCard", state="attached", timeout=20000)
    page.wait_for_timeout(1500)
    check("Without a feed the stop page shows no live section", page.is_hidden("#stopLiveCard"))

    wide = browser.new_page(viewport={"width": 320, "height": 800})
    wide.on("pageerror", lambda exc: errors.append(str(exc)))
    open_screen(wide, DEMO, "live")
    wide.wait_for_selector("#liveList li", timeout=20000)
    check("live fits 320 px", wide.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
    check("No script errors and no policy refusals", not errors, errors[:3])
    browser.close()
feed_server.shutdown()

print(f"{sum(results)}/{len(results)} passed on {dt.date.today()}")
sys.exit(0 if all(results) else 1)
