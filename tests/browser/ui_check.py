"""Browser checks for the planner dashboard, driven through Chrome against a running server.

Normally started by tests/browser/run_browser_checks.py, which builds the demo data and starts the server.
To run it by hand, first start the server and import the synthetic demo feed, then set:

  BMTC_BASE_URL      address of the running server, for example http://127.0.0.1:8000
  BMTC_ADMIN_KEY     the server's ADMIN_API_KEY
  BMTC_BACKUP_DIR    the server's BACKUP_DIR (the backup check looks for a new file there)
  BMTC_OUT_DIR       optional: folder for screenshots (default: a bmtc_ui folder in the system temp folder)
  BMTC_CHROME        optional: path to Chrome or Chromium (default: the Chromium that Playwright installed)

Prints PASS or FAIL for each check. The exit code is 1 when a check fails, 0 when all pass, 2 for setup problems.
Map tiles come from the internet. When the machine is offline, tile failures are counted and reported separately
and do not fail a check.
"""

from __future__ import annotations

import glob
import os
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


def _wait_for_function_without_eval(self, expression, arg=None, timeout=15000, **_kwargs):
    """Playwright's wait_for_function evaluates its predicate as a string inside the page, which the
    dashboard's Content-Security-Policy blocks ('unsafe-eval' is not allowed). This replacement polls
    with page.evaluate, which runs the expression as a function through the DevTools protocol."""
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
CHROME = os.environ.get("BMTC_CHROME", "")
PAGES = ["routes", "stops", "journey", "scenarios", "compare", "sources", "admin"]

results: list[tuple[str, bool]] = []
other_problems: list[str] = []
offline_tile_failures: list[str] = []
expected_unauthorized: list[str] = []
# True only while the deliberately wrong admin key is in use, so its 401 responses are not reported as problems.
expect_401 = {"on": False}


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
        url = msg.location.get("url", "") if msg.location else ""
        if expect_401["on"] and "status of 401" in msg.text:
            return  # the browser logs the same deliberate 401 that on_response already counts
        if is_tile(url) or "ERR_NAME_NOT_RESOLVED" in msg.text or "ERR_INTERNET_DISCONNECTED" in msg.text:
            offline_tile_failures.append(f"[{label}] {msg.text} {url}")
        else:
            other_problems.append(f"[{label}] console error: {msg.text} {url}")

    def on_request_failed(req):
        if is_tile(req.url):
            offline_tile_failures.append(f"[{label}] {req.url} {req.failure}")
        else:
            other_problems.append(f"[{label}] request failed: {req.url} {req.failure}")

    def on_response(res):
        if res.status < 400:
            return
        if res.status == 401 and expect_401["on"] and "/api/admin/" in res.url:
            expected_unauthorized.append(res.url)
            return
        other_problems.append(f"[{label}] HTTP {res.status} {res.request.method} {res.url}")

    page.on("console", on_console)
    page.on("pageerror", lambda err: other_problems.append(f"[{label}] page error: {err}"))
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)
    page.on("dialog", lambda dialog: dialog.accept())


def sidebar_open(page):
    return "open" in (page.get_attribute("#sidebar", "class") or "").split()


def overflow_px(page):
    return page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


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


def desktop_checks(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 860})
    page = ctx.new_page()
    watch(page, "desktop")

    # Routes: official is empty for 2027 and says why; unverified covers the whole year.
    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#yearStatus .banner")
    banner = page.inner_text("#yearStatus")
    check("year banner says no officially verified timetable exists for 2027",
          "No officially verified timetable" in banner, banner[:200])
    check("year banner says the unverified feed covers all of 2027",
          "covers all of 2027" in banner, banner[:200])
    page.wait_for_function(
        "(() => { const b = document.querySelector('#routeResults');"
        " return b && !b.innerText.includes('Searching'); })()",
        timeout=15000,
    )
    official = page.inner_text("#routeResults")
    check("official route list is empty and explains why",
          "No officially verified timetable" in official, official[:200])

    page.click('button[data-cls="UNVERIFIED_FEED"]')
    page.wait_for_function("document.querySelectorAll('#routeResults li').length > 0", timeout=15000)
    titles = page.locator("#routeResults .title").all_inner_texts()
    check("unverified list shows both demo routes", "DEMO-1" in titles and "DEMO-2" in titles, str(titles))
    page.screenshot(path=str(OUT / "desktop_routes.png"))

    # Route detail and timetable: Friday 1 January 2027 has 33 weekday trips in each of 2 directions.
    page.click('#routeResults li a[href^="#/routes/"]')
    page.wait_for_selector("#timetable table tbody tr", timeout=20000)
    trip_rows = page.locator("#timetable tbody tr").count()
    check("DEMO-1 timetable on Friday 1 January 2027 lists 66 trips", trip_rows == 66, str(trip_rows))
    check("route map draws the planned path and stops",
          page.locator("#routeMap path.leaflet-interactive").count() > 0)
    page.click('button[data-action="save-route"]')
    page.wait_for_function("!document.getElementById('toast').hidden", timeout=5000)
    check("saving a route confirms on screen", "saved" in page.inner_text("#toast").lower(),
          page.inner_text("#toast"))
    page.screenshot(path=str(OUT / "desktop_route_detail.png"))

    # Stops: six demo stops, then a name search narrows the list.
    page.goto(BASE + "/#/stops", wait_until="load")
    page.wait_for_function("document.querySelectorAll('#stopResults li').length > 0", timeout=15000)
    check("stops list shows the six demo stops", page.locator("#stopResults li").count() == 6)
    check("stops map is created", page.locator("#stopMap.leaflet-container").count() == 1)
    page.fill('#stopSearch input[name="q"]', "Junction")
    page.press('#stopSearch input[name="q"]', "Enter")
    page.wait_for_function("document.querySelectorAll('#stopResults li').length === 1", timeout=10000)
    check("stop search narrows to Demo Junction", "Demo Junction" in page.inner_text("#stopResults"))

    # Direct journeys on Monday 11 January 2027: Demo Central to Demo Junction, 33 departures.
    page.goto(BASE + "/#/journey", wait_until="load")
    page.wait_for_selector('#journeyForm input[name="origin"]')
    page.fill('#journeyForm input[name="origin"]', "Demo Central")
    page.fill('#journeyForm input[name="destination"]', "Demo Junction")
    page.fill('#journeyForm input[name="date"]', "2027-01-11")
    page.click('#journeyForm button[type="submit"]')
    page.wait_for_selector("#journeyResults table tbody tr", timeout=15000)
    journeys = page.locator("#journeyResults tbody tr").count()
    check("direct journeys are listed for a Monday", journeys == 33, str(journeys))

    # Scenarios: create two estimated scenarios, one with an intermediate stop.
    page.goto(BASE + "/#/scenarios", wait_until="load")
    page.click('button[data-action="scn-new"]')
    page.wait_for_selector('#scenarioForm input[name="name"]')
    fill_scenario(page, "Test proposal A", "PROP-001",
                  ("Demo Central", 12.975, 77.595), ("Demo Junction", 12.998, 77.624), 15)
    page.click('button[data-action="scn-add-stop"]')
    page.fill('#scnStops input[data-stop="0"][data-field="name"]', "Demo Market")
    page.fill('#scnStops input[data-stop="0"][data-field="lat"]', "12.979")
    page.fill('#scnStops input[data-stop="0"][data-field="lon"]', "77.6")
    page.click('#scenarioForm button[type="submit"]')
    page.wait_for_function("document.querySelectorAll('#scnList li').length === 1", timeout=10000)
    item = page.inner_text("#scnList")
    check("first scenario is saved with an estimate and the estimate label",
          "Test proposal A" in item and "Estimate:" in item and "n/a km" not in item, item[:200])
    check("scenario list labels the item as an estimated scenario",
          "Estimated scenario" in page.inner_text("#scnList"))

    page.click('button[data-action="scn-new"]')
    page.wait_for_selector('#scenarioForm input[name="name"]')
    fill_scenario(page, "Test proposal B", "PROP-002",
                  ("Demo Central", 12.975, 77.595), ("Demo Junction", 12.998, 77.624), 30)
    page.click('#scenarioForm button[type="submit"]')
    page.wait_for_function("document.querySelectorAll('#scnList li').length === 2", timeout=10000)
    check("second scenario is saved", True)
    page.screenshot(path=str(OUT / "desktop_scenarios.png"))

    # Compare: the two scenarios side by side, and the planning-year table.
    page.goto(BASE + "/#/compare", wait_until="load")
    page.wait_for_function("document.querySelectorAll('#cmpA option').length >= 2", timeout=10000)
    page.click('button[data-action="cmp-run"]')
    page.wait_for_selector("#cmpResult table tbody tr", timeout=10000)
    cmp_text = page.inner_text("#cmpResult")
    check("comparison lists distance, journey time and departures",
          all(word in cmp_text for word in ["Distance", "Journey time", "Departures per day"]), cmp_text[:200])
    check("planning-year table has one row per planning year",
          page.locator("#yearsCompare tbody tr").count() == 4)

    # Sources: the demo source is shown as synthetic, never as official.
    page.goto(BASE + "/#/sources", wait_until="load")
    page.wait_for_selector("text=Sources in use", timeout=10000)
    src = page.inner_text("#view")
    check("sources page shows the demo source as SYNTHETIC_DEMO and not verified",
          "kind: SYNTHETIC_DEMO" in src and "Not verified by an administrator" in src, src[:300])

    # Administration: wrong key refused, right key works, verify disabled for non-official, backup written.
    page.goto(BASE + "/#/admin", wait_until="load")
    page.wait_for_selector("#adminKeyInput")
    expect_401["on"] = True
    page.fill("#adminKeyInput", "wrong-key-0000000000")
    page.click('button[data-action="admin-key-save"]')
    page.wait_for_selector("#adminBody .banner.error", timeout=10000)
    check("a wrong admin key is refused",
          "Invalid or missing admin key" in page.inner_text("#adminBody .banner.error"))
    page.fill("#adminKeyInput", ADMIN_KEY)
    page.click('button[data-action="admin-key-save"]')
    page.wait_for_selector("#adminSources table tbody tr", timeout=10000)
    expect_401["on"] = False
    check("verify is disabled for a non-OFFICIAL source",
          page.get_attribute('button[data-action="src-verify"]', "disabled") is not None)
    check("the import is listed as completed", "COMPLETED" in page.inner_text("#adminImports"))
    check("the audit log shows recorded actions", page.locator("#adminAudit tbody tr").count() >= 2)
    page.click('button[data-action="backup"]')
    page.wait_for_function(
        "document.getElementById('toast').innerText.includes('Backup written')", timeout=10000
    )
    backups = glob.glob(str(BACKUP_DIR / "planner_backup_*.db"))
    check("a SQLite backup file was written", len(backups) == 1, str(backups))
    page.screenshot(path=str(OUT / "desktop_admin.png"))

    # Service worker and manifest.
    manifest = page.request.get(BASE + "/manifest.webmanifest")
    ctype = manifest.headers.get("content-type", "")
    check("manifest is served with a JSON or manifest content type",
          "json" in ctype or "manifest" in ctype, ctype)
    registrations = page.evaluate("async () => (await navigator.serviceWorker.getRegistrations()).length")
    check("service worker is registered", registrations >= 1, str(registrations))
    ctx.close()


def phone_checks(browser, playwright):
    ctx = browser.new_context(**playwright.devices["Pixel 7"])
    page = ctx.new_page()
    watch(page, "phone")

    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector("#navToggle")
    check("phone shows a menu button", page.is_visible("#navToggle"))
    check("menu starts closed on a phone", not sidebar_open(page))
    page.click("#navToggle")
    check("tapping the menu button opens navigation", sidebar_open(page))
    page.screenshot(path=str(OUT / "phone_menu.png"))
    page.click('#sidebar a[href="#/stops"]')
    page.wait_for_timeout(500)
    check("choosing a page closes the menu", not sidebar_open(page))

    for name in PAGES:
        page.goto(f"{BASE}/#/{name}", wait_until="load")
        page.wait_for_timeout(700)
        overflow = overflow_px(page)
        check(f"phone page has no sideways scrolling: {name}", overflow <= 1, f"{overflow}px")

    page.goto(BASE + "/#/routes", wait_until="load")
    page.wait_for_selector('button[data-cls="UNVERIFIED_FEED"]')
    page.click('button[data-cls="UNVERIFIED_FEED"]')
    page.wait_for_function("document.querySelectorAll('#routeResults li').length > 0", timeout=15000)
    page.click('#routeResults li a[href^="#/routes/"]')
    page.wait_for_selector("#timetable table tbody tr", timeout=20000)
    page.screenshot(path=str(OUT / "phone_route_detail.png"))
    overflow = overflow_px(page)
    check("phone route detail fits the screen width", overflow <= 1, f"{overflow}px")
    ctx.close()


def main() -> int:
    if not ADMIN_KEY:
        print("error: set BMTC_ADMIN_KEY to the server's ADMIN_API_KEY", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Screenshots will be written to: {OUT}")

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

    passed = sum(1 for _, ok in results if ok)
    failed = [name for name, ok in results if not ok]
    print(f"\n{passed} passed, {len(failed)} failed")
    print(f"deliberate 401 responses from the wrong-key check (expected): {len(expected_unauthorized)}")
    print(f"map-tile requests that failed (expected when the machine has no internet): {len(offline_tile_failures)}")
    for line in offline_tile_failures[:3]:
        print("   ", line)
    print(f"other browser problems: {len(other_problems)}")
    for line in other_problems:
        print("   ", line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
