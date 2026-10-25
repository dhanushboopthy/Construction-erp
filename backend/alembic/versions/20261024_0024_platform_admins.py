"""platform admins

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-24 12:00:00.000000+00:00

M16 (ADR 0012): Duolink's own admins, their sign-in sessions and an append-only log of what they
do. Hand edits:

- `platform_audit_log` gets the append-only trigger of migration 0003 (`forbid_ledger_change`).
- Every table with `tenant_id` gets a second, permissive policy `platform_admin`: rows of every
  company are visible when the transaction sets `app.platform = on`. Only the platform-admin
  dependency sets it (`core/tenancy.set_platform`). Policies combine with OR, so
  `tenant_isolation` is unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = "platform_admin"

ACTIONS = (
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
)


def _tenant_tables() -> list[str]:
    rows = op.get_bind().execute(
        sa.text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'tenant_id' "
            "AND table_name NOT IN ('tenant', 'platform_audit_log') ORDER BY table_name"
        )
    )
    return [r[0] for r in rows]


def upgrade() -> None:
    op.create_table(
        "platform_admin",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_admin")),
        sa.UniqueConstraint("email", name=op.f("uq_platform_admin_email")),
    )
    op.create_table(
        "platform_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_platform_session_admin_id_platform_admin"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_platform_session_token_hash")),
    )
    op.create_index(
        op.f("ix_platform_session_admin_id"), "platform_session", ["admin_id"], unique=False
    )
    op.create_table(
        "platform_audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                *ACTIONS,
                name="platform_action",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_platform_audit_log_admin_id_platform_admin"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_platform_audit_log_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_audit_log")),
    )
    op.create_index(op.f("ix_platform_audit_log_at"), "platform_audit_log", ["at"], unique=False)
    op.create_index(
        op.f("ix_platform_audit_log_admin_id"), "platform_audit_log", ["admin_id"], unique=False
    )
    op.create_index(
        op.f("ix_platform_audit_log_tenant_id"), "platform_audit_log", ["tenant_id"], unique=False
    )
    op.execute(
        "CREATE TRIGGER platform_audit_log_append_only BEFORE UPDATE OR DELETE "
        "ON platform_audit_log FOR EACH ROW EXECUTE FUNCTION forbid_ledger_change()"
    )

    for table in _tenant_tables():
        op.execute(
            f"CREATE POLICY {POLICY} ON {table} "
            "USING (current_setting('app.platform', true) = 'on')"
        )


def downgrade() -> None:
    for table in _tenant_tables():
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table}")
    op.execute("DROP TRIGGER IF EXISTS platform_audit_log_append_only ON platform_audit_log")
    op.drop_index(op.f("ix_platform_audit_log_tenant_id"), table_name="platform_audit_log")
    op.drop_index(op.f("ix_platform_audit_log_admin_id"), table_name="platform_audit_log")
    op.drop_index(op.f("ix_platform_audit_log_at"), table_name="platform_audit_log")
    op.drop_table("platform_audit_log")
    op.drop_index(op.f("ix_platform_session_admin_id"), table_name="platform_session")
    op.drop_table("platform_session")
    op.drop_table("platform_admin")
