"""Browser check of the Tickets screen: nothing can be bought, every item says what it needs, and history is honest.

Usage:  python tests/browser/tickets_check.py <url without accounts> <url with accounts>

Both servers have no ticketing or payment provider (as every server does today). Checks: seven items, each
"Awaiting official access" with what it needs; the promise never to ask for a UPI PIN, card number, CVV or OTP; no
buy, pay or QR control anywhere; history explained without accounts, asks to sign in with them, and is empty for a
signed-in passenger; four languages render; no script error.
"""

from __future__ import annotations

import datetime as dt
import secrets
import sys

from playwright.sync_api import expect, sync_playwright

PLAIN = sys.argv[1].rstrip("/") + "/"
ACCOUNTS = sys.argv[2].rstrip("/") + "/"
results: list[bool] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f": {str(detail)[:240]}" if not ok else ""))


def open_screen(page, base: str, path: str) -> None:
    page.goto("about:blank")
    page.goto(base + "#/" + path, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=20000)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    errors: list[str] = []
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if "Content Security Policy" in msg.text else None)

    open_screen(page, PLAIN, "tickets")
    page.wait_for_selector("#ticketStatus li", timeout=20000)
    rows = page.locator("#ticketStatus li")
    text = page.inner_text("#ticketStatus")
    check("Seven items are listed, each awaiting official access",
          rows.count() == 7 and text.count("Awaiting official access") == 7, text)
    check("Each item says what it needs",
          all(w in text for w in ("ticketing agreement with BMTC", "ONDC registration", "payment aggregator",
                                  "never holds your money", "NCMC")), text)
    check("The screen promises never to ask for payment secrets",
          "never asks for your UPI PIN, card number, CVV or OTP" in page.inner_text("#view"))
    view = page.inner_text("#view").lower()
    check("No buy, pay or QR control exists",
          page.locator("button:has-text('Buy'), button:has-text('Pay'), canvas, img[alt*='QR']").count() == 0
          and "pay now" not in view)
    check("Without accounts, the history explains why it is not shown",
          "accounts are switched off" in page.inner_text("#ticketHistory"))
    for lang in ("kn", "te", "hi"):
        page.select_option("#langSelect", lang)
        page.wait_for_timeout(700)
        check(f"Tickets renders in {lang}", "Awaiting official access" not in page.inner_text("#ticketStatus")
              and page.locator("#ticketStatus li").count() == 7)
    page.select_option("#langSelect", "en")

    open_screen(page, ACCOUNTS, "tickets")
    page.wait_for_selector("#ticketHistory a[href='#/account']", timeout=20000)
    check("With accounts but signed out, the history asks to sign in", "Sign in" in page.inner_text("#ticketHistory"))
    email = f"tickets-{secrets.token_hex(3)}@example.org"
    open_screen(page, ACCOUNTS, "account")
    page.click("summary:has-text('Create an account')")
    page.fill("#accountRegisterForm [name=email]", email)
    page.fill("#accountRegisterForm [name=password]", "correct horse battery")
    page.click("#accountRegisterForm button[type=submit]")
    page.wait_for_selector(".recovery-code", timeout=20000)
    open_screen(page, ACCOUNTS, "tickets")
    expect(page.locator("#ticketHistory")).to_contain_text("nothing has been bought", timeout=20000)
    check("A signed-in passenger's history is empty and says why", True)

    wide = browser.new_page(viewport={"width": 320, "height": 800})
    wide.on("pageerror", lambda exc: errors.append(str(exc)))
    open_screen(wide, PLAIN, "tickets")
    wide.wait_for_selector("#ticketStatus li", timeout=20000)
    check("tickets fits 320 px", wide.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
    check("No script errors and no policy refusals", not errors, errors[:3])
    browser.close()

print(f"{sum(results)}/{len(results)} passed on {dt.date.today()}")
sys.exit(0 if all(results) else 1)
