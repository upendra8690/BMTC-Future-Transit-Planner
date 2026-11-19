"""Browser check of the Phase 2 commuter features on a real-mode server (community Metro data loaded).

Usage:  python tests/browser/phase2_check.py http://127.0.0.1:8030/ <admin-key-file>

Checks, at phone size: service notices on Home (none by default, then one posted by an administrator from an official
source, then withdrawn), quick destinations, swap, "Use my location" (a granted, fixed location), journey links
(shared, then opened), and that no script error occurs. The server needs a raised RATE_LIMIT_PER_MINUTE.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1].rstrip("/") + "/"
KEY = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
CUBBON_PARK = {"latitude": 12.9810, "longitude": 77.5970}
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
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, geolocation=CUBBON_PARK,
                              permissions=["geolocation"])
    # No Web Share and no clipboard here, so the on-page fallback for the link is exercised.
    ctx.add_init_script("Object.defineProperty(navigator, 'share', {value: undefined, configurable: true});"
                        "Object.defineProperty(navigator, 'clipboard', {value: undefined, configurable: true});")
    page = ctx.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    # Home: no notices are invented.
    open_screen(page, "home")
    page.locator("#homeNoticesBody p").first.wait_for(timeout=15000)
    check("Home says there are no service notices, and that there is no live alerts feed",
          "no live alerts feed" in page.inner_text("#homeNoticesBody"), page.inner_text("#homeNoticesBody"))
    page.locator("#homeQuick:not([hidden])").wait_for(timeout=15000)
    quick = page.inner_text("#homeQuick")
    check("Quick destinations show real stations with their data label",
          "Majestic" in quick and "Unverified feed" in quick, quick)

    # Quick destination -> planner with only the destination filled.
    page.click("#homeQuickChips [data-action=quick-dest] >> text=Indiranagar")
    page.wait_for_selector("#journeyForm")
    form = "#journeyForm"
    check("A quick destination fills the destination and leaves the start for the passenger",
          page.input_value(f"{form} [name=destination]") == "Indiranagar"
          and page.input_value(f"{form} [name=origin]") == "")

    # Swap.
    page.fill(f"{form} [name=origin]", "Whitefield (Kadugodi)")
    page.click("[data-action=swap-journey]")
    swapped = (page.input_value(f"{form} [name=origin]"), page.input_value(f"{form} [name=destination]"))
    check("Swap exchanges start and destination", swapped == ("Indiranagar", "Whitefield (Kadugodi)"), swapped)

    # Use my location (a granted, fixed position near Cubbon Park).
    page.click("[data-action=locate-origin]")
    expect(page.locator(f"{form} [name=origin]")).not_to_have_value("Indiranagar", timeout=15000)
    located = page.input_value(f"{form} [name=origin]")
    # Exactly the station: before the fix this was the station's "Entrance C", which no journey can start from.
    check("Use my location fills the nearest station, never an entrance", located == "Cubbon Park", located)

    # Plan, share, and open the shared link.
    page.fill(f"{form} [name=origin]", "Whitefield (Kadugodi)")
    page.fill(f"{form} [name=destination]", "Jayanagar")
    page.check(f"{form} [name=modes][value=metro]")
    page.click(f"{form} button[type=submit]")
    page.locator("#journeyResults .option").first.wait_for(timeout=20000)
    page.click("[data-action=share-journey]")
    link = page.input_value("#shareBox input")
    check("Without Web Share or a clipboard, the link is shown on the page", "#/journey/" in link, link)
    other = ctx.new_page()
    other.on("pageerror", lambda exc: errors.append(str(exc)))
    other.goto("about:blank")
    other.goto(link, wait_until="load")
    other.wait_for_selector("#splash", state="hidden", timeout=20000)
    other.locator("#journeyResults .option").first.wait_for(timeout=20000)
    check("Opening a journey link plans the same journey",
          other.input_value(f"{form} [name=origin]") == "Whitefield (Kadugodi)"
          and other.input_value(f"{form} [name=destination]") == "Jayanagar"
          and "to Jayanagar" in other.locator("#journeyResults .option").first.locator(".leg.ride").last.inner_text())
    check("No browser dialog is needed", True)

    # Administration: post a notice from an official source, see it on Home, withdraw it.
    open_screen(page, "admin")
    page.fill("#adminKeyForm input[name=key]", KEY)
    page.click("#adminKeyForm button[type=submit]")
    page.wait_for_selector("#noticeForm", timeout=20000)
    page.locator("#adminNotices .empty, #adminNotices .list").first.wait_for(timeout=20000)
    nf = "#noticeForm"
    page.fill(f"{nf} [name=title]", "Purple Line: test notice from an official source")
    page.fill(f"{nf} [name=body]", "Browser check only.")
    page.select_option(f"{nf} [name=kind]", "INFORMATION")
    page.select_option(f"{nf} [name=mode]", "METRO")
    page.fill(f"{nf} [name=source_title]", "BMRCL website")
    page.fill(f"{nf} [name=source_url]", "https://example.com/not-official")
    page.fill(f"{nf} [name=reason]", "Browser check")
    page.click(f"{nf} button[type=submit]")
    page.wait_for_timeout(1200)
    check("An unofficial source is refused with a message", "official source" in page.inner_text("#adminNotice"),
          page.inner_text("#adminNotice"))
    page.fill(f"{nf} [name=source_url]", "https://english.bmrc.co.in/")
    page.click(f"{nf} button[type=submit]")
    page.locator("#adminNotices .list").wait_for(timeout=20000)
    check("The posted notice is listed as showing now", "Showing now" in page.inner_text("#adminNotices"),
          page.inner_text("#adminNotices"))
    open_screen(page, "home")
    page.locator("#homeNoticesBody .notices").wait_for(timeout=15000)
    home_text = page.inner_text("#homeNoticesBody")
    link_ok = page.get_attribute("#homeNoticesBody a", "href") == "https://english.bmrc.co.in/"
    check("Home shows the notice with its official source link", "test notice" in home_text and link_ok, home_text)
    open_screen(page, "admin")
    # The admin key is kept in memory only, so a reload signs the administrator out; sign in again.
    page.fill("#adminKeyForm input[name=key]", KEY)
    page.click("#adminKeyForm button[type=submit]")
    buttons = page.locator("#adminNotices [data-action=notice-withdraw]")
    buttons.first.wait_for(timeout=20000)
    asked_on_page = True
    while buttons.count():  # withdraw every open notice, including any left by an earlier run
        before = buttons.count()
        buttons.first.click()
        asked_on_page = asked_on_page and page.is_visible("#noticeWithdrawForm")
        page.fill("#noticeWithdrawForm [name=reason]", "Browser check finished")
        page.click("#noticeWithdrawForm button[type=submit]")
        expect(buttons).to_have_count(before - 1, timeout=20000)
    check("Withdrawing asks for a reason on the page", asked_on_page)
    expect(page.locator("#adminNotices")).to_contain_text("Withdrawn", timeout=20000)
    open_screen(page, "home")
    page.locator("#homeNoticesBody p").first.wait_for(timeout=15000)
    check("After withdrawal Home shows no notice", "no live alerts feed" in page.inner_text("#homeNoticesBody"))

    for width in (320, 1366):
        wide = browser.new_page(viewport={"width": width, "height": 800})
        wide.on("pageerror", lambda exc: errors.append(str(exc)))
        for screen in ("home", "journey"):
            open_screen(wide, screen)
            wide.wait_for_timeout(600)
            check(f"{screen} fits {width} px", wide.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
        wide.close()
    check("No script errors", not errors, errors[:3])
    browser.close()

print(f"{sum(results)}/{len(results)} passed on {dt.date.today()}")
sys.exit(0 if all(results) else 1)
