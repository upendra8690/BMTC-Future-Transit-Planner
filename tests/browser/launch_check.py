"""Browser check of the launch screens against a running demo server (default http://127.0.0.1:8020/).

Usage: python tests/browser/launch_check.py [base_url] [screenshot_dir]
Drives Microsoft Edge through Playwright at phone and desktop sizes, in every language, and fails on a console error,
horizontal page scroll, a missing translation, or a flow that does not produce its result.
"""
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8020/"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
# What the server itself reports, so the screens are compared with the API rather than with fixed numbers.
STATUS = json.load(urllib.request.urlopen(BASE.rstrip("/") + "/api/data-status", timeout=30))  # noqa: S310
PROVIDERS = json.load(urllib.request.urlopen(BASE.rstrip("/") + "/api/providers", timeout=30))["providers"]  # noqa: S310
LANGS = ["en", "kn", "te", "hi"]
SCREENS = ["home", "journey", "upcoming", "assistant", "providers", "more", "tickets", "live", "metro"]
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def settle(page) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)


def unverified(page) -> None:
    button = page.locator("[data-action=cls][data-cls=UNVERIFIED_FEED]").first
    if button.count():
        button.click()
        settle(page)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    for label, viewport in (("phone", {"width": 390, "height": 844}), ("desktop", {"width": 1280, "height": 900})):
        for lang in LANGS:
            ctx = browser.new_context(viewport=viewport, geolocation={"latitude": 12.9716, "longitude": 77.5946},
                                      permissions=["geolocation"])
            ctx.add_init_script(f"try {{ localStorage.setItem('bmtc.lang', '{lang}'); }} catch (e) {{}}")
            page = ctx.new_page()
            errors: list[str] = []
            page.on("console", lambda m, errs=errors: errs.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
            page.goto(BASE + "#/home", wait_until="load")
            page.wait_for_selector("#splash", state="hidden", timeout=8000)
            for screen in SCREENS:
                page.goto(BASE + "#/" + screen, wait_until="load")
                settle(page)
                text = page.inner_text("#view")
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                tag = f"{label}/{lang}/{screen}"
                check(f"{tag} renders", len(text.strip()) > 20, text[:60])
                check(f"{tag} no horizontal scroll", overflow <= 0, f"overflow {overflow}px")
                raw_keys = [w for w in text.split() if w.count(".") >= 1 and w.split(".")[0] in
                            {"upcoming", "assist", "providers", "integ", "journey", "nav", "feature"}]
                check(f"{tag} no untranslated keys", not raw_keys, " ".join(raw_keys[:5]))
                if SHOTS and lang in ("en", "kn"):
                    SHOTS.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(SHOTS / f"{label}_{lang}_{screen}.png"), full_page=True)

            # Flows, checked once per size in English and once in Kannada.
            if lang in ("en", "kn"):
                tag = f"{label}/{lang}"
                page.goto(BASE + "#/upcoming", wait_until="load")
                settle(page)
                check(f"{tag} upcoming lists 7 projects", page.locator(".project-list > li").count() == 7)
                check(f"{tag} upcoming has source links",
                      page.locator(".project-list a[href^='https://']").count() >= 7)

                page.goto(BASE + "#/journey", wait_until="load")
                settle(page)
                unverified(page)
                page.fill("#journeyForm [name=origin]", "Demo Lake View")
                page.fill("#journeyForm [name=destination]", "Demo Metro Hub")
                page.click("#journeyForm button[type=submit]")
                page.wait_for_selector("#journeyResults .option, #journeyResults .empty", timeout=8000)
                check(f"{tag} bus+metro journey found", page.locator("#journeyResults .option").count() > 0)
                check(f"{tag} bus+metro label shown",
                      page.locator("#journeyResults .leg.mode-metro").count() > 0
                      and page.locator("#journeyResults .leg.mode-bus").count() > 0)
                page.check("#journeyForm [name=modes][value=metro]")
                page.fill("#journeyForm [name=origin]", "Demo Central")
                page.fill("#journeyForm [name=destination]", "Demo Junction")
                page.click("#journeyForm button[type=submit]")
                page.wait_for_selector("#journeyResults .option, #journeyResults .empty", timeout=8000)
                check(f"{tag} metro-only with no metro says so", page.locator("#journeyResults .empty").count() == 1)

                page.goto(BASE + "#/assistant", wait_until="load")
                settle(page)
                unverified(page)
                page.locator("[data-action=assist-example]").nth(1).click()
                page.wait_for_selector("#assistAnswer .option, #assistAnswer .empty", timeout=8000)
                check(f"{tag} assistant answers a journey from data", page.locator("#assistAnswer .option").count() > 0)
                page.locator("[data-action=assist-example]").nth(5).click()
                page.wait_for_selector("#assistAnswer .notice", timeout=8000)
                check(f"{tag} assistant refuses live ETA", page.locator("#assistAnswer a[href='#/live']").count() == 1)

                page.goto(BASE + "#/providers", wait_until="load")
                settle(page)
                # The "only demonstration data" banner appears exactly when every served feed is a demo feed, and the
                # demonstration-server banner exactly when the server runs with DEMO_MODE=1.
                check(f"{tag} providers shows the demo-only banner only when all data is demo",
                      page.locator("#feedStatus .banner").count() == (1 if STATUS["demo_only"] else 0))
                check(f"{tag} demonstration banner matches the server's mode",
                      page.locator("#demoBanner").is_visible() == bool(STATUS["demo_mode"]))
                check(f"{tag} providers lists 6 blocked integrations",
                      page.locator("#integrationList li").count() == 6)
                check(f"{tag} providers lists every provider the server registers ({len(PROVIDERS)})",
                      page.locator("#providerList li").count() == len(PROVIDERS))

            check(f"{label}/{lang} no console errors", not errors, "; ".join(errors[:3]))
            ctx.close()
    browser.close()

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print("FAIL", name, "-", detail)
print(f"{len(results) - len(failed)}/{len(results)} launch browser checks passed")
sys.exit(1 if failed else 0)
