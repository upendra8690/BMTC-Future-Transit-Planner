"""Responsive and wording check against a running real-mode server.

Usage:  python tests/browser/responsive_check.py http://127.0.0.1:8000
Start the server with a raised RATE_LIMIT_PER_MINUTE: this check sends several hundred requests a minute.

For each screen width the briefs name (phones from 320 px, a tablet and desktops), it opens the main screens and a
real Metro journey, and checks that nothing scrolls sideways. It also checks the Metro wording (finding D1) and that
no script error occurs. Needs Playwright and Microsoft Edge, like the other browser checks.
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") + "/"
WIDTHS = [(320, 640), (360, 740), (375, 812), (390, 844), (412, 915), (430, 932), (768, 1024), (1024, 768),
          (1366, 768), (1920, 1080)]
SCREENS = ["home", "routes", "stops", "metro", "upcoming", "favourites", "live", "tickets", "more", "sources"]
results: list[bool] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f": {str(detail)[:240]}" if not ok else ""))


def open_screen(page, path: str) -> None:
    page.goto("about:blank")
    page.goto(BASE + "#/" + path, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=15000)


def overflow(page) -> int:
    return page.evaluate("document.documentElement.scrollWidth - window.innerWidth")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    errors: list[str] = []
    for width, height in WIDTHS:
        ctx = browser.new_context(viewport={"width": width, "height": height})
        ctx.add_init_script("try { localStorage.setItem('bmtc.classification', 'UNVERIFIED_FEED'); } catch (e) {}")
        page = ctx.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        wide = []
        for screen in SCREENS:
            open_screen(page, screen)
            extra = overflow(page)
            if extra > 1:
                wide.append(f"{screen} (+{extra}px)")
        open_screen(page, "journey")
        page.fill("#journeyForm [name=origin]", "Indiranagar")
        page.fill("#journeyForm [name=destination]", "Jayanagar")
        page.check("#journeyForm [name=modes][value=metro]")
        page.click("#journeyForm button[type=submit]")
        page.locator("#journeyResults .option, #journeyResults .empty, #journeyResults .banner").first.wait_for(
            timeout=20000)
        check(f"{width}x{height}: a real Metro journey is shown", page.locator("#journeyResults .option").count() > 0,
              page.inner_text("#journeyResults")[:200])
        extra = overflow(page)
        if extra > 1:
            wide.append(f"journey (+{extra}px)")
        check(f"{width}x{height}: no sideways scrolling on {len(SCREENS) + 1} screens", not wide, ", ".join(wide))
        if width == 390:
            text = page.inner_text("#journeyResults")
            check("Metro journey never says 'first bus'", "first bus" not in text, text[:300])
        ctx.close()
    check("no script errors", not errors, errors[:3])
    browser.close()

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
