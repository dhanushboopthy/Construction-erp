"""A company owner renews Duolink online with Razorpay (Milestone 30, ADR 0013).

1. `overview`: the plan, its end, and the prices on sale online.
2. `create_order`: a Razorpay order for one price. The amount is the plan price on the server;
   the browser only names the price.
3. `verify`: Checkout's signature is checked here, then the payment is applied.
4. The webhook (`services/platform/razorpay_webhook.py`) applies the same payment when Razorpay
   reports it, even if the buyer closed the browser.

`apply_payment` is the one place a payment lands. It is keyed on the Razorpay payment id: the
order row is locked, a paid order is a no-op, and a unique index on the payment reference backs
that up, so Checkout and the webhook can arrive in either order and only one payment and one
renewal are recorded. Access is checked on every request, so a read-only company can save again
at once.
"""

import logging
import secrets
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, BusinessRuleError, NotFoundError, UpstreamError
from app.core.tenancy import current_tenant_id
from app.domain import online_renewal as rules
from app.domain import plans as plan_rules
from app.domain import subscriptions as sub_rules
from app.domain.subscriptions import AccessState, SubscriptionRuleError
from app.models.billing import Subscription, SubscriptionOrder, SubscriptionPayment
from app.models.enums import PaymentMethod, PlatformAction, SubscriptionOrderStatus
from app.models.platform import PlatformPlan, PlatformPlanPrice
from app.models.tenancy import Tenant
from app.schemas.online_renewal import (
    RenewalOption,
    RenewalOrderCreate,
    RenewalOrderOut,
    RenewalOverview,
    RenewalResult,
    VerifyRequest,
)
from app.services import razorpay
from app.services.platform.audit import record
from app.services.platform.billing import start_paid_period
from app.services.subscription_access import access_of

logger = logging.getLogger(__name__)

PAYEE = "Duolink"
OFF_MESSAGE = "Online renewal is not set up. Contact Duolink to renew."


def _now() -> datetime:
    return datetime.now(UTC)


def _off() -> BusinessRuleError:
    return BusinessRuleError(OFF_MESSAGE, code="ONLINE_RENEWAL_OFF")


def duration_label(value: int, unit: str) -> str:
    return f"{value} {unit}" + ("" if value == 1 else "s")


def _subscription(db: Session) -> Subscription:
    sub = db.execute(
        select(Subscription).where(Subscription.tenant_id == current_tenant_id(db))
    ).scalar_one_or_none()
    if sub is None:
        raise BusinessRuleError(
            "This company has no Duolink subscription yet. Contact Duolink.",
            code="NO_SUBSCRIPTION",
        )
    return sub


def _on_sale(db: Session) -> list[tuple[PlatformPlanPrice, PlatformPlan]]:
    """Every active price of at least a rupee on an active paid plan, in catalogue order."""
    rows = db.execute(
        select(PlatformPlanPrice, PlatformPlan)
        .join(PlatformPlan, PlatformPlan.id == PlatformPlanPrice.plan_id)
        .where(PlatformPlan.is_active.is_(True), PlatformPlanPrice.is_active.is_(True))
        .order_by(
            PlatformPlan.sort_order,
            PlatformPlan.id,
            PlatformPlanPrice.sort_order,
            PlatformPlanPrice.id,
        )
    ).all()
    return [
        (price, plan)
        for price, plan in rows
        if rules.is_offered(
            price=price.price,
            plan_active=plan.is_active,
            price_active=price.is_active,
            trial_plan=plan_rules.is_trial_plan(plan.code),
        )
    ]


StatusName = Literal["trial", "active", "expired", "cancelled"]
AccessName = Literal["full", "read_only"]


def _state(tenant: Tenant, sub: Subscription, now: datetime) -> tuple[StatusName, AccessName]:
    access = access_of(tenant, sub, now)
    status = cast(StatusName, sub_rules.effective_status(sub.status.value, sub.expires_at, now))
    return status, "read_only" if access.state is AccessState.READ_ONLY else "full"


def overview(db: Session, tenant: Tenant) -> RenewalOverview:
    sub = _subscription(db)
    now = _now()
    plan = db.get(PlatformPlan, sub.plan_id)
    if plan is None:  # pragma: no cover - the foreign key keeps it
        raise NotFoundError("Plan not found", code="PLAN_NOT_FOUND")
    status, state = _state(tenant, sub, now)
    enabled = get_settings().online_renewal_enabled
    options = []
    for price, offered in _on_sale(db) if enabled else []:
        unit = price.duration_unit.value
        period = sub_rules.renewal_period(
            status=sub.status.value,
            expires_at=sub.expires_at,
            duration_value=price.duration_value,
            duration_unit=unit,
            now=now,
        )
        options.append(
            RenewalOption(
                price_id=price.id,
                plan_id=offered.id,
                plan_code=offered.code,
                plan_name=offered.name,
                plan_description=offered.short_description,
                duration_value=price.duration_value,
                duration_unit=unit,
                price=price.price,
                currency=price.currency,
                is_current_plan=offered.id == sub.plan_id,
                would_run_until=period.expires_at,
            )
        )
    return RenewalOverview(
        online_renewal=enabled,
        plan_code=plan.code,
        plan_name=plan.name,
        status=status,
        access_state=state,
        expires_at=sub.expires_at,
        days_left=sub_rules.days_left(sub.expires_at, now),
        options=options,
    )


def create_order(
    db: Session, tenant: Tenant, user_id: int, data: RenewalOrderCreate
) -> RenewalOrderOut:
    settings = get_settings()
    if not settings.online_renewal_enabled:
        raise _off()
    sub = _subscription(db)
    found = db.execute(
        select(PlatformPlanPrice, PlatformPlan)
        .join(PlatformPlan, PlatformPlan.id == PlatformPlanPrice.plan_id)
        .where(PlatformPlanPrice.id == data.price_id)
    ).first()
    if found is None:
        raise NotFoundError(
            "That price is not one of Duolink's plans.", code="PRICE_NOT_FOUND", field="price_id"
        )
    price, plan = found
    try:
        rules.check_payable(
            price=price.price,
            plan_active=plan.is_active,
            price_active=price.is_active,
            trial_plan=plan_rules.is_trial_plan(plan.code),
        )
        paise = rules.to_paise(price.price)
    except SubscriptionRuleError as exc:
        raise BusinessRuleError(str(exc), code=exc.code, field="price_id") from exc

    receipt = f"t{tenant.id}-{secrets.token_hex(8)}"
    try:
        made = razorpay.get_gateway().create_order(
            amount_paise=paise,
            currency=price.currency,
            receipt=receipt,
            notes={"company": tenant.slug, "plan": plan.code},
        )
    except razorpay.RazorpayError as exc:
        if exc.code == "ONLINE_RENEWAL_OFF":
            raise BusinessRuleError(exc.message, code=exc.code) from exc
        logger.warning("Razorpay order failed for company %s: %s", tenant.slug, exc.message)
        raise UpstreamError(exc.message, code=exc.code) from exc
    if made.amount_paise != paise or made.currency != price.currency:
        logger.warning("Razorpay made order %s for another amount; not used", made.id)
        raise UpstreamError(
            "Razorpay made an order for another amount. Nothing was charged; try again.",
            code="RAZORPAY_ERROR",
        )

    order = SubscriptionOrder(
        tenant_id=tenant.id,
        subscription_id=sub.id,
        plan_id=plan.id,
        price_id=price.id,
        duration_value=price.duration_value,
        duration_unit=price.duration_unit.value,
        amount=price.price,
        currency=price.currency,
        razorpay_order_id=made.id,
        receipt=receipt,
        status=SubscriptionOrderStatus.CREATED,
        created_by_user_id=user_id,
    )
    db.add(order)
    db.commit()
    return RenewalOrderOut(
        id=order.id,
        razorpay_order_id=made.id,
        key_id=settings.razorpay_key_id.get_secret_value(),
        amount=price.price,
        amount_paise=paise,
        currency=price.currency,
        name=PAYEE,
        description=f"{plan.name}, {duration_label(price.duration_value, order.duration_unit)}",
        company_name=tenant.name,
    )


def verify(db: Session, tenant: Tenant, data: VerifyRequest) -> RenewalResult:
    """Checkout's callback. A forged or mistyped signature is refused (400) before anything is
    looked up or saved."""
    settings = get_settings()
    if not settings.online_renewal_enabled:
        raise _off()
    if not rules.checkout_signature_ok(
        data.razorpay_order_id,
        data.razorpay_payment_id,
        data.razorpay_signature,
        settings.razorpay_key_secret.get_secret_value(),
    ):
        logger.warning("Refused a Razorpay payment with a bad signature (company %s)", tenant.slug)
        raise AppError(
            "The payment could not be verified, so nothing was recorded. If money left your "
            "account, contact Duolink with the payment id.",
            code="SIGNATURE_INVALID",
        )
    order = db.execute(
        select(SubscriptionOrder).where(
            SubscriptionOrder.tenant_id == current_tenant_id(db),
            SubscriptionOrder.razorpay_order_id == data.razorpay_order_id,
        )
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError("That order is not one of this company's.", code="ORDER_NOT_FOUND")
    applied = apply_payment(db, order.id, data.razorpay_payment_id, via="checkout")
    sub = _subscription(db)
    now = _now()
    status, state = _state(tenant, sub, now)
    plan = db.get(PlatformPlan, sub.plan_id)
    return RenewalResult(
        applied=applied,
        plan_name=plan.name if plan else "",
        status=status,
        access_state=state,
        expires_at=sub.expires_at,
        days_left=sub_rules.days_left(sub.expires_at, now),
    )


def apply_payment(db: Session, order_id: int, razorpay_payment_id: str, *, via: str) -> bool:
    """Record the payment and renew, once. True if this call applied it; False if it had
    already been recorded (the other report got there first). The caller has checked the
    signature and set the session to the order's company."""
    now = _now()
    order = db.execute(
        select(SubscriptionOrder).where(SubscriptionOrder.id == order_id).with_for_update()
    ).scalar_one()
    if order.status is SubscriptionOrderStatus.PAID:
        if order.razorpay_payment_id != razorpay_payment_id:
            logger.warning(
                "A second payment %s arrived for Razorpay order %s, already paid by %s; not "
                "applied. Refund it from the Razorpay dashboard.",
                razorpay_payment_id,
                order.razorpay_order_id,
                order.razorpay_payment_id,
            )
        return False
    sub = db.execute(
        select(Subscription).where(Subscription.id == order.subscription_id).with_for_update()
    ).scalar_one()
    tenant = db.get(Tenant, order.tenant_id)
    plan = db.get(PlatformPlan, order.plan_id)
    if tenant is None or plan is None:  # pragma: no cover - foreign keys keep both
        raise NotFoundError("Order is missing its company or plan", code="ORDER_NOT_FOUND")

    was = sub_rules.effective_status(sub.status.value, sub.expires_at, now)
    period = sub_rules.renewal_period(
        status=sub.status.value,
        expires_at=sub.expires_at,
        duration_value=order.duration_value,
        duration_unit=order.duration_unit,
        now=now,
    )
    start_paid_period(
        sub,
        tenant,
        plan,
        period,
        duration=(order.duration_value, order.duration_unit),
        price=order.amount,
    )
    payment = SubscriptionPayment(
        tenant_id=order.tenant_id,
        subscription_id=sub.id,
        plan_id=plan.id,
        amount=order.amount,
        method=PaymentMethod.RAZORPAY,
        reference=razorpay_payment_id,
        notes=f"Paid online with Razorpay (order {order.razorpay_order_id})",
        paid_at=now,
        period_starts_at=period.starts_at,
        period_ends_at=period.expires_at,
        recorded_by_admin_id=None,
    )
    db.add(payment)
    try:
        db.flush()
    except IntegrityError:  # the payment id is already recorded (by hand, by Duolink)
        db.rollback()
        logger.info("Razorpay payment %s was already recorded; not again", razorpay_payment_id)
        return False
    order.status = SubscriptionOrderStatus.PAID
    order.razorpay_payment_id = razorpay_payment_id
    order.payment_id = payment.id
    order.paid_at = now
    order.paid_via = via
    record(
        db,
        PlatformAction.SUBSCRIPTION_PAY_ONLINE,
        None,
        tenant_id=order.tenant_id,
        details={
            "plan": plan.code,
            "was": was,
            "amount": str(order.amount),
            "method": PaymentMethod.RAZORPAY.value,
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "via": via,
            "period_starts_at": period.starts_at,
            "period_ends_at": period.expires_at,
        },
    )
    db.commit()
    return True
