"""Browser check: the stricter style policy breaks nothing, and a journey can start and end at places chosen on the map.

Usage:  python tests/browser/map_and_policy_check.py <url> <admin-key-file>

Run against a real-mode server (community Metro data loaded) during service hours, for example one started with
tests/browser/serve_at.py. Checks: every screen opens with no Content-Security-Policy refusal and no script error;
Metro line chips keep their line colour; on the journey planner "Choose on map" opens a map, the map centre and a tap
both list the nearest real stations, "Start here" and "Go here" fill the form, and the journey is then planned.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1].rstrip("/") + "/"
KEY = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
SCREENS = ("home", "nearby", "journey", "live", "tickets", "metro", "favourites", "account", "more", "upcoming",
           "assistant", "providers", "routes", "stops", "scenarios", "compare", "sources", "admin", "more/sos",
           "more/airport")
results: list[bool] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f": {str(detail)[:240]}" if not ok else ""))


def open_screen(page, path: str) -> None:
    page.goto("about:blank")
    page.goto(BASE + "#/" + path, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=20000)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    errors: list[str] = []
    refused: list[str] = []
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: refused.append(msg.text) if "Content Security Policy" in msg.text else None)

    for screen in SCREENS:
        open_screen(page, screen)
        page.wait_for_timeout(900)
    open_screen(page, "admin")
    page.fill("#adminKeyForm [name=key]", KEY)
    page.click("#adminKeyForm button[type=submit]")
    page.wait_for_selector("#adminAudit tr, #adminAudit .empty", timeout=20000)
    open_screen(page, "home")
    page.wait_for_selector("#homeMap.leaflet-container", timeout=20000)
    page.wait_for_timeout(1500)
    check(f"{len(SCREENS)} screens, the admin screen and the home map open with no style or script refusal",
          not refused, refused[:3])

    # Only the community Metro feed is loaded, so choose its label, as a passenger would.
    page.evaluate("localStorage.setItem('bmtc.classification', 'UNVERIFIED_FEED')")
    open_screen(page, "metro")
    page.wait_for_selector("#metroStations .line-chip", timeout=20000)
    chip = page.locator("#metroStations .line-chip").first
    wanted = chip.get_attribute("data-colour")
    painted = chip.evaluate("el => el.style.borderColor")
    check("Metro line chips keep their line colour without a style attribute",
          wanted and wanted.startswith("#") and painted.startswith("rgb") and chip.get_attribute("style") is not None,
          (wanted, painted))

    open_screen(page, "journey")
    page.click("[data-action=map-pick]")
    page.wait_for_selector("#pickMap.leaflet-container", timeout=20000)
    check("Choose on map opens a map", page.get_attribute("[data-action=map-pick]", "aria-expanded") == "true")
    page.click("[data-action=map-centre]")
    page.wait_for_selector("#pickResults li", timeout=20000)
    first = page.locator("#pickResults [data-action=pick-origin]").first.get_attribute("data-name")
    check("The map centre lists the nearest stations with their distance",
          page.locator("#pickResults li").count() >= 1 and " m away" in page.inner_text("#pickResults"),
          page.inner_text("#pickResults"))
    page.locator("#pickResults [data-action=pick-origin]").first.click()
    expect(page.locator("#journeyForm [name=origin]")).to_have_value(first)
    check("Start here fills the start", True)

    box = page.locator("#pickMap").bounding_box()
    # A point east of the centre: the city's east, where the Purple line runs (Indiranagar side at zoom 12).
    page.mouse.click(box["x"] + box["width"] * 0.80, box["y"] + box["height"] * 0.45)
    page.wait_for_timeout(1500)
    expect(page.locator("#pickResults li").first).to_be_visible(timeout=20000)
    second = page.locator("#pickResults [data-action=pick-destination]").first.get_attribute("data-name")
    check("A tap on the map lists stations near that point", bool(second) and second != first, (first, second))
    page.locator("#pickResults [data-action=pick-destination]").first.click()
    expect(page.locator("#journeyForm [name=destination]")).to_have_value(second)
    check("Go here fills the destination", True)
    markers = page.locator("#pickMap path.leaflet-interactive").count()
    check("Markers show the tapped point and the stations", markers >= 2, markers)

    page.click("#journeyForm button[type=submit]")
    page.wait_for_selector("#journeyResults .option, #journeyResults .empty, #journeyResults .banner", timeout=30000)
    check("The journey between the two chosen places is planned",
          page.locator("#journeyResults .option").count() >= 1, page.inner_text("#journeyResults")[:300])
    page.click("[data-action=map-pick]")
    check("The map closes again", page.is_hidden("#pickMapBox"))

    for width in (320, 1366):
        wide = browser.new_page(viewport={"width": width, "height": 800})
        wide.on("pageerror", lambda exc: errors.append(str(exc)))
        open_screen(wide, "journey")
        wide.click("[data-action=map-pick]")
        wide.wait_for_selector("#pickMap.leaflet-container", timeout=20000)
        fits = wide.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        check(f"journey with map fits {width} px", fits)
        wide.close()
    check("No script errors and no policy refusals", not errors and not refused, (errors + refused)[:3])
    browser.close()

print(f"{sum(results)}/{len(results)} passed on {dt.date.today()}")
sys.exit(0 if all(results) else 1)
