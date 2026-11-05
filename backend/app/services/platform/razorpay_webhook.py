"""Razorpay's webhook: a `payment.captured` lands as a subscription payment (Milestone 30).

Razorpay calls one address for every company, so the company is found from the order, across
companies: that is why this lives under `services/platform/`. The route is open (Razorpay signs
the body instead): the signature is checked with the webhook secret, in constant time, before
the body is read. A duplicate, an unknown order or any other event answers 200 so Razorpay
stops retrying; only a bad signature or an unreadable body is refused (400).
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.core.tenancy import clear_platform, set_platform, set_tenant
from app.domain import online_renewal as rules
from app.models.billing import SubscriptionOrder
from app.schemas.online_renewal import WebhookAnswer
from app.services import online_renewal
from app.services.audit import set_actor, set_actor_label

logger = logging.getLogger(__name__)

ACTOR = "Razorpay (online payment)"


def _find_order(db: Session, razorpay_order_id: str) -> SubscriptionOrder | None:
    set_platform(db)
    try:
        found = select(SubscriptionOrder).where(
            SubscriptionOrder.razorpay_order_id == razorpay_order_id
        )
        return db.execute(found).scalar_one_or_none()
    finally:
        clear_platform(db)


def handle(db: Session, body: bytes, signature: str | None) -> WebhookAnswer:
    secret = get_settings().razorpay_webhook_secret.get_secret_value()
    if not secret:
        raise NotFoundError("Not found")
    if not rules.webhook_signature_ok(body, signature, secret):
        logger.warning("Refused a Razorpay webhook with a bad signature")
        raise AppError("The webhook signature does not match.", code="SIGNATURE_INVALID")
    try:
        event = json.loads(body)
    except ValueError as exc:
        raise AppError("The webhook body is not JSON.", code="BAD_PAYLOAD") from exc

    paid = rules.captured_payment(event)
    if paid is None:
        return WebhookAnswer(status="ignored")
    order = _find_order(db, paid.order_id)
    if order is None:  # not a renewal (another use of the same Razorpay account)
        logger.info("Razorpay webhook for order %s, which is not a renewal; ignored", paid.order_id)
        return WebhookAnswer(status="ignored")
    if not rules.matches_order(
        paid, amount_paise=rules.to_paise(order.amount), currency=order.currency
    ):
        logger.warning(
            "Razorpay payment %s does not match order %s (amount or currency); not applied",
            paid.payment_id,
            paid.order_id,
        )
        return WebhookAnswer(status="ignored")

    set_tenant(db, order.tenant_id)
    set_actor(db, None)
    set_actor_label(db, ACTOR)
    applied = online_renewal.apply_payment(db, order.id, paid.payment_id, via="webhook")
    return WebhookAnswer(status="applied" if applied else "duplicate")
