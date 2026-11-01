"""Duolink's own pricing (Milestone 20). The only admin paths allowed to carry a price are the
ones under /billing; test_platform_admin keeps that list explicit."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.models.enums import PaymentMethod
from app.schemas.billing import (
    BillingDashboard,
    CancelRequest,
    PaymentOut,
    PaymentPage,
    PlanCreate,
    PlanDelete,
    PlanFeatureOut,
    PlanOut,
    PlanReason,
    PlanUpdate,
    RenewRequest,
    ReverseRequest,
    SubscriptionRow,
)
from app.schemas.common import Page
from app.services.platform import billing as subs
from app.services.platform import plans as service

router = APIRouter(prefix="/billing", tags=["admin"])


@router.get("/plans", response_model=list[PlanOut])
def list_plans(_: PlatformAdminUser, db: DbSession, include_archived: bool = True) -> list[PlanOut]:
    """Every plan with its prices and how many companies are on it. Archived plans are
    included unless `include_archived` is false (the onboarding picker uses that)."""
    return service.list_plans(db, include_archived=include_archived)


@router.get("/plans/features", response_model=list[PlanFeatureOut])
def plan_features(_: PlatformAdminUser) -> list[PlanFeatureOut]:
    """The features a plan can list. Listing one does not switch anything on or off."""
    return service.features()


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, _: PlatformAdminUser, db: DbSession) -> PlanOut:
    return service.detail(db, plan_id)


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(body: PlanCreate, admin: SuperAdminOnly, db: DbSession) -> PlanOut:
    """409 PLAN_CODE_TAKEN, PLAN_CODE_INVALID, PLAN_PRICE_COUNT, PLAN_PRICE_DUPLICATE,
    PLAN_PRICE_DURATION, PLAN_PRICE_AMOUNT, PLAN_FEATURE_UNKNOWN, PLAN_LIMIT_INVALID."""
    return service.create(db, body, admin.admin_id)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: int, body: PlanUpdate, admin: SuperAdminOnly, db: DbSession) -> PlanOut:
    """Lowering a limit never deactivates anyone: the next add past it answers 409
    PLAN_USER_LIMIT or PLAN_LOCATION_LIMIT, as before. `is_active: true` restores an archived
    plan."""
    return service.update_plan(db, plan_id, body, admin.admin_id)


@router.post(
    "/plans/{plan_id}/duplicate", response_model=PlanOut, status_code=status.HTTP_201_CREATED
)
def duplicate_plan(plan_id: int, admin: SuperAdminOnly, db: DbSession) -> PlanOut:
    return service.duplicate(db, plan_id, admin.admin_id)


@router.post("/plans/{plan_id}/archive", response_model=PlanOut)
def archive_plan(plan_id: int, body: PlanReason, admin: SuperAdminOnly, db: DbSession) -> PlanOut:
    """Hides the plan from the onboarding picker. Companies on it keep it."""
    return service.archive(db, plan_id, body.reason, admin.admin_id)


@router.post("/plans/{plan_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: int, body: PlanDelete, admin: SuperAdminOnly, db: DbSession) -> Response:
    """Type DELETE. 409 PLAN_IN_USE while any company is on the plan."""
    service.delete(db, plan_id, body, admin.admin_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- subscriptions (Milestone 21)


@router.get("/subscriptions", response_model=Page[SubscriptionRow])
def list_subscriptions(
    _: PlatformAdminUser,
    db: DbSession,
    status: Literal["trial", "active", "expired", "cancelled"] | None = None,
    plan: Annotated[str | None, Query(description="a plan's code, e.g. PRO")] = None,
    expiring_within: Annotated[int | None, Query(ge=1, le=3650, description="days")] = None,
    tenant_id: int | None = None,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SubscriptionRow]:
    """Every company's subscription, soonest to end first. `status` is worked out from the end
    date, so an unrenewed subscription shows as expired without any job having run."""
    rows, total = subs.list_subscriptions(
        db,
        status=status,
        plan=plan,
        expiring_within=expiring_within,
        tenant_id=tenant_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return Page[SubscriptionRow](items=rows, total=total, limit=limit, offset=offset)


@router.post("/subscriptions/{subscription_id}/renew", response_model=SubscriptionRow)
def renew_subscription(
    subscription_id: int, body: RenewRequest, admin: SuperAdminOnly, db: DbSession
) -> SubscriptionRow:
    """Record a payment received by hand and extend the subscription. Paying during a trial
    starts the paid period today; renewing early adds to the current end date; renewing after it
    ended starts today. 409 RENEWAL_CHOICE, RENEWAL_DURATION, PAYMENT_AMOUNT, PAYMENT_METHOD,
    PLAN_INACTIVE; 404 PRICE_NOT_FOUND."""
    return subs.renew(db, subscription_id, body, admin.admin_id)


@router.post("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionRow)
def cancel_subscription(
    subscription_id: int, body: CancelRequest, admin: SuperAdminOnly, db: DbSession
) -> SubscriptionRow:
    """The company becomes read-only. 409 ALREADY_CANCELLED."""
    return subs.cancel(db, subscription_id, body, admin.admin_id)


@router.get("/payments", response_model=PaymentPage)
def list_payments(
    _: PlatformAdminUser,
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    method: PaymentMethod | None = None,
    tenant_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaymentPage:
    """Payments newest first, with totals for the whole filter (received, reversed, net)."""
    return subs.list_payments(
        db,
        date_from=date_from,
        date_to=date_to,
        method=method,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/payments/{payment_id}/reverse", response_model=PaymentOut, status_code=status.HTTP_201_CREATED
)
def reverse_payment(
    payment_id: int, body: ReverseRequest, admin: SuperAdminOnly, db: DbSession
) -> PaymentOut:
    """Cancel a mistaken payment with a negative row. 409 PAYMENT_REVERSED, PAYMENT_IS_REVERSAL."""
    return subs.reverse_payment(db, payment_id, body, admin.admin_id)


@router.get("/dashboard", response_model=BillingDashboard)
def dashboard(_: PlatformAdminUser, db: DbSession) -> BillingDashboard:
    """Duolink's revenue and customer numbers for the overview page."""
    return subs.dashboard(db)
