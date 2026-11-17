"""Browser checks for the planner dashboard, driven through Chrome against a running server.

Normally started by tests/browser/run_browser_checks.py, which builds the demo data and starts the server.
To run it by hand, start the server with a fresh database, import the synthetic demo feed, then set:

  BMTC_BASE_URL      address of the running server, for example http://127.0.0.1:8000
  BMTC_ADMIN_KEY     the server's ADMIN_API_KEY
  BMTC_BACKUP_DIR    the server's BACKUP_DIR (the backup check looks for a new file there)
  BMTC_UPLOAD_ZIP    a GTFS ZIP whose dates do not overlap the demo feed (the upload check imports it, then removes it)
  BMTC_OUT_DIR       optional: folder for screenshots and downloads (default: a bmtc_ui folder in the temp folder)
  BMTC_CHROME        optional: path to Chrome or Chromium (default: the Chromium that Playwright installed)

Prints PASS or FAIL for each check. The exit code is 1 when a check fails, 0 when all pass, 2 for setup problems.
Map tiles come from the internet. Tile failures are counted and reported separately and never fail a check.
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


def _wait_for_function_without_eval(self, expression, arg=None, timeout=15000, **_kwargs):
    """Playwright's wait_for_function evaluates its predicate as a string inside the page, which the
    dashboard's Content-Security-Policy blocks ('unsafe-eval' is not allowed). This replacement polls
    with page.evaluate, which runs the expression through the DevTools protocol. Pass an expression,
    not an arrow function."""
    deadline = time.time() + timeout / 1000
    last_error = None
    while True:
        try:
            if self.evaluate(f"() => ({expression})"):
                return
        except Exception as exc:  # the page may still be navigating: keep polling until the deadline
            last_error = exc
        if time.time() > deadline:
            raise TimeoutError(f"condition not met within {timeout} ms: {expression} (last error: {last_error!r})")
        self.wait_for_timeout(150)


Page.wait_for_function = _wait_for_function_without_eval

BASE = os.environ.get("BMTC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
OUT = Path(os.environ.get("BMTC_OUT_DIR") or Path(tempfile.gettempdir()) / "bmtc_ui")
ADMIN_KEY = os.environ.get("BMTC_ADMIN_KEY", "")
BACKUP_DIR = Path(os.environ.get("BMTC_BACKUP_DIR") or OUT / "backups")
UPLOAD_ZIP = Path(os.environ.get("BMTC_UPLOAD_ZIP") or "")
CHROME = os.environ.get("BMTC_CHROME", "")
PAGES = ["routes", "stops", "journey", "scenarios", "compare", "sources", "admin"]
ORIGIN = ("Demo Central", 12.975, 77.595)
DESTINATION = ("Demo Junction", 12.998, 77.624)
DEVICE_LOCATION = {"latitude": 12.975, "longitude": 77.595}  # the device stands at Demo Central
XSS_NAME = '<img src=x alt="bmtc-xss-probe">'
TIMETABLE_HEADER = [
    "classification", "route_number", "date", "trip_id", "headsign",
    "stop_sequence", "stop", "arrival", "departure",
]
EXPECTED_404 = ("/api/routes/999999",)

results: list[tuple[str, bool]] = []
other_problems: list[str] = []
offline_tile_failures: list[str] = []
offline_request_failures: list[str] = []
expected_unauthorized: list[str] = []
expected_missing: list[str] = []
expected_rejected: list[str] = []
# Switches that are on only while a deliberate failure is under way, so that the failure is not reported as a problem.
expect = {"401": False, "422": False, "offline": False}


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    line = ("PASS " if ok else "FAIL ") + name
    if not ok and detail:
        line += f"  -- {detail}"
    print(line, flush=True)


def is_tile(url):
    return "tile.openstreetmap.org" in (url or "")


def watch(page, label):
    def on_console(msg):
        if msg.type != "error":
            return
        text = msg.text
        # Failed requests and HTTP errors are reported by the request and response handlers below.
        if "net::ERR_" in text or "the server responded with a status of" in text:
            return
        url = msg.location.get("url", "") if msg.location else ""
        other_problems.append(f"[{label}] console error: {text} {url}")

    def on_request_failed(req):
        if is_tile(req.url):
            offline_tile_failures.append(f"[{label}] {req.url} {req.failure}")
        elif expect["offline"]:
            offline_request_failures.append(f"[{label}] {req.url} {req.failure}")
        else:
            other_problems.append(f"[{label}] request failed: {req.url} {req.failure}")

    def on_response(res):
        if res.status < 400:
            return
        if is_tile(res.url):
            offline_tile_failures.append(f"[{label}] HTTP {res.status} {res.url}")
            return
        if res.status == 401 and expect["401"] and "/api/admin/" in res.url:
            expected_unauthorized.append(res.url)
            return
        if res.status == 404 and any(part in res.url for part in EXPECTED_404):
            expected_missing.append(res.url)
            return
        if res.status == 422 and expect["422"] and "/api/admin/imports" in res.url:
            expected_rejected.append(res.url)
            return
        other_problems.append(f"[{label}] HTTP {res.status} {res.request.method} {res.url}")

    page.on("console", on_console)
    def on_page_error(err):
        # Keep the page's route and the start of the stack, so the place that threw can be found.
        route = page.url.split("#", 1)[-1] if "#" in page.url else page.url
        stack = (getattr(err, "stack", "") or "").replace("\n", " | ")[:700]
        other_problems.append(f"[{label}] page error on {route}: {err} :: {stack}")

    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)
    page.on("dialog", lambda dialog: dialog.accept())


def js(value):
    """A JavaScript literal for value, so that it can be placed inside an expression safely."""
    return json.dumps(value, ensure_ascii=False)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


@contextmanager
def guarded(page, name):
    """A step that breaks is reported as a failed check, and the remaining steps still run."""
    try:
        yield
    except Exception as exc:  # every failure is reported; none stops the run
        shot = OUT / f"failed_{slug(name)}.png"
        try:
            page.screenshot(path=str(shot))
            where = f"; screenshot {shot}"
        except Exception:  # the page may be gone; the check still fails
            where = ""
        message = (str(exc).strip().splitlines() or [""])[0][:300]
        check(f"{name}: the step finished", False, f"{type(exc).__name__}: {message}{where}")


def sidebar_open(page):
    return "open" in (page.get_attribute("#sidebar", "class") or "").split()


def overflow_px(page):
    return page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


def save_download(download, label):
    target = OUT / f"{label}_{download.suggested_filename}"
    download.save_as(str(target))
    return target, download.suggested_filename


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def is_pdf(path):
    data = Path(path).read_bytes()
    return data.startswith(b"%PDF") and b"%%EOF" in data[-1024:]


def fill_scenario(page, name, code, origin, destination, frequency=None):
    form = "#scenarioForm"
    page.fill(f'{form} input[name="name"]', name)
    page.fill(f'{form} input[name="route_code"]', code)
    if frequency is not None:
        page.fill(f'{form} input[name="frequency_minutes"]', str(frequency))
    page.fill(f'{form} input[name="origin_name"]', origin[0])
    page.fill(f'{form} input[name="origin_lat"]', str(origin[1]))
    page.fill(f'{form} input[name="origin_lon"]', str(origin[2]))
    page.fill(f'{form} input[name="destination_name"]', destination[0])
    page.fill(f'{form} input[name="destination_lat"]', str(destination[1]))
    page.fill(f'{form} input[name="destination_lon"]', str(destination[2]))


def storage_check(page, label):
    keys = page.evaluate("() => Object.keys(localStorage)")
    values = page.evaluate("() => Object.values(localStorage)")
    stray = [key for key in keys if not key.startswith("bmtc.")]
    check(f"browser storage holds only the planner's own keys ({label})", not stray, str(stray))
    check(f"the admin key is never written to browser storage ({label})",
          not any(ADMIN_KEY in value for value in values))


# ---------------------------------------------------------------- desktop sections

def routes_section(page):
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#yearStatus .banner")
    banner = page.inner_text("#yearStatus")
    check("year banner says no officially verified timetable exists for 2027",
          "No officially verified timetable" in banner, banner[:200])
    check("year banner says the unverified feed covers all of 2027", "covers all of 2027" in banner, banner[:200])
    page.wait_for_function("document.querySelectorAll('#routeResults li, #routeResults .empty').length > 0",
                           timeout=15000)
    official = page.inner_text("#routeResults")
    check("official route list says no official timetable is loaded",
          "No official verified timetable data" in official, official[:200])

    page.click('button[data-cls="UNVERIFIED_FEED"]')
    page.wait_for_function("document.querySelectorAll('#routeResults li').length > 0", timeout=15000)
    titles = page.locator("#routeResults .title").all_inner_texts()
    check("unverified list shows both demo routes", "DEMO-1" in titles and "DEMO-2" in titles, str(titles))
    page.screenshot(path=str(OUT / "desktop_routes.png"))

    # Friday 1 January 2027 has 33 weekday trips in each direction of DEMO-1.
    page.locator("#routeResults li", has_text="DEMO-1").locator('a[href^="#/routes/"]').click()
    page.wait_for_selector("#timetable table tbody tr", timeout=20000)
    trips = page.locator("#timetable tbody tr").count()
    check("DEMO-1 timetable on Friday 1 January 2027 lists 66 trips", trips == 66, str(trips))
    check("route map draws the planned path", page.locator("#routeMap path.leaflet-interactive").count() > 0)
    page.screenshot(path=str(OUT / "desktop_route_detail.png"))

    with page.expect_download() as info:
        page.click('button[data-action="tt-csv"]')
    path, name = save_download(info.value, "timetable")
    rows = read_csv(path)
    check("timetable CSV has the expected columns", bool(rows) and rows[0] == TIMETABLE_HEADER, str(rows[:1]))
    check("timetable CSV is named for the planned date", name.endswith(".csv") and "2027-01-01" in name, name)
    trip_ids = {row[3] for row in rows[1:] if len(row) > 3}
    check("timetable CSV lists the same 66 trips", len(trip_ids) == 66, str(len(trip_ids)))

    page.click('button[data-action="save-route"]')
    page.wait_for_function("!document.getElementById('toast').hidden", timeout=10000)
    page.goto(BASE + "/#/routes", wait_until="load")
    listed = (
        "document.getElementById('savedRoutes') &&"
        " document.getElementById('savedRoutes').innerText.includes('DEMO-1')"
    )
    page.wait_for_function(listed, timeout=15000)
    check("a saved route is listed on the routes page", True)
    page.reload(wait_until="load")
    page.wait_for_function(listed, timeout=15000)
    check("the saved route is still listed after a reload", True)

    page.goto(BASE + "/#/routes/999999", wait_until="load")
    page.wait_for_function(
        "document.getElementById('view').innerText.includes('That route is not in the current data.')",
        timeout=15000,
    )
    check("an unknown route says it is not in the current data", True)


def clock_section(page):
    clock = page.request.get(BASE + "/api/clock").json()
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_function(
        "!!document.getElementById('serviceClock') &&"
        " !document.getElementById('serviceClock').innerText.startsWith('Reading')",
        timeout=15000,
    )
    text = page.inner_text("#serviceClock")
    day = dt.date.fromisoformat(clock["service_date"])
    check("clock bar names the time zone of the feed", f"({clock['service_timezone']})" in text, text)
    check("clock bar shows the weekday of the service date", day.strftime("%A") in text, text)
    check("clock bar shows the service date",
          str(day.year) in text and re.search(rf"\b{day.day}\b", text) is not None, text)
    notice = page.inner_text(".site-note")
    check("every page says the planner is unofficial and not affiliated with BMTC or any operator",
          "not affiliated with" in notice and "Unofficial" in notice, notice)


def stops_section(page):
    page.goto(BASE + "/#/stops", wait_until="load")
    page.wait_for_function("document.querySelectorAll('#stopResults li').length > 0", timeout=15000)
    check("stops list shows the six demo stops", page.locator("#stopResults li").count() == 6)
    check("stops map is created", page.locator("#stopMap.leaflet-container").count() == 1)
    page.fill('#stopSearch input[name="q"]', "Junction")
    page.press('#stopSearch input[name="q"]', "Enter")
    page.wait_for_function("document.querySelectorAll('#stopResults li').length === 1", timeout=10000)
    check("stop search narrows to Demo Junction", "Demo Junction" in page.inner_text("#stopResults"))
    # The stop list is kept for offline reading. A search with typed words is not: its copy would record those words.
    kept = page.evaluate(
        """async () => {
          for (let i = 0; i < 50; i++) {
            const cache = await caches.open("bmtc-planner-timetable-v1");
            const urls = (await cache.keys()).map((request) => request.url);
            if (urls.some((url) => url.includes("/api/stops"))) return urls;
            await new Promise((resolve) => setTimeout(resolve, 100));
          }
          return [];
        }"""
    )
    check("the stop list is kept for offline reading", any("/api/stops?" in url for url in kept), f"{len(kept)} kept")
    check("a stop search with typed words is not kept on the device",
          not any(re.search(r"[?&]q=[^&]", url) for url in kept),
          ", ".join(url for url in kept if re.search(r"[?&]q=[^&]", url)))
    page.click('button[data-action="nearby-me"]')
    page.wait_for_function(
        "document.querySelectorAll('#stopResults li').length > 0 &&"
        " document.getElementById('stopResults').innerText.includes('Demo Central')",
        timeout=15000,
    )
    check("nearby stops from the device location include Demo Central", True)


AXE_SOURCE = Path(__file__).resolve().parent / "vendor" / "axe-core" / "axe.min.js"
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]


def scan(page, label, problems):
    """Run axe-core on the page now. The library is run through evaluate,
        because the page's policy blocks script tags."""
    if not page.evaluate("typeof axe !== 'undefined'"):
        page.evaluate(AXE_SOURCE.read_text(encoding="utf-8"))
    violations = page.evaluate(
        """async (tags) => {
            const result = await axe.run(document, { runOnly: { type: "tag", values: tags } });
            return result.violations.map((v) => ({
                id: v.id, impact: v.impact || "", help: v.help, nodes: v.nodes.length,
                targets: v.nodes.slice(0, 2).map((n) => n.target.join(" "))
            }));
        }""",
        AXE_TAGS,
    )
    for item in violations:
        problems.append(f"{label}: {item['id']} ({item['impact']}, {item['nodes']} element(s)) {item['targets']}")


def keyboard_section(page):
    """Keyboard use: the skip link keeps the page, focus shows, Enter presses a filter, arrow keys move in a group."""
    filter_button = 'button[data-action="cls"][data-cls="UNVERIFIED_FEED"]'
    # A new document, so that Tab starts at the top of the page rather than where the previous page left focus.
    page.goto("about:blank")
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#yearStatus .banner")
    page.bring_to_front()
    page.evaluate("window.focus(); document.activeElement && document.activeElement.blur()")
    page.keyboard.press("Tab")
    first = page.evaluate(
        "(() => { const a = document.activeElement; return a ? a.tagName + ' ' + a.className : 'nothing'; })()"
    )
    check("the first Tab press lands on the skip link", first.startswith("A skip-link"), first)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    where = page.evaluate("location.hash")
    focused = page.evaluate("document.activeElement && document.activeElement.id")
    check("following the skip link keeps the page and moves focus into the content",
          where.startswith("#/routes") and focused == "main", where + " focus: " + str(focused))

    page.goto("about:blank")
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#yearStatus .banner")
    page.bring_to_front()
    page.locator(filter_button).focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    outline = page.evaluate(
        "(() => { const s = getComputedStyle(document.activeElement);"
        " return s.outlineStyle + ' ' + parseFloat(s.outlineWidth); })()"
    )
    check("a button reached by the keyboard shows a visible focus ring",
          outline.startswith("solid") and float(outline.split()[1]) >= 2, outline)
    page.keyboard.press("Enter")
    page.wait_for_function(
        "document.querySelector('button[data-action=\"cls\"][data-cls=\"UNVERIFIED_FEED\"]')"
        ".getAttribute('aria-pressed') === 'true'",
        timeout=10000,
    )
    check("Enter presses a filter button", True)

    page.goto(BASE + "/#/journey", wait_until="load")
    page.wait_for_selector('#journeyForm input[name="changes"]')
    page.focus('#journeyForm input[name="changes"][value="2"]')
    page.keyboard.press("ArrowLeft")
    checked = page.evaluate("document.querySelector('#journeyForm input[name=\"changes\"]:checked').value")
    check("arrow keys move between the change choices", checked == "1", checked)


def update_notice_section(page):
    """When a new version of the app takes over, the page says that a reload shows it."""
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#yearStatus .banner")
    controlled = page.evaluate("!!(navigator.serviceWorker && navigator.serviceWorker.controller)")
    check("this page is controlled by the service worker, so the update notice can be tested", controlled)
    if not controlled:
        return
    page.evaluate("navigator.serviceWorker.dispatchEvent(new Event('controllerchange'))")
    page.wait_for_function("document.getElementById('toast').innerText.includes('Reload the page')", timeout=10000)
    check("a new version taking over shows the reload notice", True)


def accessibility_section(page):
    """Automated accessibility checks (axe-core, WCAG 2.1 AA and best practice) on every main view.

    Screen-reader use is not covered here: it needs a person with a screen reader, and it is reported as not verified.
    """
    problems: list[str] = []
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#yearStatus .banner")
    scan(page, "routes, official data", problems)
    page.click('button[data-cls="UNVERIFIED_FEED"]')
    page.wait_for_function("document.querySelectorAll('#routeResults li').length > 0", timeout=15000)
    scan(page, "routes, unverified data", problems)
    page.locator('#routeResults a[href^="#/routes/"]').first.click()
    page.wait_for_selector("#timetable table tbody tr", timeout=20000)
    scan(page, "route detail with timetable", problems)
    for label, path in [
        ("stops", "/#/stops"),
        ("journey planner", "/#/journey"),
        ("future scenarios", "/#/scenarios"),
        ("compare", "/#/compare"),
        ("data sources", "/#/sources"),
        ("administration", "/#/admin"),
    ]:
        page.goto(BASE + path, wait_until="load")
        page.wait_for_timeout(700)
        scan(page, label, problems)
    check("automated accessibility checks find no violations on any main view (axe-core, WCAG 2.1 AA)",
          not problems, " | ".join(problems)[:1500])


def map_left_at_once(page):
    """A map is fitted to its markers with an animation. Leaving the page straight after must not raise a map error."""
    before = sum("_leaflet_pos" in problem for problem in other_problems)
    page.goto(BASE + "/#/stops", wait_until="load")
    page.wait_for_function("document.querySelectorAll('#stopResults li').length > 0", timeout=15000)
    page.fill('#stopSearch input[name="q"]', "Demo")
    page.press('#stopSearch input[name="q"]', "Enter")
    page.wait_for_function("document.querySelectorAll('#stopResults li').length === 6", timeout=10000)
    page.goto(BASE + "/#/journey", wait_until="load")
    page.wait_for_timeout(800)
    after = sum("_leaflet_pos" in problem for problem in other_problems)
    check("leaving a fitted map at once raises no map error", after == before, str(after - before))


def journey_section(page):
    page.goto(BASE + "/#/journey", wait_until="load")
    page.wait_for_selector('#journeyForm input[name="origin"]')
    check("the journey date stays disabled until On a date is chosen",
          page.is_disabled('#journeyForm input[name="date"]'))
    check("the journey form offers no change, up to one change and up to two changes",
          page.locator('#journeyForm input[name="changes"]').count() == 3)
    page.fill('#journeyForm input[name="origin"]', ORIGIN[0])
    page.fill('#journeyForm input[name="destination"]', DESTINATION[0])
    page.check('#journeyForm input[name="when"][value="date"]')
    page.fill('#journeyForm input[name="date"]', "2027-01-11")
    page.click('#journeyForm button[type="submit"]')
    page.wait_for_selector("#journeyResults li.option", timeout=15000)
    options = page.locator("#journeyResults li.option").count()
    results = page.inner_text("#journeyResults")
    check("journeys are listed for Monday 11 January 2027, at most five options",
          1 <= options <= 5, str(options))
    check("the result says live vehicle information is unavailable and times are scheduled",
          "Live vehicle information is currently unavailable" in results and "scheduled data, not live tracking"
          in results, results[:200])
    check("the result labels the earliest arrival", "Earliest arrival" in results, results[:200])
    page.check('#journeyForm input[name="changes"][value="0"]')
    page.click('#journeyForm button[type="submit"]')
    page.wait_for_selector("#journeyResults li.option", timeout=15000)
    direct = page.inner_text("#journeyResults")
    check("with no change allowed, no option has a change",
          "1 change" not in direct and "2 changes" not in direct, direct[:200])


def scenario_count(page):
    return page.locator("#scnList li").count()


def scenarios_section(page):
    page.goto(BASE + "/#/scenarios", wait_until="load")
    page.wait_for_selector('button[data-action="scn-new"]', timeout=15000)
    page.wait_for_selector("#scnList", state="attached", timeout=15000)
    start = scenario_count(page)

    page.click('button[data-action="scn-new"]')
    page.wait_for_selector('#scenarioForm input[name="name"]')
    fill_scenario(page, "Test proposal A", "PROP-001", ORIGIN, DESTINATION, 15)
    page.click('button[data-action="scn-add-stop"]')
    page.fill('#scnStops input[data-stop="0"][data-field="name"]', "Demo Market")
    page.fill('#scnStops input[data-stop="0"][data-field="lat"]', "12.979")
    page.fill('#scnStops input[data-stop="0"][data-field="lon"]', "77.6")
    page.click('#scenarioForm button[type="submit"]')
    page.wait_for_function(f"document.querySelectorAll('#scnList li').length === {start + 1}", timeout=15000)
    item = page.inner_text("#scnList")
    check("first scenario is saved with an estimate and the estimate label",
          "Test proposal A" in item and "Estimate:" in item and "n/a km" not in item, item[:200])
    check("scenario list labels the item as an estimated scenario", "Estimated scenario" in item)

    page.click('button[data-action="scn-new"]')
    page.wait_for_selector('#scenarioForm input[name="name"]')
    fill_scenario(page, "Test proposal bad times", "PROP-003", ORIGIN, DESTINATION, 15)
    page.fill('#scenarioForm input[name="first_departure"]', "10:00")
    page.fill('#scenarioForm input[name="last_departure"]', "08:00")
    page.click('#scenarioForm button[type="submit"]')
    page.wait_for_function(
        "!!document.getElementById('scnError') &&"
        " document.getElementById('scnError').innerText.includes('cannot be earlier')",
        timeout=10000,
    )
    check("a last departure before the first is refused on screen", True)
    page.click('button[data-action="scn-cancel"]')
    page.wait_for_function(f"document.querySelectorAll('#scnList li').length === {start + 1}", timeout=10000)
    check("the refused scenario was not saved", True)

    page.locator("#scnList li", has_text="Test proposal A").locator('button[data-action="scn-edit"]').click()
    page.wait_for_selector('#scenarioForm input[name="name"]')
    page.fill('#scenarioForm input[name="name"]', "Test proposal A edited")
    page.click('#scenarioForm button[type="submit"]')
    page.wait_for_function("document.getElementById('scnList').innerText.includes('Test proposal A edited')",
                           timeout=15000)
    check("an edited scenario keeps its estimate", "Estimate:" in page.inner_text("#scnList"))

    page.click('button[data-action="scn-new"]')
    page.wait_for_selector('#scenarioForm input[name="name"]')
    fill_scenario(page, "Test proposal B", "PROP-002", ORIGIN, DESTINATION, 30)
    page.click('#scenarioForm button[type="submit"]')
    page.wait_for_function(f"document.querySelectorAll('#scnList li').length === {start + 2}", timeout=15000)
    check("second scenario is saved", True)

    page.click('button[data-action="scn-new"]')
    page.wait_for_selector('#scenarioForm input[name="name"]')
    fill_scenario(page, XSS_NAME, "PROP-004", ORIGIN, DESTINATION, 20)
    page.click('#scenarioForm button[type="submit"]')
    page.wait_for_function(f"document.querySelectorAll('#scnList li').length === {start + 3}", timeout=15000)
    shown = page.inner_text("#scnList")
    check("a scenario name containing HTML is shown as plain text, not as markup",
          page.locator("#scnList img").count() == 0 and "bmtc-xss-probe" in shown)
    page.locator("#scnList li", has_text="bmtc-xss-probe").locator('button[data-action="scn-del"]').click()
    page.wait_for_function(f"document.querySelectorAll('#scnList li').length === {start + 2}", timeout=15000)
    check("the test scenario with HTML in its name can be deleted", True)
    page.screenshot(path=str(OUT / "desktop_scenarios.png"))

    with page.expect_download() as info:
        page.click('button[data-action="scn-csv"]')
    path, name = save_download(info.value, "scenarios")
    rows = read_csv(path)
    names = {row[1] for row in rows[1:] if len(row) > 1}
    check("scenario CSV is named for estimated scenarios", name.endswith(".csv") and "scenario" in name, name)
    check("scenario CSV lists the saved proposals", {"Test proposal A edited", "Test proposal B"} <= names, str(names))

    with page.expect_download() as info:
        page.locator("#scnList li", has_text="Test proposal A edited").locator('button[data-action="scn-pdf"]').click()
    path, name = save_download(info.value, "scenario")
    check("scenario PDF downloads as a PDF", name.endswith(".pdf") and is_pdf(path), name)


def compare_section(page):
    page.goto(BASE + "/#/compare", wait_until="load")
    page.wait_for_function("document.querySelectorAll('#cmpA option').length >= 2", timeout=15000)
    page.click('button[data-action="cmp-run"]')
    page.wait_for_selector("#cmpResult table tbody tr", timeout=15000)
    cmp_text = page.inner_text("#cmpResult")
    check("comparison lists distance, journey time and departures",
          all(word in cmp_text for word in ["Distance", "Journey time", "Departures per day"]), cmp_text[:200])
    with page.expect_download() as info:
        page.click('button[data-action="cmp-pdf"]')
    path, name = save_download(info.value, "comparison")
    check("comparison PDF downloads as a PDF", name.endswith(".pdf") and is_pdf(path), name)
    page.wait_for_function("document.querySelectorAll('#yearsCompare tbody tr').length === 4", timeout=15000)
    check("planning-year table has one row per planning year", True)


def sources_section(page):
    page.goto(BASE + "/#/sources", wait_until="load")
    page.wait_for_selector("#sourceList li", timeout=15000)
    src = page.inner_text("#sourceList")
    check("sources page names the demo source's kind as SYNTHETIC_DEMO",
          re.search(r"Kind:\s*SYNTHETIC_DEMO", src) is not None, src[:300])
    check("the demo source is labelled as not verified by an administrator",
          "Not verified by an administrator." in src, src[:300])


def admin_section(page):
    page.goto(BASE + "/#/admin", wait_until="load")
    page.wait_for_selector('#adminKeyForm input[name="key"]', timeout=15000)
    expect["401"] = True
    page.fill('#adminKeyForm input[name="key"]', "wrong-key-0000000000")
    page.click('#adminKeyForm button[type="submit"]')
    page.wait_for_function("document.getElementById('toast').innerText.includes('was not accepted')", timeout=10000)
    expect["401"] = False
    check("a wrong admin key is refused with a message", True)
    check("a wrong key does not open administration", page.locator("#adminSources").count() == 0)

    page.fill('#adminKeyForm input[name="key"]', ADMIN_KEY)
    page.click('#adminKeyForm button[type="submit"]')
    page.wait_for_selector("#adminSources table tbody tr", timeout=15000)
    check("the right admin key opens administration", True)
    check("verify is disabled for a non-OFFICIAL source",
          page.get_attribute('button[data-action="src-verify"]', "disabled") is not None)
    page.wait_for_function("document.getElementById('adminImports').innerText.includes('Completed')", timeout=15000)
    check("the demo import is listed as Completed", True)
    page.wait_for_function("document.querySelectorAll('#adminAudit tbody tr').length >= 2", timeout=15000)
    check("the audit log records the actions taken", True)
    page.fill('#sourceForm input[name="name"]', "Browser evidence source")
    page.fill('#sourceForm input[name="publisher"]', "Test publisher")
    page.fill('#sourceForm input[name="license"]', "test")
    page.select_option('#sourceForm select[name="kind"]', "OFFICIAL")
    page.click('#sourceForm button[type="submit"]')
    page.wait_for_function(
        "document.getElementById('adminSources').innerText.includes('Browser evidence source')", timeout=15000
    )
    evidence_row = page.locator("#adminSources tr", has_text="Browser evidence source")
    evidence_row.locator('button[data-action="src-verify"]').click()
    page.wait_for_selector("#sourceDecisionForm:not([hidden])", timeout=5000)
    check("verifying asks for the evidence on the page",
          "Record the evidence" in page.inner_text("#sourceDecisionForm"))
    page.click('#sourceDecisionForm button[data-action="decision-cancel"]')
    check("cancelling leaves the source not verified",
          page.is_hidden("#sourceDecisionForm") and "Not verified" in evidence_row.inner_text())
    evidence_row.locator('button[data-action="src-verify"]').click()
    page.wait_for_selector("#sourceDecisionForm:not([hidden])", timeout=5000)
    page.keyboard.press("Escape")
    check("the Escape key closes the decision without changing the source",
          page.is_hidden("#sourceDecisionForm") and "Not verified" in evidence_row.inner_text())
    focused = page.evaluate("document.activeElement && document.activeElement.getAttribute('data-action')")
    check("closing the decision returns focus to the button that opened it", focused == "src-verify", str(focused))
    evidence_row.locator('button[data-action="src-verify"]').click()
    page.wait_for_selector("#sourceDecisionForm:not([hidden])", timeout=5000)
    page.fill('#sourceDecisionForm input[name="note"]', "Checked the publisher page on 16 November 2026")
    page.click('#sourceDecisionForm button[type="submit"]')
    page.wait_for_function(
        "[...document.querySelectorAll('#adminSources tr')].some(r => r.innerText.includes('Browser evidence source')"
        " && r.innerText.includes('Verified'))",
        timeout=15000,
    )
    check("a verification with evidence marks the source Verified", True)
    check("the verification keeps the evidence note on the source",
          "Checked the publisher page"
          in page.locator("#adminSources tr", has_text="Browser evidence source").inner_text())
    page.locator("#adminSources tr", has_text="Browser evidence source").locator(
        'button[data-action="src-revoke"]').click()
    page.wait_for_selector("#sourceDecisionForm:not([hidden])", timeout=5000)
    check("revoking asks for the reason on the page", "Reason for revoking" in page.inner_text("#sourceDecisionForm"))
    page.fill('#sourceDecisionForm input[name="note"]', "Browser check revokes the test source")
    page.click('#sourceDecisionForm button[type="submit"]')
    page.wait_for_function(
        "[...document.querySelectorAll('#adminSources tr')].some(r => r.innerText.includes('Browser evidence source')"
        " && r.innerText.includes('Not verified'))",
        timeout=15000,
    )
    check("revoking returns the source to Not verified", True)
    storage_check(page, "while the admin key is in use")

    page.click('button[data-action="backup"]')
    page.wait_for_function("document.getElementById('toast').innerText.includes('Backup written')", timeout=60000)
    backups = glob.glob(str(BACKUP_DIR / "planner_backup_*.db"))
    check("a SQLite backup file was written", len(backups) == 1, str(backups))
    page.screenshot(path=str(OUT / "desktop_admin.png"))

    page.set_input_files('#uploadForm input[name="file"]', str(UPLOAD_ZIP))
    page.click('#uploadForm button[type="submit"]')
    page.wait_for_function(
        "!!document.getElementById('uploadResult') &&"
        " document.getElementById('uploadResult').innerText.includes('Feed imported')",
        timeout=120000,
    )
    check("a feed for other dates is validated and imported", True)
    check("the import report gives the fare count", "Fare prices in this feed" in page.inner_text("#uploadResult"))
    page.wait_for_function(f"document.getElementById('adminImports').innerText.includes({js(UPLOAD_ZIP.name)})",
                           timeout=15000)
    page.locator("#adminImports tr", has_text=UPLOAD_ZIP.name).locator('button[data-action="import-delete"]').click()
    page.wait_for_function(
        f"!document.getElementById('adminImports').innerText.includes({js(UPLOAD_ZIP.name)})", timeout=15000
    )
    check("the uploaded test feed can be removed", True)
    check("the demo import is still listed after the removal",
          "Completed" in page.inner_text("#adminImports"))
    expect["422"] = True
    page.set_input_files('#uploadForm input[name="file"]', files=[
        {"name": "broken.zip", "mimeType": "application/zip", "buffer": b"this is not a zip archive"},
    ])
    page.click('#uploadForm button[type="submit"]')
    page.wait_for_function(
        "!!document.getElementById('uploadResult') &&"
        " document.getElementById('uploadResult').innerText.includes('Nothing from this feed was stored')",
        timeout=60000,
    )
    expect["422"] = False
    check("a file that is not a valid feed is refused, and the report says nothing was stored", True)

    page.click('button[data-action="admin-key-clear"]')
    page.wait_for_function("document.getElementById('adminSources') === null", timeout=10000)
    check("forgetting the key hides the administration data", True)
    storage_check(page, "after the key is forgotten")


def language_section(page):
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#langSelect option", state="attached")  # options are never "visible" to Playwright
    page.select_option("#langSelect", "en")
    page.wait_for_function("document.documentElement.lang === 'en'", timeout=10000)
    english_nav = page.inner_text('#sidebar a[href="#/routes"]').strip()
    for code, font in (("kn", "Noto Sans Kannada"), ("te", "Noto Sans Telugu"), ("hi", "Noto Sans Devanagari")):
        page.select_option("#langSelect", code)
        page.wait_for_function(f"document.documentElement.lang === {js(code)}", timeout=10000)
        nav = page.inner_text('#sidebar a[href="#/routes"]').strip()
        family = page.evaluate("() => getComputedStyle(document.documentElement).fontFamily")
        direction = page.evaluate("() => document.documentElement.dir")
        check(f"{code}: the navigation is translated", bool(nav) and nav != english_nav, nav)
        check(f"{code}: the Indic font stack is applied to the page", font in family, family)
        check(f"{code}: text still runs left to right", direction == "ltr", direction)
    page.select_option("#langSelect", "en")
    page.wait_for_function("document.documentElement.lang === 'en'", timeout=10000)
    check("switching back to English restores the navigation",
          page.inner_text('#sidebar a[href="#/routes"]').strip() == english_nav)


def saved_copy_section(ctx, page):
    """A timetable opened online can be read offline. The page says it is a saved copy, and the note goes
    away online."""
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#yearStatus .banner")
    page.click('button[data-cls="UNVERIFIED_FEED"]')
    page.wait_for_function("document.querySelectorAll('#routeResults li').length > 0", timeout=15000)
    page.locator('#routeResults a[href^="#/routes/"]').first.click()
    page.wait_for_selector("#timetable table tbody tr", timeout=20000)
    online_rows = page.locator("#timetable table tbody tr").count()
    check("a timetable opened online has rows to save", online_rows > 0, str(online_rows))
    expect["offline"] = True
    try:
        ctx.set_offline(True)
        page.reload(wait_until="load")
        page.wait_for_function("!document.getElementById('savedBanner').hidden", timeout=20000)
        rows = page.locator("#timetable table tbody tr").count()
        check("the saved timetable is shown offline with the same rows",
              rows == online_rows, f"{rows} of {online_rows}")
        notice = page.inner_text("#savedBanner")
        check("the offline timetable says it is a saved copy with the time it was saved",
              "saved copy" in notice.lower() and "scheduled" in notice.lower(), notice[:200])
    finally:
        ctx.set_offline(False)
        expect["offline"] = False
    page.reload(wait_until="load")
    page.wait_for_function("document.getElementById('savedBanner').hidden", timeout=20000)
    check("the saved-copy note goes away once the server answers again", True)


def offline_section(ctx, page):
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#offlineBanner", state="attached")
    expect["offline"] = True
    try:
        ctx.set_offline(True)
        page.wait_for_function("!document.getElementById('offlineBanner').hidden", timeout=10000)
        check("the offline banner appears when the connection drops", page.is_visible("#offlineBanner"))

        # A search nobody made online, so no saved copy of it exists and the error is the expected answer.
        page.fill('#routeSearch input[name="q"]', "ZZ-NEVER-SEARCHED")
        page.press('#routeSearch input[name="q"]', "Enter")
        page.wait_for_selector("#routeResults .banner.error", timeout=15000)
        check("a search made while offline shows an error with a retry button, not a blank page",
              page.locator("#routeResults .banner.error button").count() == 1)

        ctx.set_offline(False)
        page.wait_for_function("document.getElementById('offlineBanner').hidden", timeout=10000)
        check("the offline banner hides when the connection returns", not page.is_visible("#offlineBanner"))
        page.click("#routeResults .banner.error button")
        page.wait_for_function(
            "document.querySelectorAll('#routeResults .banner.error').length === 0 &&"
            " document.querySelectorAll('#routeResults li, #routeResults .empty').length > 0",
            timeout=15000,
        )
        check("retrying after reconnecting loads the list", True)

        ctx.set_offline(True)
        page.reload(wait_until="load")  # the service worker serves the app shell from its cache
        page.wait_for_selector('#sidebar a[href="#/routes"]', state="attached", timeout=15000)
        check("the app shell loads from the cache while the browser is offline", True)
        ctx.set_offline(False)
        page.wait_for_timeout(1000)  # late failure events from the offline window arrive before the switch goes off
    finally:
        ctx.set_offline(False)
        expect["offline"] = False


def install_section(page):
    manifest = page.request.get(BASE + "/manifest.webmanifest")
    ctype = manifest.headers.get("content-type", "")
    data = manifest.json()
    check("manifest is served with a manifest or JSON content type", "json" in ctype or "manifest" in ctype, ctype)
    check("manifest declares English, left-to-right and standalone display",
          data.get("lang") == "en" and data.get("dir") == "ltr" and data.get("display") == "standalone",
          str({key: data.get(key) for key in ("lang", "dir", "display")}))
    sizes = {icon.get("sizes") for icon in data.get("icons", [])}
    check("manifest has 192 and 512 pixel icons", {"192x192", "512x512"} <= sizes, str(sizes))
    registrations = page.evaluate("async () => (await navigator.serviceWorker.getRegistrations()).length")
    check("service worker is registered", registrations >= 1, str(registrations))
    storage_check(page, "at the end of the desktop checks")


def desktop_checks(browser):
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 860},
        permissions=["geolocation"],
        geolocation=DEVICE_LOCATION,
    )
    page = ctx.new_page()
    watch(page, "desktop")
    steps = [
        ("routes", routes_section),
        ("service clock", clock_section),
        ("stops", stops_section),
        ("map left at once", map_left_at_once),
        ("journeys", journey_section),
        ("scenarios", scenarios_section),
        ("compare", compare_section),
        ("sources", sources_section),
        ("administration", admin_section),
        ("keyboard", keyboard_section),
        ("update notice", update_notice_section),
        ("accessibility", accessibility_section),
        ("languages", language_section),
        ("saved timetable offline", lambda p: saved_copy_section(ctx, p)),
        ("offline banner", None),
        ("install and storage", install_section),
    ]
    for name, step in steps:
        with guarded(page, name):
            if step is None:
                offline_section(ctx, page)
            else:
                step(page)
    ctx.close()


# ---------------------------------------------------------------- phone sections

def phone_checks(browser, playwright):
    ctx = browser.new_context(**playwright.devices["Pixel 7"])
    page = ctx.new_page()
    watch(page, "phone")

    with guarded(page, "phone menu"):
        page.goto(BASE + "/#/routes", wait_until="load")
        page.wait_for_selector("#navToggle")
        check("phone shows a menu button", page.is_visible("#navToggle"))
        check("menu starts closed on a phone", not sidebar_open(page))
        page.click("#navToggle")
        check("tapping the menu button opens navigation", sidebar_open(page))
        # The drawer slides in over 0.2 s. Wait for the slide to finish so the picture shows the open menu.
        page.wait_for_function(
            "getComputedStyle(document.getElementById('sidebar')).transform === 'none'", timeout=5000
        )
        page.screenshot(path=str(OUT / "phone_menu.png"))
        page.keyboard.press("Escape")
        page.wait_for_function("!document.getElementById('sidebar').classList.contains('open')", timeout=5000)
        check("the Escape key closes the menu", not sidebar_open(page))
        page.click("#navToggle")
        page.click('#sidebar a[href="#/stops"]')
        page.wait_for_function("!document.getElementById('sidebar').classList.contains('open')", timeout=5000)
        check("choosing a page closes the menu", not sidebar_open(page))

    for name in PAGES:
        with guarded(page, f"phone page {name}"):
            page.goto(f"{BASE}/#/{name}", wait_until="load")
            page.wait_for_timeout(800)
            overflow = overflow_px(page)
            check(f"phone page has no sideways scrolling: {name}", overflow <= 1, f"{overflow}px")

    with guarded(page, "phone scenario form"):
        page.goto(BASE + "/#/scenarios", wait_until="load")
        page.click('button[data-action="scn-new"]')
        page.wait_for_selector('#scenarioForm input[name="name"]')
        overflow = overflow_px(page)
        check("phone scenario form fits the screen width", overflow <= 1, f"{overflow}px")
        page.click('button[data-action="scn-cancel"]')

    with guarded(page, "phone route detail"):
        page.goto(BASE + "/#/routes", wait_until="load")
        page.wait_for_selector('button[data-cls="UNVERIFIED_FEED"]')
        page.click('button[data-cls="UNVERIFIED_FEED"]')
        page.wait_for_function("document.querySelectorAll('#routeResults li').length > 0", timeout=15000)
        page.locator("#routeResults li", has_text="DEMO-1").locator('a[href^="#/routes/"]').click()
        page.wait_for_selector("#timetable table tbody tr", timeout=20000)
        page.screenshot(path=str(OUT / "phone_route_detail.png"))
        overflow = overflow_px(page)
        check("phone route detail fits the screen width", overflow <= 1, f"{overflow}px")

    for code in ("kn", "te", "hi"):
        with guarded(page, f"phone language {code}"):
            page.goto(BASE + "/#/routes", wait_until="load")
            page.select_option("#langSelect", code)
            page.wait_for_function(f"document.documentElement.lang === {js(code)}", timeout=10000)
            page.wait_for_selector("#routeResults li, #routeResults .empty", timeout=15000)
            overflow = overflow_px(page)
            check(f"{code}: the routes page has no sideways scrolling on a phone", overflow <= 1, f"{overflow}px")
            page.select_option("#langSelect", "en")
            page.wait_for_function("document.documentElement.lang === 'en'", timeout=10000)
    ctx.close()


def main() -> int:
    if not ADMIN_KEY:
        print("error: set BMTC_ADMIN_KEY to the server's ADMIN_API_KEY", file=sys.stderr)
        return 2
    if not UPLOAD_ZIP.is_file():
        print("error: set BMTC_UPLOAD_ZIP to a GTFS ZIP file whose dates do not overlap the demo feed", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Screenshots and downloads will be written to: {OUT}")

    with sync_playwright() as playwright:
        launch_options = {"headless": True}
        if CHROME:
            launch_options["executable_path"] = CHROME
        browser = playwright.chromium.launch(**launch_options)
        try:
            desktop_checks(browser)
            phone_checks(browser, playwright)
        finally:
            browser.close()

    check("no unexpected browser errors, uncaught exceptions or failed requests", not other_problems,
          "; ".join(other_problems[:3]))
    passed = sum(1 for _, ok in results if ok)
    failed = [name for name, ok in results if not ok]
    print(f"\n{passed} passed, {len(failed)} failed")
    print(f"deliberate 401 responses from the wrong-key check (expected): {len(expected_unauthorized)}")
    print(f"deliberate 404 responses from the unknown-route check (expected): {len(expected_missing)}")
    print(f"deliberately refused uploads (expected): {len(expected_rejected)}")
    print(f"requests that failed while the browser was set offline (expected): {len(offline_request_failures)}")
    print(f"map-tile requests that failed (expected when the machine has no internet): {len(offline_tile_failures)}")
    for line in offline_tile_failures[:3]:
        print("   ", line)
    print(f"other browser problems: {len(other_problems)}")
    for line in other_problems[:20]:
        print("   ", line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
