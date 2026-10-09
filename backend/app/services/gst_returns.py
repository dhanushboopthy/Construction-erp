"""GST return data for the accountant (Milestone 13): GSTR-1 tables, a GSTR-3B summary and
GSTR-2B matching. Everything is rebuilt from issued documents each time, so it always agrees with
the books. Layouts follow the portal's offline-tool JSON; confirm against the accountant's own
sample file (docs/GAP_ANALYSIS.md) before the first real filing."""

import csv
import hashlib
import io
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, BusinessRuleError
from app.core.tenancy import TENANT_ID
from app.domain import gst as gst_rules
from app.domain import gstr
from app.domain.gst import SupplyKind
from app.domain.money import ZERO, money
from app.models.documents import Gstr2bImport
from app.models.masters import Item, Party
from app.models.purchasing import Purchase
from app.models.returns import CreditNote, DebitNote
from app.models.sales import SalesInvoice
from app.schemas.gst import (
    B2bInvoice,
    B2csRow,
    DocRow,
    Gstr1,
    Gstr2bResult,
    Gstr3b,
    Heads,
    HsnRow,
    MatchRow,
    NoteRow,
    RateRow,
    Totals,
)
from app.services.shop_settings import get_settings_row

TOLERANCE = Decimal("1")  # rupees; suppliers round their tax lines differently


def _bounds(period: str) -> tuple[date, date]:
    try:
        return gstr.period_bounds(*gstr.parse_period(period))
    except ValueError as exc:
        raise BusinessRuleError(str(exc).capitalize(), code="BAD_PERIOD", field="period") from exc


def _rates(lines: list[Any]) -> list[RateRow]:
    """Group lines of one document by GST rate, as the portal wants them."""
    grouped: dict[Decimal, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO, ZERO, ZERO])
    for x in lines:
        g = grouped[x.gst_rate]
        g[0] += x.taxable
        g[1] += x.igst
        g[2] += x.cgst
        g[3] += x.sgst
    return [
        RateRow(
            rate=rate, taxable=money(v[0]), igst=money(v[1]), cgst=money(v[2]), sgst=money(v[3])
        )
        for rate, v in sorted(grouped.items())
    ]


def _sum(rows: list[RateRow]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return (
        money(sum((r.taxable for r in rows), ZERO)),
        money(sum((r.igst for r in rows), ZERO)),
        money(sum((r.cgst for r in rows), ZERO)),
        money(sum((r.sgst for r in rows), ZERO)),
    )


def _invoice_row(inv: SalesInvoice, with_ctin: bool) -> B2bInvoice:
    rates = _rates(list(inv.lines))
    taxable, igst, cgst, sgst = _sum(rates)
    return B2bInvoice(
        ctin=inv.bill_to_gstin if with_ctin else None,
        party_name=inv.bill_to_name,
        number=inv.number,
        invoice_date=inv.invoice_date,
        value=inv.grand_total,
        pos=inv.place_of_supply,
        taxable=taxable,
        igst=igst,
        cgst=cgst,
        sgst=sgst,
        rates=rates,
    )


def _note_row(note: CreditNote, invoice: SalesInvoice) -> NoteRow:
    rates = _rates(list(note.lines))
    taxable, igst, cgst, sgst = _sum(rates)
    return NoteRow(
        ctin=note.bill_to_gstin,
        party_name=note.bill_to_name,
        number=note.number,
        note_date=note.note_date,
        invoice_number=invoice.number,
        invoice_date=invoice.invoice_date,
        value=note.grand_total,
        pos=note.place_of_supply,
        taxable=taxable,
        igst=igst,
        cgst=cgst,
        sgst=sgst,
        rates=rates,
    )


def gstr1(db: Session, period: str) -> Gstr1:
    first, last = _bounds(period)
    settings = get_settings_row(db)
    invoices = list(
        db.execute(
            select(SalesInvoice)
            .where(
                SalesInvoice.tenant_id == TENANT_ID,
                SalesInvoice.invoice_date >= first,
                SalesInvoice.invoice_date <= last,
            )
            .order_by(SalesInvoice.invoice_date, SalesInvoice.id)
        ).scalars()
    )
    notes = list(
        db.execute(
            select(CreditNote)
            .where(
                CreditNote.tenant_id == TENANT_ID,
                CreditNote.note_date >= first,
                CreditNote.note_date <= last,
            )
            .order_by(CreditNote.note_date, CreditNote.id)
        ).scalars()
    )
    b2b: list[B2bInvoice] = []
    b2cl: list[B2bInvoice] = []
    b2cs: dict[tuple[str, str, Decimal], list[Decimal]] = defaultdict(lambda: [ZERO] * 4)
    cdnr: list[NoteRow] = []
    cdnur: list[NoteRow] = []

    def is_large(kind: SupplyKind, gstin: str | None, value: Decimal) -> bool:
        return gstr.is_b2cl(bool(gstin), kind is SupplyKind.INTER_STATE, value)

    for inv in invoices:
        if inv.bill_to_gstin:
            b2b.append(_invoice_row(inv, True))
        elif is_large(inv.supply_kind, inv.bill_to_gstin, inv.grand_total):
            b2cl.append(_invoice_row(inv, False))
        else:
            _add_b2cs(b2cs, inv.supply_kind, inv.place_of_supply, list(inv.lines), 1)
    for note in notes:
        invoice = db.get(SalesInvoice, note.invoice_id)
        if invoice is None:
            continue
        row = _note_row(note, invoice)
        if note.bill_to_gstin:
            cdnr.append(row)
        elif is_large(invoice.supply_kind, invoice.bill_to_gstin, invoice.grand_total):
            cdnur.append(row)
        else:  # a return on a small B2C bill reduces that month's B2CS figures
            _add_b2cs(b2cs, note.supply_kind, note.place_of_supply, list(note.lines), -1)
    b2cs_rows = [
        B2csRow(
            supply="INTRA" if supply == "intra_state" else "INTER",
            pos=pos,
            rate=rate,
            taxable=money(v[0]),
            igst=money(v[1]),
            cgst=money(v[2]),
            sgst=money(v[3]),
        )
        for (supply, pos, rate), v in sorted(b2cs.items())
    ]

    totals = [ZERO] * 4
    for inv in invoices:
        totals[0] += inv.taxable_value
        totals[1] += inv.igst
        totals[2] += inv.cgst
        totals[3] += inv.sgst
    for note in notes:
        totals[0] -= note.taxable_value
        totals[1] -= note.igst
        totals[2] -= note.cgst
        totals[3] -= note.sgst

    docs = [
        DocRow(
            nature="Invoices for outward supply",
            series=s.series,
            first=s.first,
            last=s.last,
            count=s.count,
            gaps=s.gaps,
        )
        for s in gstr.document_series([i.number for i in invoices])
    ] + [
        DocRow(
            nature="Credit note",
            series=s.series,
            first=s.first,
            last=s.last,
            count=s.count,
            gaps=s.gaps,
        )
        for s in gstr.document_series([n.number for n in notes])
    ]
    return Gstr1(
        period=period,
        gstin=settings.gstin,
        b2b=b2b,
        b2cl=b2cl,
        b2cs=b2cs_rows,
        cdnr=cdnr,
        cdnur=cdnur,
        hsn=_hsn(db, invoices, notes),
        docs=docs,
        totals=Totals(
            invoices=len(invoices),
            notes=len(notes),
            taxable=money(totals[0]),
            igst=money(totals[1]),
            cgst=money(totals[2]),
            sgst=money(totals[3]),
        ),
    )


def _add_b2cs(
    table: dict[tuple[str, str, Decimal], list[Decimal]],
    kind: SupplyKind,
    pos: str,
    lines: list[Any],
    sign: int,
) -> None:
    for x in lines:
        row = table[(kind.value, pos, x.gst_rate)]
        row[0] += sign * x.taxable
        row[1] += sign * x.igst
        row[2] += sign * x.cgst
        row[3] += sign * x.sgst


def _hsn(db: Session, invoices: list[SalesInvoice], notes: list[CreditNote]) -> list[HsnRow]:
    units = {i.id: i.base_unit for i in db.execute(select(Item)).scalars()}
    acc: dict[tuple[str, Decimal], dict[str, Any]] = {}

    def add(line: Any, sign: int, unit: str) -> None:
        row = acc.setdefault(
            (line.hsn, line.gst_rate),
            {
                "desc": line.description,
                "unit": unit,
                "q": ZERO,
                "t": ZERO,
                "i": ZERO,
                "c": ZERO,
                "s": ZERO,
            },
        )
        row["q"] += sign * line.base_qty
        row["t"] += sign * line.taxable
        row["i"] += sign * line.igst
        row["c"] += sign * line.cgst
        row["s"] += sign * line.sgst

    for inv in invoices:
        for sold in inv.lines:
            add(sold, 1, units.get(sold.item_id, sold.base_unit))
    for note in notes:
        for back in note.lines:
            add(back, -1, units.get(back.item_id, back.base_unit))
    out = []
    for (hsn, rate), v in sorted(acc.items()):
        taxable, tax = money(v["t"]), money(v["i"] + v["c"] + v["s"])
        out.append(
            HsnRow(
                hsn=hsn,
                description=v["desc"],
                uqc=gstr.uqc(v["unit"]),
                quantity=v["q"],
                rate=rate,
                value=taxable + tax,
                taxable=taxable,
                igst=money(v["i"]),
                cgst=money(v["c"]),
                sgst=money(v["s"]),
            )
        )
    return out


# ---------------------------------------------------------------------------- portal JSON


def _dmy(on: date) -> str:
    return on.strftime("%d-%m-%Y")


def _itms(rates: list[RateRow]) -> list[dict[str, Any]]:
    return [
        {
            "num": i,
            "itm_det": {
                "txval": float(r.taxable),
                "rt": float(r.rate),
                "iamt": float(r.igst),
                "camt": float(r.cgst),
                "samt": float(r.sgst),
                "csamt": 0,
            },
        }
        for i, r in enumerate(rates, start=1)
    ]


def gstr1_portal_json(data: Gstr1) -> dict[str, Any]:
    """The offline-tool JSON for GSTR-1. Amounts are numbers there, so floats appear only here,
    at the very edge, and are never read back into the system."""
    year, month = gstr.parse_period(data.period)

    def invoice(i: B2bInvoice) -> dict[str, Any]:
        return {
            "inum": i.number,
            "idt": _dmy(i.invoice_date),
            "val": float(i.value),
            "pos": i.pos,
            "rchrg": "N",
            "inv_typ": "R",
            "itms": _itms(i.rates),
        }

    by_ctin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i in data.b2b:
        by_ctin[i.ctin or ""].append(invoice(i))
    by_pos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i in data.b2cl:
        by_pos[i.pos].append(invoice(i))
    cdn_by_ctin: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def note(n: NoteRow) -> dict[str, Any]:
        return {
            "ntty": "C",
            "nt_num": n.number,
            "nt_dt": _dmy(n.note_date),
            "inum": n.invoice_number,
            "idt": _dmy(n.invoice_date),
            "val": float(n.value),
            "pos": n.pos,
            "rchrg": "N",
            "inv_typ": "R",
            "itms": _itms(n.rates),
        }

    for n in data.cdnr:
        cdn_by_ctin[n.ctin or ""].append(note(n))
    docs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for d in data.docs:
        number = 1 if d.nature.startswith("Invoices") else 5
        docs[number].append(
            {
                "num": len(docs[number]) + 1,
                "from": d.first,
                "to": d.last,
                "totnum": d.count + len(d.gaps),
                "cancel": len(d.gaps),
                "net_issue": d.count,
            }
        )
    return {
        "gstin": data.gstin or "",
        "fp": gstr.filing_period(year, month),
        "gt": 0,
        "cur_gt": 0,
        "b2b": [{"ctin": ctin, "inv": invs} for ctin, invs in by_ctin.items()],
        "b2cl": [{"pos": pos, "inv": invs} for pos, invs in by_pos.items()],
        "b2cs": [
            {
                "sply_ty": r.supply,
                "pos": r.pos,
                "typ": "OE",
                "rt": float(r.rate),
                "txval": float(r.taxable),
                "iamt": float(r.igst),
                "camt": float(r.cgst),
                "samt": float(r.sgst),
                "csamt": 0,
            }
            for r in data.b2cs
        ],
        "cdnr": [{"ctin": ctin, "nt": notes} for ctin, notes in cdn_by_ctin.items()],
        "cdnur": [dict(note(n), typ="B2CL") for n in data.cdnur],
        "hsn": {
            "data": [
                {
                    "num": i,
                    "hsn_sc": h.hsn,
                    "desc": h.description,
                    "uqc": h.uqc,
                    "qty": float(h.quantity),
                    "val": float(h.value),
                    "txval": float(h.taxable),
                    "iamt": float(h.igst),
                    "camt": float(h.cgst),
                    "samt": float(h.sgst),
                    "csamt": 0,
                    "rt": float(h.rate),
                }
                for i, h in enumerate(data.hsn, start=1)
            ]
        },
        "doc_issue": {
            "doc_det": [{"doc_num": n, "docs": rows} for n, rows in sorted(docs.items())]
        },
    }


def gstr1_workbook(data: Gstr1) -> bytes:
    """One sheet per table, for the accountant to open without any tool."""
    book = Workbook()
    summary = book.active
    assert summary is not None  # noqa: S101 - a new workbook always has an active sheet
    summary.title = "Summary"
    summary.append(["GSTR-1", data.period, data.gstin or "(shop GSTIN not set)"])
    summary.append(["Invoices", data.totals.invoices, "Credit notes", data.totals.notes])
    summary.append(["Taxable (net)", float(data.totals.taxable)])
    summary.append(
        [
            "IGST",
            float(data.totals.igst),
            "CGST",
            float(data.totals.cgst),
            "SGST",
            float(data.totals.sgst),
        ]
    )

    def sheet(name: str, header: list[str], rows: list[list[Any]]) -> None:
        ws = book.create_sheet(name)
        ws.append(header)
        for r in rows:
            ws.append(r)

    inv_header = [
        "GSTIN",
        "Party",
        "Invoice",
        "Date",
        "Value",
        "POS",
        "Taxable",
        "IGST",
        "CGST",
        "SGST",
    ]

    def inv_rows(items: list[B2bInvoice]) -> list[list[Any]]:
        return [
            [
                i.ctin or "",
                i.party_name,
                i.number,
                i.invoice_date.isoformat(),
                float(i.value),
                i.pos,
                float(i.taxable),
                float(i.igst),
                float(i.cgst),
                float(i.sgst),
            ]
            for i in items
        ]

    def note_rows(items: list[NoteRow]) -> list[list[Any]]:
        return [
            [
                n.ctin or "",
                n.party_name,
                n.number,
                n.note_date.isoformat(),
                n.invoice_number,
                n.invoice_date.isoformat(),
                float(n.value),
                n.pos,
                float(n.taxable),
                float(n.igst),
                float(n.cgst),
                float(n.sgst),
            ]
            for n in items
        ]

    note_header = [
        "GSTIN",
        "Party",
        "Note",
        "Date",
        "Invoice",
        "Invoice date",
        "Value",
        "POS",
        "Taxable",
        "IGST",
        "CGST",
        "SGST",
    ]
    sheet("B2B", inv_header, inv_rows(data.b2b))
    sheet("B2CL", inv_header, inv_rows(data.b2cl))
    sheet(
        "B2CS",
        ["Supply", "POS", "Rate", "Taxable", "IGST", "CGST", "SGST"],
        [
            [
                r.supply,
                r.pos,
                float(r.rate),
                float(r.taxable),
                float(r.igst),
                float(r.cgst),
                float(r.sgst),
            ]
            for r in data.b2cs
        ],
    )
    sheet("CDNR", note_header, note_rows(data.cdnr))
    sheet("CDNUR", note_header, note_rows(data.cdnur))
    sheet(
        "HSN",
        [
            "HSN",
            "Description",
            "UQC",
            "Quantity",
            "Rate",
            "Value",
            "Taxable",
            "IGST",
            "CGST",
            "SGST",
        ],
        [
            [
                h.hsn,
                h.description,
                h.uqc,
                float(h.quantity),
                float(h.rate),
                float(h.value),
                float(h.taxable),
                float(h.igst),
                float(h.cgst),
                float(h.sgst),
            ]
            for h in data.hsn
        ],
    )
    sheet(
        "Documents",
        ["Nature", "Series", "From", "To", "Issued", "Missing numbers"],
        [
            [d.nature, d.series, d.first, d.last, d.count, ", ".join(map(str, d.gaps))]
            for d in data.docs
        ],
    )
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------- GSTR-3B


def _purchase_figures(db: Session, first: date, last: date) -> list[tuple[Purchase, Party, Heads]]:
    settings = get_settings_row(db)
    out = []
    for purchase in db.execute(
        select(Purchase).where(
            Purchase.tenant_id == TENANT_ID,
            Purchase.bill_date >= first,
            Purchase.bill_date <= last,
        )
    ).scalars():
        supplier = db.get(Party, purchase.supplier_id)
        if supplier is None:
            continue
        kind = gst_rules.supply_kind(supplier.state_code, settings.state_code)
        taxable = igst = cgst = sgst = ZERO
        for line in purchase.lines:
            tax = gst_rules.line_tax(line.goods_value, line.gst_rate, kind)
            taxable += tax.taxable
            igst += tax.igst
            cgst += tax.cgst
            sgst += tax.sgst
        out.append((purchase, supplier, Heads(taxable=taxable, igst=igst, cgst=cgst, sgst=sgst)))
    return out


def _add_heads(a: Heads, b: Heads) -> Heads:
    return Heads(
        taxable=money(a.taxable + b.taxable),
        igst=money(a.igst + b.igst),
        cgst=money(a.cgst + b.cgst),
        sgst=money(a.sgst + b.sgst),
    )


def _zero() -> Heads:
    return Heads(taxable=ZERO, igst=ZERO, cgst=ZERO, sgst=ZERO)


def gstr3b(db: Session, period: str) -> Gstr3b:
    first, last = _bounds(period)
    settings = get_settings_row(db)
    nil = ZERO
    taxed = _zero()
    invoices = db.execute(
        select(SalesInvoice).where(
            SalesInvoice.tenant_id == TENANT_ID,
            SalesInvoice.invoice_date >= first,
            SalesInvoice.invoice_date <= last,
        )
    ).scalars()
    notes = db.execute(
        select(CreditNote).where(
            CreditNote.tenant_id == TENANT_ID,
            CreditNote.note_date >= first,
            CreditNote.note_date <= last,
        )
    ).scalars()
    groups: list[tuple[int, Iterable[Any]]] = [(1, invoices), (-1, notes)]
    for sign, docs in groups:
        for doc in docs:
            for line in doc.lines:
                if line.gst_rate == ZERO:
                    nil += sign * line.taxable
                else:
                    taxed = _add_heads(
                        taxed,
                        Heads(
                            taxable=sign * line.taxable,
                            igst=sign * line.igst,
                            cgst=sign * line.cgst,
                            sgst=sign * line.sgst,
                        ),
                    )
    itc = _zero()
    for _, _, heads in _purchase_figures(db, first, last):
        itc = _add_heads(itc, heads)
    reversed_ = _zero()
    for note in db.execute(
        select(DebitNote).where(
            DebitNote.tenant_id == TENANT_ID,
            DebitNote.note_date >= first,
            DebitNote.note_date <= last,
        )
    ).scalars():
        reversed_ = _add_heads(
            reversed_,
            Heads(taxable=note.taxable_value, igst=note.igst, cgst=note.cgst, sgst=note.sgst),
        )
    latest = _latest_import(db, period)
    in_2b: Heads | None = None
    if latest is not None:
        in_2b = _zero()
        for row in latest.rows:
            in_2b = _add_heads(
                in_2b,
                Heads(
                    taxable=Decimal(row["taxable"]),
                    igst=Decimal(row["igst"]),
                    cgst=Decimal(row["cgst"]),
                    sgst=Decimal(row["sgst"]),
                ),
            )
    net = Heads(
        taxable=taxed.taxable,
        igst=money(taxed.igst - (itc.igst - reversed_.igst)),
        cgst=money(taxed.cgst - (itc.cgst - reversed_.cgst)),
        sgst=money(taxed.sgst - (itc.sgst - reversed_.sgst)),
    )
    return Gstr3b(
        period=period,
        gstin=settings.gstin,
        outward_taxable=taxed,
        outward_nil=money(nil),
        itc_books=itc,
        itc_reversed=reversed_,
        itc_in_2b=in_2b,
        net_payable=net,
    )


# ---------------------------------------------------------------------------- GSTR-2B


def _latest_import(db: Session, period: str) -> Gstr2bImport | None:
    return db.execute(
        select(Gstr2bImport)
        .where(Gstr2bImport.tenant_id == TENANT_ID, Gstr2bImport.period == period)
        .order_by(Gstr2bImport.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else 0))
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc


def parse_2b(file_name: str, data: bytes) -> list[dict[str, str]]:
    """Read a GSTR-2B download: the portal's JSON, or a simple CSV with the columns
    gstin, supplier, invoice_no, invoice_date, taxable, igst, cgst, sgst."""
    rows: list[dict[str, str]] = []
    try:
        if data.lstrip()[:1] in (b"{", b"["):
            doc = json.loads(data.decode("utf-8-sig"))
            body = doc.get("data", doc) if isinstance(doc, dict) else {}
            b2b = (body.get("docdata", body) or {}).get("b2b", [])
            for supplier in b2b:
                for inv in supplier.get("inv", []):
                    items = inv.get("items") or inv.get("itms") or []
                    taxable = (
                        sum((_dec(i.get("txval")) for i in items), ZERO)
                        if items
                        else _dec(inv.get("txval"))
                    )
                    heads = {
                        h: sum((_dec(i.get(h)) for i in items), ZERO) if items else _dec(inv.get(h))
                        for h in ("igst", "cgst", "sgst")
                    }
                    rows.append(
                        {
                            "gstin": str(supplier.get("ctin", "")).upper(),
                            "supplier": str(supplier.get("trdnm", "")),
                            "number": str(inv.get("inum", "")),
                            "date": str(inv.get("dt") or inv.get("idt") or ""),
                            "taxable": str(taxable),
                            "igst": str(heads["igst"]),
                            "cgst": str(heads["cgst"]),
                            "sgst": str(heads["sgst"]),
                        }
                    )
        else:
            for record in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
                rec = {k.strip().lower(): (v or "").strip() for k, v in record.items() if k}
                rows.append(
                    {
                        "gstin": rec["gstin"].upper(),
                        "supplier": rec.get("supplier", ""),
                        "number": rec["invoice_no"],
                        "date": rec.get("invoice_date", ""),
                        "taxable": str(_dec(rec["taxable"])),
                        "igst": str(_dec(rec.get("igst"))),
                        "cgst": str(_dec(rec.get("cgst"))),
                        "sgst": str(_dec(rec.get("sgst"))),
                    }
                )
    except (ValueError, KeyError, AttributeError, TypeError, UnicodeDecodeError) as exc:
        raise AppError(
            "This file is not a GSTR-2B download or the simple CSV (gstin, supplier, invoice_no, "
            "invoice_date, taxable, igst, cgst, sgst).",
            code="GSTR2B_UNREADABLE",
        ) from exc
    if not rows:
        raise AppError("The file has no supplier invoices in it", code="GSTR2B_EMPTY")
    return rows


def import_2b(
    db: Session, period: str, file_name: str, data: bytes, *, actor_id: int
) -> Gstr2bImport:
    _bounds(period)
    rows = parse_2b(file_name, data)
    row = Gstr2bImport(
        tenant_id=TENANT_ID,
        period=period,
        file_name=file_name[:150],
        sha256=hashlib.sha256(data).hexdigest(),
        row_count=len(rows),
        rows=rows,
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    return row


def match_2b(db: Session, period: str) -> Gstr2bResult:
    first, last = _bounds(period)
    latest = _latest_import(db, period)
    # Books: bills from suppliers with a GSTIN, from two months before the period to its end,
    # because a supplier may report a bill late.
    start = date(first.year - (first.month <= 2), (first.month - 3) % 12 + 1, 1)
    books: list[gstr.BillFigures] = []
    meta: dict[tuple[str, str], tuple[str, date]] = {}
    for purchase, supplier, heads in _purchase_figures(db, start, last):
        if not supplier.gstin:
            continue
        bill = gstr.BillFigures(
            supplier.gstin.upper(),
            purchase.bill_no,
            heads.taxable,
            heads.igst,
            heads.cgst,
            heads.sgst,
        )
        books.append(bill)
        meta[(bill.gstin, gstr.normalize_doc_no(bill.number))] = (supplier.name, purchase.bill_date)
    portal = (
        [
            gstr.BillFigures(
                r["gstin"],
                r["number"],
                money(Decimal(r["taxable"])),
                money(Decimal(r["igst"])),
                money(Decimal(r["cgst"])),
                money(Decimal(r["sgst"])),
            )
            for r in latest.rows
        ]
        if latest
        else []
    )
    names = {
        (r["gstin"], gstr.normalize_doc_no(r["number"])): r.get("supplier") or ""
        for r in (latest.rows if latest else [])
    }
    rows = []
    for m in gstr.reconcile(books, portal, TOLERANCE):
        k = (m.gstin.upper(), gstr.normalize_doc_no(m.number))
        name, on = meta.get(k, (names.get(k) or None, None))
        rows.append(
            MatchRow(
                status=m.status,
                gstin=m.gstin,
                supplier=name,
                number=m.number,
                books_date=on if m.books else None,
                books_taxable=m.books.taxable if m.books else None,
                books_tax=m.books.tax if m.books else None,
                portal_taxable=m.portal.taxable if m.portal else None,
                portal_tax=m.portal.tax if m.portal else None,
                difference_taxable=m.difference_taxable,
                difference_tax=m.difference_tax,
            )
        )
    order = {"mismatch": 0, "missing_in_2b": 1, "missing_in_books": 2, "matched": 3}
    rows.sort(key=lambda r: (order[r.status], r.gstin, r.number))
    counts: dict[str, int] = dict.fromkeys(order, 0)
    for r in rows:
        counts[r.status] += 1
    return Gstr2bResult(
        period=period,
        file_name=latest.file_name if latest else None,
        imported_rows=latest.row_count if latest else 0,
        counts=counts,
        rows=rows,
    )
