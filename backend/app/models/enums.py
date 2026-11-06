"""Enumerations stored as VARCHAR + CHECK (no native Postgres enums: easier migrations)."""

from enum import StrEnum

import sqlalchemy as sa


class Role(StrEnum):
    OWNER = "owner"
    COUNTER = "counter"
    ACCOUNTANT = "accountant"


class TenantStatus(StrEnum):
    """A company's account with Duolink (ADR 0011). Suspended and cancelled companies cannot
    sign in; their books are kept."""

    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class DurationUnit(StrEnum):
    """How long one price of a plan lasts (Milestone 20)."""

    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class PlatformRole(StrEnum):
    """What a Duolink staff member may do (Milestone 17, ADR 0013)."""

    SUPER_ADMIN = "super_admin"  # everything
    SUPPORT = "support"  # reads, and answers tickets; changes nothing else


class PlatformAction(StrEnum):
    """What a Duolink admin did (platform_audit_log, Milestones 16 and 17)."""

    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REUSE = "token_reuse"  # noqa: S105 - an audit action name, not a secret
    TENANT_CREATE = "tenant_create"
    TENANT_UPDATE = "tenant_update"
    TENANT_SUSPEND = "tenant_suspend"
    TENANT_REACTIVATE = "tenant_reactivate"
    USER_ACTIVATE = "user_activate"
    USER_DEACTIVATE = "user_deactivate"
    USER_UNLOCK = "user_unlock"
    USER_RESET_PASSWORD = "user_reset_password"  # noqa: S105 - an audit action name
    USER_SIGN_OUT = "user_sign_out"
    STAFF_CREATE = "staff_create"
    STAFF_UPDATE = "staff_update"
    STAFF_RESET_PASSWORD = "staff_reset_password"  # noqa: S105 - an audit action name
    STAFF_UNLOCK = "staff_unlock"
    STAFF_SIGN_OUT = "staff_sign_out"
    PASSWORD_CHANGE = "password_change"  # noqa: S105 - an audit action name
    TENANT_CANCEL = "tenant_cancel"
    TENANT_SELLER_UPDATE = "tenant_seller_update"
    TENANT_LOGO_SET = "tenant_logo_set"
    TENANT_LOGO_REMOVE = "tenant_logo_remove"
    USER_UPDATE = "user_update"
    USER_SESSION_REVOKE = "user_session_revoke"
    USER_REMOVE = "user_remove"
    PLAN_CREATE = "plan_create"
    PLAN_UPDATE = "plan_update"
    PLAN_DUPLICATE = "plan_duplicate"
    PLAN_ARCHIVE = "plan_archive"
    PLAN_DELETE = "plan_delete"
    SUBSCRIPTION_RENEW = "subscription_renew"
    SUBSCRIPTION_CANCEL = "subscription_cancel"
    PAYMENT_REVERSE = "payment_reverse"
    SUPPORT_REPLY = "support_reply"
    SUPPORT_UPDATE = "support_update"
    SUPPORT_SESSION_START = "support_session_start"  # entered a company, with its owner's grant
    SUPPORT_SESSION_END = "support_session_end"
    MAINTENANCE_ON = "maintenance_on"
    MAINTENANCE_OFF = "maintenance_off"
    AUDIT_EXPORT = "audit_export"
    BACKUP_CREATE = "backup_create"
    BACKUP_DOWNLOAD = "backup_download"
    BACKUP_UPLOAD = "backup_upload"
    BACKUP_DELETE = "backup_delete"
    BACKUP_RESTORE = "backup_restore"
    BACKUP_RESTORE_FAILED = "backup_restore_failed"
    BACKUP_SCHEDULE_UPDATE = "backup_schedule_update"
    NUMBERING_SET = "numbering_set"
    COMPANY_DATA_DELETED = "company_data_deleted"
    COMPANY_DATA_DELETED_ALL = "company_data_deleted_all"
    COMPANY_DATA_DELETE_FAILED = "company_data_delete_failed"
    INTEGRATION_CONNECT = "integration_connect"
    INTEGRATION_TEST = "integration_test"
    INTEGRATION_DISCONNECT = "integration_disconnect"
    INTEGRATION_LIMITS = "integration_limits"
    GSTIN_LOOKUP = "gstin_lookup"


class SequenceChange(StrEnum):
    """Why a document counter moved (Milestone 26): set by a Super Admin, or reset because a
    data deletion emptied the series."""

    SET = "set"
    RESET = "reset"


class BackupKind(StrEnum):
    PLATFORM = "platform"
    COMPANY = "company"


class BackupSource(StrEnum):
    """Why a backup exists. Only `scheduled` ones are ever pruned (Milestone 25)."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    SAFETY = "safety"
    UPLOADED = "uploaded"


class BackupStatus(StrEnum):
    RUNNING = "running"
    VERIFIED = "verified"
    FAILED = "failed"


class BackupJobKind(StrEnum):
    BACKUP_PLATFORM = "backup_platform"
    BACKUP_COMPANY = "backup_company"
    RESTORE_COMPANY = "restore_company"


class BackupJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SupportSessionEnd(StrEnum):
    """Why a support session ended (Milestone 23)."""

    EXITED = "exited"  # the admin pressed Exit
    REVOKED = "revoked"  # the owner revoked the grant, or replaced it with a new one
    GRANT_ENDED = "grant_ended"  # the grant's time ran out
    REPLACED = "replaced"  # the same admin entered the company again
    ADMIN_NOT_ALLOWED = "admin_not_allowed"  # the admin was deactivated or is no Super Admin


class IntegrationKind(StrEnum):
    """A shared integration Duolink runs for every company (Milestone 27)."""

    GSP = "gsp"  # e-way bills and IRN
    GSTIN_LOOKUP = "gstin_lookup"


class IntegrationProvider(StrEnum):
    FAKE = "fake"  # pretend; never in production
    SANDBOX = "sandbox"
    LIVE = "live"


class IntegrationStatus(StrEnum):
    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    FAILING = "failing"


class IntegrationOutcome(StrEnum):
    """How one call ended. Only ok and failed reached the provider."""

    OK = "ok"
    FAILED = "failed"
    CACHED = "cached"
    BLOCKED = "blocked"


class SupportCategory(StrEnum):
    """What a support ticket is about (Milestone 22)."""

    SIGN_IN = "sign_in"
    BILLING = "billing"
    GST_EWAY = "gst_eway"
    STOCK = "stock"
    PRINTING = "printing"
    OTHER = "other"


class SupportPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class SupportStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_ON_COMPANY = "waiting_on_company"
    RESOLVED = "resolved"
    CLOSED = "closed"


class AuthorKind(StrEnum):
    """Who wrote a support message: a user of the company, or a Duolink admin."""

    COMPANY_USER = "company_user"
    PLATFORM_ADMIN = "platform_admin"


class SubscriptionStatus(StrEnum):
    """Stored status of a company's subscription (Milestone 21). Whether it has run out is
    worked out from `expires_at`; `expired` is never written, it is what `trial` and `active`
    become when the date passes."""

    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentMethod(StrEnum):
    """How Duolink received a subscription payment (Milestone 21)."""

    CASH = "cash"
    BANK = "bank"
    UPI = "upi"
    CHEQUE = "cheque"
    RAZORPAY = "razorpay"


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
    STOCK_WRITEDOWN = "stock_writedown"  # value-only: stock out and back in at NRV (FM6)


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
    PO_MISMATCH = "po_mismatch"  # a supplier bill that does not match its order (FM10)


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
    SUPPORT_ENTER = "support_enter"  # Duolink opened a support session here (M23)
    SUPPORT_EXIT = "support_exit"  # ...and it ended: left, revoked or the grant ran out


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
    STOCK_WRITEDOWN = "stock_writedown"  # stock value lowered to NRV (FM6)
    PURCHASE_ORDER = "purchase_order"  # an order to a supplier (FM10)
    GOODS_RECEIPT = "goods_receipt"  # what arrived against an order (FM10)
    QUOTATION = "quotation"  # an estimate for a customer: no stock, no account entry
    PROFORMA = "proforma"  # a proforma invoice, asking for payment before the bill


class QuoteKind(StrEnum):
    """A priced offer that is not a tax invoice (the bill is separate)."""

    QUOTATION = "quotation"
    PROFORMA = "proforma"


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
