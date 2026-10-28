"""quotations and proforma invoices

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-27 12:00:00.000000+00:00

`sales_quote` and `sales_quote_line`: a quotation (estimate) or a proforma invoice, priced like
a bill but not a tax invoice. No stock or account entries. Each kind has its own number series
(`quotation`, `proforma` in `document_sequence`).

Hand edits: row-level security and the `tenant_isolation` policy (as migration 0023), and the
`platform_admin` policy (as migration 0024), on both tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("sales_quote", "sales_quote_line")

DOC_TYPE_OLD = (
    "doc_type IN ('sales_invoice', 'credit_note', 'debit_note', 'delivery_challan', "
    "'purchase_entry', 'payment_receipt', 'cash_voucher', 'stock_adjustment', "
    "'bad_debt_writeoff', 'stock_writedown', 'purchase_order', 'goods_receipt')"
)
DOC_TYPE_NEW = (
    "doc_type IN ('sales_invoice', 'credit_note', 'debit_note', 'delivery_challan', "
    "'purchase_entry', 'payment_receipt', 'cash_voucher', 'stock_adjustment', "
    "'bad_debt_writeoff', 'stock_writedown', 'purchase_order', 'goods_receipt', "
    "'quotation', 'proforma')"
)


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _money(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, sa.Numeric(precision=14, scale=2), nullable=False)


def _swap_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    op.create_table(
        "sales_quote",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", _enum("quote_kind", "quotation", "proforma"), nullable=False),
        sa.Column("number", sa.String(length=16), nullable=False),
        sa.Column("financial_year", sa.String(length=5), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("party_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("bill_to_name", sa.String(length=150), nullable=False),
        sa.Column("bill_to_address", sa.Text(), nullable=False),
        sa.Column("bill_to_gstin", sa.String(length=15), nullable=True),
        sa.Column("ship_to_name", sa.String(length=150), nullable=True),
        sa.Column("ship_to_address", sa.Text(), nullable=True),
        sa.Column("place_of_supply", sa.String(length=2), nullable=False),
        sa.Column(
            "supply_kind", _enum("supply_kind", "intra_state", "inter_state"), nullable=False
        ),
        sa.Column("supply_type", _enum("supply_type", "B2B", "B2C"), nullable=False),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        _money("taxable_value"),
        _money("cgst"),
        _money("sgst"),
        _money("igst"),
        _money("round_off"),
        _money("grand_total"),
        sa.Column("remark", sa.String(length=300), nullable=True),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["sales_invoice.id"],
            name=op.f("fk_sales_quote_invoice_id_sales_invoice"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["location.id"],
            name=op.f("fk_sales_quote_location_id_location"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["party_id"],
            ["party.id"],
            name=op.f("fk_sales_quote_party_id_party"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"], ["site.id"], name=op.f("fk_sales_quote_site_id_site"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_sales_quote_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_quote")),
        sa.UniqueConstraint("tenant_id", "number", name=op.f("uq_sales_quote_tenant_id_number")),
    )
    op.create_index("ix_sales_quote_date", "sales_quote", ["quote_date"], unique=False)
    op.create_table(
        "sales_quote_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("quote_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=150), nullable=False),
        sa.Column("hsn", sa.String(length=8), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("base_qty", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("base_unit", sa.String(length=16), nullable=False),
        sa.Column("rate", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column(
            "rate_source", _enum("rate_source", "customer", "market", "override"), nullable=False
        ),
        sa.Column("rate_override_reason", sa.String(length=200), nullable=True),
        _money("discount"),
        sa.Column("discount_reason", sa.String(length=200), nullable=True),
        _money("taxable"),
        sa.Column("gst_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        _money("cgst"),
        _money("sgst"),
        _money("igst"),
        _money("line_total"),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("base_qty > 0", name=op.f("ck_sales_quote_line_positive_qty")),
        sa.ForeignKeyConstraint(
            ["item_id"], ["item.id"], name=op.f("fk_sales_quote_line_item_id_item"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["sales_quote.id"],
            name=op.f("fk_sales_quote_line_quote_id_sales_quote"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_sales_quote_line_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_quote_line")),
        sa.UniqueConstraint(
            "quote_id", "line_no", name=op.f("uq_sales_quote_line_quote_id_line_no")
        ),
    )
    _swap_check("ck_document_sequence_doc_type", "document_sequence", DOC_TYPE_NEW)

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int)"
        )
        op.execute(
            f"CREATE POLICY platform_admin ON {table} "
            "USING (current_setting('app.platform', true) = 'on')"
        )


def downgrade() -> None:
    op.execute("DELETE FROM document_sequence WHERE doc_type IN ('quotation', 'proforma')")
    _swap_check("ck_document_sequence_doc_type", "document_sequence", DOC_TYPE_OLD)
    op.drop_table("sales_quote_line")
    op.drop_index("ix_sales_quote_date", table_name="sales_quote")
    op.drop_table("sales_quote")
