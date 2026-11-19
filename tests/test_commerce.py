"""Tickets, passes, Metro QR tickets, payments, refunds and receipts.

The public service has no ticketing or payment provider, so nothing can be bought: that is tested first. The purchase
workflows are then tested with test doubles defined in this file only (an operator that issues tickets and a payment
gateway that signs its notifications). No server ever uses them; they exist so the workflow, the signature checks and
the refusals are proven before an authorised provider is connected.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json

import pytest
from app.main import create_app
from app.models import AuditLog
from app.services.commerce import Commerce, CommerceError, Issued, PaymentEvent, PaymentStart, Quote, RefundStart
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.helpers import make_settings

PASSWORD = "correct horse battery"  # noqa: S105 - a test account's password
SECRET = b"test-only-notification-secret"
TRIP = {"from_stop": "Kempegowda Bus Station", "to_stop": "Koramangala", "passengers": {"adult": 1, "child": 1}}


class TestOperator:
    """Test double for an authorised ticketing provider."""

    __test__ = False
    name = "test-operator"
    products = ("BUS_TICKET", "BUS_PASS", "METRO_QR", "COMBINED")
    environment = "production"

    def __init__(self, fail_issue: bool = False, refuse_cancel: bool = False) -> None:
        self.fail_issue = fail_issue
        self.refuse_cancel = refuse_cancel

    def quote(self, product, details):
        people = details.get("passengers", {"adult": 1})
        items = [{"type": "adult", "count": people.get("adult", 0), "unit_paise": 600},
                 {"type": "child", "count": people.get("child", 0), "unit_paise": 300}]
        return Quote(sum(i["count"] * i["unit_paise"] for i in items), items, "test operator fare table")

    def issue(self, order):
        if self.fail_issue:
            raise CommerceError("ISSUE_FAILED", "The operator could not issue the ticket.", 502)
        start = dt.datetime(2027, 3, 10, 2, 30)
        return Issued(f"OP-{order.id}", start, start + dt.timedelta(hours=2), f"provider-payload-{order.id}")

    def cancel(self, ticket):
        return not self.refuse_cancel


class TestGateway:
    """Test double for an RBI-authorised payment aggregator that signs its notifications with HMAC-SHA256."""

    __test__ = False
    name = "test-gateway"
    methods = ("UPI",)
    environment = "production"

    def start(self, order, payment):
        return PaymentStart(f"pay_{order.id}", {"type": "redirect", "url": f"https://gateway.example.invalid/{order.id}"})

    def fetch_status(self, payment):
        return PaymentEvent("status", payment.provider_ref, "PENDING", 0)

    def read_notification(self, headers, body):
        expected = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(headers.get("x-signature", ""), expected):
            raise CommerceError("BAD_SIGNATURE", "The notification signature is not valid.", 401)
        data = json.loads(body)
        return PaymentEvent(data["event_id"], data.get("payment", ""), data["status"], data.get("amount", 0),
                            data.get("refund"))

    def refund(self, payment, amount_paise, reason):
        return RefundStart(f"rfnd_{payment.id}", "PROCESSING")


def notify(client, event: dict, secret: bytes = SECRET):
    body = json.dumps(event).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return client.post("/api/commerce/notifications/test-gateway", content=body,
                       headers={"x-signature": signature, "content-type": "application/json"})


@pytest.fixture
def shop(tmp_path):
    """A server with accounts and the two test doubles, and a signed-in passenger."""
    app = create_app(make_settings(tmp_path, demo_mode=False, accounts_enabled=True, accounts_allow_sqlite=True))
    with TestClient(app) as client:
        app.state.commerce = Commerce([TestOperator()], TestGateway())
        client.post("/api/account/register", json={"email": "asha@example.org", "password": PASSWORD})
        token = client.post("/api/account/sign-in", json={"email": "asha@example.org", "password": PASSWORD}).json()
        client.headers.update({"Authorization": "Bearer " + token["token"]})
        yield client
    app.state.db.dispose()


def buy(client, key: str = "order-key-0001") -> dict:
    order = client.post("/api/commerce/orders", json={"product": "BUS_TICKET", "details": TRIP,
                                                      "idempotency_key": key})
    assert order.status_code == 201, order.text
    order = order.json()
    paying = client.post(f"/api/commerce/orders/{order['id']}/pay", json={"method": "UPI"})
    assert paying.status_code == 200, paying.text
    return paying.json()


# ---------------------------------------------------------------- the public service: nothing can be bought
def test_without_providers_every_product_says_what_it_needs(client):
    status = client.get("/api/commerce/status").json()
    products = {p["product"]: p for p in status["products"]}
    assert set(products) == {"BUS_TICKET", "BUS_PASS", "METRO_QR", "COMBINED"}
    assert all(p["available"] is False and p["code"] and p["needs"] for p in products.values())
    assert products["METRO_QR"]["code"] == "NEEDS_ONDC_REGISTRATION"
    assert status["payments"] == {"available": False, "provider": None, "methods": [], "code": "NEEDS_PAYMENT_GATEWAY",
                                  "needs": "A merchant agreement with a licensed payment aggregator"}
    assert status["wallet"]["available"] is False
    assert status["ncmc"]["available"] is False


@pytest.mark.parametrize("product", ["BUS_TICKET", "BUS_PASS", "METRO_QR", "COMBINED"])
def test_without_providers_nothing_can_be_quoted_or_ordered(client, product):
    quote = client.post("/api/commerce/quotes", json={"product": product, "details": {}})
    assert quote.status_code == 503
    assert quote.headers["x-error-code"] in ("NEEDS_TICKETING_AGREEMENT", "NEEDS_ONDC_REGISTRATION")
    order = client.post("/api/commerce/orders", json={"product": product, "details": {},
                                                      "idempotency_key": "order-key-0001"})
    assert order.status_code == 503


def test_without_providers_a_notification_is_refused(client):
    assert notify(client, {"event_id": "e1", "payment": "pay_1", "status": "SUCCEEDED", "amount": 900}).status_code \
        == 404


def test_a_signed_in_passenger_sees_an_empty_history_while_nothing_is_sold(tmp_path):
    app = create_app(make_settings(tmp_path, accounts_enabled=True, accounts_allow_sqlite=True))
    with TestClient(app) as client:
        client.post("/api/account/register", json={"email": "a@example.org", "password": PASSWORD})
        token = client.post("/api/account/sign-in", json={"email": "a@example.org", "password": PASSWORD}).json()
        history = client.get("/api/commerce/orders", headers={"Authorization": "Bearer " + token["token"]})
        assert history.json() == {"orders": []}
        assert client.get("/api/commerce/orders").status_code == 401
    app.state.db.dispose()


# ---------------------------------------------------------------- the workflow with authorised providers
def test_a_ticket_exists_only_after_the_signed_payment_notification(shop):
    quote = shop.post("/api/commerce/quotes", json={"product": "BUS_TICKET", "details": TRIP}).json()
    assert quote["amount_paise"] == 900
    paying = buy(shop)
    order = paying["order"]
    assert order["status"] == "PAYMENT_PENDING"
    assert paying["next_action"]["type"] == "redirect"
    assert "Never share your UPI PIN" in paying["note"]
    assert order["tickets"] == []
    assert shop.get(f"/api/commerce/orders/{order['id']}/receipt").status_code == 409

    done = notify(shop, {"event_id": "evt-1", "payment": f"pay_{order['id']}", "status": "SUCCEEDED", "amount": 900})
    assert done.json() == {"processed": True, "order_status": "ISSUED"}
    detail = shop.get(f"/api/commerce/orders/{order['id']}").json()
    assert detail["tickets"][0]["provider_ticket_id"] == f"OP-{order['id']}"
    assert detail["tickets"][0]["qr_payload"] == f"provider-payload-{order['id']}"  # exactly as the provider sent it
    receipt = shop.get(f"/api/commerce/orders/{order['id']}/receipt").json()
    assert receipt["amount_paise"] == 900
    assert receipt["paid_with"] == {"provider": "test-gateway", "reference": f"pay_{order['id']}", "method": "UPI"}
    assert "not a tax invoice and not a ticket" in receipt["note"]
    assert [o["id"] for o in shop.get("/api/commerce/orders").json()["orders"]] == [order["id"]]


def test_a_badly_signed_notification_changes_nothing(shop):
    order = buy(shop)["order"]
    forged = notify(shop, {"event_id": "evt-x", "payment": f"pay_{order['id']}", "status": "SUCCEEDED",
                           "amount": 900}, secret=b"wrong")
    assert forged.status_code == 401
    assert shop.get(f"/api/commerce/orders/{order['id']}").json()["status"] == "PAYMENT_PENDING"


def test_a_notification_is_processed_once(shop):
    order = buy(shop)["order"]
    event = {"event_id": "evt-1", "payment": f"pay_{order['id']}", "status": "SUCCEEDED", "amount": 900}
    assert notify(shop, event).json()["processed"] is True
    assert notify(shop, event).json() == {"processed": False, "duplicate": True}
    assert len(shop.get(f"/api/commerce/orders/{order['id']}").json()["tickets"]) == 1


def test_a_payment_for_the_wrong_amount_issues_no_ticket(shop):
    order = buy(shop)["order"]
    notify(shop, {"event_id": "evt-1", "payment": f"pay_{order['id']}", "status": "SUCCEEDED", "amount": 1})
    detail = shop.get(f"/api/commerce/orders/{order['id']}").json()
    assert detail["status"] == "FAILED"
    assert detail["tickets"] == []
    assert detail["payments"][0]["status"] == "AMOUNT_MISMATCH"


def test_a_failed_payment_issues_no_ticket_and_no_receipt(shop):
    order = buy(shop)["order"]
    notify(shop, {"event_id": "evt-1", "payment": f"pay_{order['id']}", "status": "FAILED", "amount": 900})
    assert shop.get(f"/api/commerce/orders/{order['id']}").json()["status"] == "FAILED"
    assert shop.get(f"/api/commerce/orders/{order['id']}/receipt").status_code == 409


def test_if_the_ticket_cannot_be_issued_the_money_goes_back(shop):
    shop.app.state.commerce = Commerce([TestOperator(fail_issue=True)], TestGateway())
    order = buy(shop)["order"]
    notify(shop, {"event_id": "evt-1", "payment": f"pay_{order['id']}", "status": "SUCCEEDED", "amount": 900})
    detail = shop.get(f"/api/commerce/orders/{order['id']}").json()
    assert detail["status"] == "REFUND_REQUESTED"
    assert detail["tickets"] == []
    refund = detail["refunds"][0]
    notify(shop, {"event_id": "evt-2", "status": "REFUNDED", "refund": refund["reference"], "amount": 900})
    assert shop.get(f"/api/commerce/orders/{order['id']}").json()["status"] == "REFUNDED"


def test_an_unused_ticket_can_be_refunded_once_the_operator_cancels_it(shop):
    order = buy(shop)["order"]
    notify(shop, {"event_id": "evt-1", "payment": f"pay_{order['id']}", "status": "SUCCEEDED", "amount": 900})
    asked = shop.post(f"/api/commerce/orders/{order['id']}/refund", json={"reason": "Plans changed"}).json()
    assert asked["status"] == "REFUND_REQUESTED"
    assert asked["tickets"][0]["status"] == "CANCELLED"
    notify(shop, {"event_id": "evt-2", "status": "REFUNDED", "refund": asked["refunds"][0]["reference"],
                  "amount": 900})
    done = shop.get(f"/api/commerce/orders/{order['id']}").json()
    assert done["status"] == "REFUNDED"
    assert done["tickets"][0]["status"] == "REFUNDED"
    assert done["refunds"][0]["status"] == "COMPLETED"
    assert shop.post(f"/api/commerce/orders/{order['id']}/refund", json={"reason": "Again"}).status_code == 409


def test_no_refund_when_the_operator_will_not_cancel(shop):
    shop.app.state.commerce = Commerce([TestOperator(refuse_cancel=True)], TestGateway())
    order = buy(shop)["order"]
    notify(shop, {"event_id": "evt-1", "payment": f"pay_{order['id']}", "status": "SUCCEEDED", "amount": 900})
    assert shop.post(f"/api/commerce/orders/{order['id']}/refund", json={"reason": "Plans changed"}).status_code == 409
    assert shop.get(f"/api/commerce/orders/{order['id']}").json()["status"] == "ISSUED"


def test_the_same_request_twice_makes_one_order(shop):
    body = {"product": "BUS_TICKET", "details": TRIP, "idempotency_key": "order-key-0001"}
    first = shop.post("/api/commerce/orders", json=body).json()
    second = shop.post("/api/commerce/orders", json=body).json()
    assert first["id"] == second["id"]
    assert len(shop.get("/api/commerce/orders").json()["orders"]) == 1


def test_another_passengers_order_is_reported_missing(shop):
    order = buy(shop)["order"]
    shop.post("/api/account/register", json={"email": "ravi@example.org", "password": PASSWORD})
    other = shop.post("/api/account/sign-in", json={"email": "ravi@example.org", "password": PASSWORD}).json()
    headers = {"Authorization": "Bearer " + other["token"]}
    assert shop.get(f"/api/commerce/orders/{order['id']}", headers=headers).status_code == 404
    assert shop.get(f"/api/commerce/orders/{order['id']}/receipt", headers=headers).status_code == 404
    assert shop.get("/api/commerce/orders", headers=headers).json() == {"orders": []}


@pytest.mark.parametrize("payload", [
    {"method": "UPI", "upi_pin": "1234"},
    {"method": "CARD", "card_number": "4111111111111111", "cvv": "123"},
])
def test_payment_secrets_are_never_accepted(shop, payload):
    order = shop.post("/api/commerce/orders", json={"product": "BUS_TICKET", "details": TRIP,
                                                    "idempotency_key": "order-key-0001"}).json()
    assert shop.post(f"/api/commerce/orders/{order['id']}/pay", json=payload).status_code == 422


@pytest.mark.parametrize("details", [{"upi_pin": "1234"}, {"payer": {"Card_Number": "4111"}}, {"otp": "000000"}])
def test_order_details_never_carry_payment_secrets(shop, details):
    assert shop.post("/api/commerce/orders", json={"product": "BUS_TICKET", "details": details,
                                                   "idempotency_key": "order-key-0001"}).status_code == 422


def test_purchases_are_audited_and_exported_with_the_account(shop):
    order = buy(shop)["order"]
    notify(shop, {"event_id": "evt-1", "payment": f"pay_{order['id']}", "status": "SUCCEEDED", "amount": 900})
    with shop.app.state.db.session() as db:
        actions = [e.action for e in db.scalars(select(AuditLog).order_by(AuditLog.id))]
    purchase = [a for a in actions if a.split(".")[0] in ("order", "payment", "ticket")]
    assert purchase == ["order.create", "payment.start", "payment.succeeded", "ticket.issued"]
    exported = shop.get("/api/account/export").json()
    assert exported["orders"][0]["id"] == order["id"]


def test_payment_records_stay_when_the_account_is_deleted(shop):
    order = buy(shop)["order"]
    assert shop.post("/api/account/delete", json={"password": PASSWORD}).status_code == 200
    with shop.app.state.db.session() as db:
        from app.models import Order, Payment

        kept = db.get(Order, order["id"])
        assert kept is not None
        assert kept.user_id is None
        assert db.scalars(select(Payment).where(Payment.order_id == order["id"])).first() is not None
