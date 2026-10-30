"""A4 tax invoice as a PDF. The renderer sits behind an interface so a thermal-printer layout
can be added later without touching the invoice code (ROADMAP, printing)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import segno
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.core.config import get_settings
from app.core.tenancy import current_tenant_id
from app.domain import gst
from app.domain.gst import STATE_NAMES, SupplyKind
from app.domain.money import money
from app.domain.words import amount_in_words
from app.models.compliance import EInvoice
from app.models.enums import QuoteKind
from app.models.masters import Party
from app.models.sales import SalesInvoice, SalesLine, SalesQuote, SalesQuoteLine
from app.services import lots as lot_service
from app.services.shop_settings import get_settings_row

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
STATES = STATE_NAMES


def inr(value: Decimal | str) -> str:
    """12345678.5 -> '1,23,45,678.50' (lakh and crore grouping)."""
    text = f"{money(Decimal(value)):f}"
    negative = text.startswith("-")
    whole, fraction = text.lstrip("-").split(".")
    head, tail = whole[:-3], whole[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join([*groups, tail])
    return f"{'-' if negative else ''}{grouped}.{fraction}"


def _plain(value: Decimal) -> str:
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class IrnPrint:
    """What an e-invoice adds to the printed bill: the IRN, acknowledgement and QR (G12)."""

    irn: str
    ack_no: str
    ack_date: str
    qr_uri: str


def irn_print(row: EInvoice) -> IrnPrint:
    return IrnPrint(
        irn=row.irn,
        ack_no=row.ack_no,
        ack_date=row.ack_date.strftime("%d-%m-%Y"),
        qr_uri=segno.make(row.signed_qr, error="m").svg_data_uri(scale=3, border=1),
    )


class InvoiceRenderer(Protocol):
    def render(
        self,
        db: Session,
        invoice: SalesInvoice,
        *,
        copy_label: str,
        eway_no: str | None,
        irn: IrnPrint | None = None,
    ) -> bytes: ...


@dataclass
class A4HtmlRenderer:
    """HTML template to PDF with WeasyPrint."""

    template: str = "invoice_a4.html"

    def render(
        self,
        db: Session,
        invoice: SalesInvoice,
        *,
        copy_label: str,
        eway_no: str | None = None,
        irn: IrnPrint | None = None,
    ) -> bytes:
        lots = lot_service.lots_for_lines(db, [x.id for x in invoice.lines])
        batches = {
            line_id: ", ".join(dict.fromkeys(x.batch_no for x in taken if x.batch_no))
            for line_id, taken in lots.items()
        }
        quote = db.scalar(
            select(SalesQuote).where(
                SalesQuote.tenant_id == current_tenant_id(db),
                SalesQuote.invoice_id == invoice.id,
            )
        )
        header = {
            "number": invoice.number,
            "date": _day(invoice.invoice_date),
            "eway_no": eway_no,
            "payment": _payment_terms(invoice),
            "reference": f"{quote.number} dt. {_day(quote.quote_date)}" if quote else None,
            "vehicle": invoice.vehicle_no,
            "destination": invoice.ship_to_name or "Collected from the shop",
            "terms_label": "Terms of Delivery",
            "terms": "Delivered to the site" if invoice.ship_to_name else "Ex-shop",
        }
        previous = invoice.pending_balance_at_billing
        return _render(
            db,
            self.template,
            invoice,
            invoice.lines,
            doc=TAX_INVOICE,
            header=header,
            batches=batches,
            copy_label=copy_label,
            irn=irn,
            previous_balance=inr(previous) if previous else None,
        )


DEFAULT_RENDERER: InvoiceRenderer = A4HtmlRenderer()

TAX_INVOICE = {
    "title": "Tax Invoice",
    "number_label": "Invoice No.",
    "declaration": "We declare that this invoice shows the actual price of the goods described "
    "and that all particulars are true and correct.",
    "generated": "This is a Computer Generated Invoice",
}
QUOTE_DOCS = {
    QuoteKind.QUOTATION: {
        "title": "Estimate/Quotation",
        "number_label": "Quotation No.",
        "declaration": "This is a quotation, not a tax invoice. Prices are as on its date; "
        "the tax invoice is issued when the goods are billed.",
        "generated": "This is a Computer Generated Quotation",
    },
    QuoteKind.PROFORMA: {
        "title": "Proforma Invoice",
        "number_label": "Proforma No.",
        "declaration": "This is a proforma invoice, not a tax invoice. The GST shown is charged "
        "on the tax invoice issued when the goods are billed.",
        "generated": "This is a Computer Generated Proforma Invoice",
    },
}


def render_quote(db: Session, quote: SalesQuote) -> bytes:
    """A quotation or proforma invoice on the bill's A4 layout, plainly titled as not a tax
    invoice (ADR 0005)."""
    header = {
        "number": quote.number,
        "date": _day(quote.quote_date),
        "destination": quote.ship_to_name,
        "terms_label": "Valid Until",
        "terms": _day(quote.valid_until) if quote.valid_until else None,
    }
    return _render(
        db, "invoice_a4.html", quote, quote.lines, doc=QUOTE_DOCS[quote.kind], header=header
    )


def _day(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def _payment_terms(invoice: SalesInvoice) -> str:
    paid, total = invoice.paid_at_billing, invoice.grand_total
    due_by = (
        f" by {_day(invoice.due_date)}"
        if invoice.due_date and invoice.due_date > invoice.invoice_date
        else ""
    )
    if paid >= total:
        return "Paid at billing"
    if paid > 0:
        return f"₹ {inr(paid)} paid, ₹ {inr(total - paid)} due{due_by}"
    return f"Credit, due{due_by}" if due_by else "Payable on billing"


def _party(
    name: str, address: str | None, gstin: str | None, state: str, *, no_gstin: str
) -> dict[str, str]:
    return {
        "name": name,
        "address": address or "",
        "gstin": gstin or no_gstin,
        "state_code": state,
        "state_name": STATES.get(state, ""),
    }


def _render(
    db: Session,
    template: str,
    figures: SalesInvoice | SalesQuote,
    source_lines: Sequence[SalesLine] | Sequence[SalesQuoteLine],
    *,
    doc: dict[str, str],
    header: dict[str, str | None],
    batches: dict[int, str] | None = None,
    copy_label: str | None = None,
    irn: IrnPrint | None = None,
    previous_balance: str | None = None,
) -> bytes:
    """`figures` is the bill or quotation (parties, totals, supply kind); `header` holds the
    boxes of the top-right grid, already as text."""
    settings = get_settings_row(db)
    intra = figures.supply_kind is SupplyKind.INTRA_STATE
    party = db.get(Party, figures.party_id)
    buyer_state = (
        gst.state_code_of(figures.bill_to_gstin)
        if figures.bill_to_gstin
        else (party.state_code if party else figures.place_of_supply)
    )
    buyer = _party(
        figures.bill_to_name,
        figures.bill_to_address,
        figures.bill_to_gstin,
        buyer_state,
        no_gstin="Unregistered (B2C)",
    )
    consignee = (
        _party(
            figures.ship_to_name,
            figures.ship_to_address,
            getattr(figures, "ship_to_gstin", None),
            figures.place_of_supply,
            no_gstin="URP",  # G13
        )
        if figures.ship_to_name
        else buyer
    )

    lines = []
    for line in source_lines:
        factor = line.base_qty / line.quantity
        stock_after = getattr(line, "stock_after", None)
        lines.append(
            {
                "line_no": line.line_no,
                "description": line.description,
                "hsn": line.hsn,
                "base_unit": line.base_unit,
                "stock_after": _plain(stock_after) if stock_after is not None else None,
                "batch": (batches or {}).get(line.id) or None,
                "qty": _plain(line.quantity),
                "unit": line.unit,
                "rate": inr(line.rate * factor),
                "discount": inr(line.discount) if line.discount else "",
                "amount": inr(line.taxable),
            }
        )
    units = {line.unit for line in source_lines}
    total_qty = (
        f"{_plain(sum((x.quantity for x in source_lines), Decimal(0)))} {units.pop()}"
        if len(units) == 1
        else ""
    )
    taxes = [
        (label, amount)
        for label, amount in (
            ("OUTPUT CGST", figures.cgst),
            ("OUTPUT SGST", figures.sgst),
            ("OUTPUT IGST", figures.igst),
        )
        if amount
    ]
    summary = gst.hsn_summary(
        [
            (x.hsn, gst.LineTax(x.taxable, x.gst_rate, cgst=x.cgst, sgst=x.sgst, igst=x.igst))
            for x in source_lines
        ]
    )
    hsn_rows = [
        {
            "hsn": row.hsn,
            "taxable": inr(row.taxable),
            "half_rate": f"{_plain(row.rate / 2)}%",
            "rate": f"{_plain(row.rate)}%",
            "cgst": inr(row.cgst),
            "sgst": inr(row.sgst),
            "igst": inr(row.igst),
            "tax": inr(row.tax),
        }
        for row in summary
    ]
    tax_total = figures.cgst + figures.sgst + figures.igst
    seller_name = settings.trade_name or settings.legal_name

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    html = env.get_template(template).render(
        doc=doc,
        head=header,
        seller={
            "name": seller_name,
            "legal_name": settings.legal_name if settings.trade_name else None,
            "gstin": settings.gstin,
            "pan": gst.pan_of(settings.gstin),
            "address": settings.address,
            "phone": settings.phone,
            "email": settings.email,
            "state_code": settings.state_code,
            "state_name": STATES.get(settings.state_code, ""),
            "bank_name": settings.bank_name,
            "bank_account_no": settings.bank_account_no,
            "bank_ifsc": settings.bank_ifsc,
            "bank_branch": settings.bank_branch,
            "terms": settings.invoice_terms,
            "jurisdiction": settings.jurisdiction,
        },
        buyer=buyer,
        consignee=consignee,
        place_of_supply=(
            f"{figures.place_of_supply} {STATES.get(figures.place_of_supply, '')}".strip()
        ),
        lines=lines,
        has_discount=any(x["discount"] for x in lines),
        taxes=[(label, inr(amount)) for label, amount in taxes],
        round_off=inr(abs(figures.round_off)) if figures.round_off else None,
        round_off_less=figures.round_off < 0,
        total_qty=total_qty,
        grand_total=inr(figures.grand_total),
        words=amount_in_words(figures.grand_total),
        intra=intra,
        hsn_rows=hsn_rows,
        hsn_total={
            "taxable": inr(figures.taxable_value),
            "cgst": inr(figures.cgst),
            "sgst": inr(figures.sgst),
            "igst": inr(figures.igst),
            "tax": inr(tax_total),
        },
        tax_words=amount_in_words(tax_total) if tax_total else "NIL",
        copy_label=copy_label,
        irn=irn,
        previous_balance=previous_balance,
        # Test data never leaves dev or staging unmarked (ADR 0005).
        test_mark=not get_settings().is_production,
    )
    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]
