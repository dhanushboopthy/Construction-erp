"""subscriptions and payments

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-03 09:00:00.000000+00:00

M21: every company gets a subscription with an end date, and Duolink records renewals by hand.

- `subscription` (one per company) and `subscription_payment` belong to a company, so both carry
  `tenant_id`, row-level security (`tenant_isolation`, as in 0024) and the `platform_admin`
  policy (as in 0025).
- `subscription_payment` is append-only: the `forbid_ledger_change` trigger of 0003 refuses
  UPDATE and DELETE. A mistaken payment is corrected by a negative row that points at it.
- Existing companies get a subscription from `tenant.status`, `tenant.plan_id` and
  `trial_ends_at`: a trial ends when its trial ends; any other company gets an expiry one year
  from this migration and is flagged `needs_review` for Duolink to confirm.
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
)
ACTIONS_NEW = ACTIONS_OLD + ("subscription_renew", "subscription_cancel", "payment_reverse")
CHECK_NAME = "ck_platform_audit_log_platform_action"
TABLES = ("subscription", "subscription_payment")


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscription",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("duration_value", sa.Integer(), nullable=True),
        sa.Column("duration_unit", sa.String(length=10), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "trial",
                "active",
                "expired",
                "cancelled",
                name="subscription_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_subscription_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["platform_plan.id"], name=op.f("fk_subscription_plan_id_platform_plan")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_subscription_tenant_id")),
    )
    op.create_index(op.f("ix_subscription_plan_id"), "subscription", ["plan_id"])
    op.create_index(op.f("ix_subscription_expires_at"), "subscription", ["expires_at"])

    op.create_table(
        "subscription_payment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "method",
            sa.Enum(
                "cash",
                "bank",
                "upi",
                "cheque",
                "razorpay",
                name="payment_method",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverses_id", sa.Integer(), nullable=True),
        sa.Column("recorded_by_admin_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_subscription_payment_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscription.id"],
            name=op.f("fk_subscription_payment_subscription_id_subscription"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["platform_plan.id"],
            name=op.f("fk_subscription_payment_plan_id_platform_plan"),
        ),
        sa.ForeignKeyConstraint(
            ["reverses_id"],
            ["subscription_payment.id"],
            name=op.f("fk_subscription_payment_reverses_id_subscription_payment"),
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_subscription_payment_recorded_by_admin_id_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_payment")),
    )
    op.create_index(
        op.f("ix_subscription_payment_subscription_id"), "subscription_payment", ["subscription_id"]
    )
    op.create_index(op.f("ix_subscription_payment_paid_at"), "subscription_payment", ["paid_at"])
    op.create_index(
        "uq_subscription_payment_reverses_id",
        "subscription_payment",
        ["reverses_id"],
        unique=True,
        postgresql_where=sa.text("reverses_id IS NOT NULL"),
    )

    # Payments are append-only, like the stock and party ledgers (0003).
    op.execute(
        "CREATE TRIGGER subscription_payment_append_only BEFORE UPDATE OR DELETE "
        "ON subscription_payment FOR EACH ROW EXECUTE FUNCTION forbid_ledger_change()"
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
    # Tables made after 0024 already get the app role's grants from its default privileges.

    # One subscription per existing company. A trial ends with its trial; any other company is
    # given a year from now, flagged for Duolink to confirm.
    op.execute(
        """
        INSERT INTO subscription
            (tenant_id, plan_id, status, starts_at, expires_at, needs_review)
        SELECT id, plan_id,
               CASE WHEN status = 'trial' THEN 'trial' ELSE 'active' END,
               created_at,
               CASE WHEN status = 'trial'
                    THEN coalesce(trial_ends_at, now() + interval '14 days')
                    ELSE now() + interval '1 year' END,
               status <> 'trial'
        FROM tenant
        """
    )

    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.execute("DROP TRIGGER IF EXISTS subscription_payment_append_only ON subscription_payment")
    op.drop_table("subscription_payment")
    op.drop_table("subscription")
