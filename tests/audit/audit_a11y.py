"""axe-core WCAG 2.1 AA scan of every 4.0 screen, light and dark, phone size. Usage: python audit_a11y.py <axe.min.js>"""
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8020/"
AXE = open(sys.argv[1], encoding="utf-8").read()
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"]
VIEWS = ["home", "nearby", "journey", "live", "tickets", "metro", "favourites", "account", "more"]
found = {}

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    for theme in ("light", "dark"):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme=theme, bypass_csp=True)
        page = ctx.new_page()
        page.goto(BASE + "#/home", wait_until="load")
        page.wait_for_selector("#splash", state="hidden", timeout=8000)
        for view in VIEWS + ["stop"]:
            if view == "stop":
                page.goto(BASE + "#/metro", wait_until="load")
                page.wait_for_load_state("networkidle")
                page.locator("[data-action=cls][data-cls=UNVERIFIED_FEED]").first.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(600)
                page.locator('#metroStations a[href^="#/stops/"]').first.click()
            else:
                page.goto(BASE + "#/" + view, wait_until="load")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(700)
            page.add_script_tag(content=AXE)
            result = page.evaluate(
                "async (tags) => { const r = await axe.run(document, { runOnly: { type: 'tag', values: tags } });"
                " return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help, n: v.nodes.length,"
                " target: v.nodes.slice(0, 3).map(x => x.target.join(' ')) })); }", TAGS)
            for v in result:
                key = (v["id"], theme)
                entry = found.setdefault(key, {"impact": v["impact"], "help": v["help"], "views": set(), "targets": set()})
                entry["views"].add(view)
                entry["targets"].update(v["target"])
        ctx.close()
    b.close()

if not found:
    print("NO VIOLATIONS on", len(VIEWS) + 1, "screens x 2 themes")
for (rule, theme), e in sorted(found.items()):
    print(f"[{e['impact']}] {rule} ({theme}): {e['help']}")
    print("   views:", ", ".join(sorted(e["views"])))
    print("   e.g.:", " | ".join(sorted(e["targets"])[:4]))
