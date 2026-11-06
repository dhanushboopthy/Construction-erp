"""Online renewal through Razorpay (Milestone 30, ADR 0013).

Pure rules: no database, no network, no clock. The money is always worked out by the server from
the plan's price; the browser only says which price it chose. Razorpay proves a payment with an
HMAC-SHA256 signature, checked here in constant time:

- after Checkout, over "<order id>|<payment id>" with the key secret;
- on a webhook, over the raw request body with the webhook secret.
"""

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.plans import MAX_PRICE
from app.domain.subscriptions import SubscriptionRuleError

CURRENCY = "INR"
CAPTURED_EVENT = "payment.captured"
MIN_ORDER = Decimal("1.00")  # Razorpay's smallest order is one rupee (100 paise)
_PAISA = Decimal("0.01")


def to_paise(amount: Decimal) -> int:
    """Rupees as the whole number of paise Razorpay is sent."""
    if (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or amount != amount.quantize(_PAISA)
        or not MIN_ORDER <= amount <= MAX_PRICE
    ):
        raise SubscriptionRuleError(
            "ORDER_AMOUNT", "An online payment is at least one rupee, in whole paise."
        )
    return int(amount * 100)


def is_offered(*, price: Decimal, plan_active: bool, price_active: bool, trial_plan: bool) -> bool:
    """An owner may buy online any active price, of at least a rupee, of an active paid plan."""
    return plan_active and price_active and not trial_plan and price >= MIN_ORDER


def check_payable(
    *, price: Decimal, plan_active: bool, price_active: bool, trial_plan: bool
) -> None:
    if not is_offered(
        price=price, plan_active=plan_active, price_active=price_active, trial_plan=trial_plan
    ):
        raise SubscriptionRuleError(
            "PRICE_NOT_OFFERED", "That price is not on sale online. Choose another."
        )


def _sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _same(expected: str, given: str | None) -> bool:
    """Constant-time compare. Anything that is not plain text cannot be a hex signature."""
    if not given:
        return False
    try:
        offered = given.encode("ascii")
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(expected.encode("ascii"), offered)


def checkout_signature(order_id: str, payment_id: str, secret: str) -> str:
    return _sign(secret, f"{order_id}|{payment_id}".encode())


def checkout_signature_ok(
    order_id: str, payment_id: str, signature: str | None, secret: str
) -> bool:
    """The browser's proof that Razorpay took this payment for this order. With no secret
    configured nothing passes, not even a signature made with an empty key."""
    return bool(secret) and _same(checkout_signature(order_id, payment_id, secret), signature)


def webhook_signature(body: bytes, secret: str) -> str:
    return _sign(secret, body)


def webhook_signature_ok(body: bytes, signature: str | None, secret: str) -> bool:
    return bool(secret) and _same(webhook_signature(body, secret), signature)


@dataclass(frozen=True)
class CapturedPayment:
    payment_id: str
    order_id: str
    amount_paise: int
    currency: str


def _dict(value: Any, key: str) -> dict[str, Any] | None:
    found = value.get(key) if isinstance(value, dict) else None
    return found if isinstance(found, dict) else None


def captured_payment(event: Any) -> CapturedPayment | None:
    """The payment a `payment.captured` webhook reports. Any other event, and a payment that was
    not made against an order, is None: there is nothing to apply."""
    if not isinstance(event, dict) or event.get("event") != CAPTURED_EVENT:
        return None
    entity = _dict(_dict(_dict(event, "payload"), "payment"), "entity")
    if entity is None:
        return None
    payment_id, order_id = entity.get("id"), entity.get("order_id")
    amount, currency = entity.get("amount"), entity.get("currency")
    if not (isinstance(payment_id, str) and payment_id and isinstance(order_id, str) and order_id):
        return None
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        return None
    if not isinstance(currency, str):
        return None
    return CapturedPayment(payment_id, order_id, amount, currency)


def matches_order(payment: CapturedPayment, *, amount_paise: int, currency: str) -> bool:
    """The captured payment is for exactly what the server asked."""
    return payment.amount_paise == amount_paise and payment.currency == currency
