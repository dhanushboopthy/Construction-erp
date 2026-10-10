"""labelled rate overrides

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-10 02:07:15.822064+00:00

FM3 (docs/FINANCE_REVIEW.md F4): an owner-typed price is saved as rate_source 'override' with
a reason, and every line keeps the list rate the system proposed, so the leakage report is
exact. Hand edits: the rate_source CHECK is widened (Alembic does not diff CHECKs); a CHECK
makes the reason mandatory for an override. Adding nullable columns rewrites no issued row, so
the issued-document triggers of migration 0014 stay untouched; bills issued before FM3 keep a
blank list rate and are never edited.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_OLD = "rate_source IN ('customer', 'market')"
SOURCE_NEW = "rate_source IN ('customer', 'market', 'override')"


def _swap_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    op.add_column(
        "sales_line", sa.Column("list_rate", sa.Numeric(precision=14, scale=6), nullable=True)
    )
    op.add_column(
        "sales_line", sa.Column("rate_override_reason", sa.String(length=200), nullable=True)
    )
    _swap_check("ck_sales_line_rate_source", "sales_line", SOURCE_NEW)
    op.create_check_constraint(
        op.f("ck_sales_line_override_has_reason"),
        "sales_line",
        "rate_source <> 'override' OR "
        "(rate_override_reason IS NOT NULL AND btrim(rate_override_reason) <> '')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_sales_line_override_has_reason"), "sales_line", type_="check")
    # Overridden lines cannot keep a source the old CHECK refuses; they fall back to market.
    op.execute("ALTER TABLE sales_line DISABLE TRIGGER USER")
    op.execute("UPDATE sales_line SET rate_source = 'market' WHERE rate_source = 'override'")
    op.execute("ALTER TABLE sales_line ENABLE TRIGGER USER")
    _swap_check("ck_sales_line_rate_source", "sales_line", SOURCE_OLD)
    op.drop_column("sales_line", "rate_override_reason")
    op.drop_column("sales_line", "list_rate")
