"""controls period lock and bank statements

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-10 03:26:59.367159+00:00

FM7 (docs/FINANCE_REVIEW.md F16-F18): bank accounts and imported statements (the statement and
its lines are permanent records with the issued-document triggers of migration 0014), the period
lock date and the exception-report thresholds on the shop settings. No enum or number series
changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ISSUED = ("bank_statement", "bank_statement_line")


def upgrade() -> None:
    op.create_table(
        "bank_account",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("account_no_last4", sa.String(length=4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_account")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_bank_account_tenant_id_name")),
    )
    op.create_table(
        "bank_statement",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bank_account_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("closing_balance", sa.Numeric(precision=14, scale=2), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["bank_account_id"],
            ["bank_account.id"],
            name=op.f("fk_bank_statement_bank_account_id_bank_account"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_statement")),
        sa.UniqueConstraint(
            "tenant_id",
            "bank_account_id",
            "file_sha256",
            name=op.f("uq_bank_statement_tenant_id_bank_account_id_file_sha256"),
        ),
    )
    op.create_table(
        "bank_statement_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("statement_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("line_date", sa.Date(), nullable=False),
        sa.Column("narration", sa.String(length=300), nullable=False),
        sa.Column("reference", sa.String(length=60), nullable=False),
        sa.Column("debit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("credit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("balance", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("tenant_id", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "debit >= 0 AND credit >= 0 AND debit + credit > 0",
            name=op.f("ck_bank_statement_line_one_amount"),
        ),
        sa.ForeignKeyConstraint(
            ["statement_id"],
            ["bank_statement.id"],
            name=op.f("fk_bank_statement_line_statement_id_bank_statement"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_statement_line")),
    )
    op.create_index(
        "ix_bank_statement_line_date", "bank_statement_line", ["line_date"], unique=False
    )
    op.add_column("shop_settings", sa.Column("locked_through", sa.Date(), nullable=True))
    op.add_column(
        "shop_settings",
        sa.Column("bank_match_days", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "shop_settings",
        sa.Column(
            "exception_round_amount",
            sa.Numeric(precision=14, scale=2),
            server_default="1000.00",
            nullable=False,
        ),
    )
    op.add_column(
        "shop_settings",
        sa.Column("exception_count_days", sa.Integer(), server_default="2", nullable=False),
    )
    op.add_column(
        "shop_settings",
        sa.Column("exception_returns_count", sa.Integer(), server_default="4", nullable=False),
    )
    op.add_column(
        "shop_settings",
        sa.Column("exception_returns_days", sa.Integer(), server_default="30", nullable=False),
    )
    op.add_column(
        "shop_settings",
        sa.Column(
            "exception_cash_near_pct",
            sa.Numeric(precision=5, scale=2),
            server_default="80",
            nullable=False,
        ),
    )
    op.add_column(
        "shop_settings",
        sa.Column("exception_shortage_count", sa.Integer(), server_default="3", nullable=False),
    )
    for table in ISSUED:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_issued_delete()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_edit BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_issued_edit()"
        )


def downgrade() -> None:
    for table in ISSUED:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_edit ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
    op.drop_column("shop_settings", "exception_shortage_count")
    op.drop_column("shop_settings", "exception_cash_near_pct")
    op.drop_column("shop_settings", "exception_returns_days")
    op.drop_column("shop_settings", "exception_returns_count")
    op.drop_column("shop_settings", "exception_count_days")
    op.drop_column("shop_settings", "exception_round_amount")
    op.drop_column("shop_settings", "bank_match_days")
    op.drop_column("shop_settings", "locked_through")
    op.drop_index("ix_bank_statement_line_date", table_name="bank_statement_line")
    op.drop_table("bank_statement_line")
    op.drop_table("bank_statement")
    op.drop_table("bank_account")
