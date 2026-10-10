"""Period lock (FM7, docs/FINANCE_REVIEW.md F18). Once a month's return is filed, the owner locks
the books through its last day; every service that dates a document refuses a date on or before
it (`closing.ensure_period_open`). Moving the lock earlier, or removing it, needs a reason and
is audited. Accountant to confirm whether to lock after GSTR-1 or after GSTR-3B."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.errors import BusinessRuleError
from app.core.tenancy import TENANT_ID
from app.domain import controls as rules
from app.models.audit import AuditLog
from app.models.documents import DailyClosing, Gstr2bImport
from app.models.enums import AuditAction, ClosingStatus
from app.models.sales import SalesInvoice
from app.models.setup import AppUser, Location
from app.schemas.controls import ChecklistItem, PeriodChecklist, PeriodLockOut, PeriodLockSet
from app.services import banking, exceptions
from app.services.audit import record_event
from app.services.finance import month_bounds
from app.services.shop_settings import get_settings_row

ENTITY = "period_lock"


def get_lock(db: Session) -> PeriodLockOut:
    locked = get_settings_row(db).locked_through
    last = db.scalars(
        select(AuditLog)
        .where(AuditLog.tenant_id == TENANT_ID, AuditLog.entity == ENTITY)
        .order_by(AuditLog.id.desc())
        .limit(1)
    ).first()
    who = db.get(AppUser, last.user_id) if last and last.user_id else None
    return PeriodLockOut(
        locked_through=locked,
        changed_at=last.at if last else None,
        changed_by_name=who.full_name if who else None,
        reason=(last.changes or {}).get("reason") if last else None,
    )


def set_lock(db: Session, data: PeriodLockSet, *, actor_id: int) -> PeriodLockOut:
    settings = get_settings_row(db)
    today = today_ist()
    if data.locked_through is not None and data.locked_through > today:
        raise BusinessRuleError(
            "The lock cannot be later than today", code="LOCK_IN_FUTURE", field="locked_through"
        )
    old = settings.locked_through
    if data.locked_through == old:
        raise BusinessRuleError(
            "The books are already locked to that date",
            code="LOCK_UNCHANGED",
            field="locked_through",
        )
    settings.locked_through = data.locked_through
    settings.updated_by = actor_id
    record_event(
        db,
        AuditAction.OVERRIDE,
        ENTITY,
        settings.id,
        {
            "from": old,
            "to": data.locked_through,
            "reason": data.reason.strip(),
            "reopens": rules.reopens(data.locked_through, old),
        },
        user_id=actor_id,
    )
    db.commit()
    return get_lock(db)


def checklist(db: Session, period: str) -> PeriodChecklist:
    """What to look at before locking a month. Advice only: the lock does not wait for it."""
    start, end = month_bounds(period)
    items: list[ChecklistItem] = []

    billed = {
        (loc, on)
        for loc, on in db.execute(
            select(SalesInvoice.location_id, SalesInvoice.invoice_date).where(
                SalesInvoice.tenant_id == TENANT_ID,
                SalesInvoice.invoice_date >= start,
                SalesInvoice.invoice_date <= end,
            )
        )
    }
    closed = {
        (loc, on)
        for loc, on in db.execute(
            select(DailyClosing.location_id, DailyClosing.closing_date).where(
                DailyClosing.tenant_id == TENANT_ID,
                DailyClosing.status == ClosingStatus.CLOSED,
                DailyClosing.closing_date >= start,
                DailyClosing.closing_date <= end,
            )
        )
    }
    open_days = sorted(billed - closed, key=lambda x: (x[1], x[0]))
    codes = {x.id: x.code for x in db.scalars(select(Location))}
    items.append(
        ChecklistItem(
            code="days_closed",
            label="Every shop-day with bills is closed",
            state="ok" if not open_days else "warn",
            detail="All billing days are closed."
            if not open_days
            else f"{len(open_days)} shop-day(s) not closed, the first is "
            f"{codes.get(open_days[0][0], '?')} on {open_days[0][1]:%d-%m-%Y}.",
        )
    )

    has_2b = db.execute(
        select(Gstr2bImport.id).where(
            Gstr2bImport.tenant_id == TENANT_ID, Gstr2bImport.period == period
        )
    ).first()
    items.append(
        ChecklistItem(
            code="gstr2b",
            label="GSTR-2B imported and matched",
            state="ok" if has_2b else "warn",
            detail="Imported." if has_2b else "No GSTR-2B has been imported for this month.",
        )
    )

    rec = banking.reconciliation(db, start, end)
    if rec.line_count == 0:
        bank_state, bank_detail = "warn", "No bank statement lines in this month."
    elif rec.unmatched_count or rec.not_in_bank:
        bank_state = "warn"
        bank_detail = (
            f"{rec.unmatched_count} bank line(s) with no receipt and "
            f"{len(rec.not_in_bank)} receipt(s) not on the statement."
        )
    else:
        bank_state, bank_detail = "ok", f"All {rec.line_count} bank lines match."
    items.append(
        ChecklistItem(
            code="bank", label="Bank statement reconciled", state=bank_state, detail=bank_detail
        )
    )

    flags = exceptions.exception_report(db, start, end)
    items.append(
        ChecklistItem(
            code="exceptions",
            label="Exception report reviewed",
            state="ok" if not flags.rows else "warn",
            detail="Nothing flagged." if not flags.rows else f"{len(flags.rows)} entries flagged.",
        )
    )
    return PeriodChecklist(period=period, items=items, ready=all(i.state == "ok" for i in items))
