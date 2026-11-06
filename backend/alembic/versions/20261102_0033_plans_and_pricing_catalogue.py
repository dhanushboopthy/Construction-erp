"""plans and pricing catalogue

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-02 09:00:00.000000+00:00

M20: what Duolink sells becomes data. `platform_plan` and `platform_plan_price` are platform-only
tables (no tenant_id, so no row-level security: no company owns a plan). The three plans that
were code (TRIAL, BASIC, PRO) are seeded with the same limits, and `tenant.plan` (an enum) is
replaced by `tenant.plan_id`, so every company keeps exactly the limits it had. The seeded prices
are 0.00 placeholders for Duolink to edit; nothing charges anyone until M21. The CHECK on
`platform_audit_log.action` is widened by hand; the downgrade narrows it with NOT VALID because
the log is append-only (see 0030).
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

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
)
ACTIONS_NEW = ACTIONS_OLD + (
    "plan_create",
    "plan_update",
    "plan_duplicate",
    "plan_archive",
    "plan_delete",
)
CHECK_NAME = "ck_platform_audit_log_platform_action"

ALL_FEATURES = ["EWAY_BILL", "GST_EXPORTS", "TALLY_EXPORT", "MULTI_SHOP", "ATTACHMENTS"]
# (code, name, short description, max users, max locations, features, popular, sort, price terms)
SEED = (
    (
        "TRIAL",
        "Trial",
        "Try everything for two weeks.",
        5,
        2,
        ALL_FEATURES,
        False,
        1,
        (14, "day"),
    ),
    (
        "BASIC",
        "Basic",
        "One shop and a godown, for a small team.",
        10,
        3,
        ["EWAY_BILL", "GST_EXPORTS", "ATTACHMENTS"],
        False,
        2,
        (1, "month"),
    ),
    (
        "PRO",
        "Pro",
        "Several shops, every report and export.",
        50,
        10,
        ALL_FEATURES,
        True,
        3,
        (1, "month"),
    ),
)


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_plan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("short_description", sa.String(length=200), nullable=False),
        sa.Column("long_description", sa.Text(), nullable=False),
        sa.Column("max_users", sa.Integer(), nullable=False),
        sa.Column("max_locations", sa.Integer(), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_popular", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_plan")),
        sa.UniqueConstraint("code", name=op.f("uq_platform_plan_code")),
    )
    # Only one plan is "popular" at a time (archiving a plan clears its flag in the service).
    op.create_index(
        "uq_platform_plan_one_popular",
        "platform_plan",
        ["is_popular"],
        unique=True,
        postgresql_where=sa.text("is_popular"),
    )
    op.create_table(
        "platform_plan_price",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("duration_value", sa.Integer(), nullable=False),
        sa.Column(
            "duration_unit",
            sa.Enum(
                "day",
                "month",
                "year",
                name="plan_duration_unit",
                native_enum=False,
                create_constraint=True,
                length=32,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("currency = 'INR'", name=op.f("ck_platform_plan_price_currency_inr")),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["platform_plan.id"], name=op.f("fk_platform_plan_price_plan_id_platform_plan")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_plan_price")),
        sa.UniqueConstraint(
            "plan_id",
            "duration_value",
            "duration_unit",
            name=op.f("uq_platform_plan_price_plan_id_duration_value_duration_unit"),
        ),
    )
    op.create_index(
        op.f("ix_platform_plan_price_plan_id"), "platform_plan_price", ["plan_id"], unique=False
    )

    conn = op.get_bind()
    for code, name, short, users, locations, features, popular, order, (value, unit) in SEED:
        plan_id = conn.execute(
            sa.text(
                "INSERT INTO platform_plan (code, name, short_description, long_description, "
                "max_users, max_locations, features, is_active, is_popular, sort_order) "
                "VALUES (:code, :name, :short, '', :users, :locations, CAST(:features AS jsonb), "
                "true, :popular, :sort) RETURNING id"
            ),
            {
                "code": code,
                "name": name,
                "short": short,
                "users": users,
                "locations": locations,
                "features": json.dumps(features),
                "popular": popular,
                "sort": order,
            },
        ).scalar_one()
        conn.execute(
            sa.text(
                "INSERT INTO platform_plan_price (plan_id, duration_value, duration_unit, price, "
                "currency, is_active, sort_order) "
                "VALUES (:plan, :value, :unit, 0.00, 'INR', true, 1)"
            ),
            {"plan": plan_id, "value": value, "unit": unit},
        )

    op.add_column("tenant", sa.Column("plan_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE tenant SET plan_id = (SELECT p.id FROM platform_plan p "
        "WHERE p.code = upper(tenant.plan))"
    )
    op.alter_column("tenant", "plan_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_tenant_plan_id_platform_plan"), "tenant", "platform_plan", ["plan_id"], ["id"]
    )
    op.create_index(op.f("ix_tenant_plan_id"), "tenant", ["plan_id"], unique=False)
    op.drop_column("tenant", "plan")  # its CHECK goes with it

    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.add_column(
        "tenant",
        sa.Column(
            "plan",
            sa.Enum(
                "trial",
                "basic",
                "pro",
                name="tenant_plan",
                native_enum=False,
                create_constraint=True,
                length=32,
                validate_strings=True,
            ),
            nullable=True,
        ),
    )
    # A plan Duolink added since has no old name: those companies go back to basic.
    op.execute(
        "UPDATE tenant SET plan = CASE WHEN p.code IN ('TRIAL', 'BASIC', 'PRO') "
        "THEN lower(p.code) ELSE 'basic' END "
        "FROM platform_plan p WHERE p.id = tenant.plan_id"
    )
    op.alter_column("tenant", "plan", nullable=False)
    op.drop_index(op.f("ix_tenant_plan_id"), table_name="tenant")
    op.drop_constraint(op.f("fk_tenant_plan_id_platform_plan"), "tenant", type_="foreignkey")
    op.drop_column("tenant", "plan_id")
    op.drop_index(op.f("ix_platform_plan_price_plan_id"), table_name="platform_plan_price")
    op.drop_table("platform_plan_price")
    op.drop_index("uq_platform_plan_one_popular", table_name="platform_plan")
    op.drop_table("platform_plan")
