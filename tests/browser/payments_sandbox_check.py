"""Browser check of the sandbox payment environment, end to end. Demonstration servers only; never the public service.

Usage:  python tests/browser/payments_sandbox_check.py <sandbox url> <real-mode url>

The sandbox server runs with DEMO_MODE=1, ACCOUNTS_ENABLED=1, ACCOUNTS_ALLOW_SQLITE=1, PAYMENT_PROVIDER=sandbox,
PAYMENT_ENVIRONMENT=sandbox, TICKETING_PROVIDER=sandbox and its own PAYMENT_SANDBOX_STATE file. Checks, at phone
size: the DEMONSTRATION ONLY label everywhere; a purchase approved with a webhook; one approved without a webhook
(found by the app's own status check); a gateway time-out that leaves the order pending until a later check; a
declined payment; a refund completed at the gateway; a receipt; no QR code anywhere; and on the real-mode server no
buy form and no sandbox pages.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

SANDBOX = sys.argv[1].rstrip("/") + "/"
REAL = sys.argv[2].rstrip("/") + "/"
DEMO = "DEMONSTRATION ONLY — NOT VALID FOR TRAVEL"
results: list[bool] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f": {str(detail)[:240]}" if not ok else ""))


def open_screen(page, base: str, path: str) -> None:
    page.goto("about:blank")
    page.goto(base + "#/" + path, wait_until="load")
    page.wait_for_selector("#splash", state="hidden", timeout=20000)


def buy(page, outcome_label: str, adults: str = "1") -> str:
    """Buys one test item and chooses the gateway's outcome; returns the order page's address."""
    open_screen(page, SANDBOX, "tickets")
    page.wait_for_selector("#buyForm", timeout=20000)
    page.fill("#buyForm [name=adult]", adults)
    page.click("#buyForm button[type=submit]")
    page.wait_for_url("**/sandbox/pay/**", timeout=20000)
    page.click(f"button:has-text('{outcome_label}')")
    page.wait_for_url("**/#/tickets/order/**", timeout=20000)
    page.wait_for_selector("#orderSummary", timeout=20000)
    return page.url


def api(page, path: str) -> dict:
    return page.evaluate("""async (path) => {
      const key = Object.keys(localStorage).find(k => k.endsWith('session'));
      const token = JSON.parse(localStorage.getItem(key)).token;
      const r = await fetch(path, {headers: {Authorization: 'Bearer ' + token}});
      return r.json();
    }""", path)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    errors: list[str] = []
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
    page = ctx.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if "Content Security Policy" in msg.text else None)

    open_screen(page, SANDBOX, "account")
    page.click("summary:has-text('Create an account')")
    page.fill("#accountRegisterForm [name=email]", f"sandbox-{secrets.token_hex(3)}@example.org")
    page.fill("#accountRegisterForm [name=password]", "correct horse battery")
    page.click("#accountRegisterForm button[type=submit]")
    page.wait_for_selector(".recovery-code", timeout=20000)

    open_screen(page, SANDBOX, "tickets")
    page.wait_for_selector("#buyForm", timeout=20000)
    check("The Tickets screen says DEMONSTRATION ONLY and offers a test purchase",
          DEMO in page.inner_text("#view") and "Test purchase (sandbox)" in page.inner_text("#view"))

    # 1. approved, with the gateway's signed webhook
    first = buy(page, "Approve the payment", adults="2")
    summary = page.inner_text("#view")
    check("An approved payment issues a demonstration record, labelled as not a ticket",
          "Ticket issued" in summary and "Demonstration record DEMO-" in summary and "Not valid for travel" in summary
          and DEMO in summary, summary[:400])
    check("The payment shows this app's transaction id and its status", "Transaction BTP" in summary
          and "successful" in summary)
    check("No QR code is drawn", page.locator("canvas, img[alt*='QR'], svg[aria-label*='QR']").count() == 0)

    # 2. approved, but the webhook never arrives: the app's own status check finds it
    buy(page, "Approve without a webhook")
    expect(page.locator("#orderSummary")).to_contain_text("Ticket issued", timeout=20000)
    check("Without a webhook, the order page's check with the gateway confirms the payment", True)

    # 3. the gateway stops answering: the order stays pending, and a later check completes it
    buy(page, "Make the gateway stop answering")
    expect(page.locator("#orderNote")).to_contain_text("did not answer", timeout=20000)
    order_id = page.url.rsplit("/", 1)[1]
    check("A time-out leaves the order pending and says so", "Waiting for payment" in page.inner_text("#orderSummary"))
    reference = api(page, f"/api/commerce/orders/{order_id}")["payments"][0]["reference"]
    page.goto(SANDBOX + f"sandbox/pay/{reference}")
    page.click("button:has-text('Approve without a webhook')")
    page.wait_for_selector("#orderSummary", timeout=20000)
    expect(page.locator("#orderSummary")).to_contain_text("Ticket issued", timeout=20000)
    check("When the gateway answers again, the next check completes the order", True)

    # 4. declined
    buy(page, "Decline the payment")
    expect(page.locator("#orderSummary")).to_contain_text("Failed", timeout=20000)
    check("A declined payment fails the order and issues nothing",
          "Demonstration record" not in page.inner_text("#orderSummary"))

    # 5. refund of the first order, completed at the gateway
    page.goto(first)
    page.wait_for_selector("#orderSummary form", timeout=20000)
    page.fill("#orderSummary [name=reason]", "Browser check refund")
    page.click("#orderSummary form button[type=submit]")
    expect(page.locator("#orderSummary")).to_contain_text("Refund requested", timeout=20000)
    page.click("a:has-text('Sandbox gateway console')")
    page.wait_for_selector("button:has-text('Complete the refund')", timeout=20000)
    check("The sandbox console says DEMONSTRATION ONLY", DEMO in page.inner_text("body"))
    page.click("button:has-text('Complete the refund')")
    page.goto(first)
    expect(page.locator("#orderSummary")).to_contain_text("Refunded", timeout=20000)
    check("The refund completes when the gateway confirms it", True)

    with page.expect_download(timeout=20000) as info:
        page.click("#orderSummary [data-action=order-receipt]")
    receipt = json.loads(Path(info.value.path()).read_text(encoding="utf-8"))
    check("The receipt says DEMONSTRATION ONLY and carries the transaction id",
          receipt["note"].startswith(DEMO) and receipt["transaction_id"].startswith("BTP"), receipt)

    open_screen(page, SANDBOX, "tickets")
    page.wait_for_selector("#ticketHistory li", timeout=20000)
    check("History lists the four test orders", page.locator("#ticketHistory > ul > li").count() == 4)

    # The real-mode server: no buy form, no sandbox pages.
    open_screen(page, REAL, "tickets")
    page.wait_for_selector("#ticketStatus li", timeout=20000)
    check("On a real-mode server there is no buy form and no sandbox label",
          page.locator("#buyForm").count() == 0 and DEMO not in page.inner_text("#view"))
    try:
        urllib.request.urlopen(REAL + "sandbox", timeout=20)  # noqa: S310 - local test server
        status = 200
    except urllib.error.HTTPError as exc:
        status = exc.code
    check("On a real-mode server the sandbox pages do not exist", status == 404, status)
    check("No script errors and no policy refusals", not errors, errors[:3])
    browser.close()

print(f"{sum(results)}/{len(results)} passed on {dt.date.today()}")
sys.exit(0 if all(results) else 1)
