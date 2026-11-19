"""Pages of the simulated payment gateway (sandbox). Served only while the sandbox gateway is configured, which is
possible only on a demonstration server. No money moves. Every page says DEMONSTRATION ONLY — NOT VALID FOR TRAVEL.

They stand in for the gateway's hosted payment page: a tester chooses what the "gateway" does, and the gateway then
sends this server a signed webhook (or, for "succeed without a webhook", nothing, so the app must ask for the status).
"""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .services.commerce import CommerceError
from .services.payment_providers import SandboxGateway, deliver_sandbox

router = APIRouter(prefix="/sandbox", include_in_schema=False)

BANNER = ('<div class="banner demo-mode" role="alert"><strong>DEMONSTRATION ONLY — NOT VALID FOR TRAVEL</strong>'
          "Sandbox payment gateway on a demonstration server. No money moves. Nothing here is a ticket.</div>")
OUTCOMES = (("succeed", "Approve the payment (gateway sends a signed webhook)"),
            ("succeed_silently", "Approve without a webhook (the app must ask for the status)"),
            ("fail", "Decline the payment"),
            ("pending", "Leave it pending"),
            ("timeout", "Make the gateway stop answering (time-out)"))


def _gateway(request: Request) -> SandboxGateway:
    shop = request.app.state.commerce
    if not shop.sandbox or not isinstance(shop.payment, SandboxGateway):
        raise HTTPException(status_code=404, detail="Not found.")
    return shop.payment


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">'
        f'<title>{escape(title)} — sandbox</title><link rel="stylesheet" href="/styles.css"></head>'
        f'<body><main class="sandbox-page">{BANNER}<section class="card"><h1>{escape(title)}</h1>{body}'
        "</section></main></body></html>")


@router.get("/pay/{ref}")
def pay_page(ref: str, request: Request) -> HTMLResponse:
    item = _gateway(request).payment(ref)
    if item is None:
        raise HTTPException(status_code=404, detail="Not found.")
    buttons = "".join(f'<button type="submit" name="outcome" value="{value}" class="secondary">{escape(label)}'
                      "</button>" for value, label in OUTCOMES)
    return _page("Sandbox payment", (
        f"<p>Order {item['order_id']} · transaction {escape(item['transaction_id'] or '')} · "
        f"test amount ₹{item['amount'] / 100:.2f} · method {escape(item['method'])}</p>"
        f"<p>Gateway status: <strong>{escape(item['status'])}</strong></p>"
        "<p>Choose what the gateway does. A real gateway shows your UPI apps or a UPI QR code here; the sandbox never "
        "does, and never asks for a UPI PIN.</p>"
        f'<form method="post" action="/sandbox/pay/{escape(ref)}" class="sandbox-actions">{buttons}</form>'
        f'<p><a href="/#/tickets/order/{item["order_id"]}">Back to the app without choosing</a></p>'))


@router.post("/pay/{ref}")
def pay_choice(ref: str, request: Request, outcome: str = Form(...)) -> RedirectResponse:
    gateway = _gateway(request)
    item = gateway.payment(ref)
    if item is None:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        signed = gateway.act(ref, outcome)
        with request.app.state.db.session() as db:
            deliver_sandbox(request.app.state.commerce, db, signed)
    except CommerceError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    # Back to the app, which then asks this server to check the payment with the gateway.
    return RedirectResponse(f"/#/tickets/order/{item['order_id']}", status_code=303)


@router.get("")
def console(request: Request) -> HTMLResponse:
    refunds = _gateway(request).pending_refunds()
    rows = "".join(
        f'<li><div>Refund {escape(ref)} · order {r["order_id"]} · ₹{r["amount"] / 100:.2f}</div>'
        f'<form method="post" action="/sandbox/refunds/{escape(ref)}" class="sandbox-actions">'
        '<button type="submit" name="result" value="processed" class="secondary">Complete the refund</button>'
        '<button type="submit" name="result" value="failed" class="secondary">Fail the refund</button></form></li>'
        for ref, r in refunds.items())
    return _page("Sandbox console", '<h2>Refunds waiting at the gateway</h2>' +
                 (f'<ul class="list">{rows}</ul>' if rows else "<p>No refund is waiting.</p>") +
                 '<p><a href="/#/tickets">Back to the app</a></p>')


@router.post("/refunds/{ref}")
def refund_choice(ref: str, request: Request, result: str = Form(...)) -> RedirectResponse:
    gateway = _gateway(request)
    try:
        signed = gateway.settle_refund(ref, ok=result == "processed")
        with request.app.state.db.session() as db:
            deliver_sandbox(request.app.state.commerce, db, signed)
    except CommerceError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return RedirectResponse("/sandbox", status_code=303)
