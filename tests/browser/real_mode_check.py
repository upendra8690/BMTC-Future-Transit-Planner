"""Browser check of a REAL-mode server (DEMO_MODE off), as the public service runs, at phone size.

    python tests/browser/real_mode_check.py http://127.0.0.1:8040/

It reads only; nothing on the server changes. The server must have the community Namma Metro timetable loaded
(scripts/load_community_metro.py, which the container start script runs).
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") + "/"
results: list[bool] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f": {str(detail)[:240]}" if not ok else ""))


def open_screen(page, path: str) -> None:
    page.goto("about:blank")
    page.goto(BASE + "#/" + path, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=15000)


def plan(page, origin: str, destination: str, mode: str) -> str:
    open_screen(page, "journey")
    page.fill("#journeyForm [name=origin]", origin)
    page.fill("#journeyForm [name=destination]", destination)
    page.check(f"#journeyForm [name=modes][value={mode}]")
    page.click("#journeyForm button[type=submit]")
    page.locator("#journeyResults .option, #journeyResults .empty, #journeyResults .banner").first.wait_for(
        timeout=20000)
    return page.inner_text("#journeyResults")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    errors: list[str] = []

    # The default view is officially verified data, of which there is none: the app says so and invents nothing.
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    text = plan(page, "Indiranagar", "Jayanagar", "metro")
    check("default view: no officially verified journey is invented", page.locator("#journeyResults .option").count()
          == 0, text[:200])
    check("no demonstration banner on a real-mode server", page.locator("#demoBanner").is_hidden())

    # The unverified view shows the real community Metro timetable, labelled.
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script("try { localStorage.setItem('bmtc.classification', 'UNVERIFIED_FEED'); } catch (e) {}")
    page = ctx.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    text = plan(page, "Indiranagar", "Jayanagar", "metro")
    rides = page.locator("#journeyResults .option").first.locator(".leg.ride")
    check("a real Metro journey Indiranagar to Jayanagar is found", rides.count() >= 1, text[:200])
    check("it ends at Jayanagar, not Vijayanagar", "to Jayanagar" in rides.last.inner_text(), rides.last.inner_text())
    check("every ride is labelled Unverified feed",
          page.locator("#journeyResults .option").first.locator(".leg.ride .badge.unverified").count() == rides.count())
    check("every ride says its times are approximate",
          all("Approximate times" in rides.nth(i).inner_text() for i in range(rides.count())))
    check("the community source is named", "community reconstruction" in text)
    check("no fare is shown as a price", "INR" not in text and "Fare: not" in text, text[-300:])
    check("the journey fits a 390 px screen",
          page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))

    text = plan(page, "Demo Central", "Demo Junction", "all")
    check("invented demo stops are not found", page.locator("#journeyResults .option").count() == 0, text[:200])

    open_screen(page, "metro")
    page.fill("#metroSearch input", "Majestic")
    page.press("#metroSearch input", "Enter")
    page.locator("#metroStations li", has_text="Majestic").first.wait_for(timeout=15000)
    stations = page.locator("#metroStations li")
    first = stations.first.inner_text()
    check("Metro station search finds Majestic once, on the Purple and Green lines",
          stations.count() == 1 and "Purple" in first and "Green" in first, [stations.nth(i).inner_text()
                                                                             for i in range(stations.count())])

    open_screen(page, "providers")
    page.locator("text=community project").first.wait_for(timeout=15000)
    body = page.inner_text("#view")
    check("the data screen names the community source and its ODbL licence",
          "Not verified by the operator" in body and "ODbL" in body)
    check("the data screen does not call the data demonstration-only", "Only demonstration data is loaded" not in body)

    check("no script errors", not errors, errors[:3])
    browser.close()

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
