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
    ADJUSTMENT = "adjustment"


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


class AuditAction(StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REUSE = "token_reuse"  # noqa: S105 - an audit action name, not a secret
    OVERRIDE = "override"


class DocType(StrEnum):
    """Each document type has its own gapless series per location per financial year."""

    SALES_INVOICE = "sales_invoice"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"
    DELIVERY_CHALLAN = "delivery_challan"
    PURCHASE_ENTRY = "purchase_entry"
    PAYMENT_RECEIPT = "payment_receipt"


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
