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
