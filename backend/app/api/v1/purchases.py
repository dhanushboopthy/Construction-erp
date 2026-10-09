from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly, OwnerOrCounter
from app.core.errors import NotFoundError, PermissionDeniedError
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.purchases import (
    CostComponentIn,
    CostComponentOut,
    CostComponentUpdate,
    PurchaseCreate,
    PurchaseOut,
    PurchaseOwnerOut,
    PurchasePreview,
)
from app.services import purchases as purchase_service
from app.services.shop_settings import get_settings_row

router = APIRouter(tags=["purchases"])


def _may_enter(principal: OwnerOrCounter, db: DbSession) -> None:
    """G28: whether counter staff may key in supplier bills is a setting the owner controls."""
    if principal.role is Role.COUNTER and not get_settings_row(db).counter_can_enter_purchases:
        raise PermissionDeniedError("The owner has turned off purchase entry for counter staff")


# ---------------------------------------------------------------- charge types


@router.get("/cost-components", response_model=list[CostComponentOut])
def list_components(
    _: OwnerOrCounter, db: DbSession, include_inactive: bool = False
) -> list[CostComponentOut]:
    rows = purchase_service.list_components(db, include_inactive)
    return [CostComponentOut.model_validate(r) for r in rows]


@router.post(
    "/cost-components", response_model=CostComponentOut, status_code=status.HTTP_201_CREATED
)
def create_component(body: CostComponentIn, _: OwnerOnly, db: DbSession) -> CostComponentOut:
    return CostComponentOut.model_validate(purchase_service.create_component(db, body))


@router.patch("/cost-components/{component_id}", response_model=CostComponentOut)
def update_component(
    component_id: int, body: CostComponentUpdate, _: OwnerOnly, db: DbSession
) -> CostComponentOut:
    return CostComponentOut.model_validate(
        purchase_service.update_component(db, component_id, body)
    )


# ---------------------------------------------------------------- purchases


@router.post("/purchases/preview", response_model=PurchasePreview)
def preview_purchase(body: PurchaseCreate, _: OwnerOnly, db: DbSession) -> PurchasePreview:
    """Landed cost as the server computes it, for the owner's screen. Nothing is saved."""
    return purchase_service.preview(db, body)


@router.post(
    "/purchases",
    response_model=PurchaseOwnerOut | PurchaseOut,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase(
    body: PurchaseCreate, principal: OwnerOrCounter, db: DbSession
) -> PurchaseOwnerOut | PurchaseOut:
    _may_enter(principal, db)
    purchase = purchase_service.create(
        db,
        body,
        actor_id=principal.user_id,
        can_access=principal.can_access_location(body.location_id),
    )
    return purchase_service.purchase_view(db, purchase, principal.sees_cost)


@router.get("/purchases", response_model=Page[PurchaseOwnerOut] | Page[PurchaseOut])
def list_purchases(
    principal: CurrentPrincipal,
    db: DbSession,
    supplier_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[PurchaseOwnerOut] | Page[PurchaseOut]:
    scope = principal.location_ids if principal.role is Role.COUNTER else None
    rows, total = purchase_service.list_purchases(
        db, supplier_id=supplier_id, location_ids=scope, limit=limit, offset=offset
    )
    page = Page[PurchaseOwnerOut] if principal.sees_cost else Page[PurchaseOut]
    return page(
        items=[purchase_service.purchase_view(db, r, principal.sees_cost) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/purchases/{purchase_id}", response_model=PurchaseOwnerOut | PurchaseOut)
def get_purchase(
    purchase_id: int, principal: CurrentPrincipal, db: DbSession
) -> PurchaseOwnerOut | PurchaseOut:
    purchase = purchase_service.get_purchase(db, purchase_id)
    if not principal.can_access_location(purchase.location_id):
        raise NotFoundError("Purchase not found")
    return purchase_service.purchase_view(db, purchase, principal.sees_cost)
