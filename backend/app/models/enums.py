"""Enumerations stored as VARCHAR + CHECK (no native Postgres enums: easier migrations)."""

from enum import StrEnum

import sqlalchemy as sa


class Role(StrEnum):
    OWNER = "owner"
    COUNTER = "counter"
    ACCOUNTANT = "accountant"


class LocationKind(StrEnum):
    SHOP = "shop"
    GODOWN = "godown"


class ItemCategory(StrEnum):
    TMT = "tmt"
    PIPE = "pipe"
    CEMENT = "cement"
    WIRE = "wire"
    ANGLE = "angle"
    CHANNEL = "channel"
    OTHER = "other"


class PartyType(StrEnum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    BOTH = "both"


class CustomerSegment(StrEnum):
    RETAIL = "retail"
    CONTRACTOR = "contractor"
    BULK = "bulk"


class LedgerAccount(StrEnum):
    RECEIVABLE = "receivable"  # customers owe us
    PAYABLE = "payable"  # we owe suppliers


class StockRef(StrEnum):
    """What created a stock ledger row."""

    OPENING = "opening"
    PURCHASE = "purchase"
    PURCHASE_RETURN = "purchase_return"
    SALE = "sale"
    SALE_RETURN = "sale_return"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"  # posting a stock count (ref_id is the count)
    STOCK_ADJUSTMENT = "stock_adjustment"  # an adjustment document with a reason (FM2)


class PartyRef(StrEnum):
    """What created a party ledger row."""

    OPENING = "opening"
    SALE = "sale"
    PURCHASE = "purchase"
    PAYMENT = "payment"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"
    REBATE = "rebate"
    FREIGHT = "freight"
    WRITE_OFF = "write_off"  # a bad debt written off by the owner (FM5)


class OpeningKind(StrEnum):
    STOCK = "stock"
    RECEIVABLE = "receivable"  # a customer owes us at go-live
    CUSTOMER_ADVANCE = "customer_advance"  # we hold a customer's advance
    PAYABLE = "payable"  # we owe a supplier at go-live
    SUPPLIER_ADVANCE = "supplier_advance"  # a supplier holds our advance


class OpeningStatus(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"


class PurchaseMode(StrEnum):
    STOCK = "stock"  # goods come into one of our locations
    DIRECT = "direct"  # goods go straight to a customer's site (drop-ship, M9)


class PurchaseStatus(StrEnum):
    POSTED = "posted"


class PaymentDirection(StrEnum):
    RECEIVED = "received"  # from a customer
    PAID = "paid"  # to a supplier or a transporter


class PaymentMode(StrEnum):
    CASH = "cash"
    UPI = "upi"
    BANK = "bank"  # transfer; no cheques (B7)


class CountStatus(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"


class SupplyType(StrEnum):
    B2B = "B2B"  # buyer has a GSTIN
    B2C = "B2C"  # buyer has none: still a real tax invoice


class FulfilmentSource(StrEnum):
    SHOP = "shop"  # from the stock of the shop billing
    GODOWN = "godown"  # from another location's stock
    DIRECT = "direct"  # supplier to the customer's site, no stock moves (B10)


class InvoiceStatus(StrEnum):
    POSTED = "posted"


class ApprovalAction(StrEnum):
    """What an owner PIN can approve at the counter (G18)."""

    CREDIT_OVERRIDE = "credit_override"
    BELOW_COST = "below_cost"
    DISCOUNT = "discount"
    BACKDATE = "backdate"
    LATE_RETURN = "late_return"  # a return after the return window (B11)
    EXPENSE = "expense"  # a cash-book voucher above the shop's limit (FM1)
    STOCK_ADJUSTMENT = "stock_adjustment"  # a stock adjustment above the limit (FM2)


class ComplianceStatus(StrEnum):
    """State of an e-way bill or an e-invoice (IRN) at the government portal."""

    GENERATED = "generated"
    CANCELLED = "cancelled"


class EwaySource(StrEnum):
    GSP = "gsp"  # made through the GSP API
    MANUAL = "manual"  # made on the portal by hand, number typed in (fallback)


class AttachmentRef(StrEnum):
    """What a stored file is attached to (B17)."""

    PURCHASE = "purchase"
    SALES_INVOICE = "sales_invoice"
    TRIP = "trip"


class AttachmentKind(StrEnum):
    WEIGHBRIDGE = "weighbridge"  # weighbridge slip
    DELIVERY = "delivery"  # delivery proof
    OTHER = "other"


class ClosingStatus(StrEnum):
    CLOSED = "closed"  # the shop-day is locked
    REOPENED = "reopened"  # the owner unlocked it; it can be closed again


class AuditAction(StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REUSE = "token_reuse"  # noqa: S105 - an audit action name, not a secret
    OVERRIDE = "override"
    EXPORT = "export"  # the books were exported, for example to Tally (FM4)


class DocType(StrEnum):
    """Each document type has its own gapless series per location per financial year."""

    SALES_INVOICE = "sales_invoice"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"
    DELIVERY_CHALLAN = "delivery_challan"
    PURCHASE_ENTRY = "purchase_entry"
    PAYMENT_RECEIPT = "payment_receipt"
    CASH_VOUCHER = "cash_voucher"  # cash book: expenses, bank deposits and withdrawals (FM1)
    STOCK_ADJUSTMENT = "stock_adjustment"  # breakage, theft, weighbridge, count fixes (FM2)
    BAD_DEBT_WRITEOFF = "bad_debt_writeoff"  # a customer debt given up, no GST effect (FM5)


def str_enum(enum_cls: type[StrEnum], name: str) -> sa.Enum:
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )
