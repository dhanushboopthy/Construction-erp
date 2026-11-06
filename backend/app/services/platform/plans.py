"""The plan catalogue Duolink edits: create, update, duplicate, archive and delete plans and their
prices (Milestone 20). A plan is Duolink's own record, not a company's, so nothing here is
tenant-scoped. A plan in use is archived, never deleted. Every change is written to the platform
audit log."""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.domain import plans as rules
from app.domain import user_support
from app.domain.plan_features import FEATURES
from app.models.enums import DurationUnit, PlatformAction
from app.models.platform import PlatformPlan, PlatformPlanPrice
from app.models.tenancy import Tenant
from app.schemas.billing import (
    PlanCreate,
    PlanDelete,
    PlanFeatureOut,
    PlanOut,
    PlanPriceIn,
    PlanPriceOut,
    PlanUpdate,
)
from app.services.platform.audit import record


def _refuse(exc: rules.PlanRuleError, field: str | None = None) -> BusinessRuleError:
    return BusinessRuleError(str(exc), code=exc.code, field=field)


def _companies(db: Session) -> dict[int, int]:
    rows = db.execute(select(Tenant.plan_id, func.count()).group_by(Tenant.plan_id))
    return {row[0]: row[1] for row in rows}


def _out(plan: PlatformPlan, companies: int) -> PlanOut:
    return PlanOut(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        short_description=plan.short_description,
        long_description=plan.long_description,
        max_users=plan.max_users,
        max_locations=plan.max_locations,
        features=list(plan.features),
        is_active=plan.is_active,
        is_popular=plan.is_popular,
        sort_order=plan.sort_order,
        prices=[
            PlanPriceOut(
                id=p.id,
                duration_value=p.duration_value,
                duration_unit=p.duration_unit,
                price=p.price,
                currency=p.currency,
                is_active=p.is_active,
            )
            for p in plan.prices
        ],
        companies=companies,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def features() -> list[PlanFeatureOut]:
    return [PlanFeatureOut(code=f.code, name=f.name, description=f.description) for f in FEATURES]


def list_plans(db: Session, *, include_archived: bool = True) -> list[PlanOut]:
    stmt = select(PlatformPlan).order_by(PlatformPlan.sort_order, PlatformPlan.id)
    if not include_archived:
        stmt = stmt.where(PlatformPlan.is_active.is_(True))
    used = _companies(db)
    return [_out(p, used.get(p.id, 0)) for p in db.scalars(stmt)]


def get_plan(db: Session, plan_id: int) -> PlatformPlan:
    plan = db.get(PlatformPlan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found", code="PLAN_NOT_FOUND")
    return plan


def detail(db: Session, plan_id: int) -> PlanOut:
    plan = get_plan(db, plan_id)
    return _out(plan, _companies(db).get(plan.id, 0))


def plan_for_company(db: Session, code: str) -> PlatformPlan:
    """The active plan with this code, for giving to a company."""
    plan = db.execute(
        select(PlatformPlan).where(PlatformPlan.code == code.strip().upper())
    ).scalar_one_or_none()
    if plan is None:
        raise NotFoundError("No plan has that code", code="PLAN_NOT_FOUND", field="plan")
    try:
        rules.check_assignable(plan.is_active)
    except rules.PlanRuleError as exc:
        raise ConflictError(str(exc), code=exc.code, field="plan") from exc
    return plan


def _terms(prices: list[PlanPriceIn]) -> list[rules.PriceTerms]:
    return [rules.PriceTerms(p.duration_value, p.duration_unit.value, p.price) for p in prices]


def _price_rows(prices: list[PlanPriceIn]) -> list[PlatformPlanPrice]:
    return [
        PlatformPlanPrice(
            duration_value=p.duration_value,
            duration_unit=p.duration_unit,
            price=p.price,
            currency="INR",
            is_active=p.is_active,
            sort_order=n,
        )
        for n, p in enumerate(prices, start=1)
    ]


def _price_text(plan: PlatformPlan) -> list[str]:
    return [f"{p.duration_value} {p.duration_unit.value}: {p.price}" for p in plan.prices]


def _check(
    *, max_users: int, max_locations: int, feature_codes: list[str], prices: list[PlanPriceIn]
) -> list[str]:
    try:
        rules.check_limits(max_users, max_locations)
        rules.check_prices(_terms(prices))
        return rules.check_features(feature_codes)
    except rules.PlanRuleError as exc:
        raise _refuse(exc) from exc


def _make_only_popular(db: Session, plan: PlatformPlan) -> None:
    db.execute(
        update(PlatformPlan)
        .where(PlatformPlan.is_popular.is_(True), PlatformPlan.id != plan.id)
        .values(is_popular=False)
        .execution_options(synchronize_session=False)
    )


def create(db: Session, data: PlanCreate, admin_id: int) -> PlanOut:
    try:
        code = rules.check_plan_code(data.code)
    except rules.PlanRuleError as exc:
        raise _refuse(exc, "code") from exc
    if db.execute(select(PlatformPlan.id).where(PlatformPlan.code == code)).first():
        raise ConflictError("A plan already has that code", code="PLAN_CODE_TAKEN", field="code")
    feature_codes = _check(
        max_users=data.max_users,
        max_locations=data.max_locations,
        feature_codes=data.features,
        prices=data.prices,
    )
    plan = PlatformPlan(
        code=code,
        name=data.name,
        short_description=data.short_description,
        long_description=data.long_description,
        max_users=data.max_users,
        max_locations=data.max_locations,
        features=feature_codes,
        is_active=True,
        is_popular=False,
        sort_order=data.sort_order,
    )
    plan.prices = _price_rows(data.prices)
    db.add(plan)
    db.flush()
    if data.is_popular:
        _make_only_popular(db, plan)
        plan.is_popular = True
    record(
        db,
        PlatformAction.PLAN_CREATE,
        admin_id,
        details={
            "plan": code,
            "plan_id": plan.id,
            "prices": _price_text(plan),
            "reason": data.reason,
        },
    )
    db.commit()
    return _out(plan, 0)


def update_plan(db: Session, plan_id: int, data: PlanUpdate, admin_id: int) -> PlanOut:
    plan = get_plan(db, plan_id)
    changes: dict[str, Any] = {}
    sent = data.model_fields_set

    for key in ("name", "short_description", "long_description", "sort_order"):
        value = getattr(data, key)
        if key in sent and value is not None and value != getattr(plan, key):
            changes[key] = {"from": getattr(plan, key), "to": value}
            setattr(plan, key, value)

    max_users = data.max_users if data.max_users is not None else plan.max_users
    max_locations = data.max_locations if data.max_locations is not None else plan.max_locations
    new_features = data.features if data.features is not None else list(plan.features)
    new_prices = data.prices
    price_input = (
        new_prices
        if new_prices is not None
        else [
            PlanPriceIn(
                duration_value=p.duration_value,
                duration_unit=p.duration_unit,
                price=p.price,
                is_active=p.is_active,
            )
            for p in plan.prices
        ]
    )
    feature_codes = _check(
        max_users=max_users,
        max_locations=max_locations,
        feature_codes=new_features,
        prices=price_input,
    )
    if max_users != plan.max_users:
        changes["max_users"] = {"from": plan.max_users, "to": max_users}
        plan.max_users = max_users
    if max_locations != plan.max_locations:
        changes["max_locations"] = {"from": plan.max_locations, "to": max_locations}
        plan.max_locations = max_locations
    if feature_codes != list(plan.features):
        changes["features"] = {"from": list(plan.features), "to": feature_codes}
        plan.features = feature_codes
    if new_prices is not None:
        before = _price_text(plan)
        plan.prices.clear()
        db.flush()  # the old rows go first: the same duration may be priced again
        plan.prices.extend(_price_rows(new_prices))
        db.flush()
        if _price_text(plan) != before:
            changes["prices"] = {"from": before, "to": _price_text(plan)}

    is_active = plan.is_active if data.is_active is None else data.is_active
    is_popular = plan.is_popular if data.is_popular is None else data.is_popular
    if data.is_popular and not is_active and data.is_active is None:
        raise ConflictError(
            "An archived plan cannot be the popular one", code="PLAN_INACTIVE", field="is_popular"
        )
    if not is_active:
        is_popular = False  # an archived plan is not offered, so it is not the popular one
    if is_active != plan.is_active:
        changes["is_active"] = {"from": plan.is_active, "to": is_active}
        plan.is_active = is_active
    if is_popular != plan.is_popular:
        if is_popular:
            _make_only_popular(db, plan)
        changes["is_popular"] = {"from": plan.is_popular, "to": is_popular}
        plan.is_popular = is_popular
        db.flush()

    if changes:
        record(
            db,
            PlatformAction.PLAN_UPDATE,
            admin_id,
            details={"plan": plan.code, "plan_id": plan.id, "reason": data.reason, **changes},
        )
    db.commit()
    return _out(plan, _companies(db).get(plan.id, 0))


def duplicate(db: Session, plan_id: int, admin_id: int) -> PlanOut:
    """A copy with the next free code. It is never the popular one, so Duolink can edit it
    before offering it."""
    source = get_plan(db, plan_id)
    taken = set(db.scalars(select(PlatformPlan.code)))
    code = rules.copy_code(source.code, taken)
    plan = PlatformPlan(
        code=code,
        name=f"{source.name} (copy)"[:100],
        short_description=source.short_description,
        long_description=source.long_description,
        max_users=source.max_users,
        max_locations=source.max_locations,
        features=list(source.features),
        is_active=True,
        is_popular=False,
        sort_order=source.sort_order + 1,
    )
    plan.prices = [
        PlatformPlanPrice(
            duration_value=p.duration_value,
            duration_unit=DurationUnit(p.duration_unit),
            price=Decimal(p.price),
            currency=p.currency,
            is_active=p.is_active,
            sort_order=p.sort_order,
        )
        for p in source.prices
    ]
    db.add(plan)
    db.flush()
    record(
        db,
        PlatformAction.PLAN_DUPLICATE,
        admin_id,
        details={"plan": code, "plan_id": plan.id, "copied_from": source.code},
    )
    db.commit()
    return _out(plan, 0)


def archive(db: Session, plan_id: int, reason: str, admin_id: int) -> PlanOut:
    """Hide the plan from the onboarding picker. Companies already on it keep it and its
    limits."""
    plan = get_plan(db, plan_id)
    was = plan.is_active
    plan.is_active = False
    plan.is_popular = False
    companies = _companies(db).get(plan.id, 0)
    record(
        db,
        PlatformAction.PLAN_ARCHIVE,
        admin_id,
        details={"plan": plan.code, "plan_id": plan.id, "reason": reason, "was_active": was},
    )
    db.commit()
    return _out(plan, companies)


def delete(db: Session, plan_id: int, data: PlanDelete, admin_id: int) -> None:
    """Only a plan no company has ever been on, and only when DELETE is typed."""
    plan = get_plan(db, plan_id)
    if not user_support.confirmation_matches(data.confirmation, "DELETE"):
        raise BusinessRuleError(
            "Type DELETE exactly to delete this plan",
            code="CONFIRMATION_MISMATCH",
            field="confirmation",
        )
    try:
        rules.check_deletable(_companies(db).get(plan.id, 0))
    except rules.PlanRuleError as exc:
        raise ConflictError(str(exc), code=exc.code) from exc
    record(
        db,
        PlatformAction.PLAN_DELETE,
        admin_id,
        details={"plan": plan.code, "plan_id": plan.id, "reason": data.reason},
    )
    db.delete(plan)
    db.commit()
