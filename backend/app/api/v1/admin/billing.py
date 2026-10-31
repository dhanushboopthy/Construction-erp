"""Duolink's own pricing (Milestone 20). The only admin paths allowed to carry a price are the
ones under /billing; test_platform_admin keeps that list explicit."""

from fastapi import APIRouter, Response, status

from app.api.deps import DbSession, PlatformAdminUser, SuperAdminOnly
from app.schemas.billing import (
    PlanCreate,
    PlanDelete,
    PlanFeatureOut,
    PlanOut,
    PlanReason,
    PlanUpdate,
)
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
