"""A4 PDFs for credit and debit notes, drawn like the invoice (see invoice_pdf)."""

from datetime import date
from decimal import Decimal
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.core.config import get_settings
from app.domain import gst
from app.domain.gst import STATE_NAMES, SupplyKind
from app.domain.words import amount_in_words
from app.models.enums import BillSlot
from app.models.masters import Party
from app.models.purchasing import Purchase
from app.models.returns import CreditNote, DebitNote
from app.models.sales import SalesInvoice
from app.models.setup import ShopSettings
from app.services import bill_data, bill_render, invoice_pdf
from app.services.invoice_pdf import TEMPLATES, inr
from app.services.shop_settings import get_settings_row


def _plain(value: Decimal) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _on_design(
    loaded: bill_render.Loaded,
    note: CreditNote | DebitNote,
    settings: ShopSettings,
    lines: list[dict[str, Any]],
    *,
    slot: BillSlot,
    intra: bool,
    against_date: date | None,
    extra: dict[str, Any],
) -> bytes:
    """The note on the company's own design, from the same figures."""
    tax_total = note.cgst + note.sgst + note.igst
    state = gst.state_code_of(extra["party_gstin"]) if extra["party_gstin"] else ""
    party = {
        "name": extra["party_name"],
        "address": extra["party_address"],
        "gstin": extra["party_gstin"] or "Unregistered",
        "state_code": state,
        "state_name": STATE_NAMES.get(state, ""),
    }
    rows = gst.hsn_summary(
        [
            (x.hsn, gst.LineTax(x.taxable, x.gst_rate, cgst=x.cgst, sgst=x.sgst, igst=x.igst))
            for x in note.lines
        ]
    )
    context = {
        "seller": invoice_pdf.seller_view(settings),
        "buyer": party,
        "consignee": party,
        "lines": lines,
        "intra": intra,
        "hsn_rows": [
            {
                "hsn": r.hsn,
                "taxable": inr(r.taxable),
                "half_rate": f"{_plain(r.rate / 2)}%",
                "rate": f"{_plain(r.rate)}%",
                "cgst": inr(r.cgst),
                "sgst": inr(r.sgst),
                "igst": inr(r.igst),
                "tax": inr(r.tax),
            }
            for r in rows
        ],
        "hsn_total": {
            "taxable": inr(note.taxable_value),
            "cgst": inr(note.cgst),
            "sgst": inr(note.sgst),
            "igst": inr(note.igst),
            "tax": inr(tax_total),
        },
        "round_off_text": f"{'-' if note.round_off < 0 else ''}{inr(abs(note.round_off))}",
        "grand_total": inr(note.grand_total),
        "words": amount_in_words(note.grand_total),
        "tax_words": amount_in_words(tax_total) if tax_total else "NIL",
    }
    pos = getattr(note, "place_of_supply", None)
    fields = {
        "invoice.title": "Credit Note" if slot is BillSlot.CREDIT_NOTE else "Debit Note",
        "invoice.number": note.number,
        "invoice.date": note.note_date.strftime("%d-%m-%Y"),
        "invoice.placeOfSupply": f"{pos} {STATE_NAMES.get(pos, '')}".strip() if pos else "",
        "note.againstLabel": extra["against_label"],
        "note.against": extra["against_no"],
        "note.againstDate": against_date.strftime("%d-%m-%Y") if against_date else "",
        "note.reason": note.reason,
        "note.totalLabel": extra["total_label"],
    }
    data = bill_data.build(
        context,
        slot.value,
        extra=fields,
        has_logo=bill_render.LOGO in loaded.assets,
        has_secondary_logo=bill_render.SECONDARY_LOGO in loaded.assets,
        has_qr=False,
    )
    return bill_render.render(loaded, data)


def _render(
    db: Session,
    note: CreditNote | DebitNote,
    *,
    slot: BillSlot,
    against_date: date | None,
    **extra: Any,
) -> bytes:
    settings = get_settings_row(db)
    intra = note.supply_kind is SupplyKind.INTRA_STATE
    lines = [
        {
            "line_no": x.line_no,
            "description": x.description,
            "hsn": x.hsn,
            "qty_text": f"{_plain(x.base_qty)} {x.base_unit}",
            "taxable_text": inr(x.taxable),
            "gst_rate": _plain(x.gst_rate),
            "cgst_text": inr(x.cgst),
            "sgst_text": inr(x.sgst),
            "igst_text": inr(x.igst),
            "total_text": inr(x.line_total),
            # What a company's own design can print for the line.
            "qty": _plain(x.base_qty),
            "unit": x.base_unit,
            "amount": inr(x.taxable),
            "cgst_rate": f"{_plain(x.gst_rate / 2)}%",
            "sgst_rate": f"{_plain(x.gst_rate / 2)}%",
            "igst_rate": f"{_plain(x.gst_rate)}%",
            "cgst": inr(x.cgst),
            "sgst": inr(x.sgst),
            "igst": inr(x.igst),
            "tax": inr(x.cgst + x.sgst + x.igst),
            "total": inr(x.line_total),
            "gst_rate_text": f"{_plain(x.gst_rate)}%",
        }
        for x in note.lines
    ]
    loaded = bill_render.load(db, note.bill_template_id)
    if loaded is not None:
        design_lines = [{**x, "gst_rate": x["gst_rate_text"]} for x in lines]
        return _on_design(
            loaded,
            note,
            settings,
            design_lines,
            slot=slot,
            intra=intra,
            against_date=against_date,
            extra=extra,
        )
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    html = env.get_template("note_a4.html").render(
        note=note,
        seller={
            "legal_name": settings.legal_name,
            "trade_name": settings.trade_name,
            "gstin": settings.gstin,
            "address": settings.address,
            "state_code": settings.state_code,
            "state_name": STATE_NAMES.get(settings.state_code, ""),
        },
        lines=lines,
        intra=intra,
        words=amount_in_words(note.grand_total),
        totals={
            "taxable": inr(note.taxable_value),
            "cgst": inr(note.cgst),
            "sgst": inr(note.sgst),
            "igst": inr(note.igst),
            "round_off": inr(note.round_off),
            "grand_total": inr(note.grand_total),
        },
        test_mark=not get_settings().is_production,
        **extra,
    )
    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def credit_note_pdf(db: Session, note: CreditNote) -> bytes:
    invoice = db.get(SalesInvoice, note.invoice_id)
    return _render(
        db,
        note,
        slot=BillSlot.CREDIT_NOTE,
        against_date=invoice.invoice_date if invoice else None,
        title="Credit note",
        total_label="Credited to customer",
        against_label="Invoice",
        against_no=invoice.number if invoice else "",
        party_label="Customer",
        party_name=note.bill_to_name,
        party_address=note.bill_to_address,
        party_gstin=note.bill_to_gstin,
    )


def debit_note_pdf(db: Session, note: DebitNote) -> bytes:
    purchase = db.get(Purchase, note.purchase_id)
    supplier = db.get(Party, note.party_id)
    return _render(
        db,
        note,
        slot=BillSlot.DEBIT_NOTE,
        against_date=purchase.bill_date if purchase else None,
        title="Debit note",
        total_label="Debited to supplier",
        against_label="Supplier bill",
        against_no=purchase.bill_no if purchase else "",
        party_label="Supplier",
        party_name=supplier.name if supplier else "",
        party_address=supplier.address if supplier else "",
        party_gstin=supplier.gstin if supplier else None,
    )
