"""Purchase orders, goods received and the bill match report (FM10)."""

from datetime import date, timedelta

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, OwnerOnly, OwnerOrCounter
from app.core.clock import today_ist
from app.models.enums import Role
from app.schemas.orders import (
    MatchReport,
    OrderCreate,
    OrderOut,
    OrderOwnerOut,
    ReceiptCreate,
    ReceiptOut,
)
from app.services import orders as service

router = APIRouter(tags=["orders"])


@router.post("/purchase-orders", response_model=OrderOwnerOut, status_code=status.HTTP_201_CREATED)
def create_order(
    body: OrderCreate, principal: OwnerOnly, db: DbSession
) -> OrderOut | OrderOwnerOut:
    """Place an order with a supplier at an agreed rate (owner only: it carries rates)."""
    order = service.create_order(db, body, actor_id=principal.user_id)
    return service.order_view(db, order, owner=True)


@router.get("/purchase-orders", response_model=list[OrderOwnerOut | OrderOut])
def list_orders(
    principal: CurrentPrincipal,
    db: DbSession,
    supplier_id: int | None = None,
    open_only: bool = False,
) -> list[OrderOut | OrderOwnerOut]:
    """Orders with what has been received and billed. The owner sees rates and values; counter
    staff (their own shop only) and the accountant see quantities."""
    return service.list_orders(
        db,
        owner=principal.sees_cost,
        location_ids=principal.location_ids if principal.role is Role.COUNTER else None,
        supplier_id=supplier_id,
        open_only=open_only,
    )


@router.get("/purchase-orders/{order_id}", response_model=OrderOwnerOut | OrderOut)
def get_order(
    order_id: int, principal: CurrentPrincipal, db: DbSession
) -> OrderOut | OrderOwnerOut:
    return service.get_order(
        db, order_id, owner=principal.sees_cost, can_access=principal.can_access_location
    )


@router.post(
    "/purchase-orders/{order_id}/receipts",
    response_model=ReceiptOut,
    status_code=status.HTTP_201_CREATED,
)
def receive_goods(
    order_id: int, body: ReceiptCreate, principal: OwnerOrCounter, db: DbSession
) -> ReceiptOut:
    """Record what arrived against an order. It moves no stock: stock enters with the bill."""
    receipt = service.create_receipt(
        db,
        order_id,
        body,
        actor_id=principal.user_id,
        is_owner=principal.is_owner,
        can_access=principal.can_access_location,
    )
    view = service.order_view(db, service.get_order_row(db, order_id), owner=False)
    return next(r for r in view.receipts if r.id == receipt.id)


@router.get("/reports/match-exceptions", response_model=MatchReport)
def match_exceptions(
    _: OwnerOnly,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
    all_lines: bool = False,
) -> MatchReport:
    """Bills entered against an order that differ from it beyond the tolerances (or every line
    with `all_lines`), with the purchase price variance (owner only)."""
    end = date_to or today_ist()
    return service.match_report(
        db, date_from or end - timedelta(days=30), end, only_exceptions=not all_lines
    )
