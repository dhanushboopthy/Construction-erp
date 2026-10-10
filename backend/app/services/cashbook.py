"""Cash book (FM1, docs/FINANCE_REVIEW.md F1, F2).

Vouchers for expenses, cash taken to or brought from the bank, and the owner's drawings and
capital. Each voucher is a permanent document (migration 0015); a mistake is undone by a
reversal voucher. The daily closing counts every cash voucher in the drawer, so a normal day
with petty expenses and a bank deposit closes with no difference."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.tenancy import TENANT_ID
from app.domain import finance
from app.domain.finance import CashEntryKind
from app.domain.money import ZERO, money
from app.models.approvals import Approval
from app.models.cashbook import CashEntry, ExpenseCategory
from app.models.enums import ApprovalAction, DocType, PaymentMode, Role
from app.models.setup import AppUser, Location
from app.schemas.finance import (
    CashBookOut,
    CashEntryCreate,
    CashEntryOut,
    ExpenseCategoryIn,
    ExpenseCategoryOut,
    ExpenseCategoryUpdate,
)
from app.services import approvals as approval_service
from app.services import closing as closing_service
from app.services.numbering import allocate_number
from app.services.shop_settings import get_settings_row

# Counter staff record what happens at their counter; moving the owner's own money is his.
COUNTER_KINDS = frozenset({CashEntryKind.EXPENSE, CashEntryKind.BANK_DEPOSIT})

DEFAULT_CATEGORIES: tuple[tuple[str, finance.ExpenseNature], ...] = (
    ("Rent", finance.ExpenseNature.FIXED),
    ("Salaries and wages", finance.ExpenseNature.FIXED),
    ("Electricity", finance.ExpenseNature.FIXED),
    ("Loading and unloading labour", finance.ExpenseNature.VARIABLE),
    ("Vehicle, fuel and repairs", finance.ExpenseNature.VARIABLE),
    ("Office, tea and stationery", finance.ExpenseNature.FIXED),
    ("Repairs and maintenance", finance.ExpenseNature.FIXED),
    ("Interest and bank charges", finance.ExpenseNature.INTEREST),
    ("Other expenses", finance.ExpenseNature.FIXED),
)


# ---------------------------------------------------------------------------- categories


def ensure_default_categories(db: Session) -> None:
    """Seed the usual heads once; the owner can rename, add or retire them."""
    have = set(db.execute(select(ExpenseCategory.name)).scalars())
    for name, nature in DEFAULT_CATEGORIES:
        if name not in have:
            db.add(ExpenseCategory(tenant_id=TENANT_ID, name=name, nature=nature))
    db.flush()


def list_categories(db: Session, include_inactive: bool = False) -> list[ExpenseCategoryOut]:
    stmt = select(ExpenseCategory).where(ExpenseCategory.tenant_id == TENANT_ID)
    if not include_inactive:
        stmt = stmt.where(ExpenseCategory.is_active.is_(True))
    rows = db.execute(stmt.order_by(ExpenseCategory.name)).scalars()
    return [ExpenseCategoryOut.model_validate(r) for r in rows]


def _category(db: Session, category_id: int) -> ExpenseCategory:
    row = db.get(ExpenseCategory, category_id)
    if row is None or row.tenant_id != TENANT_ID:
        raise NotFoundError("Expense head not found", field="category_id")
    return row


def _name_taken(db: Session, name: str, except_id: int | None = None) -> bool:
    stmt = select(ExpenseCategory.id).where(
        ExpenseCategory.tenant_id == TENANT_ID, ExpenseCategory.name == name
    )
    found = db.execute(stmt).scalar_one_or_none()
    return found is not None and found != except_id


def create_category(db: Session, data: ExpenseCategoryIn) -> ExpenseCategoryOut:
    name = data.name.strip()
    if _name_taken(db, name):
        raise ConflictError("An expense head with this name exists", code="DUPLICATE", field="name")
    row = ExpenseCategory(tenant_id=TENANT_ID, name=name, nature=data.nature)
    db.add(row)
    db.commit()
    return ExpenseCategoryOut.model_validate(row)


def update_category(
    db: Session, category_id: int, data: ExpenseCategoryUpdate
) -> ExpenseCategoryOut:
    row = _category(db, category_id)
    if data.name is not None:
        name = data.name.strip()
        if _name_taken(db, name, except_id=row.id):
            raise ConflictError(
                "An expense head with this name exists", code="DUPLICATE", field="name"
            )
        row.name = name
    if data.nature is not None:
        row.nature = data.nature
    if data.is_active is not None:
        row.is_active = data.is_active
    db.commit()
    return ExpenseCategoryOut.model_validate(row)


# ---------------------------------------------------------------------------- vouchers


@dataclass(frozen=True)
class Actor:
    user_id: int
    role: Role
    can_access: bool  # may work at this location (counter staff: own shop only)


def _effect(row: CashEntry) -> Decimal:
    return finance.cash_effect(
        row.kind, row.mode is PaymentMode.CASH, row.amount, reversal=row.reverses_id is not None
    )


def _views(db: Session, rows: list[CashEntry]) -> list[CashEntryOut]:
    if not rows:
        return []
    ids = [r.id for r in rows]
    codes = dict(db.execute(select(Location.id, Location.code)).all())
    cats = dict(db.execute(select(ExpenseCategory.id, ExpenseCategory.name)).all())
    users = dict(db.execute(select(AppUser.id, AppUser.full_name)).all())
    original = aliased(CashEntry)
    reverses = dict(
        db.execute(
            select(CashEntry.id, original.number)
            .join(original, original.id == CashEntry.reverses_id)
            .where(CashEntry.id.in_(ids))
        ).all()
    )
    reversed_by = dict(
        db.execute(
            select(CashEntry.reverses_id, CashEntry.number).where(CashEntry.reverses_id.in_(ids))
        ).all()
    )
    return [
        CashEntryOut(
            id=r.id,
            number=r.number,
            location_id=r.location_id,
            location_code=codes.get(r.location_id, ""),
            entry_date=r.entry_date,
            kind=r.kind,
            mode=r.mode,
            amount=r.amount,
            category_id=r.category_id,
            category_name=cats.get(r.category_id) if r.category_id else None,
            paid_to=r.paid_to,
            reference=r.reference,
            note=r.note,
            reverses_id=r.reverses_id,
            reverses_number=reverses.get(r.id),
            reversed_by_number=reversed_by.get(r.id),
            drawer_effect=_effect(r),
            created_by_name=users.get(r.created_by) if r.created_by else None,
        )
        for r in rows
    ]


def _approval(db: Session, ids: list[int], actor: Actor) -> Approval | None:
    if not ids:
        return None
    found = approval_service.load_valid(db, ids, actor.user_id, party_id=0)
    match = next((a for a in found if a.action is ApprovalAction.EXPENSE), None)
    if match is None:
        raise BusinessRuleError(
            "That approval is not for a cash-book voucher. Ask the owner again.",
            code="APPROVAL_INVALID",
            requires_owner_approval=True,
        )
    return match


def create_entry(db: Session, data: CashEntryCreate, actor: Actor) -> CashEntryOut:
    if actor.role is Role.ACCOUNTANT:
        raise PermissionDeniedError("The accountant can read the cash book but not write it")
    owner = actor.role is Role.OWNER
    if not actor.can_access:
        raise PermissionDeniedError("You can only write the cash book of your own shop")
    if not owner and data.kind not in COUNTER_KINDS:
        raise PermissionDeniedError("Only the owner records bank withdrawals, drawings or capital")
    place = db.get(Location, data.location_id)
    if place is None or place.tenant_id != TENANT_ID or not place.is_active:
        raise NotFoundError("Shop not found or inactive", field="location_id")

    today = today_ist()
    on = data.entry_date or today
    if on > today:
        raise BusinessRuleError("A voucher cannot be dated in the future", code="FUTURE_DATE")
    if on != today and not owner:
        raise BusinessRuleError(
            "Only the owner can enter a voucher for an earlier day.",
            code="BACKDATE_NEEDS_OWNER",
            field="entry_date",
        )
    closing_service.ensure_day_open(db, place.id, on)

    if finance.needs_cash_mode(data.kind) and data.mode is not PaymentMode.CASH:
        raise BusinessRuleError(
            "A bank deposit or withdrawal moves cash: choose cash.",
            code="CASH_ONLY",
            field="mode",
        )
    category_id: int | None = None
    if data.kind is CashEntryKind.EXPENSE:
        if data.category_id is None:
            raise BusinessRuleError(
                "Choose the expense head.", code="CATEGORY_REQUIRED", field="category_id"
            )
        category = _category(db, data.category_id)
        if not category.is_active:
            raise BusinessRuleError(
                "This expense head is retired.", code="CATEGORY_INACTIVE", field="category_id"
            )
        category_id = category.id
    elif data.category_id is not None:
        raise BusinessRuleError(
            "Only expenses have a head.", code="CATEGORY_NOT_ALLOWED", field="category_id"
        )

    approval = None
    if not owner:
        limit = get_settings_row(db).expense_approval_limit
        approval = _approval(db, data.approval_ids, actor)
        # Expenses only: a deposit is checked against the bank statement instead (FM7).
        if (
            approval is None
            and data.kind is CashEntryKind.EXPENSE
            and finance.needs_approval(data.amount, limit)
        ):
            raise BusinessRuleError(
                f"Vouchers above ₹{limit:,.0f} need the owner's approval.",
                code="EXPENSE_NEEDS_OWNER",
                requires_owner_approval=True,
            )

    settings = get_settings_row(db)
    number = allocate_number(
        db,
        location_id=place.id,
        doc_type=DocType.CASH_VOUCHER,
        on=on,
        fy_start_month=settings.financial_year_start_month,
    )
    row = CashEntry(
        tenant_id=TENANT_ID,
        number=number,
        location_id=place.id,
        entry_date=on,
        kind=data.kind,
        mode=data.mode,
        amount=money(data.amount),
        category_id=category_id,
        paid_to=(data.paid_to or "").strip() or None,
        reference=(data.reference or "").strip() or None,
        note=(data.note or "").strip() or None,
        approval_id=approval.id if approval else None,
        created_by=actor.user_id,
    )
    db.add(row)
    db.flush()
    if approval is not None:
        approval_service.mark_used([approval], number)
    db.commit()
    return _views(db, [row])[0]


def reverse_entry(db: Session, entry_id: int, reason: str, *, actor_id: int) -> CashEntryOut:
    """Owner only: a new voucher, dated today, that cancels the original exactly."""
    original = db.get(CashEntry, entry_id)
    if original is None or original.tenant_id != TENANT_ID:
        raise NotFoundError("Voucher not found")
    if original.reverses_id is not None:
        raise BusinessRuleError("A reversal cannot itself be reversed", code="IS_REVERSAL")
    done = db.execute(select(CashEntry.number).where(CashEntry.reverses_id == original.id)).first()
    if done is not None:
        raise BusinessRuleError(
            f"This voucher was already reversed by {done[0]}", code="ALREADY_REVERSED"
        )
    on = today_ist()
    closing_service.ensure_day_open(db, original.location_id, on)
    settings = get_settings_row(db)
    number = allocate_number(
        db,
        location_id=original.location_id,
        doc_type=DocType.CASH_VOUCHER,
        on=on,
        fy_start_month=settings.financial_year_start_month,
    )
    row = CashEntry(
        tenant_id=TENANT_ID,
        number=number,
        location_id=original.location_id,
        entry_date=on,
        kind=original.kind,
        mode=original.mode,
        amount=original.amount,
        category_id=original.category_id,
        paid_to=original.paid_to,
        note=f"Reverses {original.number}: {reason.strip()}"[:200],
        reverses_id=original.id,
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    return _views(db, [row])[0]


def cash_book(
    db: Session,
    *,
    location_ids: frozenset[int] | None,
    location_id: int | None,
    date_from: date,
    date_to: date,
) -> CashBookOut:
    if date_to < date_from:
        raise BusinessRuleError("The end date is before the start date", code="BAD_RANGE")
    stmt = select(CashEntry).where(
        CashEntry.tenant_id == TENANT_ID,
        CashEntry.entry_date >= date_from,
        CashEntry.entry_date <= date_to,
    )
    if location_id is not None:
        stmt = stmt.where(CashEntry.location_id == location_id)
    if location_ids is not None:
        stmt = stmt.where(CashEntry.location_id.in_(location_ids))
    rows = list(db.execute(stmt.order_by(CashEntry.entry_date, CashEntry.id)).scalars())
    views = _views(db, rows)
    drawer_in = sum((v.drawer_effect for v in views if v.drawer_effect > ZERO), ZERO)
    drawer_out = -sum((v.drawer_effect for v in views if v.drawer_effect < ZERO), ZERO)
    expenses = sum(
        (
            -v.amount if v.reverses_id else v.amount
            for v in views
            if v.kind is CashEntryKind.EXPENSE
        ),
        ZERO,
    )
    return CashBookOut(
        location_id=location_id,
        date_from=date_from,
        date_to=date_to,
        entries=views,
        drawer_in=money(drawer_in),
        drawer_out=money(drawer_out),
        expenses=money(expenses),
    )


@dataclass(frozen=True)
class DrawerMoves:
    """What the cash book did to one shop's drawer on one day, for the daily closing."""

    expenses: Decimal  # paid out in cash
    deposited: Decimal  # taken to the bank
    withdrawn: Decimal  # brought from the bank
    drawings: Decimal  # taken by the owner
    capital: Decimal  # put in by the owner

    @property
    def cash_in(self) -> Decimal:
        return money(self.withdrawn + self.capital)

    @property
    def cash_out(self) -> Decimal:
        return money(self.expenses + self.deposited + self.drawings)


def drawer_moves(db: Session, location_id: int, on: date) -> DrawerMoves:
    rows = db.execute(
        select(CashEntry).where(
            CashEntry.tenant_id == TENANT_ID,
            CashEntry.location_id == location_id,
            CashEntry.entry_date == on,
            CashEntry.mode == PaymentMode.CASH,
        )
    ).scalars()
    total = dict.fromkeys(CashEntryKind, ZERO)
    for row in rows:
        total[row.kind] += -row.amount if row.reverses_id is not None else row.amount
    return DrawerMoves(
        expenses=money(total[CashEntryKind.EXPENSE]),
        deposited=money(total[CashEntryKind.BANK_DEPOSIT]),
        withdrawn=money(total[CashEntryKind.BANK_WITHDRAWAL]),
        drawings=money(total[CashEntryKind.OWNER_DRAWING]),
        capital=money(total[CashEntryKind.OWNER_CAPITAL]),
    )
