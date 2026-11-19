"""The sandbox payment environment: every payment outcome, end to end, on a demonstration server.

The sandbox gateway and sandbox ticketing provider run only with DEMO_MODE=1 and PAYMENT_ENVIRONMENT=sandbox. No money
moves and the records are not tickets (no QR code, no validity). Outcomes are chosen on the sandbox payment page, as a
tester would. The scenarios: success, failure, pending (and expiry, with a late success refunded), a duplicate
callback, an invalid signature, a time-out, a refund, and a restart of this server in the middle of a payment.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from app.main import create_app
from app.models import AuditLog, Payment
from app.services.commerce import Commerce
from app.services.payment_providers import SandboxGateway, SandboxTicketing, build_commerce
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.helpers import make_settings

PASSWORD = "correct horse battery"  # noqa: S105 - a test account's password
TRIP = {"from_stop": "Majestic", "to_stop": "Indiranagar", "passengers": {"adult": 2, "child": 1}}


def sandbox_settings(tmp_path, **changes):
    values = {"demo_mode": True, "accounts_enabled": True, "accounts_allow_sqlite": True,
              "payment_provider": "sandbox", "payment_environment": "sandbox", "ticketing_provider": "sandbox",
              "payment_sandbox_state": tmp_path / "sandbox-gateway.json"}
    values.update(changes)
    return make_settings(tmp_path, **values)


def signed_in(client) -> None:
    client.post("/api/account/register", json={"email": "tester@example.org", "password": PASSWORD})
    token = client.post("/api/account/sign-in", json={"email": "tester@example.org", "password": PASSWORD}).json()
    client.headers.update({"Authorization": "Bearer " + token["token"]})


@pytest.fixture
def sandbox(tmp_path):
    app = create_app(sandbox_settings(tmp_path))
    with TestClient(app, follow_redirects=False) as client:
        signed_in(client)
        yield client
    app.state.db.dispose()


def start(client, key="order-key-0001", method="UPI"):
    order = client.post("/api/commerce/orders", json={"product": "BUS_TICKET", "details": TRIP,
                                                      "idempotency_key": key}).json()
    paying = client.post(f"/api/commerce/orders/{order['id']}/pay", json={"method": method})
    assert paying.status_code == 200, paying.text
    data = paying.json()
    return data["order"]["id"], data["next_action"]["url"].rsplit("/", 1)[1], data


def choose(client, ref, outcome):
    answer = client.post(f"/sandbox/pay/{ref}", data={"outcome": outcome})
    assert answer.status_code == 303, answer.text
    return answer


def order(client, order_id):
    return client.get(f"/api/commerce/orders/{order_id}").json()


# ---------------------------------------------------------------- separation of environments
def test_the_sandbox_is_refused_on_a_real_server(tmp_path):
    shop = build_commerce(sandbox_settings(tmp_path, demo_mode=False))
    status = shop.status()
    assert status["payments"]["available"] is False
    refused = "SANDBOX_NEEDS_DEMO_SERVER"
    assert status["refused_settings"] == {"payment": refused, "ticketing": refused}
    assert status["environment"] == "production"


def test_the_sandbox_needs_the_sandbox_environment(tmp_path):
    shop = build_commerce(sandbox_settings(tmp_path, payment_environment="production"))
    assert shop.payment is None
    assert shop.refusals == {"payment": "SANDBOX_NEEDS_DEMO_SERVER", "ticketing": "SANDBOX_NEEDS_DEMO_SERVER"}


def test_sandbox_and_production_are_never_mixed(tmp_path):
    shop = build_commerce(sandbox_settings(
        tmp_path, payment_provider="razorpay", payment_environment="sandbox", razorpay_key_id="rzp_test_ABCDEFGH1234",
        razorpay_key_secret="s" * 24, razorpay_webhook_secret="w" * 24, public_base_url="https://demo.example.org"))
    # Razorpay test keys on a demonstration server are a sandbox gateway too, so this pair is allowed...
    assert shop.payment is not None
    assert shop.sandbox
    # ...but in production the sandbox ticketing provider is refused, so a live gateway has nothing to sell.
    live = build_commerce(sandbox_settings(
        tmp_path, payment_provider="razorpay", payment_environment="production",
        razorpay_key_id="rzp_live_ABCDEFGH1234",
        razorpay_key_secret="s" * 24, razorpay_webhook_secret="w" * 24, public_base_url="https://planner.example.org"))
    assert live.tickets == {}
    assert live.refusals == {"ticketing": "SANDBOX_NEEDS_DEMO_SERVER"}
    assert not any(p["available"] for p in live.status()["products"])
    # And the two can never be put together directly.
    with pytest.raises(ValueError, match="never be combined"):
        Commerce([SandboxTicketing()], live.payment)


def test_the_sandbox_pages_do_not_exist_on_other_servers(client):
    assert client.get("/sandbox").status_code == 404
    assert client.get("/sandbox/pay/sbx_0000").status_code == 404


def test_every_sandbox_answer_says_it_is_a_demonstration(sandbox):
    status = sandbox.get("/api/commerce/status").json()
    assert status["environment"] == "sandbox"
    assert status["sandbox_notice"].startswith("DEMONSTRATION ONLY — NOT VALID FOR TRAVEL")
    quote = sandbox.post("/api/commerce/quotes", json={"product": "BUS_TICKET", "details": TRIP}).json()
    assert quote["fare_source"] == "Sandbox test amount: not a fare"
    assert quote["amount_paise"] == 300
    _, ref, _ = start(sandbox)
    assert "DEMONSTRATION ONLY — NOT VALID FOR TRAVEL" in sandbox.get(f"/sandbox/pay/{ref}").text


# ---------------------------------------------------------------- outcomes
def test_successful_payment(sandbox):
    order_id, ref, data = start(sandbox)
    assert re.fullmatch(r"BTP\d{8}[0-9A-F]{12}", data["transaction_id"])
    assert order(sandbox, order_id)["status"] == "PAYMENT_PENDING"
    choose(sandbox, ref, "succeed")
    done = order(sandbox, order_id)
    assert done["status"] == "ISSUED"
    ticket = done["tickets"][0]
    assert ticket["provider_ticket_id"].startswith("DEMO-")
    assert ticket["qr_payload"] is None  # a demonstration record never has a QR code
    receipt = sandbox.get(f"/api/commerce/orders/{order_id}/receipt").json()
    assert receipt["note"].startswith("DEMONSTRATION ONLY — NOT VALID FOR TRAVEL")
    assert receipt["transaction_id"] == data["transaction_id"]


def test_failed_payment(sandbox):
    order_id, ref, _ = start(sandbox)
    choose(sandbox, ref, "fail")
    failed = order(sandbox, order_id)
    assert failed["status"] == "FAILED"
    assert failed["tickets"] == []
    assert sandbox.get(f"/api/commerce/orders/{order_id}/receipt").status_code == 409


def test_returning_from_the_upi_app_proves_nothing(sandbox):
    order_id, ref, _ = start(sandbox)
    # The passenger comes back to the app (the redirect) without the gateway having been paid.
    sandbox.get(f"/sandbox/pay/{ref}")
    checked = sandbox.post(f"/api/commerce/orders/{order_id}/verify").json()
    assert checked["status"] == "PAYMENT_PENDING"
    assert checked["tickets"] == []


def test_pending_payment_then_expiry_and_a_late_success_is_refunded(sandbox):
    order_id, ref, _ = start(sandbox)
    choose(sandbox, ref, "pending")
    assert sandbox.post(f"/api/commerce/orders/{order_id}/verify").json()["status"] == "PAYMENT_PENDING"
    shop = sandbox.app.state.commerce
    with sandbox.app.state.db.session() as db:
        later = dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(minutes=31)
        assert shop.verify(db, None, order_id, now=later)["status"] == "FAILED"
        assert db.scalar(select(Payment.status).where(Payment.order_id == order_id)) == "EXPIRED"
    # The gateway takes the money after all: it is sent back, never kept without a ticket.
    choose(sandbox, ref, "succeed")
    late = order(sandbox, order_id)
    assert late["status"] == "REFUND_REQUESTED"
    assert late["tickets"] == []
    assert late["refunds"][0]["reason"] == "Payment arrived after the order expired"


def test_a_duplicate_callback_changes_nothing(sandbox):
    order_id, ref, _ = start(sandbox)
    gateway = sandbox.app.state.commerce.payment
    headers, body = gateway.act(ref, "succeed")
    first = sandbox.post("/api/commerce/notifications/sandbox", content=body, headers=headers)
    again = sandbox.post("/api/commerce/notifications/sandbox", content=body, headers=headers)
    assert first.json()["processed"] is True
    assert again.json() == {"processed": False, "duplicate": True}
    assert len(order(sandbox, order_id)["tickets"]) == 1


def test_an_invalid_signature_is_refused(sandbox):
    order_id, ref, _ = start(sandbox)
    _, body = sandbox.app.state.commerce.payment.act(ref, "succeed")
    forged = sandbox.post("/api/commerce/notifications/sandbox", content=body,
                          headers={"x-sandbox-signature": "0" * 64})
    assert forged.status_code == 401
    assert order(sandbox, order_id)["status"] == "PAYMENT_PENDING"


def test_a_time_out_leaves_the_order_pending_and_a_later_check_completes_it(sandbox):
    order_id, ref, _ = start(sandbox)
    choose(sandbox, ref, "timeout")
    timed_out = sandbox.post(f"/api/commerce/orders/{order_id}/verify")
    assert timed_out.status_code == 504
    assert timed_out.headers["x-error-code"] == "PROVIDER_TIMEOUT"
    assert order(sandbox, order_id)["status"] == "PAYMENT_PENDING"
    choose(sandbox, ref, "succeed_silently")  # the gateway answers again; no webhook this time
    assert sandbox.post(f"/api/commerce/orders/{order_id}/verify").json()["status"] == "ISSUED"


def test_a_second_payment_attempt_cannot_start_while_one_is_pending(sandbox):
    order_id, _, _ = start(sandbox)
    again = sandbox.post(f"/api/commerce/orders/{order_id}/pay", json={"method": "UPI"})
    assert again.status_code == 409


def test_refund(sandbox):
    order_id, ref, _ = start(sandbox)
    choose(sandbox, ref, "succeed")
    asked = sandbox.post(f"/api/commerce/orders/{order_id}/refund", json={"reason": "Plans changed"}).json()
    assert asked["status"] == "REFUND_REQUESTED"
    refund_ref = asked["refunds"][0]["reference"]
    assert refund_ref in sandbox.get("/sandbox").text
    assert sandbox.post(f"/sandbox/refunds/{refund_ref}", data={"result": "processed"}).status_code == 303
    done = order(sandbox, order_id)
    assert done["status"] == "REFUNDED"
    assert done["refunds"][0]["status"] == "COMPLETED"


def test_a_failed_refund_is_recorded(sandbox):
    order_id, ref, _ = start(sandbox)
    choose(sandbox, ref, "succeed")
    refund_ref = sandbox.post(f"/api/commerce/orders/{order_id}/refund",
                              json={"reason": "Plans changed"}).json()["refunds"][0]["reference"]
    sandbox.post(f"/sandbox/refunds/{refund_ref}", data={"result": "failed"})
    assert order(sandbox, order_id)["refunds"][0]["status"] == "FAILED"


def test_a_restart_in_the_middle_of_a_payment_loses_nothing(tmp_path):
    settings = sandbox_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, follow_redirects=False) as client:
        signed_in(client)
        order_id, ref, _ = start(client)
        token = client.headers["Authorization"]
    app.state.db.dispose()  # the server stops while the passenger is in the UPI app

    # The gateway completes the payment while this server is down: no webhook reaches it.
    SandboxGateway(settings.payment_sandbox_state).act(ref, "succeed_silently")

    app = create_app(settings)
    with TestClient(app, follow_redirects=False) as client:
        client.headers.update({"Authorization": token})
        assert order(client, order_id)["status"] == "PAYMENT_PENDING"
        with app.state.db.session() as db:
            result = app.state.commerce.reconcile_pending(db)
            entries = list(db.scalars(select(AuditLog.action)))
        assert result == {"checked": 1, "changed": 1, "unreachable": 0}
        assert order(client, order_id)["status"] == "ISSUED"
        assert "payment.start" in entries
    app.state.db.dispose()


def test_the_sandbox_ticketing_provider_never_makes_a_qr_code():
    issued = SandboxTicketing().issue(type("O", (), {"id": 7})())
    assert (issued.provider_ticket_id, issued.qr_payload, issued.valid_until) == ("DEMO-000007", None, None)
