"""A4 tax invoice as a PDF. The renderer sits behind an interface so a thermal-printer layout
can be added later without touching the invoice code (ROADMAP, printing)."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import segno
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.core.config import get_settings
from app.domain.gst import STATE_NAMES, SupplyKind
from app.domain.money import money
from app.domain.words import amount_in_words
from app.models.compliance import EInvoice
from app.models.enums import QuoteKind
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
        return _render(
            db,
            self.template,
            invoice,
            invoice.lines,
            doc=TAX_INVOICE,
            figures=invoice,
            batches=batches,
            copy_label=copy_label,
            eway_no=eway_no,
            irn=irn,
            pending_text=inr(invoice.pending_balance_at_billing),
            paid_text=inr(invoice.paid_at_billing),
            due_text=inr(invoice.grand_total - invoice.paid_at_billing),
        )


DEFAULT_RENDERER: InvoiceRenderer = A4HtmlRenderer()

TAX_INVOICE = {
    "title": "Tax invoice",
    "heading": "TAX INVOICE",
    "number_label": "Invoice no.",
    "total_label": "Bill total",
    "footer": "Subject to the jurisdiction of the shop's city. "
    "This is a computer generated tax invoice.",
}
QUOTE_DOCS = {
    QuoteKind.QUOTATION: {
        "title": "Quotation",
        "heading": "QUOTATION",
        "number_label": "Quotation no.",
        "total_label": "Estimated total",
        "footer": "This is a quotation, not a tax invoice. Prices are as on its date; "
        "the tax invoice is issued when the goods are billed.",
    },
    QuoteKind.PROFORMA: {
        "title": "Proforma invoice",
        "heading": "PROFORMA INVOICE",
        "number_label": "Proforma no.",
        "total_label": "Amount payable",
        "footer": "This is a proforma invoice, not a tax invoice. The GST shown is charged on "
        "the tax invoice issued when the goods are billed.",
    },
}


def render_quote(db: Session, quote: SalesQuote) -> bytes:
    """A quotation or proforma invoice on the bill's A4 layout, plainly titled as not a tax
    invoice (ADR 0005)."""
    inv = {
        "number": quote.number,
        "invoice_date": quote.quote_date,
        "valid_until": quote.valid_until,
        "place_of_supply": quote.place_of_supply,
        "bill_to_name": quote.bill_to_name,
        "bill_to_address": quote.bill_to_address,
        "bill_to_gstin": quote.bill_to_gstin,
        "ship_to_name": quote.ship_to_name,
        "ship_to_address": quote.ship_to_address,
    }
    return _render(
        db, "invoice_a4.html", inv, quote.lines, doc=QUOTE_DOCS[quote.kind], figures=quote
    )


def _render(
    db: Session,
    template: str,
    inv: object,
    source_lines: Sequence[SalesLine] | Sequence[SalesQuoteLine],
    *,
    doc: dict[str, str],
    figures: SalesInvoice | SalesQuote,
    batches: dict[int, str] | None = None,
    copy_label: str | None = None,
    eway_no: str | None = None,
    irn: IrnPrint | None = None,
    pending_text: str | None = None,
    paid_text: str | None = None,
    due_text: str | None = None,
) -> bytes:
    """`inv` is what the template prints in the header: the invoice, or a dict with the same
    names for a quotation. `figures` carries the totals and supply kind."""
    settings = get_settings_row(db)
    intra = figures.supply_kind is SupplyKind.INTRA_STATE
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
                "qty_text": f"{_plain(line.quantity)} {line.unit}",
                "rate_text": f"{inr(line.rate * factor)}/{line.unit}",
                "discount_text": inr(line.discount) if line.discount else "—",
                "taxable_text": inr(line.taxable),
                "cgst_text": inr(line.cgst),
                "sgst_text": inr(line.sgst),
                "igst_text": inr(line.igst),
                "gst_rate": _plain(line.gst_rate),
                "half_rate": _plain(line.gst_rate / 2),
                "total_text": inr(line.line_total),
            }
        )
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    html = env.get_template(template).render(
        inv=inv,
        doc=doc,
        seller={
            "legal_name": settings.legal_name,
            "trade_name": settings.trade_name,
            "gstin": settings.gstin,
            "address": settings.address,
            "phone": settings.phone,
            "email": settings.email,
            "state_code": settings.state_code,
            "state_name": STATES.get(settings.state_code, ""),
            "bank_name": settings.bank_name,
            "bank_account_no": settings.bank_account_no,
            "bank_ifsc": settings.bank_ifsc,
            "invoice_terms": settings.invoice_terms,
        },
        lines=lines,
        intra=intra,
        place_name=STATES.get(figures.place_of_supply, ""),
        copy_label=copy_label,
        eway_no=eway_no,
        irn=irn,
        words=amount_in_words(figures.grand_total),
        pending_text=pending_text,
        paid_text=paid_text,
        due_text=due_text,
        totals={
            "taxable": inr(figures.taxable_value),
            "cgst": inr(figures.cgst),
            "sgst": inr(figures.sgst),
            "igst": inr(figures.igst),
            "round_off": inr(figures.round_off),
            "grand_total": inr(figures.grand_total),
        },
        # Test data never leaves dev or staging unmarked (ADR 0005).
        test_mark=not get_settings().is_production,
    )
    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]
