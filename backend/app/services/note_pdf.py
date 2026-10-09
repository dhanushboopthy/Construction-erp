"""A4 PDFs for credit and debit notes, drawn like the invoice (see invoice_pdf)."""

from decimal import Decimal

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.core.config import get_settings
from app.domain.gst import STATE_NAMES, SupplyKind
from app.domain.words import amount_in_words
from app.models.masters import Party
from app.models.purchasing import Purchase
from app.models.returns import CreditNote, DebitNote
from app.models.sales import SalesInvoice
from app.services.invoice_pdf import TEMPLATES, inr
from app.services.shop_settings import get_settings_row


def _plain(value: Decimal) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _render(db: Session, note: CreditNote | DebitNote, **extra: object) -> bytes:
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
        }
        for x in note.lines
    ]
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
        title="Debit note",
        total_label="Debited to supplier",
        against_label="Supplier bill",
        against_no=purchase.bill_no if purchase else "",
        party_label="Supplier",
        party_name=supplier.name if supplier else "",
        party_address=supplier.address if supplier else "",
        party_gstin=supplier.gstin if supplier else None,
    )
