"""Browser check of the editable upcoming-transport entries and the year banner wording, at phone size.

    python tests/browser/upcoming_admin_check.py http://127.0.0.1:8020/ <admin-key-file>

It changes one entry (metro_blue becomes Delayed), so run it against a test server, never a public one.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") + "/"
KEY = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append((bool(ok), name, str(detail)[:200]))
    print(("PASS " if ok else "FAIL ") + name + (f": {str(detail)[:200]}" if not ok else ""))


def no_sideways_scroll(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    # Upcoming transport: labels say where each status comes from; every entry has its history.
    page.goto(BASE + "#/upcoming", wait_until="load")
    page.wait_for_selector("#upcomingList .project", timeout=20000)
    items = page.locator("#upcomingList .project")
    text = page.inner_text("#upcomingList")
    check("upcoming lists the seven checked entries", items.count() == 7, items.count())
    check("press entries say they are not official", "Press report (not official)" in text)
    check("secondary entries say they are not official", "Secondary source (not official)" in text)
    check("no expected start date is shown, because none comes from an official announcement",
          "Expected start" not in text)
    check("an operating entry shows its opening date", "Opened:" in text)
    first = items.first
    first.locator("summary").click()
    check("each entry has an update history", "Entry added" in first.inner_text(), first.inner_text()[-120:])
    check("upcoming fits a 390 px screen", no_sideways_scroll(page))

    # Year banner: never titled "Official verified data" when no verified timetable exists.
    page.goto(BASE + "#/routes", wait_until="load")
    # Element waits, not wait_for_function: the app's CSP (script-src 'self') rightly blocks string evaluation.
    page.locator("#yearStatus .banner.official").wait_for(timeout=20000)
    banner = page.inner_text("#yearStatus")
    check("year banner says no officially verified timetable is available",
          "No officially verified timetable is currently available for this selection." in banner, banner[:160])
    check("year banner no longer claims official verified data", "Official verified data for" not in banner, banner)

    # Administration: change an entry's status with a reason; the public list shows it with its history.
    page.goto(BASE + "#/admin", wait_until="load")
    page.fill("#adminKeyForm input[name=key]", KEY)
    page.click("#adminKeyForm button[type=submit]")
    page.wait_for_selector("#upcomingEntry option[value=metro_blue]", state="attached", timeout=20000)
    check("admin screen fits a 390 px screen", no_sideways_scroll(page))
    page.select_option("#upcomingEntry", "metro_blue")
    check("choosing an entry fills the form",
          page.input_value("#upcomingForm input[name=name]") == "Namma Metro Blue Line",
          page.input_value("#upcomingForm input[name=name]"))
    page.select_option("#upcomingStatus", "OPERATING")
    page.fill("#upcomingForm input[name=reason]", "Browser check: operating without a date")
    page.click("#upcomingForm button[type=submit]")
    # Administration shows a refused change in its error banner (adminFailure), not in a toast.
    page.locator("#adminNotice .banner.error").wait_for(timeout=15000)
    refused = page.inner_text("#adminNotice")
    check("marking it operating without an opening date is refused", "needs the date it opened" in refused, refused)
    page.wait_for_timeout(300)
    page.select_option("#upcomingStatus", "DELAYED")
    page.fill("#upcomingForm input[name=reason]", "Browser check: delay recorded")
    page.click("#upcomingForm button[type=submit]")
    page.locator("#toast", has_text="saved").wait_for(timeout=15000)
    check("a reasoned change is saved", True)

    page.goto(BASE + "#/upcoming", wait_until="load")
    page.wait_for_selector("#upcomingList .project", timeout=20000)
    blue = page.locator("#upcomingList .project", has_text="Namma Metro Blue Line")
    check("the public list shows the new status", "Delayed" in blue.inner_text(), blue.inner_text()[:160])
    blue.locator("summary").click()
    history = blue.inner_text()
    check("the history records the change and its reason",
          "Update history (2)" in history and "Status changed from Under construction to Delayed" in history
          and "Browser check: delay recorded" in history, history[-240:])

    # Kannada: the new labels are translated.
    page.select_option("#langSelect", "kn")
    page.wait_for_selector("#upcomingList .project", timeout=20000)
    check("labels are translated into Kannada", "ಪತ್ರಿಕಾ ವರದಿ (ಅಧಿಕೃತವಲ್ಲ)" in page.inner_text("#upcomingList"))
    page.select_option("#langSelect", "en")

    check("no script errors", not errors, errors[:3])
    browser.close()

passed = sum(1 for ok, _, _ in results if ok)
print(f"{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
