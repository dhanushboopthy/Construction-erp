"""support access

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-05 09:00:00.000000+00:00

M23: owner-granted support access ("Login as Company", with consent). The owner grants Duolink
access for a fixed time; a Super Admin may then open a read-only support session at the company.

- `support_access_grant`, `support_session` and `support_session_event` belong to a company, so
  each carries `tenant_id`, row-level security (`tenant_isolation`, as in 0024) and the
  `platform_admin` policy (as in 0025).
- `support_session_event` is append-only: the `forbid_ledger_change` trigger of 0003 refuses
  UPDATE and DELETE.
- The CHECKs on `audit_log.action` (two new company events) and `platform_audit_log.action` (two
  new admin actions) are widened by hand; the downgrade narrows them with NOT VALID because both
  logs keep their rows (see 0030).

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
)
ACTIONS_NEW = ACTIONS_OLD + ("support_session_start", "support_session_end")
CHECK_NAME = "ck_platform_audit_log_platform_action"

AUDIT_OLD = (
    "insert",
    "update",
    "delete",
    "login",
    "login_failed",
    "logout",
    "token_reuse",
    "override",
    "export",
)
AUDIT_NEW = AUDIT_OLD + ("support_enter", "support_exit")
AUDIT_CHECK = "ck_audit_log_audit_action"

TABLES = ("support_access_grant", "support_session", "support_session_event")


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_access_grant",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("include_costs", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_support_access_grant_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_support_access_grant_granted_by_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_support_access_grant_revoked_by_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["support_ticket.id"],
            name=op.f("fk_support_access_grant_ticket_id_support_ticket"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_access_grant")),
    )
    op.create_index(
        "ix_support_access_grant_tenant_ends", "support_access_grant", ["tenant_id", "ends_at"]
    )
    op.create_table(
        "support_session",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("grant_id", sa.Integer(), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "end_reason",
            sa.Enum(
                "exited",
                "revoked",
                "grant_ended",
                "replaced",
                "admin_not_allowed",
                name="support_session_end",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_support_session_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            ["support_access_grant.id"],
            name=op.f("fk_support_session_grant_id_support_access_grant"),
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_support_session_admin_id_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_session")),
    )
    op.create_index(
        "ix_support_session_tenant_started", "support_session", ["tenant_id", "started_at"]
    )
    op.create_index(op.f("ix_support_session_grant_id"), "support_session", ["grant_id"])
    op.create_index(op.f("ix_support_session_admin_id"), "support_session", ["admin_id"])
    op.create_table(
        "support_session_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("refused", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_support_session_event_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["support_session.id"],
            name=op.f("fk_support_session_event_session_id_support_session"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_session_event")),
    )
    op.create_index(
        op.f("ix_support_session_event_session_id"), "support_session_event", ["session_id"]
    )

    # Every request of a support session stays on record, like the ledgers (0003).
    op.execute(
        "CREATE TRIGGER support_session_event_append_only BEFORE UPDATE OR DELETE "
        "ON support_session_event FOR EACH ROW EXECUTE FUNCTION forbid_ledger_change()"
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
    op.drop_constraint(op.f(AUDIT_CHECK), "audit_log", type_="check")
    op.create_check_constraint(op.f(AUDIT_CHECK), "audit_log", _in_list(AUDIT_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(AUDIT_CHECK), "audit_log", type_="check")
    op.execute(
        f"ALTER TABLE audit_log ADD CONSTRAINT {AUDIT_CHECK} "
        f"CHECK ({_in_list(AUDIT_OLD)}) NOT VALID"
    )
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.execute("DROP TRIGGER IF EXISTS support_session_event_append_only ON support_session_event")
    op.drop_table("support_session_event")
    op.drop_table("support_session")
    op.drop_table("support_access_grant")
