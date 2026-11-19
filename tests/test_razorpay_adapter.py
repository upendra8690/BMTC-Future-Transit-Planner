"""The Razorpay adapter and the merchant settings, tested against recorded responses (no network, no real keys).

These prove the adapter sends what Razorpay's published API expects and reads its answers, webhooks and errors safely.
They do not prove that Razorpay accepts them: that needs the owner's own Razorpay test keys (merchant onboarding).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from app.models import Order, Payment
from app.services.commerce import CommerceError
from app.services.payment_providers import BmtcTicketingAdapter, RazorpayProvider, build_commerce

from tests.helpers import make_settings

KEY_ID, KEY_SECRET, HOOK = "rzp_test_ABCDEFGH1234", "test-key-secret-0123456789", "test-webhook-secret-0123456789"


class Recorded:
    """Answers each request from a table of (method, path) -> (status, body), and records what was sent."""

    def __init__(self, answers):
        self.answers = answers
        self.sent = []

    def __call__(self, method, url, headers, body, timeout):
        path = url.replace(RazorpayProvider.API, "")
        self.sent.append({"method": method, "path": path, "headers": headers,
                          "body": json.loads(body) if body else None, "timeout": timeout})
        answer = self.answers[(method, path)]
        if isinstance(answer, Exception):
            raise answer
        status, data = answer
        return status, json.dumps(data).encode()


def provider(answers):
    transport = Recorded(answers)
    return RazorpayProvider(KEY_ID, KEY_SECRET, HOOK, "sandbox", "https://demo.example.org",
                            "Bengaluru Transit Planner", transport=transport), transport


def order_and_payment(method="UPI"):
    order = Order(id=12, amount_paise=1200, product="BUS_TICKET")
    payment = Payment(id=3, order_id=12, provider_ref="plink_ABC", transaction_id="BTP20261120ABCDEF012345",
                      method=method, amount_paise=1200)
    return order, payment


def webhook(event: dict, secret: str = HOOK, event_id: str = "evt_1"):
    body = json.dumps(event).encode()
    return {"x-razorpay-signature": hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
            "x-razorpay-event-id": event_id}, body


# ---------------------------------------------------------------- merchant settings
def merchant(tmp_path, **changes):
    values = {"payment_provider": "razorpay", "payment_environment": "production",
              "razorpay_key_id": "rzp_live_ABCDEFGH1234",
              "razorpay_key_secret": "k" * 24, "razorpay_webhook_secret": "w" * 24,
              "public_base_url": "https://planner.example.org", "demo_mode": False}
    values.update(changes)
    return make_settings(tmp_path, **values)


@pytest.mark.parametrize(("changes", "reason"), [
    ({"razorpay_key_id": "rzp_test_ABCDEFGH1234"}, "TEST_KEYS_IN_PRODUCTION"),
    ({"payment_environment": "sandbox", "demo_mode": True}, "LIVE_KEYS_IN_SANDBOX"),
    ({"payment_environment": "sandbox", "razorpay_key_id": "rzp_test_ABCDEFGH1234"}, "SANDBOX_NEEDS_DEMO_SERVER"),
    ({"razorpay_webhook_secret": ""}, "INCOMPLETE_MERCHANT_SETTINGS"),
    ({"razorpay_key_id": "not-a-key"}, "INCOMPLETE_MERCHANT_SETTINGS"),
    ({"public_base_url": "http://planner.example.org"}, "PUBLIC_BASE_URL_MUST_BE_HTTPS"),
    ({"payment_provider": "somepay"}, "UNKNOWN_PAYMENT_PROVIDER"),
])
def test_unsafe_merchant_settings_are_refused(tmp_path, changes, reason):
    shop = build_commerce(merchant(tmp_path, **changes))
    assert shop.payment is None
    assert shop.refusals["payment"] == reason


def test_complete_live_settings_give_a_gateway_but_nothing_to_sell_without_ticketing(tmp_path):
    shop = build_commerce(merchant(tmp_path))
    assert isinstance(shop.payment, RazorpayProvider)
    assert shop.environment == "production"
    status = shop.status()
    assert status["payments"]["available"] is True
    assert not any(p["available"] for p in status["products"])
    assert "k" * 24 not in json.dumps(status)


def test_bmtc_ticketing_is_refused_until_bmtc_shares_its_api(tmp_path):
    shop = build_commerce(merchant(tmp_path, ticketing_provider="bmtc"))
    assert shop.refusals["ticketing"] == "AWAITING_BMTC_API_SPECIFICATION"
    with pytest.raises(CommerceError) as refused:
        BmtcTicketingAdapter().quote("BUS_TICKET", {})
    assert refused.value.status == 503


# ---------------------------------------------------------------- starting a payment
def test_upi_starts_a_payment_link_with_this_apps_transaction_id():
    gateway, sent = provider({("POST", "/payment_links"): (200, {"id": "plink_ABC", "short_url": "https://rzp.io/i/x"})})
    order, payment = order_and_payment()
    started = gateway.start(order, payment)
    assert (started.provider_ref, started.next_action) == ("plink_ABC", {"type": "redirect", "url": "https://rzp.io/i/x"})
    request = sent.sent[0]
    assert request["body"]["amount"] == 1200
    assert request["body"]["upi_link"] is True
    assert request["body"]["reference_id"] == "BTP20261120ABCDEF012345"
    assert request["body"]["accept_partial"] is False
    assert request["body"]["callback_url"] == "https://demo.example.org/#/tickets/order/12"
    basic = base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
    assert request["headers"]["Authorization"] == "Basic " + basic


def test_upi_qr_starts_a_single_use_fixed_amount_qr_code():
    gateway, sent = provider({("POST", "/payments/qr_codes"): (200, {"id": "qr_XYZ", "image_url": "https://rzp.io/q"})})
    order, payment = order_and_payment("UPI_QR")
    started = gateway.start(order, payment)
    assert started.next_action == {"type": "qr", "url": "https://rzp.io/q"}
    body = sent.sent[0]["body"]
    assert (body["type"], body["usage"], body["fixed_amount"], body["payment_amount"]) == ("upi_qr", "single_use", True,
                                                                                          1200)


def test_a_provider_error_is_reported_without_secrets():
    gateway, _ = provider({("POST", "/payment_links"): (400, {"error": {"description": "amount is invalid"}})})
    with pytest.raises(CommerceError) as refused:
        gateway.start(*order_and_payment())
    assert refused.value.status == 502
    assert "amount is invalid" in str(refused.value)
    assert KEY_SECRET not in str(refused.value)


# ---------------------------------------------------------------- webhooks
def test_a_signed_payment_link_webhook_is_read():
    gateway, _ = provider({})
    headers, body = webhook({"event": "payment_link.paid", "payload": {
        "payment_link": {"entity": {"id": "plink_ABC", "amount_paid": 1200, "status": "paid"}}}})
    event = gateway.read_notification(headers, body)
    assert (event.event_id, event.provider_ref, event.status, event.amount_paise) == ("evt_1", "plink_ABC", "SUCCEEDED",
                                                                                      1200)


def test_a_qr_payment_and_refund_webhooks_are_read():
    gateway, _ = provider({})
    credited = gateway.read_notification(*webhook({"event": "qr_code.credited", "payload": {
        "qr_code": {"entity": {"id": "qr_XYZ"}}, "payment": {"entity": {"id": "pay_1", "amount": 1200}}}}))
    assert (credited.provider_ref, credited.status, credited.amount_paise) == ("qr_XYZ", "SUCCEEDED", 1200)
    refunded = gateway.read_notification(*webhook({"event": "refund.processed", "payload": {
        "refund": {"entity": {"id": "rfnd_9", "amount": 1200}}}}))
    assert (refunded.status, refunded.refund_ref) == ("REFUNDED", "rfnd_9")
    other = gateway.read_notification(*webhook({"event": "payment.authorized", "payload": {}}))
    assert other.status == "IGNORED"


def test_a_webhook_with_a_wrong_signature_is_refused():
    gateway, _ = provider({})
    headers, body = webhook({"event": "payment_link.paid", "payload": {}}, secret="someone-else")  # noqa: S106
    with pytest.raises(CommerceError) as refused:
        gateway.read_notification(headers, body)
    assert refused.value.status == 401


# ---------------------------------------------------------------- status checks and refunds
@pytest.mark.parametrize(("link", "expected"), [
    ({"status": "paid", "amount_paid": 1200}, ("SUCCEEDED", 1200)),
    ({"status": "created"}, ("PENDING", 0)),
    ({"status": "partially_paid"}, ("PENDING", 0)),
    ({"status": "expired"}, ("FAILED", 0)),
])
def test_the_payment_status_is_asked_from_razorpay(link, expected):
    gateway, _ = provider({("GET", "/payment_links/plink_ABC"): (200, link)})
    event = gateway.fetch_status(order_and_payment()[1])
    assert (event.status, event.amount_paise) == expected


def test_a_status_check_that_times_out_says_so():
    gateway, _ = provider({("GET", "/payment_links/plink_ABC"): CommerceError("PROVIDER_TIMEOUT", "no answer", 504)})
    with pytest.raises(CommerceError) as timed_out:
        gateway.fetch_status(order_and_payment()[1])
    assert timed_out.value.code == "PROVIDER_TIMEOUT"


def test_a_refund_goes_to_the_captured_payment():
    gateway, sent = provider({
        ("GET", "/payment_links/plink_ABC"): (200, {"status": "paid", "payments": [
            {"payment_id": "pay_77", "amount": 1200, "status": "captured"}]}),
        ("POST", "/payments/pay_77/refund"): (200, {"id": "rfnd_1", "status": "pending"}),
    })
    started = gateway.refund(order_and_payment()[1], 1200, "Plans changed")
    assert (started.provider_ref, started.status) == ("rfnd_1", "PROCESSING")
    body = sent.sent[-1]["body"]
    assert (body["amount"], body["speed"], body["receipt"]) == (1200, "normal", "BTP20261120ABCDEF012345")
