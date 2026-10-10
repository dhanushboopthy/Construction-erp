"""Tally day-book export (FM4, docs/FINANCE_REVIEW.md F5). Owner and accountant.

Every issued document in a date range becomes a balanced voucher (sales, credit notes,
purchases, debit notes, receipts, payments, cash-book entries, and the rebates and freight that
sit on a party's account). Nothing is stored except the accountant's ledger names: the file is
built from the documents each time and checked against the GST returns and the party ledger, so
it cannot drift from the books. Real Tally accepts the file only after the accountant has
tried an import into a test company (docs/GAP_ANALYSIS.md)."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError
from app.core.tenancy import TENANT_ID
from app.domain import tally as rules
from app.domain.money import ZERO, money
from app.domain.tally import Purpose, VoucherKind
from app.models.cashbook import CashEntry, ExpenseCategory
from app.models.enums import AuditAction, LedgerAccount, PartyRef, PaymentDirection, PaymentMode
from app.models.ledgers import PartyLedger
from app.models.masters import Party
from app.models.purchasing import Payment
from app.models.returns import CreditNote, DebitNote
from app.models.sales import SalesInvoice
from app.models.tally import TallyLedger
from app.schemas.tally import (
    TallyCheckOut,
    TallyKindOut,
    TallyLedgerOut,
    TallyLedgersOut,
    TallyLedgersPut,
    TallyPreviewOut,
)
from app.services import audit, gst_returns
from app.services.shop_settings import get_settings_row

COMPANY = "company"
MAX_DAYS = 366

LABELS: dict[Purpose, str] = {
    Purpose.SALES: "Sales (taxable value of bills, less credit notes)",
    Purpose.PURCHASE: "Purchases (supplier bills, less debit notes)",
    Purpose.OUTPUT_CGST: "CGST on sales",
    Purpose.OUTPUT_SGST: "SGST on sales",
    Purpose.OUTPUT_IGST: "IGST on sales",
    Purpose.INPUT_CGST: "CGST on purchases (input tax)",
    Purpose.INPUT_SGST: "SGST on purchases (input tax)",
    Purpose.INPUT_IGST: "IGST on purchases (input tax)",
    Purpose.ROUND_OFF: "Round off on bills",
    Purpose.CASH: "Cash in the drawer",
    Purpose.BANK: "Bank (UPI and transfers)",
    Purpose.DRAWINGS: "Owner's drawings",
    Purpose.CAPITAL: "Owner's capital",
    Purpose.REBATE: "Supplier rebates",
    Purpose.FREIGHT: "Freight payable to transporters",
}

_ORDER = {kind: i for i, kind in enumerate(VoucherKind)}


# ------------------------------------------------------------------------------ ledger names


def _saved(db: Session) -> dict[str, str]:
    rows = db.execute(select(TallyLedger).where(TallyLedger.tenant_id == TENANT_ID)).scalars()
    return {r.purpose: r.name for r in rows}


def names(db: Session) -> dict[Purpose, str]:
    return rules.ledger_names(_saved(db))


def company(db: Session) -> str:
    return _saved(db).get(COMPANY) or get_settings_row(db).legal_name


def read_ledgers(db: Session) -> TallyLedgersOut:
    saved = _saved(db)
    current = rules.ledger_names(saved)
    return TallyLedgersOut(
        company=company(db),
        default_company=get_settings_row(db).legal_name,
        ledgers=[
            TallyLedgerOut(
                purpose=purpose.value,
                label=LABELS[purpose],
                name=current[purpose],
                default=default,
                group=group,
                is_custom=current[purpose] != default,
            )
            for purpose, (default, group) in rules.DEFAULTS.items()
        ],
    )


def save_ledgers(db: Session, data: TallyLedgersPut, *, actor_id: int) -> TallyLedgersOut:
    unknown = sorted(set(data.names) - {p.value for p in Purpose})
    if unknown:
        raise BusinessRuleError(
            f"There is no ledger called {unknown[0]!r}", code="UNKNOWN_LEDGER", field="names"
        )
    chosen = rules.ledger_names(data.names)
    seen: dict[str, Purpose] = {}
    for purpose, name in chosen.items():
        if name.lower() in seen:
            raise BusinessRuleError(
                f"{name!r} is used for two ledgers ({LABELS[seen[name.lower()]]} and "
                f"{LABELS[purpose]}). Give each its own name.",
                code="DUPLICATE_LEDGER_NAME",
                field="names",
            )
        seen[name.lower()] = purpose
    wanted = {
        purpose.value: name
        for purpose, name in chosen.items()
        if name != rules.DEFAULTS[purpose][0]
    }
    if data.company and data.company.strip():
        wanted[COMPANY] = data.company.strip()
    existing = {
        r.purpose: r
        for r in db.execute(select(TallyLedger).where(TallyLedger.tenant_id == TENANT_ID)).scalars()
    }
    for key, row in existing.items():
        if key not in wanted:
            db.delete(row)
    for key, name in wanted.items():
        if key in existing:
            existing[key].name = name
            existing[key].updated_by = actor_id
        else:
            db.add(TallyLedger(tenant_id=TENANT_ID, purpose=key, name=name, created_by=actor_id))
    db.commit()
    return read_ledgers(db)


# ------------------------------------------------------------------------------ the vouchers


def _party_names(db: Session) -> dict[int, str]:
    return {
        p.id: p.name
        for p in db.execute(select(Party).where(Party.tenant_id == TENANT_ID)).scalars()
    }


def build_vouchers(db: Session, date_from: date, date_to: date) -> list[rules.Voucher]:
    ledger = names(db)
    people = _party_names(db)
    out: list[rules.Voucher] = []

    for inv in db.execute(
        select(SalesInvoice).where(
            SalesInvoice.tenant_id == TENANT_ID,
            SalesInvoice.invoice_date >= date_from,
            SalesInvoice.invoice_date <= date_to,
        )
    ).scalars():
        out.append(
            _document(
                VoucherKind.SALES,
                inv.number,
                inv.invoice_date,
                people[inv.party_id],
                f"Sales bill {inv.number}",
                inv,
                ledger,
                outward=True,
                party_debit=True,
            )
        )
    for note in db.execute(
        select(CreditNote).where(
            CreditNote.tenant_id == TENANT_ID,
            CreditNote.note_date >= date_from,
            CreditNote.note_date <= date_to,
        )
    ).scalars():
        out.append(
            _document(
                VoucherKind.CREDIT_NOTE,
                note.number,
                note.note_date,
                people[note.party_id],
                f"Credit note {note.number}: {note.reason}",
                note,
                ledger,
                outward=True,
                party_debit=False,
            )
        )
    for purchase, supplier, heads in gst_returns._purchase_figures(db, date_from, date_to):
        tax = heads.cgst + heads.sgst + heads.igst
        out.append(
            rules.tax_document(
                VoucherKind.PURCHASE,
                number=purchase.number,
                on=purchase.bill_date,
                party=supplier.name,
                narration=f"Supplier bill {purchase.bill_no}",
                grand=purchase.supplier_payable,
                taxable=purchase.supplier_payable - tax,
                cgst=heads.cgst,
                sgst=heads.sgst,
                igst=heads.igst,
                round_off=ZERO,
                names=ledger,
                outward=False,
                party_debit=False,
            )
        )
    for dn in db.execute(
        select(DebitNote).where(
            DebitNote.tenant_id == TENANT_ID,
            DebitNote.note_date >= date_from,
            DebitNote.note_date <= date_to,
        )
    ).scalars():
        out.append(
            _document(
                VoucherKind.DEBIT_NOTE,
                dn.number,
                dn.note_date,
                people[dn.party_id],
                f"Debit note {dn.number}: {dn.reason}",
                dn,
                ledger,
                outward=False,
                party_debit=True,
            )
        )
    for pay in db.execute(
        select(Payment).where(
            Payment.tenant_id == TENANT_ID,
            Payment.payment_date >= date_from,
            Payment.payment_date <= date_to,
        )
    ).scalars():
        received = pay.direction is PaymentDirection.RECEIVED
        out.append(
            rules.settlement(
                pay.number,
                pay.payment_date,
                people[pay.party_id],
                pay.amount,
                pay.mode.value,
                received=received,
                names=ledger,
                narration=" ".join(
                    x for x in (pay.mode.value.upper(), pay.reference or "", pay.note or "") if x
                ),
            )
        )
    heads_by_id = {
        c.id: c.name
        for c in db.execute(
            select(ExpenseCategory).where(ExpenseCategory.tenant_id == TENANT_ID)
        ).scalars()
    }
    for entry in db.execute(
        select(CashEntry).where(
            CashEntry.tenant_id == TENANT_ID,
            CashEntry.entry_date >= date_from,
            CashEntry.entry_date <= date_to,
        )
    ).scalars():
        out.append(
            rules.cash_entry_voucher(
                entry.kind,
                entry.number,
                entry.entry_date,
                entry.amount,
                in_cash=entry.mode is PaymentMode.CASH,
                head=heads_by_id.get(entry.category_id or 0, ""),
                reversal=entry.reverses_id is not None,
                narration=" ".join(
                    x
                    for x in (
                        entry.kind.value.replace("_", " "),
                        entry.paid_to or "",
                        entry.note or "",
                    )
                    if x
                ),
                names=ledger,
            )
        )
    out.extend(_party_journals(db, date_from, date_to, people, ledger))
    return sorted(out, key=lambda v: (v.on, _ORDER[v.kind], v.number))


def _document(
    kind: VoucherKind,
    number: str,
    on: date,
    party: str,
    narration: str,
    doc: SalesInvoice | CreditNote | DebitNote,
    ledger: dict[Purpose, str],
    *,
    outward: bool,
    party_debit: bool,
) -> rules.Voucher:
    return rules.tax_document(
        kind,
        number=number,
        on=on,
        party=party,
        narration=narration,
        grand=doc.grand_total,
        taxable=doc.taxable_value,
        cgst=doc.cgst,
        sgst=doc.sgst,
        igst=doc.igst,
        round_off=doc.round_off,
        names=ledger,
        outward=outward,
        party_debit=party_debit,
    )


def _party_journals(
    db: Session, date_from: date, date_to: date, people: dict[int, str], ledger: dict[Purpose, str]
) -> list[rules.Voucher]:
    """Rebates and freight sit on the party's account with no document of their own."""
    rows = db.execute(
        select(PartyLedger).where(
            PartyLedger.tenant_id == TENANT_ID,
            PartyLedger.ref_type.in_([PartyRef.REBATE, PartyRef.FREIGHT]),
            PartyLedger.entry_date >= date_from,
            PartyLedger.entry_date <= date_to,
        )
    ).scalars()
    grouped: dict[tuple[PartyRef, int | None], list[PartyLedger]] = defaultdict(list)
    for row in rows:
        grouped[(row.ref_type, row.ref_id)].append(row)
    out = []
    for (ref, _), parts in grouped.items():
        first = parts[0]
        net = sum((r.debit - r.credit for r in parts), ZERO)  # payable account: a debit is ours
        out.append(
            rules.journal(
                first.doc_no or f"{ref.value}-{first.ref_id}",
                first.entry_date,
                people[first.party_id],
                abs(net),
                Purpose.REBATE if ref is PartyRef.REBATE else Purpose.FREIGHT,
                names=ledger,
                party_debit=net > ZERO,
                narration=first.narration or "",
            )
        )
    return out


# ------------------------------------------------------------------------------ checks


def _movement(db: Session, account: LedgerAccount, date_from: date, date_to: date) -> Decimal:
    """How much more is owed on an account in the range, opening balances excluded."""
    rows = db.execute(
        select(PartyLedger).where(
            PartyLedger.tenant_id == TENANT_ID,
            PartyLedger.account == account,
            PartyLedger.ref_type != PartyRef.OPENING,
            PartyLedger.entry_date >= date_from,
            PartyLedger.entry_date <= date_to,
        )
    ).scalars()
    net = sum((r.debit - r.credit for r in rows), ZERO)
    return money(net if account is LedgerAccount.RECEIVABLE else -net)


def _check(code: str, label: str, vouchers: Decimal, report: Decimal) -> TallyCheckOut:
    return TallyCheckOut(
        code=code,
        label=label,
        vouchers=money(vouchers),
        report=money(report),
        ok=money(vouchers) == money(report),
    )


def checks(
    db: Session, vouchers: list[rules.Voucher], date_from: date, date_to: date
) -> tuple[list[TallyCheckOut], bool]:
    found: list[TallyCheckOut] = []
    got = rules.purpose_totals(vouchers)

    def total(purpose: Purpose) -> Decimal:
        return got.get(purpose, ZERO)

    found.append(
        _check(
            "receivable",
            "Customers owe (change in the dues report)",
            sum(
                (v.party_effect for v in vouchers if v.account is rules.PartyAccount.RECEIVABLE),
                ZERO,
            ),
            _movement(db, LedgerAccount.RECEIVABLE, date_from, date_to),
        )
    )
    found.append(
        _check(
            "payable",
            "We owe suppliers (change in the dues report)",
            sum(
                (v.party_effect for v in vouchers if v.account is rules.PartyAccount.PAYABLE), ZERO
            ),
            _movement(db, LedgerAccount.PAYABLE, date_from, date_to),
        )
    )
    months = rules.whole_months(date_from, date_to)
    if months is None:
        return found, False
    sales = {"taxable": ZERO, "igst": ZERO, "cgst": ZERO, "sgst": ZERO}
    itc = {"igst": ZERO, "cgst": ZERO, "sgst": ZERO}
    for period in months:
        one = gst_returns.gstr1(db, period).totals
        sales["taxable"] += one.taxable
        sales["igst"] += one.igst
        sales["cgst"] += one.cgst
        sales["sgst"] += one.sgst
        three = gst_returns.gstr3b(db, period)
        for head in itc:
            itc[head] += getattr(three.itc_books, head) - getattr(three.itc_reversed, head)
    found.append(
        _check(
            "gstr1_taxable",
            "Sales, taxable value (GSTR-1)",
            -total(Purpose.SALES),
            sales["taxable"],
        )
    )
    found.append(
        _check("gstr1_cgst", "CGST on sales (GSTR-1)", -total(Purpose.OUTPUT_CGST), sales["cgst"])
    )
    found.append(
        _check("gstr1_sgst", "SGST on sales (GSTR-1)", -total(Purpose.OUTPUT_SGST), sales["sgst"])
    )
    found.append(
        _check("gstr1_igst", "IGST on sales (GSTR-1)", -total(Purpose.OUTPUT_IGST), sales["igst"])
    )
    found.append(
        _check(
            "itc_cgst",
            "CGST input tax (GSTR-3B 4A less 4B)",
            total(Purpose.INPUT_CGST),
            itc["cgst"],
        )
    )
    found.append(
        _check(
            "itc_sgst",
            "SGST input tax (GSTR-3B 4A less 4B)",
            total(Purpose.INPUT_SGST),
            itc["sgst"],
        )
    )
    found.append(
        _check(
            "itc_igst",
            "IGST input tax (GSTR-3B 4A less 4B)",
            total(Purpose.INPUT_IGST),
            itc["igst"],
        )
    )
    return found, True


# ------------------------------------------------------------------------------ public


def _range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise BusinessRuleError(
            "The end date is before the start date", code="BAD_RANGE", field="date_to"
        )
    if (date_to - date_from).days >= MAX_DAYS:
        raise BusinessRuleError(
            "Export one financial year at a time at most", code="RANGE_TOO_LONG", field="date_to"
        )


def preview(db: Session, date_from: date, date_to: date) -> TallyPreviewOut:
    _range(date_from, date_to)
    vouchers = build_vouchers(db, date_from, date_to)
    found, gst_checked = checks(db, vouchers, date_from, date_to)
    kinds = rules.totals_by_kind(vouchers)
    return TallyPreviewOut(
        date_from=date_from,
        date_to=date_to,
        company=company(db),
        voucher_count=len(vouchers),
        kinds=[
            TallyKindOut(kind=kind.value, count=count, total=total)
            for kind, (count, total) in sorted(kinds.items(), key=lambda x: _ORDER[x[0]])
        ],
        checks=found,
        gst_checked=gst_checked,
        note=None
        if gst_checked
        else "The GST checks need whole calendar months, so only the dues are checked here.",
    )


def export_xml(db: Session, date_from: date, date_to: date, *, masters: bool, actor_id: int) -> str:
    """The Tally file. Refuses to export when a check fails: a file that disagrees with the
    books is worse than no file."""
    result = preview(db, date_from, date_to)
    failed = [c for c in result.checks if not c.ok]
    if failed:
        raise BusinessRuleError(
            f"The export does not agree with the books ({failed[0].label}). Run the integrity "
            "check and tell your accountant before exporting.",
            code="EXPORT_MISMATCH",
        )
    vouchers = build_vouchers(db, date_from, date_to)
    ledger = names(db)
    heads = _heads(db)
    # Masters come from the parties the vouchers use, so a transporter or a customer who is also
    # a supplier is always there, under the group their account belongs to.
    customers = _used_parties(vouchers, rules.PartyAccount.RECEIVABLE)
    suppliers = _used_parties(vouchers, rules.PartyAccount.PAYABLE)
    listed: Iterable[rules.Master] = (
        rules.masters_for(
            ledger,
            customers=customers,
            suppliers=[p for p in suppliers if p not in customers],
            expense_heads=heads,
        )
        if masters
        else []
    )
    audit.record_event(
        db,
        AuditAction.EXPORT,
        "tally",
        None,
        {"from": date_from, "to": date_to, "vouchers": len(vouchers), "masters": masters},
        user_id=actor_id,
    )
    db.commit()
    return rules.render_xml(company(db), vouchers, listed)


def _heads(db: Session) -> list[str]:
    return [
        c.name
        for c in db.execute(
            select(ExpenseCategory)
            .where(ExpenseCategory.tenant_id == TENANT_ID)
            .order_by(ExpenseCategory.name)
        ).scalars()
    ]


def _used_parties(vouchers: list[rules.Voucher], account: rules.PartyAccount) -> list[str]:
    return sorted({v.party for v in vouchers if v.party is not None and v.account is account})
