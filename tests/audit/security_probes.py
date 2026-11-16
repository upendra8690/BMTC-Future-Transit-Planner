"""Manual-style security probes against a running server, with evidence. Usage: python security_probes.py <keyfile>"""
import io
import sys
import time
import zipfile

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8030"
KEY = open(sys.argv[1]).read().strip()
results = []


def check(name, ok, evidence):
    results.append(("PASS" if ok else "FAIL", name, evidence))


c = httpx.Client(base_url=BASE, timeout=30)
for _ in range(60):
    try:
        c.get("/api/health")
        break
    except Exception:
        time.sleep(0.5)

# 1. Security headers on the page and the API.
page = c.get("/")
api = c.get("/api/meta")
for name, resp in (("page /", page), ("api /api/meta", api)):
    h = resp.headers
    check(f"{name}: X-Frame-Options DENY", h.get("x-frame-options") == "DENY", h.get("x-frame-options"))
    check(f"{name}: X-Content-Type-Options nosniff", h.get("x-content-type-options") == "nosniff", h.get("x-content-type-options"))
    check(f"{name}: Referrer-Policy set", bool(h.get("referrer-policy")), h.get("referrer-policy"))
check("page: CSP blocks inline and third-party scripts", "script-src 'self'" in page.headers.get("content-security-policy", ""),
      page.headers.get("content-security-policy", "")[:80])
check("page: CSP forbids framing", "frame-ancestors 'none'" in page.headers.get("content-security-policy", ""), "")

# 2. CORS closed by default.
r = c.get("/api/meta", headers={"Origin": "https://evil.example"})
check("CORS: no Access-Control-Allow-Origin for another site", "access-control-allow-origin" not in r.headers, dict(r.headers).get("access-control-allow-origin"))

# 3. Admin endpoints need the key.
check("admin without key is refused", c.get("/api/admin/stats").status_code == 401, c.get("/api/admin/stats").status_code)
check("admin with wrong key is refused", c.get("/api/admin/stats", headers={"X-Admin-Key": "wrong" * 8}).status_code == 401, "")
check("admin with correct key works", c.get("/api/admin/stats", headers={"X-Admin-Key": KEY}).status_code == 200, "")

# 4. Device-scoped data isolation (saved routes).
A, B = {"X-Client-Key": "A" * 24}, {"X-Client-Key": "B" * 24}
route = c.get("/api/routes", params={"classification": "UNVERIFIED_FEED", "q": "DEMO-1"}).json()["results"][0]
saved = c.post("/api/saved-routes", headers=A, json={"gtfs_route_id": route["gtfs_route_id"], "classification": "UNVERIFIED_FEED", "label": "A's route"})
check("device A can save a route", saved.status_code in (200, 201), saved.status_code)
check("device B cannot see device A's saved routes", c.get("/api/saved-routes", headers=B).json()["saved"] == [], "")
del_b = c.delete(f"/api/saved-routes/{saved.json()['id']}", headers=B)
check("device B cannot delete device A's saved route", del_b.status_code == 404, del_b.status_code)
check("device A's route is still there", len(c.get("/api/saved-routes", headers=A).json()["saved"]) == 1, "")
check("saved routes need a device key", c.get("/api/saved-routes").status_code == 400, c.get("/api/saved-routes").status_code)

# 5. Injection-shaped input is handled as data.
for q in ("' OR 1=1--", "%' UNION SELECT name FROM sqlite_master--", "\\", "_%_"):
    r = c.get("/api/stops", params={"classification": "UNVERIFIED_FEED", "q": q})
    check(f"SQL-shaped search {q!r} returns no rows and no error", r.status_code == 200 and r.json()["results"] == [], (r.status_code, r.text[:80]))
r = c.get("/api/stops", params={"q": "x" * 81})
check("over-long search is rejected (422)", r.status_code == 422, r.status_code)
r = c.get("/api/plan", params={"origin": "a", "destination": "b"})
check("plan input length is validated (422)", r.status_code == 422, r.status_code)

# 6. Static files: no path traversal, no source or env files.
for path in ("/../backend/app/main.py", "/%2e%2e/backend/app/main.py", "/.env", "/data/planner.db", "/..%2f..%2f.env"):
    r = c.get(path)
    leaked = "ADMIN_API_KEY" in r.text or "import " in r.text[:200] or r.content[:15] == b"SQLite format 3"
    check(f"no file leak at {path}", not leaked, r.status_code)

# 7. Upload limits: a non-ZIP and a ZIP bomb-like file are rejected safely.
src = c.post("/api/admin/data-sources", headers={"X-Admin-Key": KEY},
             json={"name": "XSS probe", "publisher": "Security test", "kind": "UNKNOWN", "license": "test"}).json()
bad = c.post("/api/admin/imports", headers={"X-Admin-Key": KEY}, files={"file": ("x.zip", b"not a zip", "application/zip")},
             data={"data_source_id": str(src["id"])})
check("non-ZIP upload is rejected", bad.status_code in (400, 413, 422), bad.status_code)
bomb = io.BytesIO()
with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("stops.txt", "0" * (60 * 1024 * 1024))
r = c.post("/api/admin/imports", headers={"X-Admin-Key": KEY}, files={"file": ("bomb.zip", bomb.getvalue(), "application/zip")},
           data={"data_source_id": str(src["id"])})
check("highly compressed (ZIP bomb) upload is rejected", r.status_code in (400, 413, 422), (r.status_code, r.text[:120]))

# 8. Stored XSS: names with HTML/script in a feed are shown as text, never executed.
evil_stop = "<img src=x onerror=window.__xss=1>Evil Stop"
evil_route = "<script>window.__xss=2</script>Evil Route"
files = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nE,<b>Evil Agency</b>,https://example.invalid,Asia/Kolkata\n",
    "routes.txt": f"route_id,route_short_name,route_long_name,route_type\nER,EVIL-1,{evil_route},3\n",
    "stops.txt": f"stop_id,stop_name,stop_lat,stop_lon\nE1,{evil_stop},12.97,77.59\nE2,Plain Stop,12.98,77.60\n",
    "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nS,1,1,1,1,1,1,1,20260101,20271231\n",
    "trips.txt": "route_id,service_id,trip_id,trip_headsign\nER,S,T1,<svg onload=window.__xss=3>\n",
    "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nT1,08:00:00,08:00:00,E1,1\nT1,08:10:00,08:10:00,E2,2\n",
}
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    for name, text in files.items():
        z.writestr(name, text)
up = c.post("/api/admin/imports", headers={"X-Admin-Key": KEY}, files={"file": ("evil.zip", buf.getvalue(), "application/zip")},
            data={"data_source_id": str(src["id"])})
check("feed with HTML in names imports (it is data, to be shown as text)", up.status_code == 201, (up.status_code, up.text[:120]))

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page()
    dialogs = []
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    pg.goto(BASE + "/#/stops", wait_until="load")
    pg.wait_for_load_state("networkidle")
    pg.locator("[data-action=cls][data-cls=UNVERIFIED_FEED]").first.click()
    pg.wait_for_load_state("networkidle")
    pg.fill("#stopSearch input[name=q]", "Evil")
    pg.click("#stopSearch button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(800)
    shown = pg.inner_text("#stopResults")
    pg.locator('#stopResults a[href^="#/stops/"]').first.click()
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(1200)
    detail = pg.inner_text("#view")
    executed = pg.evaluate("window.__xss")
    b.close()
check("stored XSS: script in names never runs", executed is None and not dialogs, f"window.__xss={executed}, dialogs={dialogs}")
check("stored XSS: the names are shown as plain text", "<img src=x" in shown and "<script>" in detail, (shown[:60], detail[:120]))

for status, name, evidence in results:
    print(f"{status} {name}" + ("" if status == "PASS" else f"  -- {evidence}"))
print(f"{sum(r[0] == 'PASS' for r in results)} passed, {sum(r[0] == 'FAIL' for r in results)} failed")
