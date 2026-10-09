"""A4 tax invoice as a PDF. The renderer sits behind an interface so a thermal-printer layout
can be added later without touching the invoice code (ROADMAP, printing)."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.core.config import get_settings
from app.domain.gst import STATE_NAMES, SupplyKind
from app.domain.money import money
from app.domain.words import amount_in_words
from app.models.sales import SalesInvoice
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


class InvoiceRenderer(Protocol):
    def render(
        self, db: Session, invoice: SalesInvoice, *, copy_label: str, eway_no: str | None
    ) -> bytes: ...


@dataclass
class A4HtmlRenderer:
    """HTML template to PDF with WeasyPrint."""

    template: str = "invoice_a4.html"

    def render(
        self, db: Session, invoice: SalesInvoice, *, copy_label: str, eway_no: str | None = None
    ) -> bytes:
        settings = get_settings_row(db)
        intra = invoice.supply_kind is SupplyKind.INTRA_STATE
        lines = []
        for line in invoice.lines:
            factor = line.base_qty / line.quantity
            lines.append(
                {
                    "line_no": line.line_no,
                    "description": line.description,
                    "hsn": line.hsn,
                    "base_unit": line.base_unit,
                    "stock_after": _plain(line.stock_after)
                    if line.stock_after is not None
                    else None,
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
        env = Environment(
            loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"])
        )
        html = env.get_template(self.template).render(
            inv=invoice,
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
            place_name=STATES.get(invoice.place_of_supply, ""),
            copy_label=copy_label,
            eway_no=eway_no,
            words=amount_in_words(invoice.grand_total),
            pending_text=inr(invoice.pending_balance_at_billing),
            paid_text=inr(invoice.paid_at_billing),
            due_text=inr(invoice.grand_total - invoice.paid_at_billing),
            totals={
                "taxable": inr(invoice.taxable_value),
                "cgst": inr(invoice.cgst),
                "sgst": inr(invoice.sgst),
                "igst": inr(invoice.igst),
                "round_off": inr(invoice.round_off),
                "grand_total": inr(invoice.grand_total),
            },
            # Test data never leaves dev or staging unmarked (ADR 0005).
            test_mark=not get_settings().is_production,
        )
        return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


DEFAULT_RENDERER: InvoiceRenderer = A4HtmlRenderer()
