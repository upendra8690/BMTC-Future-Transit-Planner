"""Bus tickets, passes, Metro QR tickets, combined tickets, payments, refunds and receipts.

A purchase needs two providers, configured on the server (app/services/payment_providers.py):
- a **ticketing provider** for the product: BMTC's authorised ticketing provider for bus tickets and passes, ONDC with
  BMRCL for Metro QR tickets. It quotes the official fare and issues the ticket. None is connected.
- a **payment provider**: an RBI-authorised payment aggregator under the owner's merchant account. It takes the
  payment (UPI intent, UPI QR and others) on its own page or in the passenger's UPI app, and makes refunds.

Without both, every purchase answers 503 with the code and the official channel, and every history is empty.

A **sandbox environment** exists for testing only: a simulated gateway and a simulated ticketing provider, accepted
only on a demonstration server (DEMO_MODE=1, PAYMENT_ENVIRONMENT=sandbox). No money moves, every screen says
"DEMONSTRATION ONLY — NOT VALID FOR TRAVEL", and its records carry no QR code. A sandbox provider is never combined
with a production one.

Rules that hold in every environment:
- **Paid means confirmed by the provider, server to server.** An order is paid only after the provider's signed
  notification, or the provider's status API asked by this server, says so for the exact amount. Returning from a
  UPI app, a browser redirect or anything the app's own page says is never enough.
- **Unique transaction ids:** each payment attempt gets its own id (``BTP...``), sent to the provider as the receipt.
- **Each notification once:** a provider event id is processed one time only; a repeated callback changes nothing.
- **No ticket is made here.** A ticket exists only when the ticketing provider issued it; its QR payload is stored
  and shown exactly as sent. This app never draws or encodes a ticket QR itself.
- **Money is never kept by mistake:** a failed issue after payment, or a payment that arrives after its order
  expired, is refunded automatically.
- **No payment secrets:** no card number, CVV, UPI PIN, OTP or password is ever received or stored.
- **No stored-value wallet:** holding passengers' money needs an RBI prepaid payment instrument licence.
- **Records are kept** after an account is deleted, as payment records must be, and every change is audited.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import PRODUCTS, Order, Payment, PaymentNotification, Refund, TravelTicket, User, utcnow
from . import integrations
from .audit import record_audit

PRODUCT_CAPABILITY = {"BUS_TICKET": "bus_tickets", "BUS_PASS": "bus_passes", "METRO_QR": "metro_qr_tickets",
                      "COMBINED": "bus_tickets"}
PAYMENT_METHODS = ("UPI", "UPI_QR", "CARD", "NETBANKING")
REFUNDABLE = ("ISSUED",)
PENDING_MINUTES = 30  # a payment still pending after this is expired; a later success is refunded automatically
ENV_PRODUCTION, ENV_SANDBOX = "production", "sandbox"


class CommerceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, official_url: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.official_url = official_url


# ---------------------------------------------------------------- what providers return
@dataclass(frozen=True)
class Quote:
    amount_paise: int
    breakdown: list[dict[str, Any]] = field(default_factory=list)
    fare_source: str = ""


@dataclass(frozen=True)
class PaymentStart:
    provider_ref: str
    next_action: dict[str, Any]  # {"type": "redirect", "url": ...} to the provider's page (UPI intent or QR there)


@dataclass(frozen=True)
class PaymentEvent:
    event_id: str
    provider_ref: str
    status: str  # SUCCEEDED, FAILED, PENDING, REFUNDED or REFUND_FAILED
    amount_paise: int
    refund_ref: str | None = None


@dataclass(frozen=True)
class Issued:
    provider_ticket_id: str
    valid_from: dt.datetime | None
    valid_until: dt.datetime | None
    qr_payload: str | None


@dataclass(frozen=True)
class RefundStart:
    provider_ref: str
    status: str


class TicketProvider(Protocol):
    name: str
    products: tuple[str, ...]
    environment: str

    def quote(self, product: str, details: dict[str, Any]) -> Quote: ...

    def issue(self, order: Order) -> Issued: ...

    def cancel(self, ticket: TravelTicket) -> bool: ...


class PaymentProvider(Protocol):
    name: str
    methods: tuple[str, ...]
    environment: str

    def start(self, order: Order, payment: Payment) -> PaymentStart: ...

    def read_notification(self, headers: dict[str, str], body: bytes) -> PaymentEvent: ...

    def fetch_status(self, payment: Payment) -> PaymentEvent: ...  # raises CommerceError("PROVIDER_TIMEOUT", ..., 504)

    def refund(self, payment: Payment, amount_paise: int, reason: str) -> RefundStart: ...


def _stamp(value: dt.datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


def new_transaction_id(now: dt.datetime | None = None) -> str:
    """BTP + UTC date + 12 random hex characters: unique, unguessable, at most 40 characters (a provider receipt)."""
    return "BTP" + (now or utcnow()).strftime("%Y%m%d") + secrets.token_hex(6).upper()


class Commerce:
    def __init__(self, ticket_providers: list[TicketProvider] | None = None,
                 payment_provider: PaymentProvider | None = None, refusals: dict[str, str] | None = None) -> None:
        self.tickets: dict[str, TicketProvider] = {}
        for provider in ticket_providers or []:
            for product in provider.products:
                self.tickets[product] = provider
        self.payment = payment_provider
        self.refusals = refusals or {}
        environments = {getattr(p, "environment", ENV_PRODUCTION) for p in self.tickets.values()}
        if self.payment is not None:
            environments.add(getattr(self.payment, "environment", ENV_PRODUCTION))
        if len(environments) > 1:
            raise ValueError("A sandbox provider can never be combined with a production provider.")
        self.environment = environments.pop() if environments else ENV_PRODUCTION

    @property
    def sandbox(self) -> bool:
        return self.environment == ENV_SANDBOX

    # ------------------------------------------------------------ availability
    def status(self) -> dict[str, Any]:
        products = []
        for product in PRODUCTS:
            adapter = integrations.adapter(PRODUCT_CAPABILITY[product])
            connected = product in self.tickets
            products.append({"product": product, "available": connected and self.payment is not None,
                             "ticketing_connected": connected,
                             "code": None if connected else adapter.code, "needs": None if connected else adapter.needs,
                             "official_url": adapter.official_url})
        payment = integrations.adapter("payments")
        return {
            "environment": self.environment,
            "sandbox": self.sandbox,
            "sandbox_notice": "DEMONSTRATION ONLY — NOT VALID FOR TRAVEL. Sandbox payments: no money moves."
            if self.sandbox else None,
            "products": products,
            "payments": {"available": self.payment is not None, "provider": self.payment.name if self.payment else None,
                         "methods": list(self.payment.methods) if self.payment else [],
                         "code": None if self.payment else payment.code,
                         "needs": None if self.payment else payment.needs},
            "wallet": {"available": False, "code": "NEEDS_OPERATOR_WALLET",
                       "needs": "A wallet held by the operator or an RBI-licensed prepaid payment instrument issuer; "
                                "this app never holds passengers' money"},
            "ncmc": {"available": False, "code": integrations.adapter("ncmc").code,
                     "needs": integrations.adapter("ncmc").needs},
            "refused_settings": self.refusals,
            "note": "No ticket, pass, QR code, payment or receipt is produced by this app until authorised providers "
                    "are connected.",
        }

    def require(self, product: str) -> None:
        """Raises CommerceError (503 with the official channel) unless this product can be bought."""
        self._ticketing(product)

    def _ticketing(self, product: str) -> TicketProvider:
        if product not in PRODUCTS:
            raise CommerceError("UNKNOWN_PRODUCT", "Unknown product.", 422)
        provider = self.tickets.get(product)
        if provider is None:
            adapter = integrations.adapter(PRODUCT_CAPABILITY[product])
            raise CommerceError(adapter.code, f"Buying this is not available: {adapter.needs} is needed. "
                                              "Use the operator's official channel.", 503, adapter.official_url)
        if self.payment is None:
            adapter = integrations.adapter("payments")
            raise CommerceError(adapter.code, f"Payments are not available: {adapter.needs} is needed.", 503)
        return provider

    # ------------------------------------------------------------ buying
    def quote(self, product: str, details: dict[str, Any]) -> dict[str, Any]:
        quote = self._ticketing(product).quote(product, details)
        return {"product": product, "amount_paise": quote.amount_paise, "currency": "INR",
                "breakdown": quote.breakdown, "fare_source": quote.fare_source, "environment": self.environment}

    def create_order(self, db: Session, user: User, product: str, details: dict[str, Any], key: str) -> dict[str, Any]:
        provider = self._ticketing(product)
        existing = db.scalar(select(Order).where(Order.user_id == user.id, Order.idempotency_key == key))
        if existing is not None:
            return self.order_out(db, existing)
        quote = provider.quote(product, details)
        if quote.amount_paise <= 0:
            raise CommerceError("BAD_QUOTE", "The provider's fare could not be used.", 502)
        now = utcnow()
        order = Order(user_id=user.id, product=product, ticket_provider=provider.name, status="CREATED",
                      amount_paise=quote.amount_paise, currency="INR", details=json.dumps(details, sort_keys=True),
                      quote=json.dumps({"breakdown": quote.breakdown, "fare_source": quote.fare_source,
                                        "environment": self.environment}),
                      idempotency_key=key, created_at=now, updated_at=now)
        db.add(order)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(Order).where(Order.user_id == user.id, Order.idempotency_key == key))
            return self.order_out(db, existing)
        record_audit(db, actor=f"user:{user.id}", action="order.create", entity="order", entity_id=order.id,
                     detail={"product": product, "amount_paise": quote.amount_paise, "environment": self.environment})
        db.commit()
        return self.order_out(db, order)

    def _own_order(self, db: Session, user: User, order_id: int) -> Order:
        order = db.get(Order, order_id)
        if order is None or order.user_id != user.id:  # another account's order is reported as missing
            raise CommerceError("NO_SUCH_ORDER", "No such order.", 404)
        return order

    def pay(self, db: Session, user: User, order_id: int, method: str) -> dict[str, Any]:
        order = self._own_order(db, user, order_id)
        self._ticketing(order.product)
        if method not in self.payment.methods:
            raise CommerceError("METHOD_NOT_OFFERED", "That payment method is not offered.", 422)
        if order.status not in ("CREATED", "PAYMENT_PENDING"):
            raise CommerceError("ORDER_NOT_PAYABLE", "This order cannot be paid now.", 409)
        pending = db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.status == "PENDING"))
        if pending is not None:  # one payment attempt at a time: a second tap cannot charge twice
            raise CommerceError("PAYMENT_IN_PROGRESS", "A payment for this order is already in progress. Check its "
                                                       "status before trying again.", 409)
        now = utcnow()
        payment = Payment(order_id=order.id, provider=self.payment.name, provider_ref="", method=method,
                          status="PENDING", amount_paise=order.amount_paise, transaction_id=new_transaction_id(now),
                          created_at=now, updated_at=now)
        payment.provider_ref = "starting-" + payment.transaction_id
        db.add(payment)
        db.flush()
        try:
            started = self.payment.start(order, payment)
        except CommerceError:
            db.rollback()
            raise
        payment.provider_ref = started.provider_ref
        order.status = "PAYMENT_PENDING"
        order.updated_at = now
        record_audit(db, actor=f"user:{user.id}", action="payment.start", entity="order", entity_id=order.id,
                     detail={"transaction_id": payment.transaction_id, "method": method,
                             "provider": self.payment.name, "environment": self.environment})
        db.commit()
        return {"order": self.order_out(db, order), "next_action": started.next_action,
                "transaction_id": payment.transaction_id,
                "note": "Pay on the payment provider's page or in your UPI app. Never share your UPI PIN, card "
                        "number or CVV with this app: it never asks for them. After paying, this app asks the "
                        "provider whether the payment arrived; returning to the app is not enough."}

    # ------------------------------------------------------------ confirmation: webhook or server-side status check
    def notification(self, db: Session, provider_name: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        if self.payment is None or provider_name != self.payment.name:
            raise CommerceError("UNKNOWN_PROVIDER", "Unknown payment provider.", 404)
        event = self.payment.read_notification(headers, body)  # raises CommerceError(401) for a bad signature
        seen = db.scalar(select(PaymentNotification.id).where(PaymentNotification.provider == provider_name,
                                                              PaymentNotification.event_id == event.event_id))
        if seen is not None:
            return {"processed": False, "duplicate": True}
        db.add(PaymentNotification(provider=provider_name, event_id=event.event_id, received_at=utcnow()))
        actor = f"provider:{provider_name}"
        if event.status == "IGNORED":  # an event type this app does not act on
            db.commit()
            return {"processed": False, "ignored": True}
        if event.status in ("REFUNDED", "REFUND_FAILED"):
            return self._refund_result(db, event, actor)
        payment = db.scalar(select(Payment).where(Payment.provider_ref == event.provider_ref))
        if payment is None:
            db.commit()
            raise CommerceError("UNKNOWN_PAYMENT", "Unknown payment reference.", 404)
        result = self._apply(db, payment, event.status, event.amount_paise, actor)
        db.commit()
        return result

    def verify(self, db: Session, user: User | None, order_id: int, now: dt.datetime | None = None) -> dict[str, Any]:
        """Asks the payment provider, server to server, what happened to the order's pending payment."""
        order = self._own_order(db, user, order_id) if user is not None else db.get(Order, order_id)
        if order is None:
            raise CommerceError("NO_SUCH_ORDER", "No such order.", 404)
        payment = db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.status == "PENDING")
                            .order_by(Payment.id.desc()))
        if payment is None or self.payment is None:
            return self.order_out(db, order)
        event = self.payment.fetch_status(payment)  # CommerceError 504 on a timeout: nothing changes
        now = now or utcnow()
        if event.status == "PENDING":
            if now - payment.created_at > dt.timedelta(minutes=PENDING_MINUTES):
                payment.status, payment.updated_at = "EXPIRED", now
                order.status, order.updated_at = "FAILED", now
                record_audit(db, actor="system", action="payment.expired", entity="order", entity_id=order.id,
                             detail={"transaction_id": payment.transaction_id})
                db.commit()
            return self.order_out(db, order)
        self._apply(db, payment, event.status, event.amount_paise, f"provider:{self.payment.name}")
        db.commit()
        return self.order_out(db, order)

    def reconcile_pending(self, db: Session, now: dt.datetime | None = None) -> dict[str, int]:
        """Checks every pending payment with the provider (after a restart, or from an administrator)."""
        checked = changed = failed = 0
        ids = list(db.scalars(select(Payment.order_id).where(Payment.status == "PENDING")))
        for order_id in ids:
            before = db.get(Order, order_id).status
            try:
                after = self.verify(db, None, order_id, now)["status"]
            except CommerceError:
                failed += 1
                continue
            checked += 1
            changed += int(after != before)
        return {"checked": checked, "changed": changed, "unreachable": failed}

    def _apply(self, db: Session, payment: Payment, status: str, amount: int, actor: str) -> dict[str, Any]:
        order = db.get(Order, payment.order_id)
        now = utcnow()
        payment.updated_at = order.updated_at = now
        if status == "SUCCEEDED" and payment.status in ("EXPIRED", "FAILED"):
            # Money arrived after the order was given up: it is sent back, never kept without a ticket.
            payment.status = "SUCCEEDED"
            self._start_refund(db, payment, order, amount, "Payment arrived after the order expired", actor)
            return {"processed": True, "order_status": order.status}
        if payment.status != "PENDING":
            return {"processed": False, "order_status": order.status}
        if status == "PENDING":
            return {"processed": False, "order_status": order.status}
        if status == "SUCCEEDED" and amount != payment.amount_paise:
            payment.status, order.status = "AMOUNT_MISMATCH", "FAILED"
            record_audit(db, actor=actor, action="payment.amount_mismatch", entity="order", entity_id=order.id,
                         detail={"expected": payment.amount_paise, "notified": amount,
                                 "transaction_id": payment.transaction_id})
            return {"processed": True, "order_status": order.status}
        if status != "SUCCEEDED":
            payment.status, order.status = "FAILED", "FAILED"
            record_audit(db, actor=actor, action="payment.failed", entity="order", entity_id=order.id,
                         detail={"transaction_id": payment.transaction_id})
            return {"processed": True, "order_status": order.status}
        payment.status, order.status = "SUCCEEDED", "PAID"
        record_audit(db, actor=actor, action="payment.succeeded", entity="order", entity_id=order.id,
                     detail={"amount_paise": payment.amount_paise, "transaction_id": payment.transaction_id})
        try:
            issued = self.tickets[order.product].issue(order)
        except Exception:  # the provider failed after the payment: the passenger gets the money back automatically
            self._start_refund(db, payment, order, payment.amount_paise, "The ticket could not be issued", actor)
            return {"processed": True, "order_status": order.status}
        db.add(TravelTicket(order_id=order.id, provider=self.tickets[order.product].name,
                            provider_ticket_id=issued.provider_ticket_id, product=order.product, status="ISSUED",
                            valid_from=issued.valid_from, valid_until=issued.valid_until,
                            qr_payload=issued.qr_payload, created_at=now))
        order.status = "ISSUED"
        record_audit(db, actor=actor, action="ticket.issued", entity="order", entity_id=order.id,
                     detail={"environment": self.environment})
        return {"processed": True, "order_status": order.status}

    def _start_refund(self, db: Session, payment: Payment, order: Order, amount: int, reason: str, actor: str) -> None:
        started = self.payment.refund(payment, amount, reason)
        now = utcnow()
        db.add(Refund(payment_id=payment.id, provider_ref=started.provider_ref, amount_paise=amount,
                      status=started.status, reason=reason[:300], created_at=now, updated_at=now))
        order.status = "REFUND_REQUESTED"
        order.updated_at = now
        record_audit(db, actor=actor, action="refund.requested", entity="order", entity_id=order.id,
                     detail={"amount_paise": amount, "reason": reason[:300], "transaction_id": payment.transaction_id})

    def _refund_result(self, db: Session, event: PaymentEvent, actor: str) -> dict[str, Any]:
        refund = db.scalar(select(Refund).where(Refund.provider_ref == (event.refund_ref or "")))
        if refund is None:
            db.commit()
            raise CommerceError("UNKNOWN_REFUND", "Unknown refund reference.", 404)
        payment = db.get(Payment, refund.payment_id)
        order = db.get(Order, payment.order_id)
        now = utcnow()
        refund.updated_at = now
        if event.status == "REFUND_FAILED":
            refund.status = "FAILED"
            record_audit(db, actor=actor, action="refund.failed", entity="order", entity_id=order.id,
                         detail={"refund": refund.provider_ref})
            db.commit()
            return {"processed": True, "order_status": order.status}
        refund.status = "COMPLETED"
        order.status, order.updated_at = "REFUNDED", now
        for ticket in db.scalars(select(TravelTicket).where(TravelTicket.order_id == order.id)):
            ticket.status = "REFUNDED"
        record_audit(db, actor=actor, action="refund.completed", entity="order", entity_id=order.id,
                     detail={"amount_paise": refund.amount_paise})
        db.commit()
        return {"processed": True, "order_status": order.status}

    # ------------------------------------------------------------ refunds asked for by the passenger
    def request_refund(self, db: Session, user: User, order_id: int, reason: str) -> dict[str, Any]:
        order = self._own_order(db, user, order_id)
        if self.payment is None or order.product not in self.tickets:
            raise CommerceError("PROVIDER_NOT_CONNECTED", "Refunds need the provider that sold the ticket.", 503)
        if order.status not in REFUNDABLE:
            raise CommerceError("NOT_REFUNDABLE", "This order cannot be refunded.", 409)
        payment = db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.status == "SUCCEEDED"))
        tickets = list(db.scalars(select(TravelTicket).where(TravelTicket.order_id == order.id)))
        if payment is None or any(t.status != "ISSUED" for t in tickets):
            raise CommerceError("NOT_REFUNDABLE", "Only an unused ticket can be refunded.", 409)
        if not all(self.tickets[order.product].cancel(t) for t in tickets):
            raise CommerceError("CANCEL_REFUSED", "The operator did not cancel the ticket, so it cannot be refunded.",
                                409)
        for ticket in tickets:
            ticket.status = "CANCELLED"
        self._start_refund(db, payment, order, payment.amount_paise, reason, f"user:{user.id}")
        db.commit()
        return self.order_out(db, order)

    # ------------------------------------------------------------ history and receipts
    def order_out(self, db: Session, order: Order) -> dict[str, Any]:
        payments = list(db.scalars(select(Payment).where(Payment.order_id == order.id).order_by(Payment.id)))
        refunds = list(db.scalars(select(Refund).where(Refund.payment_id.in_([p.id for p in payments])))) \
            if payments else []
        tickets = list(db.scalars(select(TravelTicket).where(TravelTicket.order_id == order.id)))
        quote = json.loads(order.quote)
        return {
            "id": order.id, "product": order.product, "status": order.status, "amount_paise": order.amount_paise,
            "currency": order.currency, "ticket_provider": order.ticket_provider,
            "environment": quote.get("environment", ENV_PRODUCTION),
            "details": json.loads(order.details), "quote": quote,
            "created_at": _stamp(order.created_at), "updated_at": _stamp(order.updated_at),
            "payments": [{"provider": p.provider, "reference": p.provider_ref, "transaction_id": p.transaction_id,
                          "method": p.method, "status": p.status, "amount_paise": p.amount_paise,
                          "at": _stamp(p.updated_at)} for p in payments],
            "tickets": [{"provider": t.provider, "provider_ticket_id": t.provider_ticket_id, "status": t.status,
                         "valid_from": _stamp(t.valid_from), "valid_until": _stamp(t.valid_until),
                         "qr_payload": t.qr_payload} for t in tickets],
            "refunds": [{"reference": r.provider_ref, "status": r.status, "amount_paise": r.amount_paise,
                         "reason": r.reason, "at": _stamp(r.updated_at)} for r in refunds],
            "receipt_available": any(p.status == "SUCCEEDED" for p in payments),
            "refundable": order.status in REFUNDABLE and all(t.status == "ISSUED" for t in tickets),
            "payable": order.status in ("CREATED", "PAYMENT_PENDING")
            and not any(p.status == "PENDING" for p in payments),
            "checkable": any(p.status == "PENDING" for p in payments),
        }

    def history(self, db: Session, user: User) -> list[dict[str, Any]]:
        orders = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()))
        return [self.order_out(db, order) for order in orders]

    def order(self, db: Session, user: User, order_id: int) -> dict[str, Any]:
        return self.order_out(db, self._own_order(db, user, order_id))

    def receipt(self, db: Session, user: User, order_id: int) -> dict[str, Any]:
        order = self._own_order(db, user, order_id)
        payment = db.scalar(select(Payment).where(Payment.order_id == order.id, Payment.status == "SUCCEEDED"))
        if payment is None:
            raise CommerceError("NO_RECEIPT", "A receipt exists only for a payment the provider confirmed.", 409)
        quote = json.loads(order.quote)
        sandbox = quote.get("environment") == ENV_SANDBOX
        return {
            "receipt_number": f"BTP-{order.id:08d}",
            "transaction_id": payment.transaction_id,
            "environment": quote.get("environment", ENV_PRODUCTION),
            "order_id": order.id, "product": order.product, "status": order.status,
            "items": quote.get("breakdown", []), "fare_source": quote.get("fare_source"),
            "amount_paise": payment.amount_paise, "currency": order.currency,
            "paid_with": {"provider": payment.provider, "reference": payment.provider_ref, "method": payment.method},
            "paid_at": _stamp(payment.updated_at), "ticket_provider": order.ticket_provider,
            "note": ("DEMONSTRATION ONLY — NOT VALID FOR TRAVEL. Sandbox record: no money moved. " if sandbox else "")
            + "Record of a payment confirmed by the payment provider. It is not a tax invoice and not a ticket.",
        }
