"""Integrity checks and system status (Milestone 14).

`run_checks` re-adds the books from scratch and compares them with what was stored, so a bug,
a bad restore or a console slip shows up as a named failure. It is read-only. The same checks
run after every restore drill (`python -m app.scripts.verify`) and from the owner's System page."""

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.core.config import GspProvider, get_settings
from app.core.tenancy import TENANT_ID
from app.domain import gstr
from app.domain import stock_valuation as stock_rules
from app.domain.money import ZERO
from app.models.cashbook import CashEntry
from app.models.documents import Attachment, DailyClosing
from app.models.enums import (
    ClosingStatus,
    FulfilmentSource,
    LocationKind,
    PartyRef,
    PurchaseMode,
    StockRef,
)
from app.models.ledgers import PartyLedger, StockLedger
from app.models.purchasing import Payment, Purchase, PurchaseLine
from app.models.receivables import BadDebtWriteoff
from app.models.returns import CreditNote, DebitNote
from app.models.sales import SalesInvoice, SalesLine
from app.models.setup import Location
from app.models.stock_ops import StockAdjustment
from app.schemas.system import Check, StatusOut, VerifyOut
from app.services.storage import StorageError, get_storage

# Triggers the migrations install; the check below counts them by name.
LEDGER_TABLES = ["stock_ledger", "party_ledger"]
NO_DELETE = [
    "sales_invoice", "sales_line", "credit_note", "credit_note_line", "debit_note",
    "debit_note_line", "purchase", "purchase_line", "purchase_cost", "payment",
    "stock_transfer", "stock_transfer_line", "drop_ship_link", "eway_bill", "einvoice",
    "daily_closing", "attachment", "gstr2b_import", "cash_entry", "stock_adjustment",
    "stock_adjustment_line", "bad_debt_writeoff",
]  # fmt: skip
NO_EDIT = [
    "sales_invoice", "sales_line", "credit_note", "credit_note_line", "debit_note",
    "debit_note_line", "purchase_line", "purchase_cost", "payment", "attachment", "gstr2b_import",
    "cash_entry", "stock_adjustment", "stock_adjustment_line", "bad_debt_writeoff",
]  # fmt: skip
BACKUP_MAX_AGE_HOURS = 30


def expected_triggers() -> set[str]:
    return (
        {f"{t}_append_only" for t in LEDGER_TABLES}
        | {f"{t}_no_delete" for t in NO_DELETE}
        | {f"{t}_no_edit" for t in NO_EDIT}
    )


def _ok(name: str, detail: str) -> Check:
    return Check(name=name, state="ok", detail=detail)


def _fail(name: str, detail: str) -> Check:
    return Check(name=name, state="fail", detail=detail)


def _warn(name: str, detail: str) -> Check:
    return Check(name=name, state="warn", detail=detail)


# ---------------------------------------------------------------------------- the checks


def migrations_check(db: Session) -> Check:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    heads = set(ScriptDirectory.from_config(config).get_heads())
    current = set(MigrationContext.configure(db.connection()).get_current_heads())
    if current == heads:
        return _ok("Database version", f"At the latest version ({', '.join(sorted(heads))}).")
    return _fail(
        "Database version",
        f"The database is at {sorted(current) or 'nothing'}, the program expects {sorted(heads)}.",
    )


def triggers_check(db: Session) -> Check:
    found = set(
        db.execute(
            text(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND "
                "(tgname LIKE '%\\_append\\_only' OR tgname LIKE '%\\_no\\_delete' "
                "OR tgname LIKE '%\\_no\\_edit')"
            )
        ).scalars()
    )
    missing = sorted(expected_triggers() - found)
    if missing:
        return _fail("Protection against edits", f"Missing database guards: {', '.join(missing)}.")
    return _ok("Protection against edits", f"All {len(found)} database guards are in place.")


def numbering_check(db: Session) -> Check:
    sources = {
        "bills": SalesInvoice.number,
        "credit notes": CreditNote.number,
        "debit notes": DebitNote.number,
        "purchases": Purchase.number,
        "receipts": Payment.number,
        "cash vouchers": CashEntry.number,
        "stock adjustments": StockAdjustment.number,
        "bad-debt write-offs": BadDebtWriteoff.number,
    }
    problems: list[str] = []
    total = 0
    for label, column in sources.items():
        numbers = [n for n in db.execute(select(column)).scalars() if n]
        total += len(numbers)
        for series in gstr.document_series(numbers):
            if series.gaps:
                problems.append(f"{label} {series.series}: missing {series.gaps[:5]}")
    if problems:
        return _fail("Document numbers", "; ".join(problems))
    return _ok("Document numbers", f"{total} numbers, no gaps in any series.")


def totals_check(db: Session) -> Check:
    problems: list[str] = []
    for label, model in (
        ("bill", SalesInvoice),
        ("credit note", CreditNote),
        ("debit note", DebitNote),
    ):
        bad = db.execute(
            select(model.number).where(
                model.taxable_value + model.cgst + model.sgst + model.igst + model.round_off
                != model.grand_total
            )
        ).scalars()
        problems += [f"{label} {n}: parts do not add up to the total" for n in bad]
    for label, table, line_table, fk in (
        ("bill", "sales_invoice", "sales_line", "invoice_id"),
        ("credit note", "credit_note", "credit_note_line", "credit_note_id"),
        ("debit note", "debit_note", "debit_note_line", "debit_note_id"),
    ):
        rows = db.execute(
            text(
                f"SELECT h.number FROM {table} h JOIN ("  # noqa: S608 - fixed names above
                f"SELECT {fk} AS id, SUM(taxable) AS t FROM {line_table} GROUP BY {fk}"
                ") l ON l.id = h.id WHERE l.t <> h.taxable_value"
            )
        ).scalars()
        problems += [f"{label} {n}: lines do not add up to the header" for n in rows]
    if problems:
        return _fail("Document totals", "; ".join(problems[:10]))
    return _ok("Document totals", "Every bill and note adds up, lines to header.")


def _sum(db: Session, stmt: object) -> Decimal:
    return Decimal(str(db.execute(stmt).scalar_one() or 0))  # type: ignore[call-overload]


def ledger_check(db: Session) -> Check:
    pairs = [
        (
            "bills",
            select(func.coalesce(func.sum(PartyLedger.debit), 0)).where(
                PartyLedger.ref_type == PartyRef.SALE
            ),
            select(func.coalesce(func.sum(SalesInvoice.grand_total), 0)),
        ),
        (
            "credit notes",
            select(func.coalesce(func.sum(PartyLedger.credit), 0)).where(
                PartyLedger.ref_type == PartyRef.CREDIT_NOTE
            ),
            select(func.coalesce(func.sum(CreditNote.grand_total), 0)),
        ),
        (
            "purchases",
            select(func.coalesce(func.sum(PartyLedger.credit), 0)).where(
                PartyLedger.ref_type == PartyRef.PURCHASE
            ),
            select(func.coalesce(func.sum(Purchase.supplier_payable), 0)),
        ),
        (
            "debit notes",
            select(func.coalesce(func.sum(PartyLedger.debit), 0)).where(
                PartyLedger.ref_type == PartyRef.DEBIT_NOTE
            ),
            select(func.coalesce(func.sum(DebitNote.grand_total), 0)),
        ),
        (
            "bad-debt write-offs",
            select(func.coalesce(func.sum(PartyLedger.credit), 0)).where(
                PartyLedger.ref_type == PartyRef.WRITE_OFF
            ),
            select(func.coalesce(func.sum(BadDebtWriteoff.amount), 0)),
        ),
    ]
    problems = []
    for label, ledger, documents in pairs:
        a, b = _sum(db, ledger), _sum(db, documents)
        if a != b:
            problems.append(
                f"{label}: customer and supplier accounts show {a}, documents total {b}"
            )
    if problems:
        return _fail("Accounts agree with documents", "; ".join(problems))
    return _ok("Accounts agree with documents", "Party accounts match bills, purchases and notes.")


def stock_check(db: Session) -> Check:
    rows = db.execute(
        select(StockLedger)
        .where(StockLedger.tenant_id == TENANT_ID)
        .order_by(StockLedger.entry_date, StockLedger.id)
    ).scalars()
    by_item: dict[int, list[stock_rules.StockMove]] = {}
    for r in rows:
        by_item.setdefault(r.item_id, []).append(
            stock_rules.StockMove(
                r.entry_date, str(r.location_id), r.qty_in, r.qty_out, r.unit_cost
            )
        )
    negative: list[str] = []
    for item_id, moves in by_item.items():
        try:
            result = stock_rules.replay(moves)
        except stock_rules.NegativeStockError as exc:
            negative.append(f"item {item_id}: {exc}")
            continue
        negative += [
            f"item {item_id} at {loc}" for loc, q in result.by_location.items() if q < ZERO
        ]
    if negative:
        return _fail("Stock", "Negative stock: " + "; ".join(negative[:10]))
    return _ok(
        "Stock", f"{len(by_item)} items replayed from the stock ledger; nothing is negative."
    )


COGS_TOLERANCE_PCT = Decimal("0.0001")  # 0.01 % of what moved: unit costs are kept to 4 places
COGS_TOLERANCE_MIN = Decimal("10")


def cogs_months(today: date) -> list[tuple[date, date]]:
    """The month just finished and the month so far: the periods the cost check covers."""
    first = today.replace(day=1)
    last_end = first - timedelta(days=1)
    return [(last_end.replace(day=1), last_end), (first, today)]


def cogs_check(db: Session, today: date | None = None) -> Check:
    """Opening stock + purchases - cost of goods sold +/- everything else that moved stock must
    equal the closing stock (docs/FINANCE_REVIEW.md F28). Purchases and cost of goods come from
    the bills; the rest, and the stock itself, from the stock ledger, so a costing bug in either
    shows as a difference."""
    from app.services.working_capital import stock_values  # function-level: avoids an import loop

    today = today or today_ist()
    problems: list[str] = []
    checked = 0
    for start, end in cogs_months(today):
        rows = list(
            db.execute(
                select(StockLedger).where(
                    StockLedger.tenant_id == TENANT_ID,
                    StockLedger.entry_date >= start,
                    StockLedger.entry_date <= end,
                )
            ).scalars()
        )
        try:
            values = stock_values(db, [start - timedelta(days=1), end])
        except stock_rules.NegativeStockError:
            return _fail("Cost of goods", "Stock cannot be replayed; see the Stock check above.")
        opening, closing = values[start - timedelta(days=1)], values[end]
        if not rows and opening == ZERO and closing == ZERO:
            continue
        checked += 1
        bought = _sum(
            db,
            select(func.coalesce(func.sum(PurchaseLine.total_cost), 0))
            .join(Purchase, Purchase.id == PurchaseLine.purchase_id)
            .where(
                Purchase.tenant_id == TENANT_ID,
                Purchase.mode == PurchaseMode.STOCK,
                Purchase.bill_date >= start,
                Purchase.bill_date <= end,
            ),
        )
        cogs = _sum(
            db,
            select(func.coalesce(func.sum(SalesLine.base_qty * SalesLine.cost_per_unit), 0))
            .join(SalesInvoice, SalesInvoice.id == SalesLine.invoice_id)
            .where(
                SalesInvoice.tenant_id == TENANT_ID,
                SalesLine.fulfilment_source != FulfilmentSource.DIRECT,
                SalesInvoice.invoice_date >= start,
                SalesInvoice.invoice_date <= end,
            ),
        )
        other = sum(
            (
                (r.qty_in - r.qty_out) * r.unit_cost
                for r in rows
                if r.ref_type not in (StockRef.PURCHASE, StockRef.SALE)
            ),
            ZERO,
        )
        expected = opening + bought - cogs + other
        tolerance = max(COGS_TOLERANCE_MIN, (opening + bought) * COGS_TOLERANCE_PCT)
        if abs(closing - expected) > tolerance:
            problems.append(
                f"{start:%b %Y}: opening {opening:,.2f} + purchases {bought:,.2f} - cost of goods "
                f"sold {cogs:,.2f} + other stock moves {other:,.2f} = {expected:,.2f}, but the "
                f"stock ledger shows {closing:,.2f}"
            )
    if problems:
        return _fail("Cost of goods", "; ".join(problems))
    if not checked:
        return _ok("Cost of goods", "No stock moved in the last two months, so nothing to check.")
    return _ok(
        "Cost of goods",
        "Opening stock + purchases - cost of goods sold + other moves equals closing stock "
        f"for {checked} month{'s' if checked != 1 else ''}.",
    )


def files_check(db: Session, *, full: bool) -> Check:
    store = get_storage()
    missing: list[str] = []
    damaged: list[str] = []
    rows = list(db.execute(select(Attachment)).scalars())
    for a in rows:
        try:
            if not store.exists(a.storage_key):
                missing.append(a.file_name)
            elif full and hashlib.sha256(store.get(a.storage_key)).hexdigest() != a.sha256:
                damaged.append(a.file_name)
        except StorageError:
            missing.append(a.file_name)
    closings = list(
        db.execute(
            select(DailyClosing).where(DailyClosing.status == ClosingStatus.CLOSED)
        ).scalars()
    )
    for c in closings:
        try:
            if not c.pdf_key or not store.exists(c.pdf_key):
                missing.append(f"closing {c.closing_date}")
        except StorageError:
            missing.append(f"closing {c.closing_date}")
    if missing or damaged:
        return _fail(
            "Stored files",
            f"Missing: {missing[:5]}; damaged: {damaged[:5]}. Restore the files from backup.",
        )
    return _ok(
        "Stored files",
        f"{len(rows)} papers and {len(closings)} closing PDFs found"
        + (", contents checked." if full else "."),
    )


def run_checks(db: Session, *, full: bool = False) -> VerifyOut:
    checks = [
        migrations_check(db),
        triggers_check(db),
        numbering_check(db),
        totals_check(db),
        ledger_check(db),
        stock_check(db),
        cogs_check(db),
        files_check(db, full=full),
    ]
    return VerifyOut(ok=all(c.state != "fail" for c in checks), checks=checks)


# ---------------------------------------------------------------------------- status


def backup_check() -> tuple[Check, datetime | None]:
    folder = get_settings().backup_dir
    if not folder:
        return _warn(
            "Nightly backup", "BACKUP_DIR is not set, so backups cannot be checked from here."
        ), None
    files = sorted(Path(folder).glob("erp-*.dump"), key=lambda p: p.stat().st_mtime)
    if not files:
        return _fail("Nightly backup", "No backup file found. Check the backup service."), None
    made = datetime.fromtimestamp(files[-1].stat().st_mtime, tz=UTC)
    age = datetime.now(UTC) - made
    if age > timedelta(hours=BACKUP_MAX_AGE_HOURS):
        return _fail(
            "Nightly backup", f"The newest backup is {int(age.total_seconds() // 3600)} hours old."
        ), made
    return _ok(
        "Nightly backup",
        f"Newest backup is {int(age.total_seconds() // 3600)} hours old ({files[-1].name}).",
    ), made


def storage_check() -> Check:
    try:
        store = get_storage()
        probe = b"ok"
        store.put("health/probe.txt", probe)
        if store.get("health/probe.txt") != probe:
            return _fail("File storage", "A test file came back different.")
    except (StorageError, OSError) as exc:
        return _fail("File storage", f"Cannot save files: {exc}")
    return _ok(
        "File storage", f"Saving and reading files works ({get_settings().storage_provider.value})."
    )


def gsp_check() -> Check:
    settings = get_settings()
    if settings.gsp_provider is GspProvider.FAKE:
        if settings.is_production:
            return _fail("E-way bill provider", "No provider is set: e-way bills cannot be made.")
        return _warn(
            "E-way bill provider", "Pretend provider (development). No real e-way bills are made."
        )
    return _ok("E-way bill provider", f"Using the {settings.gsp_provider.value} provider.")


def unclosed_yesterday(db: Session) -> list[str]:
    yesterday = today_ist() - timedelta(days=1)
    shops = list(
        db.execute(
            select(Location).where(
                Location.tenant_id == TENANT_ID,
                Location.kind == LocationKind.SHOP,
                Location.is_active.is_(True),
            )
        ).scalars()
    )
    closed = set(
        db.execute(
            select(DailyClosing.location_id).where(
                DailyClosing.closing_date == yesterday, DailyClosing.status == ClosingStatus.CLOSED
            )
        ).scalars()
    )
    had_sales = set(
        db.execute(
            select(SalesInvoice.location_id)
            .where(SalesInvoice.invoice_date == yesterday)
            .distinct()
        ).scalars()
    )
    return [s.code for s in shops if s.id not in closed and s.id in had_sales]


def status(db: Session) -> StatusOut:
    settings = get_settings()
    db.execute(text("SELECT 1"))
    backup, made = backup_check()
    return StatusOut(
        version=settings.app_version,
        environment=settings.app_env.value,
        test_watermark=not settings.is_production,
        database="ok",
        migrations=migrations_check(db),
        backup=backup,
        last_backup_at=made,
        storage=storage_check(),
        gsp=gsp_check(),
        unclosed=unclosed_yesterday(db),
        as_of=today_ist(),
    )
