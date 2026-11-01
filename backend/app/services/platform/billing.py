"""Subscriptions, manual renewals, payments and Duolink's revenue dashboard (Milestone 21).

A payment row is Duolink's receipt record; Duolink's own GST tax invoice for the subscription is
raised in Duolink's books, outside this ERP. These are the only admin answers that carry money,
and they live under /admin/billing (ADR 0013). Payments are append-only: a mistake is cancelled
by a negative row. Every change is written to the platform audit log.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.domain import plans as plan_rules
from app.domain import subscriptions as rules
from app.domain.fiscal import fy_bounds
from app.models.billing import Subscription, SubscriptionPayment
from app.models.enums import PaymentMethod, PlatformAction, SubscriptionStatus, TenantStatus
from app.models.platform import PlatformAdmin, PlatformPlan, PlatformPlanPrice
from app.models.tenancy import Tenant
from app.schemas.billing import (
    BillingDashboard,
    CancelRequest,
    CompaniesByStatus,
    ExpiringSoon,
    PaymentOut,
    PaymentPage,
    PaymentTotals,
    PlanShare,
    RenewRequest,
    ReverseRequest,
    SubscriptionRow,
    TrendPoint,
)
from app.services.platform.audit import record

ZERO = Decimal("0.00")


def _money(value: Decimal | int) -> Decimal:
    """A sum from the database as rupees with two decimals (an empty sum is the integer 0)."""
    return Decimal(value).quantize(ZERO)


def _now() -> datetime:
    return datetime.now(UTC)


def _refuse(exc: rules.SubscriptionRuleError, field: str | None = None) -> BusinessRuleError:
    return BusinessRuleError(str(exc), code=exc.code, field=field)


# ---------------------------------------------------------------- creating and keeping in step


def start_subscription(
    db: Session, tenant: Tenant, *, trial_ends_at: datetime | None, now: datetime
) -> Subscription:
    """A new company's subscription. A trial ends with its trial. A company started active has
    no end date yet: it is flagged for Duolink to set one by recording its first renewal."""
    on_trial = tenant.status is TenantStatus.TRIAL
    sub = Subscription(
        tenant_id=tenant.id,
        plan_id=tenant.plan_id,
        status=SubscriptionStatus.TRIAL if on_trial else SubscriptionStatus.ACTIVE,
        starts_at=now,
        expires_at=trial_ends_at if on_trial else None,
        needs_review=not on_trial,
    )
    db.add(sub)
    return sub


def subscription_for(db: Session, tenant_id: int) -> Subscription | None:
    return db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).scalar_one_or_none()


def follow_tenant_change(
    db: Session, tenant: Tenant, *, plan_changed: bool, trial_moved: bool
) -> None:
    """The company page changed the plan or moved the trial end: keep the subscription in step."""
    sub = subscription_for(db, tenant.id)
    if sub is None:
        return
    if plan_changed:
        sub.plan_id = tenant.plan_id
    if trial_moved and sub.status is SubscriptionStatus.TRIAL:
        sub.expires_at = tenant.trial_ends_at


# ---------------------------------------------------------------- subscriptions


def _row(sub: Subscription, tenant: Tenant, plan: PlatformPlan, now: datetime) -> SubscriptionRow:
    return SubscriptionRow(
        id=sub.id,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        plan_id=plan.id,
        plan_code=plan.code,
        plan_name=plan.name,
        status=rules.effective_status(sub.status.value, sub.expires_at, now),
        starts_at=sub.starts_at,
        expires_at=sub.expires_at,
        days_left=rules.days_left(sub.expires_at, now),
        needs_review=sub.needs_review,
        duration_value=sub.duration_value,
        duration_unit=sub.duration_unit,
        price=sub.price,
        cancelled_at=sub.cancelled_at,
        cancel_reason=sub.cancel_reason,
    )


def _status_filter(status: str, now: datetime) -> ColumnElement[bool]:
    stored = Subscription.status
    running = or_(Subscription.expires_at.is_(None), Subscription.expires_at > now)
    if status == "cancelled":
        return stored == SubscriptionStatus.CANCELLED
    if status == "expired":
        return and_(stored != SubscriptionStatus.CANCELLED, Subscription.expires_at <= now)
    return and_(stored == SubscriptionStatus(status), running)


def list_subscriptions(
    db: Session,
    *,
    status: str | None,
    plan: str | None,
    expiring_within: int | None,
    tenant_id: int | None,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[SubscriptionRow], int]:
    now = _now()
    stmt = (
        select(Subscription, Tenant, PlatformPlan)
        .join(Tenant, Tenant.id == Subscription.tenant_id)
        .join(PlatformPlan, PlatformPlan.id == Subscription.plan_id)
    )
    if status:
        stmt = stmt.where(_status_filter(status, now))
    if plan:
        stmt = stmt.where(PlatformPlan.code == plan.strip().upper())
    if expiring_within is not None:
        stmt = stmt.where(
            Subscription.status != SubscriptionStatus.CANCELLED,
            Subscription.expires_at > now,
            Subscription.expires_at <= now + timedelta(days=expiring_within),
        )
    if tenant_id is not None:
        stmt = stmt.where(Subscription.tenant_id == tenant_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Tenant.name.ilike(like), Tenant.slug.ilike(like)))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Subscription.expires_at.asc().nulls_last(), Tenant.name)
        .limit(limit)
        .offset(offset)
    ).all()
    return [_row(s, t, p, now) for s, t, p in rows], total


def _load(db: Session, subscription_id: int) -> tuple[Subscription, Tenant, PlatformPlan]:
    row = db.execute(
        select(Subscription, Tenant, PlatformPlan)
        .join(Tenant, Tenant.id == Subscription.tenant_id)
        .join(PlatformPlan, PlatformPlan.id == Subscription.plan_id)
        .where(Subscription.id == subscription_id)
    ).first()
    if row is None:
        raise NotFoundError("Subscription not found", code="SUBSCRIPTION_NOT_FOUND")
    return row[0], row[1], row[2]


def renew(db: Session, subscription_id: int, data: RenewRequest, admin_id: int) -> SubscriptionRow:
    """Record a payment Duolink received and move the subscription's end date. Access is checked
    on every request, so the company can save again at once, with no sign-out."""
    sub, tenant, _ = _load(db, subscription_id)
    plan = db.get(PlatformPlan, data.plan_id)
    if plan is None:
        raise NotFoundError("No plan has that id", code="PLAN_NOT_FOUND", field="plan_id")
    if plan.id != sub.plan_id:  # staying on an archived plan is allowed; moving to one is not
        try:
            plan_rules.check_assignable(plan.is_active)
        except plan_rules.PlanRuleError as exc:
            raise BusinessRuleError(str(exc), code=exc.code, field="plan_id") from exc

    if (data.price_id is None) == (data.custom_days is None):
        raise BusinessRuleError(
            "Choose one of the plan's prices, or a number of days, not both.",
            code="RENEWAL_CHOICE",
            field="price_id",
        )
    option: PlatformPlanPrice | None = None
    if data.price_id is not None:
        option = db.get(PlatformPlanPrice, data.price_id)
        if option is None or option.plan_id != plan.id or not option.is_active:
            raise NotFoundError(
                "That price is not one of this plan's prices",
                code="PRICE_NOT_FOUND",
                field="price_id",
            )
        value, unit = option.duration_value, option.duration_unit.value
    else:
        value, unit = data.custom_days or 0, "day"

    now = _now()
    try:
        rules.check_payment(data.amount, data.method.value)
        period = rules.renewal_period(
            status=sub.status.value,
            expires_at=sub.expires_at,
            duration_value=value,
            duration_unit=unit,
            now=now,
        )
    except rules.SubscriptionRuleError as exc:
        raise _refuse(exc, "amount" if exc.code.startswith("PAYMENT") else "custom_days") from exc

    was = rules.effective_status(sub.status.value, sub.expires_at, now)
    sub.plan_id = plan.id
    sub.duration_value, sub.duration_unit = value, unit
    sub.price = option.price if option else None
    sub.status = SubscriptionStatus.ACTIVE
    sub.starts_at = period.starts_at
    sub.expires_at = period.expires_at
    sub.needs_review = False
    sub.cancelled_at = None
    sub.cancel_reason = None
    tenant.plan = plan
    if tenant.status is TenantStatus.TRIAL and not plan_rules.is_trial_plan(plan.code):
        tenant.status = TenantStatus.ACTIVE  # paying ends the trial
        tenant.trial_ends_at = None

    db.add(
        SubscriptionPayment(
            tenant_id=tenant.id,
            subscription_id=sub.id,
            plan_id=plan.id,
            amount=data.amount,
            method=data.method,
            reference=data.reference,
            notes=data.notes,
            paid_at=data.paid_at or now,
            period_starts_at=period.starts_at,
            period_ends_at=period.expires_at,
            recorded_by_admin_id=admin_id,
        )
    )
    record(
        db,
        PlatformAction.SUBSCRIPTION_RENEW,
        admin_id,
        tenant_id=tenant.id,
        details={
            "plan": plan.code,
            "was": was,
            "amount": str(data.amount),
            "method": data.method.value,
            "reference": data.reference,
            "period_starts_at": period.starts_at,
            "period_ends_at": period.expires_at,
        },
    )
    db.commit()
    return _row(sub, tenant, plan, now)


def cancel(
    db: Session, subscription_id: int, data: CancelRequest, admin_id: int
) -> SubscriptionRow:
    """End the subscription now: the company becomes read-only. Nothing is deleted, and a
    later renewal brings it back."""
    sub, tenant, plan = _load(db, subscription_id)
    try:
        rules.check_cancellable(sub.status.value)
    except rules.SubscriptionRuleError as exc:
        raise _refuse(exc) from exc
    now = _now()
    was = rules.effective_status(sub.status.value, sub.expires_at, now)
    sub.status = SubscriptionStatus.CANCELLED
    sub.cancelled_at = now
    sub.cancel_reason = data.reason
    record(
        db,
        PlatformAction.SUBSCRIPTION_CANCEL,
        admin_id,
        tenant_id=tenant.id,
        details={"reason": data.reason, "was": was, "plan": plan.code},
    )
    db.commit()
    return _row(sub, tenant, plan, now)


# ---------------------------------------------------------------- payments


def _payment_out(
    pay: SubscriptionPayment,
    tenant: Tenant,
    plan: PlatformPlan,
    admin: PlatformAdmin,
    reversed_ids: set[int],
) -> PaymentOut:
    return PaymentOut(
        id=pay.id,
        subscription_id=pay.subscription_id,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        plan_code=plan.code,
        plan_name=plan.name,
        amount=pay.amount,
        method=pay.method,
        reference=pay.reference,
        notes=pay.notes,
        paid_at=pay.paid_at,
        period_starts_at=pay.period_starts_at,
        period_ends_at=pay.period_ends_at,
        reverses_id=pay.reverses_id,
        reversed=pay.id in reversed_ids,
        recorded_by=admin.full_name,
    )


def _reversed_among(db: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    found = db.execute(
        select(SubscriptionPayment.reverses_id).where(SubscriptionPayment.reverses_id.in_(ids))
    ).scalars()
    return {i for i in found if i is not None}


def list_payments(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    method: PaymentMethod | None,
    tenant_id: int | None,
    limit: int,
    offset: int,
) -> PaymentPage:
    filters: list[ColumnElement[bool]] = []
    if date_from:
        filters.append(
            SubscriptionPayment.paid_at >= datetime.combine(date_from, datetime.min.time(), UTC)
        )
    if date_to:
        filters.append(
            SubscriptionPayment.paid_at
            < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), UTC)
        )
    if method:
        filters.append(SubscriptionPayment.method == method)
    if tenant_id is not None:
        filters.append(SubscriptionPayment.tenant_id == tenant_id)

    total = db.execute(
        select(func.count()).select_from(SubscriptionPayment).where(*filters)
    ).scalar_one()
    received, reversed_ = db.execute(
        select(
            func.coalesce(
                func.sum(SubscriptionPayment.amount).filter(SubscriptionPayment.amount > 0), 0
            ),
            func.coalesce(
                func.sum(SubscriptionPayment.amount).filter(SubscriptionPayment.amount < 0), 0
            ),
        ).where(*filters)
    ).one()
    rows = db.execute(
        select(SubscriptionPayment, Tenant, PlatformPlan, PlatformAdmin)
        .join(Tenant, Tenant.id == SubscriptionPayment.tenant_id)
        .join(PlatformPlan, PlatformPlan.id == SubscriptionPayment.plan_id)
        .join(PlatformAdmin, PlatformAdmin.id == SubscriptionPayment.recorded_by_admin_id)
        .where(*filters)
        .order_by(SubscriptionPayment.paid_at.desc(), SubscriptionPayment.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    reversed_ids = _reversed_among(db, [r[0].id for r in rows])
    return PaymentPage(
        items=[_payment_out(p, t, pl, a, reversed_ids) for p, t, pl, a in rows],
        total=total,
        limit=limit,
        offset=offset,
        totals=PaymentTotals(
            received=_money(received),
            reversed=_money(-reversed_),
            net=_money(received + reversed_),
        ),
    )


def reverse_payment(
    db: Session, payment_id: int, data: ReverseRequest, admin_id: int
) -> PaymentOut:
    """Cancel a mistaken payment with a row of the opposite sign. The original is never edited,
    and the subscription's end date does not change: cancel or shorten it separately if needed."""
    row = db.execute(
        select(SubscriptionPayment, Tenant, PlatformPlan, PlatformAdmin)
        .join(Tenant, Tenant.id == SubscriptionPayment.tenant_id)
        .join(PlatformPlan, PlatformPlan.id == SubscriptionPayment.plan_id)
        .join(PlatformAdmin, PlatformAdmin.id == SubscriptionPayment.recorded_by_admin_id)
        .where(SubscriptionPayment.id == payment_id)
    ).first()
    if row is None:
        raise NotFoundError("Payment not found", code="PAYMENT_NOT_FOUND")
    original, tenant, plan, _ = row
    try:
        rules.check_reversible(
            original.amount, already_reversed=bool(_reversed_among(db, [original.id]))
        )
    except rules.SubscriptionRuleError as exc:
        raise _refuse(exc) from exc

    now = _now()
    reversal = SubscriptionPayment(
        tenant_id=tenant.id,
        subscription_id=original.subscription_id,
        plan_id=original.plan_id,
        amount=rules.reversal_of(original.amount),
        method=original.method,
        reference=f"Reversal of payment {original.id}",
        notes=data.reason,
        paid_at=now,
        reverses_id=original.id,
        recorded_by_admin_id=admin_id,
    )
    db.add(reversal)
    record(
        db,
        PlatformAction.PAYMENT_REVERSE,
        admin_id,
        tenant_id=tenant.id,
        details={"payment_id": original.id, "amount": str(original.amount), "reason": data.reason},
    )
    try:
        db.commit()
    except IntegrityError as exc:  # two admins reversed it at once
        db.rollback()
        raise BusinessRuleError(
            "That payment was already reversed.", code="PAYMENT_REVERSED"
        ) from exc
    admin = db.get(PlatformAdmin, admin_id)
    if admin is None:
        raise NotFoundError("Admin not found", code="ADMIN_NOT_FOUND")
    return _payment_out(reversal, tenant, plan, admin, set())


# ---------------------------------------------------------------- dashboard


def _month_key(on: date) -> str:
    return f"{on.year}-{on.month:02d}"


def dashboard(db: Session) -> BillingDashboard:
    now = _now()
    today = now.date()
    this_month = rules.month_start(today)
    months = rules.twelve_months_ending(today)
    window_start = datetime.combine(months[0], datetime.min.time(), UTC)
    fy_start = datetime.combine(fy_bounds(today)[0], datetime.min.time(), UTC)
    month_begin = datetime.combine(this_month, datetime.min.time(), UTC)

    by_status = dict(db.execute(select(Tenant.status, func.count()).group_by(Tenant.status)).all())
    open_company = Tenant.status.in_([TenantStatus.TRIAL, TenantStatus.ACTIVE])

    active_subscriptions = db.execute(
        select(func.count())
        .select_from(Subscription)
        .join(Tenant, Tenant.id == Subscription.tenant_id)
        .where(
            open_company,
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
        )
    ).scalar_one()

    payments = db.execute(
        select(SubscriptionPayment.paid_at, SubscriptionPayment.amount).where(
            SubscriptionPayment.paid_at >= min(window_start, fy_start)
        )
    ).all()
    monthly: dict[str, Decimal] = defaultdict(lambda: ZERO)
    revenue_month = revenue_fy = ZERO
    for paid_at, amount in payments:
        monthly[_month_key(paid_at.astimezone(UTC).date())] += amount
        if paid_at >= month_begin:
            revenue_month += amount
        if paid_at >= fy_start:
            revenue_fy += amount

    signups: dict[str, int] = defaultdict(int)
    for (created,) in db.execute(
        select(Tenant.created_at).where(Tenant.created_at >= window_start)
    ):
        signups[_month_key(created.astimezone(UTC).date())] += 1

    renewals_month = db.execute(
        select(func.count()).where(
            SubscriptionPayment.amount > 0,
            SubscriptionPayment.period_ends_at.is_not(None),
            SubscriptionPayment.paid_at >= month_begin,
        )
    ).scalar_one()

    soon_rows = db.execute(
        select(Tenant, PlatformPlan, Subscription)
        .join(Subscription, Subscription.tenant_id == Tenant.id)
        .join(PlatformPlan, PlatformPlan.id == Subscription.plan_id)
        .where(
            open_company,
            Subscription.status != SubscriptionStatus.CANCELLED,
            Subscription.expires_at > now,
            Subscription.expires_at <= now + timedelta(days=30),
        )
        .order_by(Subscription.expires_at)
    ).all()

    shares = db.execute(
        select(PlatformPlan.id, PlatformPlan.code, PlatformPlan.name, func.count(Tenant.id))
        .join(Tenant, Tenant.plan_id == PlatformPlan.id)
        .group_by(PlatformPlan.id)
        .order_by(PlatformPlan.sort_order, PlatformPlan.id)
    ).all()

    return BillingDashboard(
        companies_by_status=CompaniesByStatus(
            trial=by_status.get(TenantStatus.TRIAL, 0),
            active=by_status.get(TenantStatus.ACTIVE, 0),
            suspended=by_status.get(TenantStatus.SUSPENDED, 0),
            cancelled=by_status.get(TenantStatus.CANCELLED, 0),
        ),
        active_subscriptions=active_subscriptions,
        revenue_month=revenue_month,
        revenue_fy=revenue_fy,
        new_companies_month=signups.get(_month_key(this_month), 0),
        renewals_month=renewals_month,
        expiring_30=len(soon_rows),
        trend=[
            TrendPoint(
                month=_month_key(m),
                revenue=monthly.get(_month_key(m), ZERO),
                signups=signups.get(_month_key(m), 0),
            )
            for m in months
        ],
        plan_breakdown=[
            PlanShare(plan_id=i, plan_code=c, plan_name=n, companies=k) for i, c, n, k in shares
        ],
        expiring_soon=[
            ExpiringSoon(
                tenant_id=t.id,
                tenant_name=t.name,
                plan_code=p.code,
                expires_at=s.expires_at,
                days_left=rules.days_left(s.expires_at, now) or 0,
            )
            for t, p, s in soon_rows[:10]
        ],
    )
