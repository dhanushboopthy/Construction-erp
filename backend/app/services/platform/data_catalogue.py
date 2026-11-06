"""The catalogue of a company's deletable business data (Milestone 26, ADR 0013).

A hand-written list, never worked out from the schema: every table that carries `tenant_id`
would be swept up by anything that read the schema (users, settings, the number series, the
subscription, the audit log). `PRESERVED` names what is never touched; the dependency test
(`tests/integration/test_data_catalogue.py`) checks against `pg_constraint` that every table with
`tenant_id` is in exactly one of the two, that `blocked_by` is the real foreign-key graph and
that `ORDER` is a valid order.

`tables` are child first. `blocked_by` lists the kinds whose rows point at this kind through a
foreign key: they must be deleted first, and they are what a refused deletion names. The ledgers
have no foreign key to the documents that post them, so each document kind lists the ledger
`ref_type` values it posted (`stock_refs`, `party_refs`) and takes those rows with it; the
`ledgers` kind (what is left) is held back by `posted_by` until those kinds are gone.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class View:
    """Four identifying columns of the latest 25 rows. Never an amount."""

    labels: tuple[str, str, str, str]
    sql: str  # a SELECT of four text columns, newest first, with :t the company


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    tables: tuple[str, ...]
    headline: tuple[str, ...]
    view: View
    blocked_by: tuple[str, ...] = ()
    posted_by: tuple[str, ...] = ()
    stock_refs: tuple[str, ...] = ()
    party_refs: tuple[str, ...] = ()
    attachment_refs: tuple[str, ...] = ()
    files: tuple[tuple[str, str], ...] = ()  # (table, column) holding a stored file's key


def _view(a: str, b: str, c: str, d: str, sql: str) -> View:
    return View((a, b, c, d), sql)


CATALOGUE: tuple[Kind, ...] = (
    Kind(
        "attachments",
        "Attachments (and their files)",
        ("attachment",),
        ("attachment",),
        _view(
            "Id",
            "Attached to",
            "Kind",
            "File",
            "SELECT id::text, ref_type::text, kind::text, file_name FROM attachment "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
        files=(("attachment", "storage_key"),),
    ),
    Kind(
        "lost_sales",
        "Lost sales",
        ("lost_sale",),
        ("lost_sale",),
        _view(
            "Id",
            "Date",
            "Unit",
            "Note",
            "SELECT id::text, entry_date::text, unit, coalesce(note, '') FROM lost_sale "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
    ),
    Kind(
        "gstr2b",
        "GSTR-2B imports",
        ("gstr2b_import",),
        ("gstr2b_import",),
        _view(
            "Id",
            "Month",
            "File",
            "Rows",
            "SELECT id::text, period, file_name, row_count::text FROM gstr2b_import "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
    ),
    Kind(
        "quotes",
        "Quotations and proformas",
        ("sales_quote_line", "sales_quote"),
        ("sales_quote",),
        _view(
            "Number",
            "Kind",
            "Date",
            "Customer",
            "SELECT number, kind::text, quote_date::text, bill_to_name FROM sales_quote "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
    ),
    Kind(
        "lots",
        "Bill lots (batch picks)",
        ("sales_line_lot",),
        ("sales_line_lot",),
        _view(
            "Id",
            "Bill line",
            "Purchase line",
            "Made in",
            "SELECT id::text, sales_line_id::text, purchase_line_id::text, "
            "mfg_week::text || '/' || mfg_year::text FROM sales_line_lot "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
    ),
    Kind(
        "notes",
        "Credit and debit notes",
        ("credit_note_line", "credit_note", "debit_note_line", "debit_note"),
        ("credit_note", "debit_note"),
        _view(
            "Number",
            "Kind",
            "Date",
            "Reason",
            "SELECT number, kind, d, reason FROM ("
            "SELECT id, number, 'Credit note' AS kind, note_date::text AS d, "
            "coalesce(reason, '') AS reason, note_date AS sort FROM credit_note "
            "WHERE tenant_id = :t "
            "UNION ALL SELECT id, number, 'Debit note', note_date::text, coalesce(reason, ''), "
            "note_date FROM debit_note WHERE tenant_id = :t) n "
            "ORDER BY sort DESC, id DESC LIMIT 25",
        ),
        stock_refs=("sale_return", "purchase_return"),
        party_refs=("credit_note", "debit_note"),
    ),
    Kind(
        "transport",
        "Transport (vehicles and trips)",
        ("trip", "vehicle"),
        ("trip", "vehicle"),
        _view(
            "Kind",
            "Reference",
            "Date",
            "Detail",
            "SELECT kind, ref, d, detail FROM ("
            "SELECT 'Trip' AS kind, id::text AS ref, trip_date::text AS d, "
            "coalesce(from_place, '') || ' to ' || coalesce(to_place, '') AS detail, "
            "trip_date AS sort, id FROM trip WHERE tenant_id = :t "
            "UNION ALL SELECT 'Vehicle', number, '', coalesce(owner_name, ''), NULL, id "
            "FROM vehicle WHERE tenant_id = :t) x ORDER BY sort DESC NULLS LAST, id DESC LIMIT 25",
        ),
        party_refs=("freight",),
        attachment_refs=("trip",),
    ),
    Kind(
        "sales",
        "Sales bills (with e-way bills, IRNs, drop-ship links)",
        ("drop_ship_link", "eway_bill", "einvoice", "sales_line", "sales_invoice"),
        ("sales_invoice",),
        _view(
            "Number",
            "Date",
            "Status",
            "Customer",
            "SELECT number, invoice_date::text, status::text, bill_to_name FROM sales_invoice "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
        blocked_by=("quotes", "notes", "transport", "lots"),
        stock_refs=("sale",),
        party_refs=("sale",),
        attachment_refs=("sales_invoice",),
    ),
    Kind(
        "purchases",
        "Purchases (with costs, batches)",
        ("purchase_cost", "purchase_line", "purchase"),
        ("purchase",),
        _view(
            "Number",
            "Supplier bill",
            "Date",
            "Mode",
            "SELECT number, bill_no, bill_date::text, mode::text FROM purchase "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
        blocked_by=("notes", "lots", "sales", "transport"),
        stock_refs=("purchase",),
        party_refs=("purchase",),
        attachment_refs=("purchase",),
    ),
    Kind(
        "orders",
        "Purchase orders and goods receipts",
        ("goods_receipt_line", "goods_receipt", "purchase_order_line", "purchase_order"),
        ("purchase_order", "goods_receipt"),
        _view(
            "Number",
            "Kind",
            "Date",
            "Note",
            "SELECT number, kind, d, note FROM ("
            "SELECT id, number, 'Order' AS kind, order_date::text AS d, "
            "coalesce(note, '') AS note, order_date AS sort FROM purchase_order "
            "WHERE tenant_id = :t "
            "UNION ALL SELECT id, number, 'Goods receipt', receipt_date::text, coalesce(note, ''), "
            "receipt_date FROM goods_receipt WHERE tenant_id = :t) o "
            "ORDER BY sort DESC, id DESC LIMIT 25",
        ),
        blocked_by=("purchases",),
    ),
    Kind(
        "payments",
        "Payments and write-offs",
        ("payment", "bad_debt_writeoff"),
        ("payment", "bad_debt_writeoff"),
        _view(
            "Number",
            "Kind",
            "Date",
            "Reference",
            "SELECT number, kind, d, ref FROM ("
            "SELECT id, number, direction::text AS kind, payment_date::text AS d, "
            "coalesce(reference, '') AS ref, payment_date AS sort FROM payment "
            "WHERE tenant_id = :t "
            "UNION ALL SELECT id, number, 'Write-off', writeoff_date::text, '', writeoff_date "
            "FROM bad_debt_writeoff WHERE tenant_id = :t) p ORDER BY sort DESC, id DESC LIMIT 25",
        ),
        party_refs=("payment", "write_off"),
    ),
    Kind(
        "cashbook",
        "Cash book and expenses",
        ("cash_entry",),
        ("cash_entry",),
        _view(
            "Number",
            "Date",
            "Kind",
            "Paid to",
            "SELECT number, entry_date::text, kind::text, coalesce(paid_to, '') FROM cash_entry "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
    ),
    Kind(
        "closings",
        "Daily closings (and their PDFs)",
        ("daily_closing",),
        ("daily_closing",),
        _view(
            "Id",
            "Date",
            "Status",
            "Bills",
            "SELECT id::text, closing_date::text, status::text, invoices_count::text "
            "FROM daily_closing WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
        files=(("daily_closing", "pdf_key"),),
    ),
    Kind(
        "bank",
        "Bank statements and matches",
        ("bank_statement_line", "bank_statement"),
        ("bank_statement",),
        _view(
            "Id",
            "File",
            "From",
            "To",
            "SELECT id::text, filename, from_date::text, to_date::text FROM bank_statement "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
    ),
    Kind(
        "stock_ops",
        "Stock transfers, counts, adjustments and write-downs",
        (
            "stock_transfer_line",
            "stock_transfer",
            "stock_count_line",
            "stock_count",
            "stock_adjustment_line",
            "stock_adjustment",
            "stock_writedown_line",
            "stock_writedown",
        ),
        ("stock_transfer", "stock_count", "stock_adjustment", "stock_writedown"),
        _view(
            "Number",
            "Kind",
            "Date",
            "Note",
            "SELECT number, kind, d, note FROM ("
            "SELECT id, number, 'Transfer' AS kind, transfer_date::text AS d, "
            "coalesce(note, '') AS note, transfer_date AS sort FROM stock_transfer "
            "WHERE tenant_id = :t "
            "UNION ALL SELECT id, 'Count ' || id::text, 'Count', count_date::text, "
            "coalesce(note, ''), count_date FROM stock_count WHERE tenant_id = :t "
            "UNION ALL SELECT id, number, 'Adjustment', adjustment_date::text, "
            "coalesce(note, ''), adjustment_date FROM stock_adjustment WHERE tenant_id = :t "
            "UNION ALL SELECT id, number, 'Write-down', writedown_date::text, "
            "coalesce(note, ''), writedown_date FROM stock_writedown WHERE tenant_id = :t) s "
            "ORDER BY sort DESC, id DESC LIMIT 25",
        ),
        stock_refs=("transfer", "adjustment", "stock_adjustment", "stock_writedown"),
    ),
    Kind(
        "rates",
        "Rates, customer rates and supplier schemes",
        ("customer_rate", "market_rate", "supplier_scheme"),
        ("customer_rate", "market_rate", "supplier_scheme"),
        _view(
            "Kind",
            "Item or scheme",
            "Party",
            "From",
            "SELECT kind, name, party, d FROM ("
            "SELECT 'Customer rate' AS kind, i.name AS name, p.name AS party, "
            "r.valid_from::text AS d, r.id, r.valid_from AS sort FROM customer_rate r "
            "JOIN item i ON i.id = r.item_id JOIN party p ON p.id = r.party_id "
            "WHERE r.tenant_id = :t "
            "UNION ALL SELECT 'Market rate', i.name, '', r.effective_date::text, r.id, "
            "r.effective_date FROM market_rate r JOIN item i ON i.id = r.item_id "
            "WHERE r.tenant_id = :t "
            "UNION ALL SELECT 'Scheme', s.name, p.name, s.period_start::text, s.id, s.period_start "
            "FROM supplier_scheme s JOIN party p ON p.id = s.party_id WHERE s.tenant_id = :t) x "
            "ORDER BY sort DESC, id DESC LIMIT 25",
        ),
    ),
    Kind(
        "opening_balances",
        "Opening balances",
        ("opening_balance",),
        ("opening_balance",),
        _view(
            "Id",
            "Kind",
            "Status",
            "As of",
            "SELECT id::text, kind::text, status::text, as_of::text FROM opening_balance "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
        stock_refs=("opening",),
        party_refs=("opening",),
    ),
    Kind(
        "approvals",
        "Owner approvals",
        ("approval",),
        ("approval",),
        _view(
            "Id",
            "Action",
            "Reason",
            "Used on",
            "SELECT id::text, action::text, reason, coalesce(used_ref, '') FROM approval "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
        blocked_by=("cashbook", "purchases", "stock_ops"),
    ),
    Kind(
        "ledgers",
        "Stock and party ledgers",
        ("stock_ledger", "party_ledger"),
        ("stock_ledger", "party_ledger"),
        _view(
            "Ledger",
            "Posted by",
            "Date",
            "Reference",
            "SELECT ledger, ref, d, doc FROM ("
            "SELECT id, 'Stock' AS ledger, ref_type::text AS ref, entry_date::text AS d, "
            "coalesce(narration, '') AS doc, entry_date AS sort FROM stock_ledger "
            "WHERE tenant_id = :t "
            "UNION ALL SELECT id, 'Party', ref_type::text, entry_date::text, "
            "coalesce(doc_no, ''), entry_date FROM party_ledger WHERE tenant_id = :t) l "
            "ORDER BY sort DESC, id DESC LIMIT 25",
        ),
        posted_by=(
            "sales",
            "purchases",
            "notes",
            "payments",
            "stock_ops",
            "opening_balances",
            "transport",
        ),
    ),
    Kind(
        "items",
        "Items and units",
        ("item_margin", "item_unit", "item"),
        ("item",),
        _view(
            "Id",
            "Name",
            "Category",
            "Unit",
            "SELECT id::text, name, category::text, base_unit FROM item "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
        blocked_by=(
            "stock_ops",
            "purchases",
            "sales",
            "notes",
            "opening_balances",
            "rates",
            "quotes",
            "orders",
            "ledgers",
            "lost_sales",
        ),
    ),
    Kind(
        "parties",
        "Parties and sites",
        ("site", "party"),
        ("party",),
        _view(
            "Id",
            "Name",
            "Type",
            "GSTIN",
            "SELECT id::text, name, type::text, coalesce(gstin, '') FROM party "
            "WHERE tenant_id = :t ORDER BY id DESC LIMIT 25",
        ),
        blocked_by=(
            "approvals",
            "opening_balances",
            "rates",
            "purchases",
            "sales",
            "quotes",
            "notes",
            "payments",
            "orders",
            "transport",
            "ledgers",
        ),
    ),
)

KINDS: dict[str, Kind] = {k.key: k for k in CATALOGUE}
ORDER: tuple[str, ...] = tuple(k.key for k in CATALOGUE)
LABELS: dict[str, str] = {k.key: k.label for k in CATALOGUE}
TABLES: frozenset[str] = frozenset(t for k in CATALOGUE for t in k.tables)

PRESERVED: frozenset[str] = frozenset(
    {
        # The company, its people and its shops.
        "app_user",
        "auth_session",
        "user_location",
        "location",
        "shop_settings",
        # Reconciled, never deleted (the series exist; the counters of emptied ones are reset).
        "document_sequence",
        "document_sequence_event",
        "company_counter",
        # Set-up lists a company starts with: cost heads, expense heads, bank accounts, Tally names.
        "cost_component",
        "expense_category",
        "bank_account",
        "tally_ledger",
        # Duolink's own records about the company.
        "subscription",
        "subscription_payment",
        "support_ticket",
        "support_message",
        "audit_log",
        "platform_audit_log",
        # The owner's support grants and Duolink's visits to the company (M23), append-only.
        "support_access_grant",
        "support_session",
        "support_session_event",
    }
)
