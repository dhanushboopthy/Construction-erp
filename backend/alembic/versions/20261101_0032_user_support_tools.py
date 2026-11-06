"""user support tools

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-01 09:00:00.000000+00:00

M19: `app_user.mobile` and `app_user.removed_at` (a removed account stays as a name on old
documents), and `auth_session.signed_in_at` (the first sign-in of a chain of refreshed
sessions, for the sessions list). All three are nullable, so no existing row is rewritten. No
new table, so no new row-level security policy. The CHECK on `platform_audit_log.action` is
widened by hand; the downgrade narrows it with NOT VALID because the log is append-only (see 0030).
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
    "tenant_cancel",
    "tenant_seller_update",
    "tenant_logo_set",
    "tenant_logo_remove",
)
ACTIONS_NEW = ACTIONS_OLD + ("user_update", "user_session_revoke", "user_remove")
CHECK_NAME = "ck_platform_audit_log_platform_action"


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("mobile", sa.String(length=20), nullable=True))
    op.add_column("app_user", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "auth_session", sa.Column("signed_in_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.drop_column("auth_session", "signed_in_at")
    op.drop_column("app_user", "removed_at")
    op.drop_column("app_user", "mobile")
