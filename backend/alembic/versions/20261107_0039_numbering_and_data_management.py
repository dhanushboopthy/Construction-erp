"""numbering and data management

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-07 09:00:00.000000+00:00

M26: a Super Admin sets a company's number series and deletes its business data.

- `document_sequence_event` records each audited change to a series (a Super Admin set it, or a
  data deletion reset it). It belongs to a company, so it carries `tenant_id`, row-level security
  (`tenant_isolation`, as in 0024) and the `platform_admin` policy (as in 0025). It is
  append-only: the `forbid_ledger_change` trigger refuses UPDATE and DELETE, except inside the
  purge switch of 0038 (company restore, data management).
- The purge switch itself was built in 0038 and is reused as it is.
- The CHECK on `platform_audit_log.action` is widened by hand; the downgrade narrows it with
  NOT VALID because the log is append-only (see 0030).

Parallel branch: before merging, set `down_revision` to the head of the branch merged before it,
and make `ACTIONS_OLD` in this migration equal that head's `ACTIONS_NEW`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

ACTIONS_OLD = (
    "login",
    "login_failed",
    "logout",
    "token_reuse",
    "tenant_create",
    "tenant_update",
    "tenant_suspend",
    "tenant_reactivate",
    "user_activate",
    "user_deactivate",
    "user_unlock",
    "user_reset_password",
    "user_sign_out",
    "staff_create",
    "staff_update",
    "staff_reset_password",
    "staff_unlock",
    "staff_sign_out",
    "password_change",
    "tenant_cancel",
    "tenant_seller_update",
    "tenant_logo_set",
    "tenant_logo_remove",
    "user_update",
    "user_session_revoke",
    "user_remove",
    "plan_create",
    "plan_update",
    "plan_duplicate",
    "plan_archive",
    "plan_delete",
    "subscription_renew",
    "subscription_cancel",
    "payment_reverse",
    "support_reply",
    "support_update",
    "maintenance_on",
    "maintenance_off",
    "audit_export",
    "backup_create",
    "backup_download",
    "backup_upload",
    "backup_delete",
    "backup_restore",
    "backup_restore_failed",
    "backup_schedule_update",
)
ACTIONS_NEW = ACTIONS_OLD + (
    "numbering_set",
    "company_data_deleted",
    "company_data_deleted_all",
    "company_data_delete_failed",
)
CHECK_NAME = "ck_platform_audit_log_platform_action"
DOC_TYPES = (
    "sales_invoice",
    "credit_note",
    "debit_note",
    "delivery_challan",
    "purchase_entry",
    "payment_receipt",
    "cash_voucher",
    "stock_adjustment",
    "bad_debt_writeoff",
    "stock_writedown",
    "purchase_order",
    "goods_receipt",
    "quotation",
    "proforma",
)


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_sequence_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("doc_type", _enum("doc_type", *DOC_TYPES), nullable=False),
        sa.Column("financial_year", sa.String(length=5), nullable=False),
        sa.Column("change", _enum("sequence_change", "set", "reset"), nullable=False),
        sa.Column("from_value", sa.Integer(), nullable=False),
        sa.Column("to_value", sa.Integer(), nullable=False),
        sa.Column("floor_value", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_document_sequence_event_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["location.id"],
            name=op.f("fk_document_sequence_event_location_id_location"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_sequence_event")),
    )
    op.create_index(
        "ix_document_sequence_event_series",
        "document_sequence_event",
        ["tenant_id", "location_id", "doc_type", "financial_year"],
    )
    op.execute(
        "CREATE TRIGGER document_sequence_event_append_only BEFORE UPDATE OR DELETE "
        "ON document_sequence_event FOR EACH ROW EXECUTE FUNCTION forbid_ledger_change()"
    )
    op.execute("ALTER TABLE document_sequence_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_sequence_event FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON document_sequence_event "
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int)"
    )
    op.execute(
        "CREATE POLICY platform_admin ON document_sequence_event "
        "USING (current_setting('app.platform', true) = 'on')"
    )

    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS document_sequence_event_append_only ON document_sequence_event"
    )
    op.drop_table("document_sequence_event")
