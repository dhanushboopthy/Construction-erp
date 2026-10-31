"""company profile

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-31 12:39:53.861387+00:00

M18: Duolink's own record of each company (owner contact, city, state, internal notes, last
activity, when it was closed) on `tenant`; PAN and CIN on `shop_settings`; and
`app_user.must_change_password` for an owner onboarded with a temporary password. All columns are
nullable or have a default, so no existing row is rewritten. `tenant.state_code` is filled from
each company's shop settings. No new table, so no new row-level security policy. The CHECK on
`platform_audit_log.action` is widened by hand; the downgrade narrows it with NOT VALID because
the log is append-only (see 0030).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


# The values of ck_platform_audit_log_platform_action before and after this migration.
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
)
ACTIONS_NEW = ACTIONS_OLD + (
    "tenant_cancel",
    "tenant_seller_update",
    "tenant_logo_set",
    "tenant_logo_remove",
)
CHECK_NAME = "ck_platform_audit_log_platform_action"


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column("shop_settings", sa.Column("pan", sa.String(length=10), nullable=True))
    op.add_column("shop_settings", sa.Column("cin", sa.String(length=21), nullable=True))
    op.add_column("tenant", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenant", sa.Column("cancelled_reason", sa.Text(), nullable=True))
    op.add_column("tenant", sa.Column("owner_name", sa.String(length=100), nullable=True))
    op.add_column("tenant", sa.Column("owner_email", sa.String(length=200), nullable=True))
    op.add_column("tenant", sa.Column("owner_mobile", sa.String(length=20), nullable=True))
    op.add_column("tenant", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("tenant", sa.Column("state_code", sa.String(length=2), nullable=True))
    op.add_column("tenant", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "tenant", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE tenant SET state_code = s.state_code "
        "FROM shop_settings s WHERE s.tenant_id = tenant.id"
    )
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(
        op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW)
    )


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.drop_column("tenant", "last_activity_at")
    op.drop_column("tenant", "notes")
    op.drop_column("tenant", "state_code")
    op.drop_column("tenant", "city")
    op.drop_column("tenant", "owner_mobile")
    op.drop_column("tenant", "owner_email")
    op.drop_column("tenant", "owner_name")
    op.drop_column("tenant", "cancelled_reason")
    op.drop_column("tenant", "cancelled_at")
    op.drop_column("shop_settings", "cin")
    op.drop_column("shop_settings", "pan")
    op.drop_column("app_user", "must_change_password")
