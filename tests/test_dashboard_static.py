"""Static checks on the dashboard files. They need no browser, so they also run on a machine without Chrome.

They cover the rules that a browser run would otherwise be the only check for: no inline script and no code built
from strings, local references that resolve, the four languages agreeing with each other, every translation key
the code asks for existing and being used, and the rules that keep the admin key and API answers out of the
browser's storage and cache.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.main import DASHBOARD_CSP

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"
LANGUAGES = ("en", "kn", "te", "hi")
# Text that is the same in every language on purpose: product name, format strings, abbreviations.
ALLOWED_UNTRANSLATED = {"app.brand", "clock.line", "common.pdf", "route.col_seq", "admin.col_id"}
# Keys whose full name is built at run time from a prefix, such as "cls." + classification code.
DYNAMIC_PREFIXES = (
    "cls.", "day.", "msgcode.", "feature.state.", "feature.reason.", "feature.name.", "svc.cat.", "mode.",
    "upcoming.status.", "upcoming.type.", "upcoming.kind.", "providers.feed_state.", "providers.permission.",
    "providers.integration.", "integ.cap.", "notices.kind.", "notices.mode.", "notices.status.", "account.reason.",
    "account.role.", "live.state.", "live.fresh.", "live.kind.",
    "tickets.product.", "tickets.needs.", "tickets.order_status.", "tickets.refund_status.",
    "tickets.method.", "tickets.payment_status.",
)
# Storage keys the dashboard may write. The admin key must never be one of them.
STORED_KEYS = {
    "clientKey", "lang", "classification", "year", "theme", "lowData", "largeText", "favStops", "favJourneys", "recent",
    "session",
}
DYNAMIC_CODE = (
    r"\beval\s*\(",
    r"new\s+Function\s*\(",
    r"\bsetTimeout\s*\(\s*[\"'`]",
    r"\bsetInterval\s*\(\s*[\"'`]",
    r"document\.write\s*\(",
)


def read(name: str) -> str:
    return (DASHBOARD / name).read_text(encoding="utf-8")


def dictionary(language: str) -> dict[str, str]:
    """The entries of one language block in i18n.js, from its `var <language> = {` line to its end marker."""
    source = read("i18n.js")
    start = source.index(f"var {language} = {{")
    end = source.index(f"// end: {language}", start)
    entries: dict[str, str] = {}
    for line in source[start:end].splitlines():
        stripped = line.strip()
        if not stripped.startswith('"'):
            continue
        match = re.match(r'^"([^"]+)":\s*"([^"]*)",?$', stripped)
        assert match, f"{language}: this line is not in the form \"key\": \"text\": {stripped}"
        key = match.group(1)
        assert key not in entries, f"{language}: key {key} is defined twice"
        entries[key] = match.group(2)
    return entries


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def literal_keys_in_code() -> set[str]:
    """Translation keys written out in full in app.js or index.html (dynamic prefixes end with a dot)."""
    app = read("app.js")
    html = read("index.html")
    keys = set(re.findall(r'\bt\(\s*"([a-z][a-zA-Z0-9_.]*)"', app))
    keys |= set(re.findall(r'data-i18n(?:-aria)?="([^"]+)"', app + html))
    return {key for key in keys if not key.endswith(".")}


# ---------------------------------------------------------------- languages

def test_the_dictionary_lists_the_four_languages_and_nothing_else():
    source = read("i18n.js")
    codes = re.findall(r'\{\s*code:\s*"([a-z]+)"', source)
    assert sorted(codes) == sorted(LANGUAGES), codes
    assert "messages: { en: en, kn: kn, te: te, hi: hi }" in source


def test_every_language_has_exactly_the_same_keys():
    en = set(dictionary("en"))
    for language in ("kn", "te", "hi"):
        keys = set(dictionary(language))
        assert keys == en, (
            f"{language}: missing {sorted(en - keys)}, extra {sorted(keys - en)}"
        )


def test_no_translation_is_empty_and_each_keeps_its_placeholders():
    en = dictionary("en")
    for language in LANGUAGES:
        for key, text in dictionary(language).items():
            assert text.strip(), f"{language}: {key} is empty"
            assert placeholders(text) == placeholders(en[key]), f"{language}: {key} has different {{placeholders}}"


def test_english_is_copied_into_another_language_only_on_purpose():
    en = dictionary("en")
    for language in ("kn", "te", "hi"):
        copies = {
            key for key, text in dictionary(language).items()
            if text == en[key] and re.search(r"[A-Za-z]{2,}", text)
        }
        unexpected = copies - ALLOWED_UNTRANSLATED
        assert not unexpected, f"{language}: English text copied without translation: {sorted(unexpected)}"


def test_every_translation_key_the_code_asks_for_exists():
    en = dictionary("en")
    missing = sorted(key for key in literal_keys_in_code() if key not in en)
    assert not missing, f"keys used by the code but not defined: {missing}"
    for prefix in DYNAMIC_PREFIXES:
        assert any(key.startswith(prefix) for key in en), f"no key starts with {prefix}"


# ---------------------------------------------------------------- message codes

BACKEND = Path(__file__).resolve().parents[1] / "backend" / "app"
# Every code the server can send with an answer. The server source is searched below: a code set there but missing from
# this list fails the test, and so does a listed code that the source no longer sets.
SERVER_MESSAGE_CODES = {
    "DESTINATION_NOT_FOUND", "DESTINATION_NOT_SERVED", "NEED_BOTH_STOPS", "NOT_COVERED", "NO_DEPARTURES",
    "NO_DIRECT_SERVICE", "NO_JOURNEY_FOR_MODE", "NO_METRO_STATIONS",
    "NO_OFFICIAL_DATA", "NO_PLANNED_JOURNEY", "NO_SERVICE", "NO_TRIPS", "NO_UNVERIFIED_DATA",
    "ORIGIN_NOT_FOUND", "ORIGIN_NOT_SERVED", "SAME_STOP",
}


def codes_set_in_server_source() -> set[str]:
    """The codes the server sets: message_code assignments, _with_message calls and returns."""
    source = "\n".join(path.read_text(encoding="utf-8") for path in BACKEND.rglob("*.py"))
    found = set(re.findall(r'message_code"\]\s*=\s*"([A-Z_]+)"', source))
    found |= set(re.findall(r'"message_code":[^\n]*?"([A-Z_]+)"', source))
    found |= set(re.findall(r'_with_message\(\s*result,\s*(?:"[^"\n]*"|[A-Za-z_]+),\s*"([A-Z_]+)"', source))
    for first, second in re.findall(r'return "([A-Z_]+)" if [^\n]*?else "([A-Z_]+)"', source):
        found |= {first, second}
    return found


def test_the_server_sets_only_the_codes_on_the_list():
    found = codes_set_in_server_source()
    assert found == SERVER_MESSAGE_CODES, (
        f"set in the server but not listed: {sorted(found - SERVER_MESSAGE_CODES)}; "
        f"listed but not set in the server: {sorted(SERVER_MESSAGE_CODES - found)}"
    )


def test_every_message_code_the_server_can_send_is_translated_in_every_language():
    for language in LANGUAGES:
        entries = dictionary(language)
        missing = sorted(code for code in SERVER_MESSAGE_CODES if f"msgcode.{code}" not in entries)
        assert not missing, f"{language}: no translation for message codes {missing}"


def test_no_translation_is_defined_and_then_left_unused():
    code = read("app.js") + read("index.html")
    quoted = set(re.findall(r'"([A-Za-z0-9_.]+)"', code)) | set(re.findall(r"'([A-Za-z0-9_.]+)'", code))
    unused = sorted(
        key for key in dictionary("en")
        if key not in quoted and not key.startswith(DYNAMIC_PREFIXES)
    )
    assert not unused, f"defined but never used: {unused}"


def test_the_indic_fonts_have_their_own_rules():
    css = read("styles.css")
    assert "html:lang(kn)" in css
    assert "Noto Sans Kannada" in css
    assert "html:lang(hi)" in css
    assert "Noto Sans Devanagari" in css
    assert "html:lang(te)" in css
    assert "Noto Sans Telugu" in css


def test_the_default_font_rule_leaves_out_exactly_the_languages_with_their_own_font():
    # The default rule is more specific than a plain html:lang(...) rule, so a language it does not leave out
    # would have its own font stack replaced without any error.
    css = read("styles.css")
    own_rules = re.findall(r"html:lang\((\w+)\)\s*\{[^}]*font-family", css)
    default = re.search(r"html((?::not\(:lang\(\w+\)\))+)\s*\{", css)
    assert own_rules, "no language has its own font rule"
    assert default, "the default font rule is missing"
    left_out = re.findall(r":lang\((\w+)\)", default.group(1))
    assert sorted(left_out) == sorted(own_rules), f"default rule leaves out {left_out}, own rules are {own_rules}"


# ---------------------------------------------------------------- page and scripts

def test_the_page_declares_its_language_and_is_ready_for_phones():
    html = read("index.html")
    assert '<html lang="en">' in html
    assert 'name="viewport"' in html
    assert "width=device-width" in html
    assert 'rel="manifest"' in html


def test_the_page_has_no_inline_script_and_no_event_handler_attributes():
    html = read("index.html")
    assert not re.findall(r"<script(?![^>]*\bsrc=)", html), "inline script found"
    assert not re.findall(r"\son[a-z]+\s*=", html), "inline event handler attribute found"
    assert not re.search(r"\s(on[a-z]+)=\\?[\"']", read("app.js")), "app.js writes an event handler attribute"


def test_the_dictionary_loads_before_the_app_and_the_app_loads_last():
    scripts = re.findall(r'<script src="([^"]+)"', read("index.html"))
    assert scripts.index("/i18n.js") < scripts.index("/app.js")
    assert scripts[-1] == "/app.js"


def test_no_file_builds_code_from_strings():
    for name in ("app.js", "i18n.js", "sw.js"):
        source = read(name)
        for pattern in DYNAMIC_CODE:
            assert not re.search(pattern, source), f"{name} matches {pattern}"


def test_the_server_policy_blocks_inline_script_and_eval():
    script_sources = re.search(r"script-src([^;]*)", DASHBOARD_CSP).group(1)
    assert script_sources.strip() == "'self'", script_sources
    assert "unsafe-eval" not in DASHBOARD_CSP


# ---------------------------------------------------------------- references and network

def test_every_local_reference_in_the_page_and_stylesheet_exists():
    for ref in re.findall(r'(?:href|src)="(/[^"#?]*)', read("index.html")):
        target = "index.html" if ref == "/" else ref.lstrip("/")
        assert (DASHBOARD / target).is_file(), f"index.html refers to a missing file: {ref}"
    for ref in re.findall(r"url\(([^)]+)\)", read("styles.css")):
        ref = ref.strip("'\"")
        if ref.startswith(("data:", "#")):
            continue
        assert (DASHBOARD / ref.lstrip("/")).is_file(), f"styles.css refers to a missing file: {ref}"


def test_the_only_external_hosts_are_openstreetmap_tiles_and_walking_directions():
    hosts = set()
    for name in ("index.html", "app.js", "i18n.js", "styles.css", "sw.js", "manifest.webmanifest"):
        hosts |= {match.group(1) for match in re.finditer(r"https?://([^/\s\"'`)]+)", read(name))}
    assert hosts, "expected the map tile address in app.js"
    allowed = {"www.openstreetmap.org"}
    assert all(host.endswith("tile.openstreetmap.org") or host in allowed for host in hosts), sorted(hosts)


def test_the_network_is_used_only_through_the_one_send_function():
    app = read("app.js")
    calls = [match.start() for match in re.finditer(r"\bfetch\(", app)]
    assert len(calls) == 1, f"fetch is called {len(calls)} times in app.js"
    start = app.index("async function send(")
    end = app.index("\n  }\n", start)
    assert start < calls[0] < end, "fetch is called outside the send function"


def test_browser_storage_is_used_only_by_the_storage_wrapper_and_holds_no_admin_key():
    app = read("app.js")
    assert "sessionStorage" not in app
    assert "document.cookie" not in app
    begin = app.index("// storage-begin")
    end = app.index("// storage-end")
    for match in re.finditer(r"localStorage|setItem|getItem", app):
        assert begin < match.start() < end, f"browser storage used outside the wrapper at offset {match.start()}"
    written = set(re.findall(r'storage\.set\(PREFIX \+ "([A-Za-z]+)"', app))
    assert written <= STORED_KEYS, f"unexpected stored keys: {sorted(written - STORED_KEYS)}"
    assert not any("admin" in key.lower() for key in written)


def test_the_service_worker_saves_only_public_timetable_answers():
    """Offline reading uses an allowlist: nothing that depends on the time, the device or administration."""
    sw = read("sw.js")
    assert 'if (request.method !== "GET") return;' in sw
    assert "if (SAVED_API.test(url.pathname)) event.respondWith(savedAnswer(event));" in sw, "the guard is missing"
    assert 'searchParams.get("q")' in sw, "a search with typed words must never be kept on the device"
    found = re.search(r"var SAVED_API = (/.*/);", sw)
    assert found, "SAVED_API allowlist not found in sw.js"
    allowed = re.compile(found.group(1)[1:-1])
    kept = ["/api/routes", "/api/routes/R1", "/api/routes/R1/timetable", "/api/stops", "/api/data-sources",
            "/api/services"]
    for path in kept:
        assert allowed.fullmatch(path), f"should be kept for offline reading: {path}"
    never_kept = [
        "/api/clock", "/api/meta", "/api/health", "/api/journey", "/api/plan", "/api/stops/nearby",
        "/api/stops/S1/departures", "/api/routes/R1/timetable.csv", "/api/years/2027/status",
        "/api/scenarios", "/api/scenarios/compare", "/api/saved-routes", "/api/preferences", "/api/admin/stats",
        "/api/features", "/api/account/me", "/api/account/journeys", "/api/account/export",
        "/api/account/notifications", "/api/admin/users",
    ]
    for path in never_kept:
        assert not allowed.fullmatch(path), f"must never be kept: {path}"


def test_every_file_the_service_worker_stores_exists():
    block = re.search(r"var SHELL = \[(.*?)\];", read("sw.js"), re.S)
    assert block, "SHELL list not found in sw.js"
    for url in re.findall(r'"([^"]+)"', block.group(1)):
        target = "index.html" if url == "/" else url.lstrip("/")
        assert (DASHBOARD / target).is_file(), f"sw.js stores a missing file: {url}"


def test_the_manifest_declares_language_direction_standalone_display_and_icons():
    data = json.loads(read("manifest.webmanifest"))
    assert data["lang"] == "en"
    assert data["dir"] == "ltr"
    assert data["display"] == "standalone"
    assert data["start_url"]
    assert data["scope"]
    assert data["id"]
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert {"192x192", "512x512"} <= sizes, sizes
    for icon in data["icons"]:
        assert (DASHBOARD / icon["src"].lstrip("/")).is_file(), icon["src"]


def test_verification_is_asked_for_on_the_page_and_never_in_a_browser_dialog():
    source = read("app.js")
    assert "window.prompt" not in source
    assert "prompt(" not in source
    assert 'id="sourceDecisionForm"' in source
    assert 'case "sourceDecisionForm":' in source
    assert 'data-action="decision-cancel"' in source



def test_every_scrollable_table_can_be_reached_by_keyboard():
    """axe rule scrollable-region-focusable: a table that scrolls sideways must be focusable and labelled."""
    app = read("app.js")
    wraps = re.findall(r'<div class="table-wrap"[^>]*>', app)
    assert wraps, "no table containers found"
    for tag in wraps:
        assert 'tabindex="0"' in tag, tag
        assert 'role="region"' in tag, tag
        assert "aria-label=" in tag, tag


def test_no_form_control_hides_a_form_property():
    # A control named "id" makes form.id return that control, so the submit handler's switch on form.id misses the
    # form and the browser submits it natively (a page reload with the fields in the address). Found in the
    # upcoming-transport editor by tests/browser/upcoming_admin_check.py.
    reserved = re.compile(r"""name=\\?["'](id|action|method|elements|submit|reset)\\?["']""")
    for name in ("index.html", "app.js"):
        found = reserved.findall(read(name))
        assert not found, f"{name}: form controls named {found}"


def test_markup_has_no_style_attributes_so_the_policy_needs_no_unsafe_inline():
    """The security policy allows styles only from the app's own stylesheet. Inline style attributes would be refused,
    so none may appear in the page or in markup the script builds. Colours from data are set through the DOM."""
    for name in ("app.js", "index.html"):
        text = read(name)
        assert 'style="' not in text, f"inline style attribute in {name}"
        assert "<style" not in text, f"style element in {name}"
        assert 'setAttribute("style"' not in text
