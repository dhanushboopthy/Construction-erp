"""Bill templates per company (Milestone 28, ADR 0013).

An uploaded bill design is HTML **data** with a small placeholder grammar, never a Jinja (or any
other) template: nothing in it is evaluated. Anywhere the design writes `{{key}}` or
`{{key|format}}`, the value of that registered field goes, escaped. Anything else between
`{{ }}`, `{% %}` or `{# #}` is unknown: it prints blank and is listed by the diagnostics.

The field registry is built from the fields the built-in layouts print (`invoice_a4.html` for
bills, proformas and quotations; `note_a4.html` for credit and debit notes), so a template and the
built-in layout never disagree about what a total is.

A tax invoice, credit note or debit note must stay a full GST document, so a template for those
slots is refused when it leaves out a field the GST rules require (`requirements`). A proforma or
quotation must say plainly that it is not a tax invoice.

Pure: no database, files or clock. The HTML itself is handled in `bill_html.py`.
"""

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

SLOTS = ("tax_invoice", "proforma", "quotation", "credit_note", "debit_note")
TAX_DOCUMENT_SLOTS = ("tax_invoice", "credit_note", "debit_note")
QUOTE_SLOTS = ("proforma", "quotation")

MAX_HTML_BYTES = 500 * 1024
MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_ASSETS = 20

PNG, JPEG = "image/png", "image/jpeg"
_ASSET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")

ALL = SLOTS
INVOICE = ("tax_invoice",)
SALES = ("tax_invoice", "proforma", "quotation")
NOTES = ("credit_note", "debit_note")
NOT_DEBIT = ("tax_invoice", "proforma", "quotation", "credit_note")


class TemplateRuleError(ValueError):
    """The template rules refuse this. `code` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Field:
    key: str
    description: str
    sample: str
    slots: tuple[str, ...]
    image: bool = False

    @property
    def group(self) -> str:
        return self.key.split(".", 1)[0]


def _f(key: str, description: str, sample: str, slots: tuple[str, ...] = ALL) -> Field:
    return Field(key, description, sample, slots)


def _img(key: str, description: str, slots: tuple[str, ...] = ALL) -> Field:
    return Field(key, description, "(image)", slots, image=True)


FIELDS: tuple[Field, ...] = (
    # The document itself.
    _f(
        "invoice.title",
        "The document's name: Tax Invoice, Proforma Invoice, Estimate/Quotation, Credit Note "
        "or Debit Note",
        "Tax Invoice",
    ),
    _f("invoice.number", "The document's number", "MS/2627/000123"),
    _f("invoice.date", "The document's date", "01-11-2026"),
    _f(
        "invoice.copyLabel",
        "Which copy this print is: Original for recipient, Duplicate for transporter or "
        "Triplicate for supplier",
        "Original for recipient",
        INVOICE,
    ),
    _f(
        "invoice.placeOfSupply",
        "Place of supply: state code and name",
        "33 Tamil Nadu",
        NOT_DEBIT,
    ),
    _f("invoice.supplyKind", "Intra-state (CGST + SGST) or Inter-state (IGST)", "Intra-state"),
    _f("invoice.paymentTerms", "Mode and terms of payment", "Credit, due by 01-12-2026", INVOICE),
    _f(
        "invoice.reference",
        "The quotation the bill came from, with its date",
        "QT/2627/000042 dt. 28-10-2026",
        INVOICE,
    ),
    _f("invoice.vehicleNo", "Motor vehicle number", "TN 09 AB 1234", INVOICE),
    _f("invoice.ewayBillNo", "e-Way bill number, when there is one", "331234567890", INVOICE),
    _f("invoice.destination", "Where the goods go", "Anna Nagar site", SALES),
    _f(
        "invoice.termsLabel",
        "Caption of the terms box: Terms of Delivery, or Valid Until on a quotation",
        "Terms of Delivery",
        SALES,
    ),
    _f(
        "invoice.terms",
        "Terms of delivery, or the date a quotation is valid until",
        "Ex-shop",
        SALES,
    ),
    _f(
        "invoice.declaration",
        "The declaration at the foot (on a proforma or quotation it says it is not a tax invoice)",
        "We declare that this invoice shows the actual price of the goods described and that "
        "all particulars are true and correct.",
        SALES,
    ),
    _f(
        "invoice.footer",
        "The line at the very foot",
        "This is a Computer Generated Invoice",
        SALES,
    ),
    _f(
        "invoice.previousBalance",
        "The customer's balance before this bill, when there was one",
        "12,500.00",
        INVOICE,
    ),
    # What a credit or debit note corrects.
    _f("note.againstLabel", "Invoice, or Supplier bill", "Invoice", NOTES),
    _f("note.against", "Number of the invoice or supplier bill corrected", "MS/2627/000099", NOTES),
    _f("note.againstDate", "Date of that invoice or supplier bill", "20-10-2026", NOTES),
    _f("note.reason", "Why the note was issued", "Goods returned", NOTES),
    _f(
        "note.totalLabel",
        "Credited to customer, or Debited to supplier",
        "Credited to customer",
        NOTES,
    ),
    # e-Invoice.
    _f("einvoice.irn", "Invoice Reference Number, when the bill has one", "8f3c…e21a", INVOICE),
    _f("einvoice.ackNo", "Acknowledgement number", "112410000012345", INVOICE),
    _f("einvoice.ackDate", "Acknowledgement date", "01-11-2026", INVOICE),
    _img("einvoice.qr", "The signed e-Invoice QR code (use as an image source)", INVOICE),
    # The seller.
    _f("company.name", "Trade name (or the legal name when there is none)", "Sri Balaji Steels"),
    _f("company.legalName", "Legal name, when a trade name is used", "Balaji Traders Pvt Ltd"),
    _f("company.address", "Address (line breaks kept)", "12, Mount Road\nChennai 600002"),
    _f("company.gstin", "GSTIN", "33ABCDE1234F1Z5"),
    _f("company.pan", "PAN", "ABCDE1234F"),
    _f("company.cin", "CIN, for a company", "U27100TN2010PTC012345"),
    _f("company.stateCode", "State code", "33"),
    _f("company.stateName", "State name", "Tamil Nadu"),
    _f("company.phone", "Phone", "+91 44 2345 6789"),
    _f("company.email", "E-mail", "accounts@balajisteels.in"),
    _f("company.bankName", "Bank name", "State Bank of India"),
    _f("company.bankAccountNo", "Bank account number", "12345678901"),
    _f("company.bankIfsc", "IFSC", "SBIN0001234"),
    _f("company.bankBranch", "Bank branch", "Mount Road"),
    _f(
        "company.terms",
        "Terms and conditions printed on bills",
        "Goods once sold are not taken back.",
    ),
    _f("company.jurisdiction", "Jurisdiction city", "Chennai"),
    _img("company.logo", "The company's logo (use as an image source)"),
    _img("company.secondaryLogo", "The second logo Duolink uploaded (use as an image source)"),
    # The party the document is made out to (for a debit note, the supplier).
    _f("customer.name", "Buyer's name (for a debit note, the supplier's)", "Kumar Builders"),
    _f("customer.address", "Buyer's address", "4, Lake View Road\nChennai 600040"),
    _f("customer.gstin", "Buyer's GSTIN, or Unregistered (B2C)", "33PQRSX5678K1Z2"),
    _f("customer.stateCode", "Buyer's state code", "33"),
    _f("customer.stateName", "Buyer's state name", "Tamil Nadu"),
    # Ship to: the site, or the buyer when there is no site.
    _f(
        "consignee.name",
        "Ship-to name (falls back to the buyer)",
        "Kumar Builders, Anna Nagar site",
        SALES,
    ),
    _f("consignee.address", "Ship-to address", "Plot 7, 2nd Avenue\nAnna Nagar", SALES),
    _f("consignee.gstin", "Ship-to GSTIN, or URP", "URP", SALES),
    _f("consignee.stateCode", "Ship-to state code", "33", SALES),
    _f("consignee.stateName", "Ship-to state name", "Tamil Nadu", SALES),
    # One line: the `<tr>` (or the section between <!-- items:start --> and <!-- items:end -->)
    # holding these is repeated once per line.
    _f("item.lineNo", "Line number", "1"),
    _f("item.description", "Item description", "TMT bar Fe 500D 12 mm"),
    _f("item.hsn", "HSN code", "7214"),
    _f("item.qty", "Quantity", "1.5"),
    _f("item.unit", "Unit", "t"),
    _f("item.rate", "Rate per unit, before tax", "62,000.00", SALES),
    _f("item.discount", "Discount on the line, when there is one", "500.00", SALES),
    _f("item.taxable", "Taxable value of the line", "92,500.00"),
    _f("item.gstRate", "GST rate", "18%"),
    _f("item.cgstRate", "CGST rate (blank on an inter-state document)", "9%"),
    _f("item.cgstAmount", "CGST amount (blank on an inter-state document)", "8,325.00"),
    _f("item.sgstRate", "SGST rate (blank on an inter-state document)", "9%"),
    _f("item.sgstAmount", "SGST amount (blank on an inter-state document)", "8,325.00"),
    _f("item.igstRate", "IGST rate (blank on an intra-state document)", "18%"),
    _f("item.igstAmount", "IGST amount (blank on an intra-state document)", "16,650.00"),
    _f("item.taxAmount", "Total tax on the line", "16,650.00"),
    _f("item.total", "Line total with tax", "1,09,150.00"),
    _f("item.batch", "Batch numbers taken, when tracked", "B-2611", INVOICE),
    _f("item.stockLeft", "Stock left at the shop after this sale", "8.25 t", INVOICE),
    # One HSN summary row: repeated like the item row (or <!-- hsn:start --> … <!-- hsn:end -->).
    _f("hsn.hsn", "HSN code", "7214"),
    _f("hsn.taxable", "Taxable value for the HSN code", "92,500.00"),
    _f("hsn.rate", "GST rate", "18%"),
    _f("hsn.cgstRate", "CGST rate (blank on an inter-state document)", "9%"),
    _f("hsn.cgstAmount", "CGST amount (blank on an inter-state document)", "8,325.00"),
    _f("hsn.sgstRate", "SGST rate (blank on an inter-state document)", "9%"),
    _f("hsn.sgstAmount", "SGST amount (blank on an inter-state document)", "8,325.00"),
    _f("hsn.igstRate", "IGST rate (blank on an intra-state document)", "18%"),
    _f("hsn.igstAmount", "IGST amount (blank on an intra-state document)", "16,650.00"),
    _f("hsn.taxAmount", "Total tax for the HSN code", "16,650.00"),
    # Totals.
    _f("totals.totalQty", "Total quantity, when every line has the same unit", "1.5 t", SALES),
    _f("totals.taxable", "Total taxable value", "92,500.00"),
    _f("totals.cgst", "Total CGST (blank on an inter-state document)", "8,325.00"),
    _f("totals.sgst", "Total SGST (blank on an inter-state document)", "8,325.00"),
    _f("totals.igst", "Total IGST (blank on an intra-state document)", "16,650.00"),
    _f("totals.taxTotal", "Total tax", "16,650.00"),
    _f("totals.roundOff", "Rounding (negative when rounded down)", "0.00"),
    _f("totals.grandTotal", "Grand total", "1,09,150.00"),
    _f(
        "totals.amountInWords",
        "Grand total in words",
        "Indian Rupees One Lakh Nine Thousand One Hundred Fifty Only",
    ),
    _f(
        "totals.taxInWords",
        "Total tax in words",
        "Indian Rupees Sixteen Thousand Six Hundred Fifty Only",
    ),
)
REGISTRY: dict[str, Field] = {f.key: f for f in FIELDS}

# An image placeholder is written as an image's source (`<img src="{{company.logo}}">`); the
# renderer serves these addresses itself, from the company's own files.
IMAGE_URIS: dict[str, str] = {
    "company.logo": "asset:@logo",
    "company.secondaryLogo": "asset:@secondary-logo",
    "einvoice.qr": "asset:@einvoice-qr",
}
ITEM, HSN = "item.", "hsn."
FORMATS = ("symbol", "upper")


def check_slot(slot: str) -> None:
    if slot not in SLOTS:
        raise TemplateRuleError("SLOT_UNKNOWN", f"There is no bill slot called {slot!r}.")


def fields_for(slot: str) -> tuple[Field, ...]:
    return tuple(f for f in FIELDS if slot in f.slots)


# ------------------------------------------------------------------ what may not be dropped


@dataclass(frozen=True)
class Requirement:
    """Met when every field of any one option is printed."""

    label: str
    any_of: tuple[frozenset[str], ...]

    def met_by(self, present: Iterable[str]) -> bool:
        have = set(present)
        return any(option <= have for option in self.any_of)


def _req(label: str, *options: Iterable[str]) -> Requirement:
    return Requirement(label, tuple(frozenset(o) for o in options))


def _one(label: str, key: str) -> Requirement:
    return _req(label, [key])


_SELLER = (
    _one("Seller's name", "company.name"),
    _one("Seller's address", "company.address"),
    _one("Seller's GSTIN", "company.gstin"),
)
_DOCUMENT = (
    _one("Document name", "invoice.title"),
    _one("Document number", "invoice.number"),
    _one("Document date", "invoice.date"),
)
_RATE = _req(
    "Rate of tax",
    ["item.gstRate"],
    ["item.cgstRate", "item.sgstRate", "item.igstRate"],
    ["hsn.rate"],
    ["hsn.cgstRate", "hsn.sgstRate", "hsn.igstRate"],
)
_TAX = _req(
    "Amount of CGST, SGST and IGST",
    ["totals.cgst", "totals.sgst", "totals.igst"],
    ["item.cgstAmount", "item.sgstAmount", "item.igstAmount"],
    ["hsn.cgstAmount", "hsn.sgstAmount", "hsn.igstAmount"],
)
_TOTAL = _one("Invoice total", "totals.grandTotal")

# Rule 46 of the CGST Rules (tax invoice) and Rule 53 (credit and debit notes).
_REQUIREMENTS: dict[str, tuple[Requirement, ...]] = {
    "tax_invoice": (
        *_SELLER,
        *_DOCUMENT,
        _one("Copy marking (original, duplicate, triplicate)", "invoice.copyLabel"),
        _one("Buyer's name", "customer.name"),
        _one("Buyer's address", "customer.address"),
        _one("Buyer's GSTIN", "customer.gstin"),
        _one("Place of supply", "invoice.placeOfSupply"),
        _one("Description of each item", "item.description"),
        _one("HSN code of each item", "item.hsn"),
        _req("Quantity and unit of each item", ["item.qty", "item.unit"]),
        _one("Taxable value of each item", "item.taxable"),
        _RATE,
        _TAX,
        _TOTAL,
        _req("e-Invoice IRN and QR code", ["einvoice.irn", "einvoice.qr"]),
    ),
    **{
        slot: (
            *_SELLER,
            *_DOCUMENT,
            _one("Party's name", "customer.name"),
            _one("Party's address", "customer.address"),
            _one("Party's GSTIN", "customer.gstin"),
            _req("Original document number and date", ["note.against", "note.againstDate"]),
            _req("Taxable value", ["item.taxable"], ["totals.taxable"], ["hsn.taxable"]),
            _RATE,
            _TAX,
            _TOTAL,
        )
        for slot in NOTES
    },
    **{
        slot: (
            _one("Seller's name", "company.name"),
            *_DOCUMENT,
            _one("Not-a-tax-invoice wording", "invoice.declaration"),
            _one("Buyer's name", "customer.name"),
            _one("Description of each item", "item.description"),
            _TOTAL,
        )
        for slot in QUOTE_SLOTS
    },
}


def requirements(slot: str) -> tuple[Requirement, ...]:
    return _REQUIREMENTS[slot]


def missing_requirements(slot: str, present: Iterable[str]) -> list[str]:
    """The labels of what the template leaves out. Empty: the template may be stored."""
    have = set(present)
    return [r.label for r in requirements(slot) if not r.met_by(have)]


_TAX_INVOICE_WORDS = re.compile(r"(?<!not a )tax\s+invoice", re.IGNORECASE)


def has_forbidden_wording(slot: str, text: str) -> bool:
    """A proforma or quotation never calls itself a tax invoice in its own words."""
    return slot in QUOTE_SLOTS and bool(_TAX_INVOICE_WORDS.search(" ".join(text.split())))


# ------------------------------------------------------------------ the grammar

TOKEN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_KEY = re.compile(r"^[a-z]+\.[A-Za-z][A-Za-z0-9]*$")


@dataclass(frozen=True)
class Token:
    raw: str
    key: str | None
    fmt: str | None
    known: bool


def parse_token(raw: str) -> Token:
    """`{{ key }}` or `{{ key | format }}` with a registered key and format; anything else is
    unknown and prints blank."""
    if not raw.startswith("{{"):
        return Token(raw, None, None, False)
    parts = [p.strip() for p in raw[2:-2].split("|")]
    key = parts[0] if _KEY.match(parts[0]) else None
    fmt = parts[1] if len(parts) == 2 else None
    known = key in REGISTRY and len(parts) <= 2 and (fmt is None or fmt in FORMATS)
    return Token(raw, key, fmt, known)


def tokens(text: str) -> list[Token]:
    return [parse_token(m.group(0)) for m in TOKEN.finditer(text)]


def substitute(text: str, lookup: Callable[[Token], str]) -> str:
    """Replace every token in one pass. A value is never scanned again, so a customer called
    `{{company.gstin}}` prints as written."""
    return TOKEN.sub(lambda m: lookup(parse_token(m.group(0))), text)


def format_value(value: str, fmt: str | None) -> str:
    if fmt == "symbol":
        return f"₹ {value}" if value else ""
    if fmt == "upper":
        return value.upper()
    return value


# ------------------------------------------------------------------ uploaded files


def decode_html(data: bytes) -> str:
    if len(data) > MAX_HTML_BYTES:
        raise TemplateRuleError(
            "TEMPLATE_TOO_LARGE", "The template is larger than 500 KB. Use a smaller file."
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TemplateRuleError(
            "TEMPLATE_NOT_UTF8", "The template must be saved as UTF-8 text."
        ) from exc
    if not text.strip():
        raise TemplateRuleError("TEMPLATE_EMPTY", "The template file is empty.")
    return text


def check_asset(name: str, data: bytes) -> str:
    """The asset's content type, decided from its bytes, if it is acceptable."""
    if not _ASSET_NAME.match(name):
        raise TemplateRuleError(
            "ASSET_NAME",
            f"{name!r}: an image name is up to 80 letters, digits, dots, dashes or underscores.",
        )
    if not data:
        raise TemplateRuleError("ASSET_EMPTY", f"{name}: the file is empty.")
    if len(data) > MAX_ASSET_BYTES:
        raise TemplateRuleError("ASSET_TOO_LARGE", f"{name}: an image may be up to 2 MB.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    raise TemplateRuleError("ASSET_TYPE", f"{name}: an image must be a PNG or JPEG file.")


def check_assets(files: Sequence[tuple[str, bytes]]) -> dict[str, str]:
    if len(files) > MAX_ASSETS:
        raise TemplateRuleError("ASSET_TOO_MANY", f"A template may have up to {MAX_ASSETS} images.")
    types: dict[str, str] = {}
    for name, data in files:
        if name.lower() in {n.lower() for n in types}:
            raise TemplateRuleError("ASSET_DUPLICATE", f"Two images are called {name}.")
        types[name] = check_asset(name, data)
    return types


# ------------------------------------------------------------------ what fills a template


@dataclass(frozen=True)
class BillData:
    """The values for one document: the single fields, one mapping per line and one per HSN
    summary row. Every value is already text."""

    fields: Mapping[str, str]
    items: Sequence[Mapping[str, str]]
    hsn: Sequence[Mapping[str, str]]


_SAMPLE_TITLES = {
    "tax_invoice": "Tax Invoice",
    "proforma": "Proforma Invoice",
    "quotation": "Estimate/Quotation",
    "credit_note": "Credit Note",
    "debit_note": "Debit Note",
}


def _sample(field: Field) -> str:
    if field.image:
        return IMAGE_URIS[field.key]
    if "igst" in field.key.lower():
        return ""  # the sample is an intra-state document
    return field.sample


def sample_data(slot: str) -> BillData:
    """What the preview prints: every field of the slot with its sample, two lines and one HSN
    row."""
    offered = fields_for(slot)
    fields = {f.key: _sample(f) for f in offered if not f.key.startswith((ITEM, HSN))}
    fields["invoice.title"] = _SAMPLE_TITLES[slot]
    line = {f.key: _sample(f) for f in offered if f.key.startswith(ITEM)}
    hsn = {f.key: _sample(f) for f in offered if f.key.startswith(HSN)}
    second = {**line, "item.lineNo": "2", "item.description": "Binding wire 20 SWG"}
    return BillData(fields=fields, items=[line, second], hsn=[hsn])
