"""Bus tickets, passes, Metro QR tickets, combined tickets, payments, refunds and receipts: integration-ready.

Nothing here sells anything. A purchase needs two authorised providers, and none is connected:
- a **ticketing provider** for the product: BMTC for bus tickets and passes, ONDC with BMRCL for Metro QR tickets
  (and both for a combined ticket). It quotes the official fare and issues the ticket.
- a **payment provider**: an RBI-authorised payment aggregator under a merchant agreement. It takes the payment
  (UPI and others) on its own page or in the passenger's UPI app, and makes refunds.

Until both exist, every purchase call answers 503 with the code and the official channel, and every history is empty.
Providers are classes with the methods in TicketProvider and PaymentProvider below. They are registered in
``Commerce(...)`` only after a written agreement exists; their credentials come from the environment.

Rules that hold even with providers connected:
- **No ticket is made here.** A ticket exists only when the ticketing provider issued it. Its QR payload is stored and
  shown exactly as the provider returned it; this app never draws or encodes one itself.
- **Paid means confirmed by the provider.** An order is paid only after the payment provider's signed notification
  says so, for the exact amount. A browser redirect or a passenger's word is never enough.
- **No payment secrets.** No card number, CVV, UPI PIN or password is ever received or stored: only the provider's
  references. Requests carrying unknown fields are refused.
- **Automatic refund** if the ticket cannot be issued after a payment.
- **Each notification once:** a provider event id is processed one time only.
- **No stored-value wallet:** holding passengers' money needs an RBI prepaid payment instrument licence. A wallet
  balance, if ever shown, would come from the operator's own provider.
- **Records are kept** after an account is deleted (the order loses its link to the account), as payment records
  must be.
"""

from __future__ import annotations

import datetime as dt
import json
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
PAYMENT_METHODS = ("UPI", "CARD", "NETBANKING")
REFUNDABLE = ("ISSUED",)


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
    next_action: dict[str, Any]  # for example {"type": "redirect", "url": ...} to the provider's own payment page


@dataclass(frozen=True)
class PaymentEvent:
    event_id: str
    provider_ref: str
    status: str  # SUCCEEDED, FAILED or REFUNDED
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

    def quote(self, product: str, details: dict[str, Any]) -> Quote: ...

    def issue(self, order: Order) -> Issued: ...

    def cancel(self, ticket: TravelTicket) -> bool: ...


class PaymentProvider(Protocol):
    name: str
    methods: tuple[str, ...]

    def start(self, order: Order, method: str) -> PaymentStart: ...

    def read_notification(self, headers: dict[str, str], body: bytes) -> PaymentEvent: ...

    def refund(self, payment: Payment, amount_paise: int, reason: str) -> RefundStart: ...


def _stamp(value: dt.datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


class Commerce:
    def __init__(self, ticket_providers: list[TicketProvider] | None = None,
                 payment_provider: PaymentProvider | None = None) -> None:
        self.tickets: dict[str, TicketProvider] = {}
        for provider in ticket_providers or []:
            for product in provider.products:
                self.tickets[product] = provider
        self.payment = payment_provider

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
            "products": products,
            "payments": {"available": self.payment is not None,
                         "methods": list(self.payment.methods) if self.payment else [],
                         "code": None if self.payment else payment.code,
                         "needs": None if self.payment else payment.needs},
            "wallet": {"available": False, "code": "NEEDS_OPERATOR_WALLET",
                       "needs": "A wallet held by the operator or an RBI-licensed prepaid payment instrument issuer; "
                                "this app never holds passengers' money"},
            "ncmc": {"available": False, "code": integrations.adapter("ncmc").code,
                     "needs": integrations.adapter("ncmc").needs},
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
                "breakdown": quote.breakdown, "fare_source": quote.fare_source}

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
                      quote=json.dumps({"breakdown": quote.breakdown, "fare_source": quote.fare_source}),
                      idempotency_key=key, created_at=now, updated_at=now)
        db.add(order)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(Order).where(Order.user_id == user.id, Order.idempotency_key == key))
            return self.order_out(db, existing)
        record_audit(db, actor=f"user:{user.id}", action="order.create", entity="order", entity_id=order.id,
                     detail={"product": product, "amount_paise": quote.amount_paise})
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
        started = self.payment.start(order, method)
        now = utcnow()
        db.add(Payment(order_id=order.id, provider=self.payment.name, provider_ref=started.provider_ref,
                       method=method, status="PENDING", amount_paise=order.amount_paise, created_at=now,
                       updated_at=now))
        order.status = "PAYMENT_PENDING"
        order.updated_at = now
        db.commit()
        return {"order": self.order_out(db, order), "next_action": started.next_action,
                "note": "Pay on the payment provider's page or in your UPI app. Never share your UPI PIN, card "
                        "number or CVV with this app: it never asks for them."}

    # ------------------------------------------------------------ provider notifications
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
        if event.status == "REFUNDED":
            return self._refunded(db, event, actor)
        payment = db.scalar(select(Payment).where(Payment.provider_ref == event.provider_ref))
        if payment is None:
            db.commit()
            raise CommerceError("UNKNOWN_PAYMENT", "Unknown payment reference.", 404)
        order = db.get(Order, payment.order_id)
        now = utcnow()
        payment.updated_at = order.updated_at = now
        if payment.status != "PENDING":
            db.commit()
            return {"processed": False, "order_status": order.status}
        if event.status == "SUCCEEDED" and event.amount_paise != payment.amount_paise:
            payment.status, order.status = "AMOUNT_MISMATCH", "FAILED"
            record_audit(db, actor=actor, action="payment.amount_mismatch", entity="order", entity_id=order.id,
                         detail={"expected": payment.amount_paise, "notified": event.amount_paise})
            db.commit()
            return {"processed": True, "order_status": order.status}
        if event.status != "SUCCEEDED":
            payment.status, order.status = "FAILED", "FAILED"
            record_audit(db, actor=actor, action="payment.failed", entity="order", entity_id=order.id, detail={})
            db.commit()
            return {"processed": True, "order_status": order.status}
        payment.status, order.status = "SUCCEEDED", "PAID"
        record_audit(db, actor=actor, action="payment.succeeded", entity="order", entity_id=order.id,
                     detail={"amount_paise": payment.amount_paise})
        try:
            issued = self.tickets[order.product].issue(order)
        except Exception:  # the provider failed after the payment: the passenger gets the money back automatically
            self._start_refund(db, payment, order, payment.amount_paise, "The ticket could not be issued", actor)
            db.commit()
            return {"processed": True, "order_status": order.status}
        db.add(TravelTicket(order_id=order.id, provider=self.tickets[order.product].name,
                            provider_ticket_id=issued.provider_ticket_id, product=order.product, status="ISSUED",
                            valid_from=issued.valid_from, valid_until=issued.valid_until,
                            qr_payload=issued.qr_payload, created_at=now))
        order.status = "ISSUED"
        record_audit(db, actor=actor, action="ticket.issued", entity="order", entity_id=order.id, detail={})
        db.commit()
        return {"processed": True, "order_status": order.status}

    def _start_refund(self, db: Session, payment: Payment, order: Order, amount: int, reason: str, actor: str) -> None:
        started = self.payment.refund(payment, amount, reason)
        now = utcnow()
        db.add(Refund(payment_id=payment.id, provider_ref=started.provider_ref, amount_paise=amount,
                      status=started.status, reason=reason[:300], created_at=now, updated_at=now))
        order.status = "REFUND_REQUESTED"
        order.updated_at = now
        record_audit(db, actor=actor, action="refund.requested", entity="order", entity_id=order.id,
                     detail={"amount_paise": amount, "reason": reason[:300]})

    def _refunded(self, db: Session, event: PaymentEvent, actor: str) -> dict[str, Any]:
        refund = db.scalar(select(Refund).where(Refund.provider_ref == (event.refund_ref or "")))
        if refund is None:
            db.commit()
            raise CommerceError("UNKNOWN_REFUND", "Unknown refund reference.", 404)
        payment = db.get(Payment, refund.payment_id)
        order = db.get(Order, payment.order_id)
        now = utcnow()
        refund.status, refund.updated_at = "COMPLETED", now
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
        return {
            "id": order.id, "product": order.product, "status": order.status, "amount_paise": order.amount_paise,
            "currency": order.currency, "ticket_provider": order.ticket_provider,
            "details": json.loads(order.details), "quote": json.loads(order.quote),
            "created_at": _stamp(order.created_at), "updated_at": _stamp(order.updated_at),
            "payments": [{"provider": p.provider, "reference": p.provider_ref, "method": p.method, "status": p.status,
                          "amount_paise": p.amount_paise, "at": _stamp(p.updated_at)} for p in payments],
            "tickets": [{"provider": t.provider, "provider_ticket_id": t.provider_ticket_id, "status": t.status,
                         "valid_from": _stamp(t.valid_from), "valid_until": _stamp(t.valid_until),
                         "qr_payload": t.qr_payload} for t in tickets],
            "refunds": [{"reference": r.provider_ref, "status": r.status, "amount_paise": r.amount_paise,
                         "reason": r.reason, "at": _stamp(r.updated_at)} for r in refunds],
            "receipt_available": any(p.status == "SUCCEEDED" for p in payments),
            "refundable": order.status in REFUNDABLE and all(t.status == "ISSUED" for t in tickets),
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
        return {
            "receipt_number": f"BTP-{order.id:08d}",
            "order_id": order.id, "product": order.product, "status": order.status,
            "items": quote.get("breakdown", []), "fare_source": quote.get("fare_source"),
            "amount_paise": payment.amount_paise, "currency": order.currency,
            "paid_with": {"provider": payment.provider, "reference": payment.provider_ref, "method": payment.method},
            "paid_at": _stamp(payment.updated_at), "ticket_provider": order.ticket_provider,
            "note": "Record of a payment confirmed by the payment provider. It is not a tax invoice and not a ticket.",
        }
