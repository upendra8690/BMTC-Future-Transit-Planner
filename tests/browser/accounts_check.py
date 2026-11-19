"""Browser check of accounts and individual administrator sign-in.

Usage:  python tests/browser/accounts_check.py <url with accounts> <admin-key-file> [<url without accounts>]

The first server runs with ACCOUNTS_ENABLED=1 (ACCOUNTS_ALLOW_SQLITE=1 is acceptable for this check only), an empty
database and a raised RATE_LIMIT_PER_MINUTE. The optional second server runs without accounts, as the public service
does today. At phone size the check registers, keeps the recovery code, survives a reload, copies a device journey
into the account, saves notification choices, downloads the account data, makes the first administrator with the
shared key, signs in as that administrator (and is signed out by a reload), recovers the password with the code, and
deletes the account. No script error may occur.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1].rstrip("/") + "/"
KEY = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
PLAIN = sys.argv[3].rstrip("/") + "/" if len(sys.argv) > 3 else ""
EMAIL, PASSWORD, NEW_PASSWORD = "asha@example.org", "correct horse battery", "another long passphrase"
results: list[bool] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f": {str(detail)[:240]}" if not ok else ""))


def open_screen(page, base: str, path: str) -> None:
    page.goto("about:blank")
    page.goto(base + "#/" + path, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=20000)


def sign_in(page, password: str) -> None:
    open_screen(page, BASE, "account")
    page.fill("#accountSignInForm [name=email]", EMAIL)
    page.fill("#accountSignInForm [name=password]", password)
    page.click("#accountSignInForm button[type=submit]")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    errors: list[str] = []
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
    page = ctx.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    open_screen(page, BASE, "account")
    page.wait_for_selector("#accountSignInForm")
    check("The account screen offers sign-in, registration and recovery",
          page.locator("#accountRegisterForm").count() == 1 and page.locator("#accountRecoverForm").count() == 1)

    page.click("summary:has-text('Create an account')")
    page.fill("#accountRegisterForm [name=email]", EMAIL)
    page.fill("#accountRegisterForm [name=password]", PASSWORD)
    page.click("#accountRegisterForm button[type=submit]")
    page.wait_for_selector(".recovery-code", timeout=20000)
    code = page.inner_text(".recovery-code").strip()
    check("Registering shows a one-time recovery code", re.fullmatch(r"[0-9a-f]{6}(-[0-9a-f]{6}){3}", code), code)
    check("Registering signs in as a passenger",
          "Signed in as " + EMAIL in page.inner_text("#view") and "Passenger" in page.inner_text("#view"))
    page.click("[data-action=account-code-done]")
    expect(page.locator(".recovery-code")).to_have_count(0)

    open_screen(page, BASE, "account")
    page.wait_for_selector("#accountJourneys")
    check("A passenger stays signed in after a reload", "Signed in as " + EMAIL in page.inner_text("#view"))
    stored = page.evaluate("localStorage.getItem('bmtc.session') || localStorage.getItem('btp.session') || ''")
    check("The stored sign-in holds no password", PASSWORD not in json.dumps(stored))

    # A journey saved on the device is copied into the account once, even if the button is pressed twice.
    page.evaluate("""() => {
      const key = Object.keys(localStorage).find(k => k.endsWith('session')).replace(/session$/, '');
      localStorage.setItem(key + 'favJourneys', JSON.stringify([{from: 'Majestic', to: 'Indiranagar', modes: 'metro',
        cls: 'UNVERIFIED_FEED'}]));
    }""")
    open_screen(page, BASE, "account")
    page.wait_for_selector("#accountJourneys .empty")
    page.click("[data-action=account-copy-journeys]")
    expect(page.locator("#accountJourneys li")).to_have_count(1, timeout=20000)
    page.click("[data-action=account-copy-journeys]")
    page.wait_for_timeout(1500)
    check("Device journeys are copied into the account once", page.locator("#accountJourneys li").count() == 1)
    href = page.get_attribute("#accountJourneys li a", "href") or ""
    check("An account journey links to the planner", href.startswith("#/journey/Majestic/Indiranagar/metro/"), href)

    page.check("#accountNotifyForm [name=service_notices]")
    page.click("#accountNotifyForm button[type=submit]")
    expect(page.locator("#toast")).to_contain_text("Choices saved", timeout=10000)
    open_screen(page, BASE, "account")
    page.wait_for_selector("#accountJourneys li")
    expect(page.locator("#accountNotifyForm [name=service_notices]")).to_be_checked(timeout=10000)
    check("Notification choices are kept, and the screen says nothing is sent yet",
          "nothing is sent yet" in page.inner_text("#accountNotifyForm"))

    with page.expect_download(timeout=20000) as info:
        page.click("[data-action=account-export]")
    download = info.value
    exported = json.loads(Path(download.path()).read_text(encoding="utf-8"))
    check("The account data download has the account and journeys and no password or hash",
          download.suggested_filename == "my-account-data.json" and exported["account"]["email"] == EMAIL
          and len(exported["saved_journeys"]) == 1 and "hash" not in json.dumps(exported).lower(), exported)

    # The shared key, with accounts running, only makes the first administrator.
    open_screen(page, BASE, "admin")
    page.wait_for_selector("#adminKeyForm")
    check("Administration asks for an account and offers the key only for setting up roles",
          "Set up administrator accounts" in page.inner_text("#view"))
    page.fill("#adminKeyForm [name=key]", KEY)
    page.click("#adminKeyForm button[type=submit]")
    page.wait_for_selector("#adminUsers li", timeout=20000)
    check("With the key only the accounts panel is shown",
          page.is_hidden("#adminSources") and page.is_hidden("#uploadForm") and page.is_visible("#adminUsers"))
    page.select_option("#adminUsers select", "admin")
    page.click("#adminUsers [data-action=user-role]")
    expect(page.locator("#toast")).to_contain_text("Role changed", timeout=20000)

    sign_in(page, PASSWORD)
    page.wait_for_selector("text=Signed in as " + EMAIL, timeout=20000)
    check("After the role change the account signs in as an administrator",
          "Administrator" in page.inner_text("#view") and "kept only in this page" in page.inner_text("#view"))
    page.click("#view a[href='#/admin']")
    page.wait_for_selector("#adminAudit tr", timeout=20000)
    admin_text = page.inner_text("#view")
    check("The administrator sees every section, including accounts",
          page.is_visible("#adminSources") and page.is_visible("#adminUsers") and "Signed in as " + EMAIL in admin_text)
    audit = page.inner_text("#adminAudit")
    check("The audit log names the sign-in and the role change", "account.sign_in" in audit and "user.role" in audit,
          audit[:300])
    stored_sessions = "Object.keys(localStorage).filter(k => k.endsWith('session')).map(k => localStorage.getItem(k))"
    check("The administrator's sign-in is not written to the device",
          page.evaluate(stored_sessions + ".join('')") == "")

    open_screen(page, BASE, "admin")
    page.wait_for_selector("text=Go to sign-in", timeout=20000)
    check("Reloading signs the administrator out", page.locator("#adminSources").count() == 0)

    open_screen(page, BASE, "account")
    page.click("summary:has-text('Forgot your password?')")
    page.fill("#accountRecoverForm [name=email]", EMAIL)
    page.fill("#accountRecoverForm [name=recovery_code]", code)
    page.fill("#accountRecoverForm [name=new_password]", NEW_PASSWORD)
    page.click("#accountRecoverForm button[type=submit]")
    page.wait_for_selector(".recovery-code", timeout=20000)
    check("Recovery sets a new password and issues a new code", page.inner_text(".recovery-code").strip() != code)
    page.click("[data-action=account-code-done]")

    sign_in(page, PASSWORD)
    expect(page.locator("#toast")).to_contain_text("incorrect", timeout=20000)
    check("The old password no longer works", page.locator("#accountSignInForm").count() == 1)
    sign_in(page, NEW_PASSWORD)
    page.wait_for_selector("#accountDeleteForm", timeout=20000)
    page.fill("#accountDeleteForm [name=password]", NEW_PASSWORD)
    page.click("#accountDeleteForm button[type=submit]")
    expect(page.locator("#toast")).to_contain_text("deleted", timeout=20000)
    sign_in(page, NEW_PASSWORD)
    expect(page.locator("#toast")).to_contain_text("incorrect", timeout=20000)
    check("A deleted account cannot sign in", page.locator("#accountSignInForm").count() == 1)

    if PLAIN:
        open_screen(page, PLAIN, "account")
        page.wait_for_selector("text=My account")
        page.wait_for_timeout(800)
        view = page.inner_text("#view")
        check("Without accounts the screen explains why and keeps settings",
              "switched off" in view and page.locator("#accountSignInForm").count() == 0 and
              page.locator("#settingsForm").count() == 1, view[:300])
        open_screen(page, PLAIN, "admin")
        page.fill("#adminKeyForm [name=key]", KEY)
        page.click("#adminKeyForm button[type=submit]")
        page.wait_for_selector("#adminSources tr, #adminSources .empty", timeout=20000)
        check("Without accounts the admin key still opens every section",
              page.is_visible("#adminSources") and page.locator("#adminUsers").count() == 1
              and page.is_hidden("#adminUsers"))

    for width in (320, 1366):
        wide = browser.new_page(viewport={"width": width, "height": 800})
        wide.on("pageerror", lambda exc: errors.append(str(exc)))
        open_screen(wide, BASE, "account")
        wide.wait_for_selector("#accountSignInForm")
        check(f"account fits {width} px", wide.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
        wide.close()
    check("No script errors", not errors, errors[:3])
    browser.close()

print(f"{sum(results)}/{len(results)} passed on {dt.date.today()}")
sys.exit(0 if all(results) else 1)
