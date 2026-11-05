"""online renewal through Razorpay

Revision ID: 0043
Revises: 0035
Create Date: 2026-11-12 09:00:00.000000+00:00

M30: a company owner renews online and the payment lands as a subscription payment by itself.

- `subscription_order` (one row per Razorpay order an owner asked for) belongs to a company, so
  it carries `tenant_id`, row-level security (`tenant_isolation`, as in 0024) and the
  `platform_admin` policy (as in 0025): the webhook finds the order across companies.
- `subscription_payment.recorded_by_admin_id` may be blank, for an online payment only (a CHECK
  says so); a reversal is always made by an admin.
- A unique index on `subscription_payment.reference` for method `razorpay` makes applying a
  payment idempotent: the same Razorpay payment id lands once. The upgrade stops, with the rows
  named, if hand-recorded Razorpay payments already share a reference.
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
)
ACTIONS_NEW = ACTIONS_OLD + ("subscription_pay_online",)
CHECK_NAME = "ck_platform_audit_log_platform_action"
ONLINE_CHECK = "ck_subscription_payment_recorded_by_admin_or_online"
REFERENCE_INDEX = "uq_subscription_payment_razorpay_reference"
TABLE = "subscription_order"


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0043"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("price_id", sa.Integer(), nullable=True),
        sa.Column("duration_value", sa.Integer(), nullable=False),
        sa.Column("duration_unit", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("razorpay_order_id", sa.String(length=40), nullable=False),
        sa.Column("receipt", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "created",
                "paid",
                name="subscription_order_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("razorpay_payment_id", sa.String(length=40), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_via", sa.String(length=10), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_subscription_order_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscription.id"],
            name=op.f("fk_subscription_order_subscription_id_subscription"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["platform_plan.id"], name=op.f("fk_subscription_order_plan_id_platform_plan")
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["subscription_payment.id"],
            name=op.f("fk_subscription_order_payment_id_subscription_payment"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_subscription_order_created_by_user_id_app_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_order")),
        sa.UniqueConstraint("razorpay_order_id", name=op.f("uq_subscription_order_razorpay_order_id")),
    )
    op.create_index(
        op.f("ix_subscription_order_subscription_id"), TABLE, ["subscription_id"], unique=False
    )

    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {TABLE} "
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int)"
    )
    op.execute(
        f"CREATE POLICY platform_admin ON {TABLE} "
        "USING (current_setting('app.platform', true) = 'on')"
    )

    # An online payment has no Duolink admin behind it.
    op.alter_column(
        "subscription_payment", "recorded_by_admin_id", existing_type=sa.Integer(), nullable=True
    )
    op.create_check_constraint(
        op.f(ONLINE_CHECK),
        "subscription_payment",
        "recorded_by_admin_id IS NOT NULL OR (method = 'razorpay' AND reverses_id IS NULL)",
    )

    # One row per Razorpay payment id. Hand-recorded Razorpay rows that share a reference would
    # break the index; payments are append-only, so say which they are and stop.
    clashes = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT reference, string_agg(id::text, ', ' ORDER BY id) FROM subscription_payment "
                "WHERE method = 'razorpay' AND reference IS NOT NULL "
                "GROUP BY reference HAVING count(*) > 1"
            )
        )
        .all()
    )
    if clashes:
        listed = "; ".join(f"{ref!r}: payments {ids}" for ref, ids in clashes)
        raise RuntimeError(
            "Razorpay payments recorded by hand share a reference, so the payment id cannot be "
            f"made unique: {listed}. Reverse the duplicates and record them again with a "
            "distinct reference, then run the migration again."
        )
    op.create_index(
        REFERENCE_INDEX,
        "subscription_payment",
        ["reference"],
        unique=True,
        postgresql_where=sa.text("method = 'razorpay'"),
    )

    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.drop_index(REFERENCE_INDEX, table_name="subscription_payment")
    op.drop_constraint(op.f(ONLINE_CHECK), "subscription_payment", type_="check")
    # Online payments (no admin) are kept: payments are append-only. If there are any, the
    # column stays nullable rather than refusing the downgrade or deleting receipt records.
    online = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM subscription_payment WHERE recorded_by_admin_id IS NULL")
        )
        .scalar_one()
    )
    if not online:
        op.alter_column(
            "subscription_payment",
            "recorded_by_admin_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
    op.drop_index(op.f("ix_subscription_order_subscription_id"), table_name=TABLE)
    op.drop_table(TABLE)
