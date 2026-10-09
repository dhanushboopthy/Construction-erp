"""issued documents are permanent

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-10 09:00:00+00:00

Hand written. Issued documents are never deleted, and their figures are never edited in place
(B16, G15): corrections are credit and debit notes. The application already behaves this way;
these triggers make the database refuse anything else, including a mistake in a script or a
console session.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Never deleted.
NO_DELETE = [
    "sales_invoice",
    "sales_line",
    "credit_note",
    "credit_note_line",
    "debit_note",
    "debit_note_line",
    "purchase",
    "purchase_line",
    "purchase_cost",
    "payment",
    "stock_transfer",
    "stock_transfer_line",
    "drop_ship_link",
    "eway_bill",
    "einvoice",
    "daily_closing",
    "attachment",
    "gstr2b_import",
]

# Never changed after saving (only the bookkeeping columns may move).
NO_EDIT = [
    "sales_invoice",
    "sales_line",
    "credit_note",
    "credit_note_line",
    "debit_note",
    "debit_note_line",
    "purchase_line",
    "purchase_cost",
    "payment",
    "attachment",
    "gstr2b_import",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION forbid_issued_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is an issued document: it cannot be deleted. Use a credit or debit note.',
                TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION forbid_issued_edit() RETURNS trigger AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'updated_at' - 'updated_by')
               IS DISTINCT FROM (to_jsonb(OLD) - 'updated_at' - 'updated_by') THEN
                RAISE EXCEPTION '% is an issued document: it cannot be changed. Use a credit or debit note.',
                    TG_TABLE_NAME;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in NO_DELETE:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_issued_delete()"
        )
    for table in NO_EDIT:
        op.execute(
            f"CREATE TRIGGER {table}_no_edit BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_issued_edit()"
        )


def downgrade() -> None:
    for table in NO_EDIT:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_edit ON {table}")
    for table in NO_DELETE:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
    op.execute("DROP FUNCTION IF EXISTS forbid_issued_edit()")
    op.execute("DROP FUNCTION IF EXISTS forbid_issued_delete()")
