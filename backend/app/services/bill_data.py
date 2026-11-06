"""What a bill template is filled with (Milestone 28): the same figures the built-in layouts print.

`invoice_pdf` and `note_pdf` each build one context for their built-in Jinja layout (their own
HTML, never an uploaded one). The functions here turn that context into the text values of the
field registry (`app/domain/bill_template.py`), so a design and the built-in layout can never
disagree about what a total is. Nothing is recalculated: every figure is already text.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.bill_template import IMAGE_URIS, BillData, fields_for

LINE_KEYS = {
    "item.lineNo": "line_no",
    "item.description": "description",
    "item.hsn": "hsn",
    "item.qty": "qty",
    "item.unit": "unit",
    "item.rate": "rate",
    "item.discount": "discount",
    "item.taxable": "amount",
    "item.gstRate": "gst_rate",
    "item.cgstRate": "cgst_rate",
    "item.cgstAmount": "cgst",
    "item.sgstRate": "sgst_rate",
    "item.sgstAmount": "sgst",
    "item.igstRate": "igst_rate",
    "item.igstAmount": "igst",
    "item.taxAmount": "tax",
    "item.total": "total",
    "item.batch": "batch",
    "item.stockLeft": "stock_left",
}
HSN_KEYS = {
    "hsn.hsn": "hsn",
    "hsn.taxable": "taxable",
    "hsn.rate": "rate",
    "hsn.cgstRate": "half_rate",
    "hsn.cgstAmount": "cgst",
    "hsn.sgstRate": "half_rate",
    "hsn.sgstAmount": "sgst",
    "hsn.igstRate": "rate",
    "hsn.igstAmount": "igst",
    "hsn.taxAmount": "tax",
}


def text(value: object) -> str:
    return "" if value is None else str(value)


def _party(prefix: str, party: Mapping[str, Any]) -> dict[str, str]:
    return {
        f"{prefix}.name": text(party.get("name")),
        f"{prefix}.address": text(party.get("address")),
        f"{prefix}.gstin": text(party.get("gstin")),
        f"{prefix}.stateCode": text(party.get("state_code")),
        f"{prefix}.stateName": text(party.get("state_name")),
    }


def _company(seller: Mapping[str, Any]) -> dict[str, str]:
    return {
        "company.name": text(seller.get("name")),
        "company.legalName": text(seller.get("legal_name")),
        "company.address": text(seller.get("address")),
        "company.gstin": text(seller.get("gstin")),
        "company.pan": text(seller.get("pan")),
        "company.cin": text(seller.get("cin")),
        "company.stateCode": text(seller.get("state_code")),
        "company.stateName": text(seller.get("state_name")),
        "company.phone": text(seller.get("phone")),
        "company.email": text(seller.get("email")),
        "company.bankName": text(seller.get("bank_name")),
        "company.bankAccountNo": text(seller.get("bank_account_no")),
        "company.bankIfsc": text(seller.get("bank_ifsc")),
        "company.bankBranch": text(seller.get("bank_branch")),
        "company.terms": text(seller.get("terms")),
        "company.jurisdiction": text(seller.get("jurisdiction")),
    }


def _rows(
    keys: Mapping[str, str], rows: Sequence[Mapping[str, Any]], slot: str, *, intra: bool
) -> list[dict[str, str]]:
    offered = {f.key for f in fields_for(slot)}
    out: list[dict[str, str]] = []
    for row in rows:
        values = {k: text(row.get(src)) for k, src in keys.items() if k in offered}
        for key in values:
            # A tax that does not apply prints blank, never 0.00.
            if ("igst" in key.lower() and intra) or (
                ("cgst" in key.lower() or "sgst" in key.lower()) and not intra
            ):
                values[key] = ""
        out.append(values)
    return out


def build(
    ctx: Mapping[str, Any],
    slot: str,
    *,
    extra: Mapping[str, str],
    has_logo: bool,
    has_secondary_logo: bool,
    has_qr: bool,
) -> BillData:
    """`ctx` has `seller`, `buyer`, `consignee`, `lines`, `hsn_rows`, `hsn_total`, `intra`,
    `grand_total`, `round_off_text`, `words` and `tax_words`; `extra` holds the document's own
    fields (`invoice.*`, `note.*`, `einvoice.*`)."""
    intra = bool(ctx["intra"])
    total = ctx["hsn_total"]
    fields: dict[str, str] = {
        **_company(ctx["seller"]),
        **_party("customer", ctx["buyer"]),
        **_party("consignee", ctx["consignee"]),
        **extra,
        "invoice.supplyKind": "Intra-state" if intra else "Inter-state",
        "totals.totalQty": text(ctx.get("total_qty")),
        "totals.taxable": text(total["taxable"]),
        "totals.cgst": text(total["cgst"]) if intra else "",
        "totals.sgst": text(total["sgst"]) if intra else "",
        "totals.igst": "" if intra else text(total["igst"]),
        "totals.taxTotal": text(total["tax"]),
        "totals.roundOff": text(ctx["round_off_text"]),
        "totals.grandTotal": text(ctx["grand_total"]),
        "totals.amountInWords": text(ctx["words"]),
        "totals.taxInWords": text(ctx["tax_words"]),
        "company.logo": IMAGE_URIS["company.logo"] if has_logo else "",
        "company.secondaryLogo": IMAGE_URIS["company.secondaryLogo"] if has_secondary_logo else "",
        "einvoice.qr": IMAGE_URIS["einvoice.qr"] if has_qr else "",
    }
    return BillData(
        fields=fields,
        items=_rows(LINE_KEYS, ctx["lines"], slot, intra=intra),
        hsn=_rows(HSN_KEYS, ctx["hsn_rows"], slot, intra=intra),
    )
