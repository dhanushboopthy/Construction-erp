"""gsp and gstin lookup admin

Revision ID: 0040
Revises: 0036
Create Date: 2026-11-09 09:00:00.000000+00:00

M27: Duolink's shared GSP account and the GSTIN lookup are configured, tested, limited and
watched from the admin.

- `platform_integration` (one row per kind, both seeded here with the default limits) and
  `gstin_cache` (public registry data) are platform-only: no tenant_id, so no row-level
  security, like `platform_plan` (0033). Credentials are stored as a Fernet token, never plain.
- `integration_call` counts calls per company. It carries tenant_id (blank for a Duolink admin's
  own call), so it gets row-level security with the `tenant_isolation` (0024) and
  `platform_admin` (0025) policies. It has no column for a request or response body.
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
    "support_session_start",
    "support_session_end",
)
ACTIONS_NEW = ACTIONS_OLD + (
    "integration_connect",
    "integration_test",
    "integration_disconnect",
    "integration_limits",
    "gstin_lookup",
)
CHECK_NAME = "ck_platform_audit_log_platform_action"
KINDS = ("gsp", "gstin_lookup")


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


revision: str = "0040"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    integration = op.create_table(
        "platform_integration",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", _enum("integration_kind", *KINDS), nullable=False),
        sa.Column(
            "provider",
            _enum("integration_provider", "fake", "sandbox", "live"),
            nullable=True,
        ),
        sa.Column("base_url", sa.String(length=300), server_default="", nullable=False),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("key_last4", sa.String(length=4), nullable=True),
        sa.Column(
            "status",
            _enum("integration_status", "not_connected", "connected", "failing"),
            server_default="not_connected",
            nullable=False,
        ),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_by", sa.Integer(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_message", sa.String(length=200), nullable=True),
        sa.Column("daily_limit", sa.Integer(), server_default="50", nullable=False),
        sa.Column("monthly_limit", sa.Integer(), server_default="500", nullable=False),
        sa.Column("warn_at_percent", sa.Integer(), server_default="80", nullable=False),
        sa.Column("cache_hours", sa.Integer(), server_default="168", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["connected_by"],
            ["platform_admin.id"],
            name=op.f("fk_platform_integration_connected_by_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_integration")),
        sa.UniqueConstraint("kind", name=op.f("uq_platform_integration_kind")),
    )
    op.bulk_insert(integration, [{"kind": kind} for kind in KINDS])

    op.create_table(
        "gstin_cache",
        sa.Column("gstin", sa.String(length=15), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("trade_name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("gstin", name=op.f("pk_gstin_cache")),
    )

    op.create_table(
        "integration_call",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("kind", _enum("integration_kind", *KINDS), nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column(
            "outcome",
            _enum("integration_outcome", "ok", "failed", "cached", "blocked"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_integration_call_tenant_id_tenant")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_call")),
    )
    op.create_index(
        "ix_integration_call_tenant_kind_at", "integration_call", ["tenant_id", "kind", "at"]
    )
    op.create_index("ix_integration_call_kind_at", "integration_call", ["kind", "at"])

    op.execute("ALTER TABLE integration_call ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE integration_call FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON integration_call "
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int)"
    )
    op.execute(
        "CREATE POLICY platform_admin ON integration_call "
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
    op.drop_index("ix_integration_call_kind_at", table_name="integration_call")
    op.drop_index("ix_integration_call_tenant_kind_at", table_name="integration_call")
    op.drop_table("integration_call")
    op.drop_table("gstin_cache")
    op.drop_table("platform_integration")
