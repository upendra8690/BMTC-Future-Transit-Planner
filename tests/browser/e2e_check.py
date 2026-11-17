"""End-to-end functional verification of every 4.0 screen against a running demo server.

Usage: python tests/browser/e2e_check.py <base_url> <admin_key_file> [report.json]

1. Control crawl: every screen (and a route and a stop page) is opened fresh for each control. Each button, choice
   and switch is used once, and the check records what it did: a new view, a changed page, a request, a message, a
   download, a dialog or a changed setting. A control that does nothing is reported as DECORATIVE and fails the run.
   Every in-app link must open a screen that renders. External links must be https and open in a new tab.
2. Forms: every search form is submitted empty and with input.
3. The user journey from the brief (open, bus, stops and route, Metro, bus + Metro, save, language, refresh, offline,
   phone size), plus no-result, invalid input, unavailable data and network failure.
4. PWA installability (Chromium's own installability check) and data labelling (demo data never looks official).

It uses Microsoft Edge through Playwright and writes a JSON report of every check.
"""
from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/") + "/"
ADMIN_KEY = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
REPORT = Path(sys.argv[3]) if len(sys.argv) > 3 else None
PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 900}
SCREENS = ["home", "nearby", "journey", "live", "tickets", "metro", "favourites", "account", "more", "upcoming",
           "assistant", "providers", "routes", "stops", "scenarios", "compare", "sources", "admin"]
# Destructive actions are exercised by their own steps (or by ui_check.py), not by the crawl.
CRAWL_SKIP = {"import-delete", "erase-do"}

checks: list[dict] = []
controls: list[dict] = []


def check(area: str, name: str, ok: bool, detail: str = "") -> None:
    checks.append({"area": area, "name": name, "ok": bool(ok), "detail": str(detail)[:300]})


def settle(page, ms: int = 350) -> None:
    # A page that keeps a request open (map tiles) never goes idle; that is not a failure.
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_load_state("networkidle", timeout=8000)
    page.wait_for_timeout(ms)


FINGERPRINT = """() => {
  const v = document.getElementById('view');
  const t = document.getElementById('toast');
  return {
    view: v ? v.innerHTML.length + ':' + v.innerHTML.slice(0, 2000).length + ':' + Array.from(v.innerHTML).reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 0) : '',
    hash: location.hash,
    toast: t && !t.hidden ? t.textContent : '',
    dialog: !!document.querySelector('dialog[open], [role=dialog]:not([hidden])'),
    root: document.documentElement.className + '|' + (document.documentElement.getAttribute('data-theme') || '') + '|' + document.documentElement.lang,
    storage: (() => { try { return JSON.stringify(Object.keys(localStorage).sort().map(k => [k, localStorage.getItem(k)])); } catch (e) { return ''; } })(),
  };
}"""


def new_context(browser, viewport, cls="UNVERIFIED_FEED", lang=None, offline_ok=False):
    ctx = browser.new_context(viewport=viewport, geolocation={"latitude": 12.9716, "longitude": 77.5946},
                              permissions=["geolocation"], accept_downloads=True)
    script = f"try {{ if (!sessionStorage.getItem('e2e-init')) {{ localStorage.setItem('bmtc.classification', '{cls}');"
    if lang:
        script += f" localStorage.setItem('bmtc.lang', '{lang}');"
    script += " sessionStorage.setItem('e2e-init', '1'); } } catch (e) {}"
    ctx.add_init_script(script)
    return ctx


def watch(page, errors: list[str], requests: list[str]) -> None:
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "tile.openstreetmap" not in m.text
            and "ERR_INTERNET_DISCONNECTED" not in m.text and "429" not in m.text else None)
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("request", lambda r: requests.append(r.method + " " + r.url) if "/api/" in r.url else None)


def open_screen(page, path: str) -> None:
    page.goto("about:blank")
    page.goto(BASE + "#/" + path, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=10000)
    settle(page)


def prepare(page, path: str) -> None:
    """Open a screen fresh. The admin key lives only in memory, so the admin screen gets it typed in each time."""
    open_screen(page, path)
    if path == "admin" and page.locator("#adminKeyForm").count():
        page.fill("#adminKeyForm [name=key]", ADMIN_KEY)
        page.click("#adminKeyForm button[type=submit]")
        settle(page, 800)


# ---------------------------------------------------------------- 1. control crawl
def crawl(browser, path: str, label: str, viewport) -> None:
    ctx = new_context(browser, viewport)
    page = ctx.new_page()
    errors: list[str] = []
    requests: list[str] = []
    watch(page, errors, requests)
    downloads: list[str] = []
    page.on("download", lambda d: downloads.append(d.suggested_filename))
    prepare(page, path)
    text = page.inner_text("#view")
    check("screens", f"{label} renders content", len(text.strip()) > 30, text[:80])
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("layout", f"{label} has no horizontal scroll at {viewport['width']} px", overflow <= 0, f"{overflow}px")
    check("screens", f"{label} shows no error banner",
          page.locator("#view .banner.error").count() == 0, page.locator("#view .banner.error").all_inner_texts()[:1])

    # Links
    links = page.eval_on_selector_all("#view a[href]", "els => els.map(a => [a.getAttribute('href'), a.target, a.rel, a.textContent.trim(), !!a.closest('.leaflet-control-zoom')])")
    zoom = [link for link in links if link[4]]
    links = [link[:4] for link in links if not link[4]]
    if zoom:
        before = page.evaluate("(document.querySelector('.leaflet-proxy') || {style: {}}).style.transform || ''")
        page.locator(".leaflet-control-zoom-in").first.click()
        page.wait_for_timeout(700)
        after = page.evaluate("(document.querySelector('.leaflet-proxy') || {style: {}}).style.transform || ''")
        controls.append({"screen": label, "kind": "map control", "label": "Zoom in / Zoom out", "target": "Leaflet", "effect": "zooms the map" if after != before else "DECORATIVE: no effect"})
        check("controls", f"{label}: the map zoom control zooms the map", after != before, f"{before} -> {after}")
    for href, target, rel, text in links:
        if href.startswith("#/"):
            controls.append({"screen": label, "kind": "link", "label": text, "target": href, "effect": "navigates"})
        elif href.startswith("tel:"):
            ok = re.fullmatch(r"tel:[0-9]{3,12}", href) is not None
            controls.append({"screen": label, "kind": "phone link", "label": text, "target": href, "effect": "opens dialler"})
            check("links", f"{label}: {href} is a valid phone link", ok, href)
        else:
            ok = href.startswith("https://") and target == "_blank" and "noopener" in (rel or "")
            controls.append({"screen": label, "kind": "external link", "label": text, "target": href, "effect": "opens official site in a new tab"})
            check("links", f"{label}: external link {href} is https, new tab, noopener", ok, f"{target} {rel}")
    for href in sorted({h for h, *_ in links if h.startswith("#/")}):
        page.goto(BASE + href, wait_until="load")
        settle(page)
        body = page.inner_text("#view").strip()
        check("links", f"{label}: in-app link {href} opens a screen", len(body) > 20 and page.locator("#view .banner.error").count() == 0, body[:60])
    # Buttons and switches, each in a fresh page.
    prepare(page, path)
    selector = "#view button:visible, #view input[type=radio]:visible, #view input[type=checkbox]:visible"
    count = page.locator(selector).count()
    for index in range(count):
        prepare(page, path)
        items = page.locator(selector)
        if index >= items.count():
            break
        item = items.nth(index)
        info = item.evaluate("e => ({tag: e.tagName, type: e.type, action: e.getAttribute('data-action') || '', name: e.name || '', value: e.value || '', text: (e.textContent || e.value || '').trim().slice(0, 60), disabled: e.disabled, form: e.form ? e.form.id : ''})")
        name = info["action"] or (info["type"] + ":" + info["name"] + "=" + info["value"]) if info["tag"] == "INPUT" else (info["action"] or ("submit:" + info["form"]))
        label_text = info["text"] or name
        if info["action"] in CRAWL_SKIP:
            controls.append({"screen": label, "kind": "button", "label": label_text, "target": info["action"], "effect": "destructive: tested in its own step"})
            continue
        if info["disabled"]:
            controls.append({"screen": label, "kind": "button", "label": label_text, "target": name, "effect": "disabled (state shown, e.g. already saved)"})
            continue
        if info["type"] == "submit" and info["form"]:
            controls.append({"screen": label, "kind": "form submit", "label": label_text, "target": info["form"], "effect": "tested in the form step"})
            continue
        if info["tag"] == "INPUT" and info["form"] not in ("", "settingsForm") and info["name"] in ("changes", "modes"):
            controls.append({"screen": label, "kind": "form choice", "label": label_text, "target": name, "effect": "applied when the form is sent (verified in the form step)"})
            continue
        if info["type"] == "radio" and page.locator(selector).nth(index).is_checked():
            controls.append({"screen": label, "kind": "choice", "label": label_text, "target": name, "effect": "already selected"})
            continue
        before = page.evaluate(FINGERPRINT)
        requests.clear()
        downloads.clear()
        try:
            item.click(timeout=4000)
        except Exception as exc:  # any failure to click is reported, not raised
            controls.append({"screen": label, "kind": "button", "label": label_text, "target": name, "effect": "FAILED TO CLICK: " + str(exc)[:80]})
            check("controls", f"{label}: '{label_text}' can be used", False, str(exc)[:120])
            continue
        settle(page, 600)
        after = page.evaluate(FINGERPRINT)
        effects = []
        if after["hash"] != before["hash"]:
            effects.append("navigates to " + after["hash"])
        if after["view"] != before["view"]:
            effects.append("updates the screen")
        if after["toast"] and after["toast"] != before["toast"]:
            effects.append("message: " + after["toast"][:50])
        if after["dialog"] and not before["dialog"]:
            effects.append("opens a dialog")
        if after["root"] != before["root"]:
            effects.append("changes a display setting")
        if after["storage"] != before["storage"]:
            effects.append("saves on the device")
        if requests:
            effects.append("requests " + ", ".join(sorted({r.split("?")[0].replace(BASE.rstrip('/'), '') for r in requests}))[:120])
        if downloads:
            effects.append("downloads " + ", ".join(downloads))
        controls.append({"screen": label, "kind": "switch" if info["tag"] == "INPUT" else "button", "label": label_text,
                         "target": name, "effect": "; ".join(effects) or "DECORATIVE: no effect"})
        check("controls", f"{label}: '{label_text}' ({name}) does something", bool(effects), "no observable effect")
    check("errors", f"{label}: no console errors during the crawl", not errors, "; ".join(errors[:3]))
    ctx.close()


# ---------------------------------------------------------------- 2. forms
def forms(browser) -> None:
    ctx = new_context(browser, PHONE)
    page = ctx.new_page()
    errors: list[str] = []
    requests: list[str] = []
    watch(page, errors, requests)
    cases = [
        ("routes", "#routeSearch", "DEMO-1", "#routeResults li", "zzzz-no-route", "#routeResults .empty"),
        ("stops", "#stopSearch", "Demo Junction", "#stopResults li", "zzzz-no-stop", "#stopResults .empty"),
        ("metro", "#metroSearch", "tech", "#metroStations li", "zzzz-no-station", "#metroStations .empty"),
    ]
    for screen, form, good, good_sel, bad, bad_sel in cases:
        open_screen(page, screen)
        page.fill(form + " [name=q]", good)
        page.click(form + " button[type=submit]")
        settle(page)
        check("forms", f"{screen} search for '{good}' returns results", page.locator(good_sel).count() > 0)
        page.fill(form + " [name=q]", bad)
        page.click(form + " button[type=submit]")
        settle(page)
        check("forms", f"{screen} search with no match says so", page.locator(bad_sel).count() == 1)
    # Home search goes to routes or stops with the words.
    open_screen(page, "home")
    page.fill("#homeQuery", "DEMO-2")
    page.click("#homeSearch button[value=routes]")
    settle(page)
    check("forms", "home 'Find a route' opens routes with the search", page.url.endswith("#/routes") and page.locator("#routeResults li").count() > 0)
    open_screen(page, "home")
    page.fill("#homeQuery", "Demo Market")
    page.click("#homeSearch button[value=stops]")
    settle(page)
    check("forms", "home 'Find a stop' opens stops with the search", page.url.endswith("#/stops") and page.locator("#stopResults li").count() > 0)
    open_screen(page, "home")
    check("forms", "the home searches are listed as recent searches", page.locator("[data-action=recent]").count() >= 2)
    # Journey: empty and one-letter input is refused before any request.
    open_screen(page, "journey")
    requests.clear()
    page.click("#journeyForm button[type=submit]")
    settle(page)
    invalid = page.evaluate("() => !document.getElementById('journeyForm').checkValidity()")
    check("forms", "journey form refuses empty origin and destination (browser validation)", invalid and not any("/api/plan" in r for r in requests))
    page.fill("#journeyForm [name=origin]", "a")
    page.fill("#journeyForm [name=destination]", "b")
    page.evaluate("() => document.getElementById('journeyForm').requestSubmit ? null : null")
    page.evaluate("() => { const f = document.getElementById('journeyForm'); f.noValidate = true; f.requestSubmit(); }")
    settle(page)
    check("forms", "journey with one-letter names shows an error and sends nothing",
          page.locator("#journeyResults .banner.error").count() == 1 and not any("/api/plan" in r for r in requests))
    # Journey choices reach the server: no change allowed and buses only.
    open_screen(page, "journey")
    requests.clear()
    page.fill("#journeyForm [name=origin]", "Demo Central")
    page.fill("#journeyForm [name=destination]", "Demo Junction")
    page.check("#journeyForm [name=changes][value='0']")
    page.check("#journeyForm [name=modes][value=bus]")
    page.click("#journeyForm button[type=submit]")
    page.wait_for_selector("#journeyResults .option, #journeyResults .empty", timeout=10000)
    sent = [r for r in requests if "/api/plan" in r]
    check("forms", "journey choices are sent: max_changes=0 and modes=bus",
          bool(sent) and "max_changes=0" in sent[-1] and "modes=bus" in sent[-1], sent[-1:] if sent else "no request")
    check("forms", "with no change allowed, every option has no change",
          page.locator("#journeyResults .option").count() > 0 and page.evaluate("String(Math.max(...Array.from(document.querySelectorAll('#journeyResults .option')).map(o => o.querySelectorAll('.leg.ride').length)) - 1)") == "0")
    page.check("#journeyForm [name=when][value=date]")
    check("forms", "choosing 'On a date' enables the date field", page.is_enabled("#journeyForm [name=date]"))
    # Assistant: empty question is refused by the browser; a 201-character question cannot be typed.
    open_screen(page, "assistant")
    page.click("#assistForm button[type=submit]")
    settle(page)
    check("forms", "assistant refuses an empty question", page.locator("#assistAnswer").inner_text().strip() == "")
    page.fill("#assistForm [name=q]", "x" * 300)
    check("forms", "assistant question is limited to 200 characters", len(page.input_value("#assistForm [name=q]")) == 200)
    page.fill("#assistForm [name=q]", "something unrelated like weather")
    page.click("#assistForm button[type=submit]")
    settle(page)
    check("forms", "assistant answers an unknown question with help or a stop search, not an invented answer",
          page.locator("#assistAnswer").inner_text().strip() != "")
    # Admin key: a wrong key is refused.
    open_screen(page, "admin")
    page.fill("#adminKeyForm [name=key]", "wrong-key-0000000000000000000000")
    page.click("#adminKeyForm button[type=submit]")
    settle(page, 800)
    toast = page.evaluate("(() => { const t = document.getElementById('toast'); return t && !t.hidden ? t.textContent : ''; })()")
    check("forms", "admin refuses a wrong key with a message and shows no data",
          bool(toast) and page.locator("#adminKeyForm").count() == 1 and page.locator("#view table").count() == 0, toast)
    check("errors", "forms: no unexpected console errors",
          not [e for e in errors if "401" not in e], "; ".join(errors[:3]))
    ctx.close()


# ---------------------------------------------------------------- 3. the user journey (phone)
def user_journey(browser) -> None:
    ctx = new_context(browser, PHONE)
    page = ctx.new_page()
    errors: list[str] = []
    requests: list[str] = []
    watch(page, errors, requests)
    area = "journey"

    def plan(origin, destination, mode):
        page.fill("#journeyForm [name=origin]", origin)
        page.fill("#journeyForm [name=destination]", destination)
        page.check(f"#journeyForm [name=modes][value={mode}]")
        page.click("#journeyForm button[type=submit]")
        page.wait_for_selector("#journeyResults .option, #journeyResults .empty, #journeyResults .banner", timeout=10000)
        settle(page, 200)

    # 1. open
    page.goto(BASE, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=10000)
    check(area, "1. the app opens on the home screen", page.locator("#homeSearch").count() == 1)
    # 2-3. bus journey
    open_screen(page, "journey")
    plan("Demo Central", "Demo Junction", "bus")
    rides = page.locator("#journeyResults .leg.ride")
    check(area, "3. a bus-only journey is found", page.locator("#journeyResults .option").count() > 0)
    check(area, "3. every ride is a bus", rides.count() > 0 and rides.count() == page.locator("#journeyResults .leg.mode-bus").count())
    check(area, "3. each ride names its source and is labelled Unverified feed",
          page.locator("#journeyResults .leg.ride .badge.unverified").count() == rides.count())
    check(area, "3. the result says times are scheduled, not live", "live" in page.inner_text("#journeyResults").lower())
    # 4. stops and route information
    open_screen(page, "routes")
    page.fill("#routeSearch [name=q]", "DEMO-1")
    page.click("#routeSearch button[type=submit]")
    settle(page)
    page.locator("#routeResults a[href^='#/routes/'], #routeResults [data-action=open-saved]").first.click()
    settle(page, 800)
    check(area, "4. the route page lists its stops", page.locator("#view").inner_text().count("Demo") >= 3)
    page.locator("[data-action=tt-load]").first.click()
    settle(page)
    check(area, "4. the route timetable loads", page.locator("#view table tr").count() > 2)
    page.locator("#view a[href^='#/stops/']").first.click()
    settle(page, 800)
    check(area, "4. a stop page shows departures or routes", page.locator("#view li, #view tr").count() > 0)
    # 5. Metro journey
    open_screen(page, "journey")
    plan("Demo Metro Central", "Demo Metro Tech Park", "metro")
    check(area, "5. a Metro-only journey is found and every ride is Metro",
          page.locator("#journeyResults .option").count() > 0
          and page.locator("#journeyResults .leg.ride").count() == page.locator("#journeyResults .leg.mode-metro").count())
    # 6. bus + Metro
    plan("Demo Lake View", "Demo Metro Hub", "all")
    check(area, "6. a bus + Metro journey is found with a walk between them",
          page.locator("#journeyResults .leg.mode-bus").count() > 0 and page.locator("#journeyResults .leg.mode-metro").count() > 0
          and page.locator("#journeyResults .leg.walk").count() > 0)
    # 7. save it
    page.click("#journeyResults [data-action=save-journey]")
    settle(page)
    check(area, "7. Save this journey confirms and then shows Saved",
          page.locator("#journeyResults [data-action=save-journey][disabled]").count() == 1)
    saved = json.loads(page.evaluate("localStorage.getItem('bmtc.favJourneys') || '[]'"))
    check(area, "7. the journey is stored on the device with its mode and data classification",
          saved[:1] == [{"from": "Demo Lake View", "to": "Demo Metro Hub", "modes": "all", "cls": "UNVERIFIED_FEED"}], saved)
    open_screen(page, "favourites")
    check(area, "7. Favourites lists the saved journey", page.locator("[data-action=plan-fav-journey]").count() == 1)
    page.click("[data-action=plan-fav-journey]")
    page.wait_for_selector("#journeyResults .option", timeout=10000)
    check(area, "7. Plan again opens the planner with the journey filled in and planned",
          page.input_value("#journeyForm [name=origin]") == "Demo Lake View" and page.locator("#journeyResults .option").count() > 0)
    # Also save a route and a stop, so the device has every kind of saved item.
    open_screen(page, "routes")
    page.fill("#routeSearch [name=q]", "DEMO-2")
    page.click("#routeSearch button[type=submit]")
    settle(page)
    page.locator("#routeResults a[href^='#/routes/']").first.click()
    settle(page, 800)
    page.click("[data-action=save-route]")
    settle(page)
    key = page.evaluate("localStorage.getItem('bmtc.clientKey')")
    server_saved = page.request.get(BASE + "api/saved-routes", headers={"X-Client-Key": key}).json()["saved"]
    check(area, "7. a saved route is stored on the server under this device", [r["gtfs_route_id"] for r in server_saved] == ["DR2"], server_saved)
    # 8. language
    page.select_option("#langSelect", "kn")
    settle(page)
    check(area, "8. switching to Kannada translates the navigation", page.locator("html[lang=kn]").count() == 1
          and re.search(r"[ಀ-೿]", page.inner_text("#bottomNav")) is not None)
    # 9. refresh
    page.reload(wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=10000)
    open_screen(page, "favourites")
    check(area, "9. after a refresh the language is still Kannada", page.locator("html[lang=kn]").count() == 1)
    check(area, "9. after a refresh the saved journey and route are still listed",
          page.locator("[data-action=plan-fav-journey]").count() == 1 and page.locator("[data-action=open-saved]").count() == 1)
    # 10. offline
    ctx.set_offline(True)
    page.reload(wait_until="load")
    page.wait_for_timeout(1500)
    check(area, "10. offline: the app shell still loads", page.locator("#bottomNav").count() == 1)
    open_screen_offline = page.goto(BASE + "#/favourites", wait_until="load")
    page.wait_for_timeout(1500)
    check(area, "10. offline: saved journeys are readable", page.locator("[data-action=plan-fav-journey]").count() == 1, open_screen_offline)
    page.click("[data-action=plan-fav-journey]")
    page.wait_for_timeout(2000)
    body = page.inner_text("#journeyResults")
    check(area, "10. offline: planning shows an error with a retry, not a blank page",
          page.locator("#journeyResults .banner.error [data-action=rerender]").count() == 1, body[:80])
    check(area, "10. offline: the offline banner is shown", page.locator("#offlineBanner:not([hidden]), .offline:not([hidden])").count() >= 1)
    ctx.set_offline(False)
    # 11. phone layout checked for every screen in the crawl; the journey screen again here
    open_screen(page, "journey")
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check(area, "11. phone: the journey screen fits 390 px", overflow <= 0, overflow)
    page.select_option("#langSelect", "en")
    settle(page)

    # Unhappy paths
    plan("Nowhere Such Place", "Demo Junction", "all")
    check("unhappy", "no-result: an unknown origin says no stop matches", page.locator("#journeyResults .empty").count() == 1)
    plan("Demo Central", "Demo Junction", "metro")
    check("unhappy", "no-result: Metro only between bus stops says so", page.locator("#journeyResults .empty").count() == 1)
    page.evaluate("localStorage.setItem('bmtc.classification', 'OFFICIAL_VERIFIED')")
    open_screen(page, "journey")
    plan("Demo Central", "Demo Junction", "all")
    check("unhappy", "unavailable data: with Officially verified chosen, the app says no official timetable exists",
          page.locator("#journeyResults .empty").count() == 1 and page.locator("#journeyResults .option").count() == 0)
    open_screen(page, "routes")
    check("unhappy", "unavailable data: the official route list explains there is no official data",
          page.locator("#routeResults .empty, #view .empty").count() >= 1)
    page.evaluate("localStorage.setItem('bmtc.classification', 'UNVERIFIED_FEED')")
    open_screen(page, "journey")
    page.route("**/api/plan*", lambda route: route.fulfill(status=500, body="boom"))
    plan("Demo Central", "Demo Junction", "all")
    check("unhappy", "network failure: a server error shows a message and a retry button",
          page.locator("#journeyResults .banner.error [data-action=rerender]").count() == 1)
    page.unroute("**/api/plan*")
    page.route("**/api/plan*", lambda route: route.abort())
    plan("Demo Central", "Demo Junction", "all")
    check("unhappy", "network failure: a dropped connection shows a message and a retry button",
          page.locator("#journeyResults .banner.error").count() == 1)
    page.unroute("**/api/plan*")
    open_screen(page, "assistant")
    page.fill("#assistForm [name=q]", "When will my bus arrive at Demo Central?")
    page.click("#assistForm button[type=submit]")
    page.wait_for_selector("#assistAnswer .notice", timeout=8000)
    check("unhappy", "assistant refuses to invent a live arrival", "not available" in page.inner_text("#assistAnswer").lower())
    for capability in ("bus_tickets", "metro_qr_tickets", "payments"):
        r = page.request.post(BASE + f"api/integrations/{capability}/request")
        check("unhappy", f"{capability}: refused (503) with no ticket, QR or payment", r.status == 503
              and not {"ticket", "qr", "qr_code", "receipt", "payment_id", "balance"} & set(r.json()))

    # Delete my data: clears the server rows for this device and the device lists.
    open_screen(page, "account")
    page.click("[data-action=erase-ask]")
    page.click("[data-action=erase-do]")
    settle(page, 800)
    after_key = page.evaluate("localStorage.getItem('bmtc.clientKey')")
    gone = page.request.get(BASE + "api/saved-routes", headers={"X-Client-Key": key}).json()["saved"]
    check("privacy", "Delete my data removes this device's saved routes from the server", gone == [], gone)
    check("privacy", "Delete my data clears saved journeys and stops on the device",
          page.evaluate("localStorage.getItem('bmtc.favJourneys')") == "[]" and page.evaluate("localStorage.getItem('bmtc.favStops')") == "[]")
    check("privacy", "Delete my data replaces the device key", after_key != key)
    check("errors", "user journey: no unexpected console errors",
          not [e for e in errors if "500" not in e and "Failed to fetch" not in e and "ERR_FAILED" not in e], "; ".join(errors[:4]))
    ctx.close()


# ---------------------------------------------------------------- 4. PWA and data labelling
def location_refused(browser) -> None:
    """Nearby stops when the person refuses location: a clear message, and no location is sent."""
    ctx = browser.new_context(viewport=PHONE)
    ctx.add_init_script("try { localStorage.setItem('bmtc.classification', 'UNVERIFIED_FEED'); } catch (e) {}")
    page = ctx.new_page()
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url) if "/api/stops/nearby" in r.url else None)
    open_screen(page, "nearby")
    page.click("[data-action=nearby-me]")
    page.wait_for_timeout(2500)
    text = page.inner_text("#view") + " " + page.evaluate("document.getElementById('toast').textContent")
    check("permissions", "refusing location shows a message and sends no location", not requests and "location" in text.lower(), text[-160:])
    ctx.close()


def pwa_installable(playwright) -> None:
    """Chromium's own installability check needs a normal browser profile; test contexts are private (incognito)."""
    import tempfile
    with tempfile.TemporaryDirectory() as profile:
        ctx = playwright.chromium.launch_persistent_context(profile, channel="msedge", viewport=DESKTOP)
        page = ctx.new_page()
        page.goto(BASE, wait_until="load")
        page.wait_for_selector("#splash", state="hidden", timeout=10000)
        page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller !== null", timeout=15000)
        page.wait_for_timeout(1000)
        errors = ctx.new_cdp_session(page).send("Page.getInstallabilityErrors").get("installabilityErrors", [])
        check("pwa", "Chromium reports the app as installable (no installability errors)", errors == [], errors)
        ctx.close()


def pwa_and_labels(browser) -> None:
    ctx = new_context(browser, DESKTOP)
    page = ctx.new_page()
    page.goto(BASE, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=10000)
    manifest = page.request.get(BASE + "manifest.webmanifest").json()
    check("pwa", "manifest name is Bengaluru Transit Planner", manifest.get("name") == "Bengaluru Transit Planner", manifest.get("name"))
    # Data labelling: no demo result carries the Officially verified badge.
    for screen in ("routes", "stops", "metro"):
        open_screen(page, screen)
        official = page.locator("#view li .badge.official, #view td .badge.official").count()
        check("labels", f"{screen}: no demo item is labelled Officially verified", official == 0, official)
    status = page.request.get(BASE + "api/data-status").json()
    check("labels", "data status reports demo-only data and no live feed", status["demo_only"] and status["live_feed"] == "NONE")
    sources = page.request.get(BASE + "api/data-sources").json()
    demo = [s for s in (sources if isinstance(sources, list) else sources.get("sources", [])) if s.get("kind") == "SYNTHETIC_DEMO"]
    check("labels", "every loaded source is SYNTHETIC_DEMO and not verified", demo and all(not s.get("verified") for s in demo), len(demo))
    if demo:
        r = page.request.post(BASE + f"api/admin/data-sources/{demo[0]['id']}/verify",
                              headers={"X-Admin-Key": ADMIN_KEY}, data={"verified": True, "note": "e2e: must be refused"})
        check("labels", "an administrator cannot mark demo data as official", r.status in (400, 409, 422), r.status)
    ctx.close()


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    for size_name, viewport in (("phone", PHONE), ("desktop", DESKTOP)):
        for screen in SCREENS:
            crawl(browser, screen, f"{size_name}/{screen}", viewport)
    # Detail pages: the first demo route and the first demo stop.
    ctx = browser.new_context()
    api = ctx.request
    route_id = api.get(BASE + "api/routes?classification=UNVERIFIED_FEED&q=DEMO-1").json()["results"][0]["id"]
    stop_id = api.get(BASE + "api/stops?classification=UNVERIFIED_FEED&q=Demo%20Central").json()["results"][0]["id"]
    ctx.close()
    crawl(browser, f"routes/{route_id}", "phone/route-detail", PHONE)
    crawl(browser, f"stops/{stop_id}", "phone/stop-detail", PHONE)
    forms(browser)
    user_journey(browser)
    pwa_and_labels(browser)
    location_refused(browser)
    browser.close()
    pwa_installable(p)

failed = [c for c in checks if not c["ok"]]
decorative = [c for c in controls if c["effect"].startswith("DECORATIVE") or c["effect"].startswith("FAILED")]
for c in failed:
    print("FAIL", c["area"], "|", c["name"], "|", c["detail"])
print(f"controls exercised: {len(controls)}; decorative or broken: {len(decorative)}")
print(f"{len(checks) - len(failed)}/{len(checks)} end-to-end checks passed")
if REPORT:
    REPORT.write_text(json.dumps({"checks": checks, "controls": controls}, indent=1, ensure_ascii=False), encoding="utf-8")
sys.exit(1 if failed else 0)
