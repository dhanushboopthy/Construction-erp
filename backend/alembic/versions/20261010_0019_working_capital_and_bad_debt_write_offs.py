"""working capital and bad debt write offs

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-10 02:37:25.785029+00:00

FM5 (docs/FINANCE_REVIEW.md F7-F9): bad-debt write-off documents and the provision percentage
by overdue bucket. Hand edits: the party ledger gains the ref type 'write_off' and the number
series gains 'bad_debt_writeoff' (Alembic does not diff CHECKs, so both are widened and
narrowed again on downgrade); write-offs get the issued-document triggers of migration 0014.
Downgrading removes the write-off ledger rows, which only a database restore could bring back.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PARTY_REF_OLD = (
    "ref_type IN ('opening', 'sale', 'purchase', 'payment', 'credit_note', 'debit_note', "
    "'rebate', 'freight')"
)
PARTY_REF_NEW = (
    "ref_type IN ('opening', 'sale', 'purchase', 'payment', 'credit_note', 'debit_note', "
    "'rebate', 'freight', 'write_off')"
)
DOC_TYPE_OLD = (
    "doc_type IN ('sales_invoice', 'credit_note', 'debit_note', 'delivery_challan', "
    "'purchase_entry', 'payment_receipt', 'cash_voucher', 'stock_adjustment')"
)
DOC_TYPE_NEW = (
    "doc_type IN ('sales_invoice', 'credit_note', 'debit_note', 'delivery_challan', "
    "'purchase_entry', 'payment_receipt', 'cash_voucher', 'stock_adjustment', "
    "'bad_debt_writeoff')"
)


def _swap_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    op.create_table(
        "bad_debt_writeoff",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("party_id", sa.Integer(), nullable=False),
        sa.Column("writeoff_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("balance_before", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("tenant_id", sa.Integer(), server_default="1", nullable=False),
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
        sa.CheckConstraint("amount > 0", name=op.f("ck_bad_debt_writeoff_positive_amount")),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["location.id"],
            name=op.f("fk_bad_debt_writeoff_location_id_location"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["party_id"],
            ["party.id"],
            name=op.f("fk_bad_debt_writeoff_party_id_party"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bad_debt_writeoff")),
        sa.UniqueConstraint(
            "tenant_id", "number", name=op.f("uq_bad_debt_writeoff_tenant_id_number")
        ),
    )
    op.create_index(
        "ix_bad_debt_writeoff_party",
        "bad_debt_writeoff",
        ["party_id", "writeoff_date"],
        unique=False,
    )
    op.add_column(
        "shop_settings",
        sa.Column(
            "provision_pct_current",
            sa.Numeric(precision=5, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "shop_settings",
        sa.Column(
            "provision_pct_1_15",
            sa.Numeric(precision=5, scale=2),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "shop_settings",
        sa.Column(
            "provision_pct_16_30",
            sa.Numeric(precision=5, scale=2),
            server_default="2",
            nullable=False,
        ),
    )
    op.add_column(
        "shop_settings",
        sa.Column(
            "provision_pct_31_60",
            sa.Numeric(precision=5, scale=2),
            server_default="10",
            nullable=False,
        ),
    )
    op.add_column(
        "shop_settings",
        sa.Column(
            "provision_pct_over_60",
            sa.Numeric(precision=5, scale=2),
            server_default="50",
            nullable=False,
        ),
    )
    _swap_check("ck_party_ledger_party_ref", "party_ledger", PARTY_REF_NEW)
    _swap_check("ck_document_sequence_doc_type", "document_sequence", DOC_TYPE_NEW)
    # A write-off is an issued document (ADR 0010): never deleted, figures never edited.
    op.execute(
        "CREATE TRIGGER bad_debt_writeoff_no_delete BEFORE DELETE ON bad_debt_writeoff "
        "FOR EACH ROW EXECUTE FUNCTION forbid_issued_delete()"
    )
    op.execute(
        "CREATE TRIGGER bad_debt_writeoff_no_edit BEFORE UPDATE ON bad_debt_writeoff "
        "FOR EACH ROW EXECUTE FUNCTION forbid_issued_edit()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS bad_debt_writeoff_no_edit ON bad_debt_writeoff")
    op.execute("DROP TRIGGER IF EXISTS bad_debt_writeoff_no_delete ON bad_debt_writeoff")
    # The ledger is append-only; its guard is lifted for this one removal.
    op.execute("ALTER TABLE party_ledger DISABLE TRIGGER USER")
    op.execute("DELETE FROM party_ledger WHERE ref_type = 'write_off'")
    op.execute("ALTER TABLE party_ledger ENABLE TRIGGER USER")
    op.execute("DELETE FROM document_sequence WHERE doc_type = 'bad_debt_writeoff'")
    _swap_check("ck_document_sequence_doc_type", "document_sequence", DOC_TYPE_OLD)
    _swap_check("ck_party_ledger_party_ref", "party_ledger", PARTY_REF_OLD)
    op.drop_column("shop_settings", "provision_pct_over_60")
    op.drop_column("shop_settings", "provision_pct_31_60")
    op.drop_column("shop_settings", "provision_pct_16_30")
    op.drop_column("shop_settings", "provision_pct_1_15")
    op.drop_column("shop_settings", "provision_pct_current")
    op.drop_index("ix_bad_debt_writeoff_party", table_name="bad_debt_writeoff")
    op.drop_table("bad_debt_writeoff")
