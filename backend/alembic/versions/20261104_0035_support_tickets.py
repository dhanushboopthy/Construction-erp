"""support tickets

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-04 09:00:00.000000+00:00

M22: a company raises a question from inside the ERP and Duolink answers it from the admin.

- `support_ticket`, `support_message` and `company_counter` belong to a company, so each carries
  `tenant_id`, row-level security (`tenant_isolation`, as in 0024) and the `platform_admin`
  policy (as in 0025).
- `support_message` is append-only: the `forbid_ledger_change` trigger of 0003 refuses UPDATE and
  DELETE.
- `company_counter` is the gapless counter for the ticket number (T-000012), per company: tickets
  belong to the company, not to a shop, so the location-based series does not fit.
- The CHECK on `platform_audit_log.action` is widened by hand; the downgrade narrows it with
  NOT VALID because the log is append-only (see 0030).
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
)
ACTIONS_NEW = ACTIONS_OLD + ("support_reply", "support_update")
CHECK_NAME = "ck_platform_audit_log_platform_action"
TABLES = ("support_ticket", "support_message", "company_counter")


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(
        *values, name=name, native_enum=False, create_constraint=True, length=32
    )


revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_counter",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_company_counter_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("tenant_id", "name", name=op.f("pk_company_counter")),
    )
    op.create_table(
        "support_ticket",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column(
            "category",
            _enum("support_category", "sign_in", "billing", "gst_eway", "stock", "printing", "other"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            _enum("support_priority", "low", "normal", "high", "urgent"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum(
                "support_status",
                "open",
                "in_progress",
                "waiting_on_company",
                "resolved",
                "closed",
            ),
            nullable=False,
        ),
        sa.Column("raised_by_user_id", sa.Integer(), nullable=False),
        sa.Column("assigned_admin_id", sa.Integer(), nullable=True),
        sa.Column("last_reply_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("company_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_support_ticket_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["raised_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_support_ticket_raised_by_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_support_ticket_assigned_admin_id_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_ticket")),
    )
    op.create_index(
        "uq_support_ticket_tenant_number", "support_ticket", ["tenant_id", "number"], unique=True
    )
    op.create_index("ix_support_ticket_tenant_status", "support_ticket", ["tenant_id", "status"])
    op.create_index(
        op.f("ix_support_ticket_raised_by_user_id"), "support_ticket", ["raised_by_user_id"]
    )
    op.create_table(
        "support_message",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "author_kind",
            _enum("support_author_kind", "company_user", "platform_admin"),
            nullable=False,
        ),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("author_admin_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(author_kind = 'company_user' AND author_user_id IS NOT NULL "
            "AND author_admin_id IS NULL) OR "
            "(author_kind = 'platform_admin' AND author_admin_id IS NOT NULL "
            "AND author_user_id IS NULL)",
            name=op.f("ck_support_message_author_matches_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_support_message_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["support_ticket.id"],
            name=op.f("fk_support_message_ticket_id_support_ticket"),
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["app_user.id"],
            name=op.f("fk_support_message_author_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["author_admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_support_message_author_admin_id_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_message")),
    )
    op.create_index(op.f("ix_support_message_ticket_id"), "support_message", ["ticket_id"])

    # Messages are append-only, like the ledgers (0003).
    op.execute(
        "CREATE TRIGGER support_message_append_only BEFORE UPDATE OR DELETE "
        "ON support_message FOR EACH ROW EXECUTE FUNCTION forbid_ledger_change()"
    )

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

    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.execute("DROP TRIGGER IF EXISTS support_message_append_only ON support_message")
    op.drop_table("support_message")
    op.drop_table("support_ticket")
    op.drop_table("company_counter")
