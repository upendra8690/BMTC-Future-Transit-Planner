"""Payment and ticketing providers, chosen from the server's settings: the merchant onboarding configuration.

Settings (environment only; secrets are never logged, stored in the database or returned by the API):

| Setting | Values |
|---|---|
| ``PAYMENT_PROVIDER`` | empty (none, the default), ``razorpay`` or ``sandbox`` |
| ``PAYMENT_ENVIRONMENT`` | ``production`` (default) or ``sandbox`` |
| ``RAZORPAY_KEY_ID`` / ``RAZORPAY_KEY_SECRET`` | the merchant's key pair: ``rzp_live_`` (production), ``rzp_test_`` |
| ``RAZORPAY_WEBHOOK_SECRET`` | the secret set for this server's webhook in the merchant dashboard |
| ``PUBLIC_BASE_URL`` | this server's https address, where passengers return after paying |
| ``MERCHANT_NAME`` | the name shown on the provider's payment page |
| ``TICKETING_PROVIDER`` | empty (none), ``bmtc`` (refused until BMTC's API specification exists) or ``sandbox`` |

Separation of environments:
- ``sandbox`` providers (the simulated gateway, the simulated ticketing provider and Razorpay test keys) are accepted
  only on a demonstration server (``DEMO_MODE=1``) with ``PAYMENT_ENVIRONMENT=sandbox``. The public service runs with
  ``DEMO_MODE=0``, so it can never use them.
- A sandbox provider is never combined with a production one, so no real money can pay for a demonstration record.
- Production needs live keys and an https ``PUBLIC_BASE_URL``. It also needs a production ticketing provider, which
  does not exist until BMTC (or ONDC with BMRCL) grants access; until then nothing can be bought.

The Razorpay adapter is written against Razorpay's published REST API (payment links with UPI, UPI QR codes,
refunds and signed webhooks). It has been tested only against recorded responses. It must be run against
Razorpay's test mode with the owner's own test keys before any live use.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..models import PRODUCTS, Order, Payment, TravelTicket
from .commerce import (
    ENV_PRODUCTION,
    ENV_SANDBOX,
    Commerce,
    CommerceError,
    Issued,
    PaymentEvent,
    PaymentStart,
    Quote,
    RefundStart,
)

LINK_MINUTES = 30
Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, bytes]]


def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None,
                      timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)  # noqa: S310 - fixed https host
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 # nosec B310
            return response.status, response.read(1_000_000)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(100_000)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CommerceError("PROVIDER_TIMEOUT", "The payment provider did not answer. Nothing was changed; the "
                                                "order stays pending and can be checked again.", 504) from exc


def _signature_ok(secret: bytes, body: bytes, supplied: str) -> bool:
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied or "")


# ---------------------------------------------------------------- Razorpay (production or its own test mode)
class RazorpayProvider:
    """Razorpay payment links with UPI (intent on phones, QR on desktops) and UPI QR codes; refunds; webhooks."""

    name = "razorpay"
    methods = ("UPI", "UPI_QR")
    API = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str, environment: str, public_base_url: str,
                 merchant_name: str, transport: Transport | None = None, timeout: float = 10.0) -> None:
        self.environment = environment
        self._auth = "Basic " + base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
        self._webhook_secret = webhook_secret.encode()
        self.public_base_url = public_base_url.rstrip("/")
        self.merchant_name = merchant_name[:80] or "Bengaluru Transit Planner"
        self._transport = transport or _urllib_transport
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": self._auth, "Content-Type": "application/json", "Accept": "application/json"}
        status, raw = self._transport(method, self.API + path, headers, data, self.timeout)
        try:
            answer = json.loads(raw or b"{}")
        except ValueError:
            answer = {}
        if status >= 400:
            reason = (answer.get("error") or {}).get("description") or f"HTTP {status}"
            raise CommerceError("PROVIDER_ERROR", f"The payment provider refused the request: {reason[:200]}", 502)
        return answer

    def start(self, order: Order, payment: Payment) -> PaymentStart:
        close_by = int(time.time()) + LINK_MINUTES * 60
        notes = {"transaction_id": payment.transaction_id, "order_id": str(order.id)}
        if payment.method == "UPI_QR":
            qr = self._call("POST", "/payments/qr_codes", {
                "type": "upi_qr", "name": self.merchant_name, "usage": "single_use", "fixed_amount": True,
                "payment_amount": order.amount_paise, "description": f"Order {order.id}", "close_by": close_by,
                "notes": notes})
            return PaymentStart(qr["id"], {"type": "qr", "url": qr.get("image_url", "")})
        link = self._call("POST", "/payment_links", {
            "amount": order.amount_paise, "currency": "INR", "accept_partial": False, "upi_link": True,
            "reference_id": payment.transaction_id, "description": f"{self.merchant_name}: order {order.id}",
            "expire_by": close_by, "notify": {"sms": False, "email": False}, "reminder_enable": False,
            "callback_url": f"{self.public_base_url}/#/tickets/order/{order.id}", "callback_method": "get",
            "notes": notes})
        return PaymentStart(link["id"], {"type": "redirect", "url": link.get("short_url", "")})

    def read_notification(self, headers: dict[str, str], body: bytes) -> PaymentEvent:
        if not _signature_ok(self._webhook_secret, body, headers.get("x-razorpay-signature", "")):
            raise CommerceError("BAD_SIGNATURE", "The notification signature is not valid.", 401)
        data = json.loads(body)
        event_id = headers.get("x-razorpay-event-id") or hashlib.sha256(body).hexdigest()
        event, payload = data.get("event", ""), data.get("payload", {})
        entity = lambda key: (payload.get(key) or {}).get("entity") or {}  # noqa: E731
        if event == "payment_link.paid":
            link = entity("payment_link")
            return PaymentEvent(event_id, link.get("id", ""), "SUCCEEDED", int(link.get("amount_paid", 0)))
        if event in ("payment_link.expired", "payment_link.cancelled"):
            return PaymentEvent(event_id, entity("payment_link").get("id", ""), "FAILED", 0)
        if event == "qr_code.credited":
            return PaymentEvent(event_id, entity("qr_code").get("id", ""), "SUCCEEDED",
                                int(entity("payment").get("amount", 0)))
        if event == "qr_code.closed" and entity("qr_code").get("close_reason") != "paid":
            return PaymentEvent(event_id, entity("qr_code").get("id", ""), "FAILED", 0)
        if event == "refund.processed":
            return PaymentEvent(event_id, "", "REFUNDED", int(entity("refund").get("amount", 0)),
                                entity("refund").get("id"))
        if event == "refund.failed":
            return PaymentEvent(event_id, "", "REFUND_FAILED", 0, entity("refund").get("id"))
        return PaymentEvent(event_id, "", "IGNORED", 0)

    def _captured(self, payment: Payment) -> list[dict[str, Any]]:
        if payment.provider_ref.startswith("qr_"):
            items = self._call("GET", f"/payments/qr_codes/{payment.provider_ref}/payments").get("items", [])
            return [{"id": i.get("id"), "amount": i.get("amount", 0)} for i in items if i.get("status") == "captured"]
        link = self._call("GET", f"/payment_links/{payment.provider_ref}")
        return [{"id": p.get("payment_id"), "amount": p.get("amount", 0)} for p in (link.get("payments") or [])
                if p.get("status") == "captured"]

    def fetch_status(self, payment: Payment) -> PaymentEvent:
        ref = payment.provider_ref
        if ref.startswith("qr_"):
            paid = self._captured(payment)
            if paid:
                return PaymentEvent("status-" + ref, ref, "SUCCEEDED", sum(int(p["amount"]) for p in paid))
            qr = self._call("GET", f"/payments/qr_codes/{ref}")
            return PaymentEvent("status-" + ref, ref, "FAILED" if qr.get("status") == "closed" else "PENDING", 0)
        link = self._call("GET", f"/payment_links/{ref}")
        state = link.get("status")
        if state == "paid":
            return PaymentEvent("status-" + ref, ref, "SUCCEEDED", int(link.get("amount_paid", 0)))
        if state in ("expired", "cancelled"):
            return PaymentEvent("status-" + ref, ref, "FAILED", 0)
        return PaymentEvent("status-" + ref, ref, "PENDING", 0)

    def refund(self, payment: Payment, amount_paise: int, reason: str) -> RefundStart:
        paid = self._captured(payment)
        if not paid:
            raise CommerceError("NOTHING_TO_REFUND", "The provider has no captured payment for this order.", 409)
        refund = self._call("POST", f"/payments/{paid[0]['id']}/refund", {
            "amount": amount_paise, "speed": "normal", "receipt": payment.transaction_id,
            "notes": {"reason": reason[:200], "transaction_id": payment.transaction_id}})
        return RefundStart(refund["id"], "PROCESSING")


# ---------------------------------------------------------------- sandbox: a simulated gateway, no money
class SandboxGateway:
    """A local stand-in for a payment gateway, for testing every outcome. Demonstration servers only.

    Its state (and a random signing secret made on first use, never written in code) lives in a JSON file, so a
    payment survives a restart of this server, as it would at a real gateway. Outcomes are chosen on the sandbox
    payment page: succeed, succeed without a webhook, fail, stay pending, or time out.
    """

    name = "sandbox"
    methods = ("UPI", "UPI_QR")
    environment = ENV_SANDBOX
    OUTCOMES = ("succeed", "succeed_silently", "fail", "pending", "timeout")

    def __init__(self, state_path: Path) -> None:
        self.path = state_path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"secret": secrets.token_hex(32), "payments": {}, "refunds": {}}

    def _save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state), encoding="utf-8")

    def payment(self, ref: str) -> dict[str, Any] | None:
        with self._lock:
            return self._load()["payments"].get(ref)

    def pending_refunds(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: v for k, v in self._load()["refunds"].items() if v["status"] == "pending"}

    def start(self, order: Order, payment: Payment) -> PaymentStart:
        ref = "sbx_" + secrets.token_hex(8)
        with self._lock:
            state = self._load()
            state["payments"][ref] = {"order_id": order.id, "amount": order.amount_paise, "status": "created",
                                      "mode": "normal", "transaction_id": payment.transaction_id,
                                      "method": payment.method}
            self._save(state)
        return PaymentStart(ref, {"type": "redirect", "url": f"/sandbox/pay/{ref}"})

    def _signed(self, state: dict[str, Any], event: dict[str, Any]) -> tuple[dict[str, str], bytes]:
        body = json.dumps(event).encode()
        signature = hmac.new(state["secret"].encode(), body, hashlib.sha256).hexdigest()
        return {"x-sandbox-signature": signature}, body

    def act(self, ref: str, outcome: str) -> tuple[dict[str, str], bytes] | None:
        """Applies a tester's choice. Returns the signed webhook to deliver, or None when no webhook is sent."""
        if outcome not in self.OUTCOMES:
            raise CommerceError("UNKNOWN_OUTCOME", "Unknown sandbox outcome.", 422)
        with self._lock:
            state = self._load()
            item = state["payments"].get(ref)
            if item is None:
                raise CommerceError("UNKNOWN_PAYMENT", "Unknown sandbox payment.", 404)
            item["mode"] = "timeout" if outcome == "timeout" else "normal"
            if outcome in ("succeed", "succeed_silently"):
                item["status"] = "captured"
            elif outcome == "fail":
                item["status"] = "failed"
            self._save(state)
            if outcome in ("succeed", "fail"):
                return self._signed(state, {"event_id": "sbx_evt_" + secrets.token_hex(8), "payment": ref,
                                            "status": "SUCCEEDED" if outcome == "succeed" else "FAILED",
                                            "amount": item["amount"]})
        return None

    def settle_refund(self, ref: str, ok: bool = True) -> tuple[dict[str, str], bytes]:
        with self._lock:
            state = self._load()
            refund = state["refunds"].get(ref)
            if refund is None:
                raise CommerceError("UNKNOWN_REFUND", "Unknown sandbox refund.", 404)
            refund["status"] = "processed" if ok else "failed"
            self._save(state)
            return self._signed(state, {"event_id": "sbx_evt_" + secrets.token_hex(8), "refund": ref,
                                        "status": "REFUNDED" if ok else "REFUND_FAILED", "amount": refund["amount"]})

    def read_notification(self, headers: dict[str, str], body: bytes) -> PaymentEvent:
        with self._lock:
            secret = self._load()["secret"].encode()
        if not _signature_ok(secret, body, headers.get("x-sandbox-signature", "")):
            raise CommerceError("BAD_SIGNATURE", "The notification signature is not valid.", 401)
        data = json.loads(body)
        return PaymentEvent(data["event_id"], data.get("payment", ""), data["status"], int(data.get("amount", 0)),
                            data.get("refund"))

    def fetch_status(self, payment: Payment) -> PaymentEvent:
        item = self.payment(payment.provider_ref)
        if item is None:
            raise CommerceError("UNKNOWN_PAYMENT", "Unknown sandbox payment.", 404)
        if item["mode"] == "timeout":
            raise CommerceError("PROVIDER_TIMEOUT", "The payment provider did not answer. Nothing was changed; the "
                                                    "order stays pending and can be checked again.", 504)
        status = {"captured": "SUCCEEDED", "failed": "FAILED"}.get(item["status"], "PENDING")
        return PaymentEvent("status-" + payment.provider_ref, payment.provider_ref, status,
                            item["amount"] if status == "SUCCEEDED" else 0)

    def refund(self, payment: Payment, amount_paise: int, reason: str) -> RefundStart:
        ref = "sbx_rfnd_" + secrets.token_hex(8)
        with self._lock:
            state = self._load()
            state["refunds"][ref] = {"payment": payment.provider_ref, "amount": amount_paise, "status": "pending",
                                     "reason": reason[:200], "order_id": payment.order_id}
            self._save(state)
        return RefundStart(ref, "PROCESSING")


class SandboxTicketing:
    """A local stand-in for a ticketing provider. Its records are not tickets: no QR code, no validity, test amounts."""

    name = "sandbox-ticketing"
    products = PRODUCTS
    environment = ENV_SANDBOX

    def quote(self, product: str, details: dict[str, Any]) -> Quote:  # noqa: ARG002 - the provider interface
        people = details.get("passengers") if isinstance(details.get("passengers"), dict) else {}
        count = sum(int(v) for v in people.values() if isinstance(v, int) and 0 <= v <= 9) or 1
        return Quote(100 * count, [{"type": "test amount (not a fare)", "count": count, "unit_paise": 100}],
                     "Sandbox test amount: not a fare")

    def issue(self, order: Order) -> Issued:
        return Issued(f"DEMO-{order.id:06d}", None, None, None)

    def cancel(self, ticket: TravelTicket) -> bool:  # noqa: ARG002 - the provider interface
        return True


# ---------------------------------------------------------------- BMTC: waiting for its API specification
class BmtcTicketingAdapter:
    """BMTC's authorised ticketing provider. It refuses everything until BMTC shares its API and credentials.

    Nothing is guessed about an API that has not been published or shared with this project. When BMTC provides the
    specification (endpoints, authentication, fare and issue messages, ticket QR format and its validation, refund
    and cancellation rules, sandbox access), each method below is written against it and tested in BMTC's sandbox.
    """

    name = "bmtc"
    products = ("BUS_TICKET", "BUS_PASS", "COMBINED")
    environment = ENV_PRODUCTION
    CODE = "AWAITING_BMTC_API_SPECIFICATION"

    def _refuse(self) -> CommerceError:
        return CommerceError(self.CODE, "BMTC ticketing is not connected: BMTC's API specification and credentials "
                                        "are needed.", 503, "https://mybmtc.karnataka.gov.in/")

    def quote(self, product: str, details: dict[str, Any]) -> Quote:  # noqa: ARG002 - the provider interface
        raise self._refuse()

    def issue(self, order: Order) -> Issued:  # noqa: ARG002 - the provider interface
        raise self._refuse()

    def cancel(self, ticket: TravelTicket) -> bool:  # noqa: ARG002 - the provider interface
        raise self._refuse()


# ---------------------------------------------------------------- choosing providers from the settings
KEY_RE = re.compile(r"^rzp_(live|test)_[A-Za-z0-9]{8,40}$")


def build_commerce(settings: Any) -> Commerce:
    """The providers this server may use, or none. Refused settings are reported (never their values)."""
    refusals: dict[str, str] = {}
    environment = (settings.payment_environment or ENV_PRODUCTION).lower()
    sandbox_ok = environment == ENV_SANDBOX and settings.demo_mode
    if environment not in (ENV_PRODUCTION, ENV_SANDBOX):
        refusals["environment"] = "UNKNOWN_PAYMENT_ENVIRONMENT"
        return Commerce(refusals=refusals)

    payment = None
    choice = (settings.payment_provider or "").lower()
    if choice == "sandbox":
        if sandbox_ok:
            payment = SandboxGateway(settings.payment_sandbox_state)
        else:
            refusals["payment"] = "SANDBOX_NEEDS_DEMO_SERVER"
    elif choice == "razorpay":
        key_id = settings.razorpay_key_id or ""
        match = KEY_RE.fullmatch(key_id)
        secrets_ok = len(settings.razorpay_key_secret or "") >= 16 and len(settings.razorpay_webhook_secret or "") >= 16
        if not match or not secrets_ok:
            refusals["payment"] = "INCOMPLETE_MERCHANT_SETTINGS"
        elif environment == ENV_PRODUCTION and match.group(1) != "live":
            refusals["payment"] = "TEST_KEYS_IN_PRODUCTION"
        elif environment == ENV_SANDBOX and match.group(1) != "test":
            refusals["payment"] = "LIVE_KEYS_IN_SANDBOX"
        elif environment == ENV_SANDBOX and not settings.demo_mode:
            refusals["payment"] = "SANDBOX_NEEDS_DEMO_SERVER"
        elif not (settings.public_base_url or "").startswith("https://"):
            refusals["payment"] = "PUBLIC_BASE_URL_MUST_BE_HTTPS"
        else:
            payment = RazorpayProvider(key_id, settings.razorpay_key_secret, settings.razorpay_webhook_secret,
                                       environment, settings.public_base_url, settings.merchant_name)
    elif choice:
        refusals["payment"] = "UNKNOWN_PAYMENT_PROVIDER"

    tickets = []
    ticketing = (settings.ticketing_provider or "").lower()
    if ticketing == "sandbox":
        if sandbox_ok:
            tickets.append(SandboxTicketing())
        else:
            refusals["ticketing"] = "SANDBOX_NEEDS_DEMO_SERVER"
    elif ticketing == "bmtc":
        refusals["ticketing"] = BmtcTicketingAdapter.CODE
    elif ticketing:
        refusals["ticketing"] = "UNKNOWN_TICKETING_PROVIDER"

    # Never mix: a sandbox ticketing provider with a real gateway (or the reverse) is refused as a whole.
    envs = {p.environment for p in tickets} | ({payment.environment} if payment else set())
    if len(envs) > 1:
        refusals["environment"] = "SANDBOX_AND_PRODUCTION_MIXED"
        return Commerce(refusals=refusals)
    return Commerce(tickets, payment, refusals)


def deliver_sandbox(commerce: Commerce, db: Any, signed: tuple[dict[str, str], bytes] | None) -> None:
    """Delivers a sandbox webhook to this server's own notification handler, as the real gateway would over HTTPS."""
    if signed is not None:
        commerce.notification(db, SandboxGateway.name, signed[0], signed[1])

