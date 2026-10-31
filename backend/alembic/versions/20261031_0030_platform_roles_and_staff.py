"""platform roles and staff

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-31 12:08:05.504064+00:00

M17 (ADR 0013): Duolink staff get a role (`super_admin` or `support`), a mobile number and a
"must change password" flag. Hand edits:

- Every admin that exists today becomes `super_admin`, because before this milestone every admin
  could change everything. New staff default to `support` (the column default).
- `platform_audit_log.target_admin_id` names the staff member an action was done to.
- The CHECK on `platform_audit_log.action` is widened by hand (autogenerate does not diff it).
  The log is append-only, so the downgrade narrows it with NOT VALID: rows already written keep
  their new action names and only new rows are checked.
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
)
ACTIONS_NEW = ACTIONS_OLD + (
    "staff_create",
    "staff_update",
    "staff_reset_password",
    "staff_unlock",
    "staff_sign_out",
    "password_change",
)
CHECK_NAME = "ck_platform_audit_log_platform_action"


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("platform_admin", sa.Column("mobile", sa.String(length=20), nullable=True))
    op.add_column(
        "platform_admin",
        sa.Column(
            "role",
            sa.Enum(
                "super_admin",
                "support",
                name="platform_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="support",
            nullable=False,
        ),
    )
    op.add_column(
        "platform_admin",
        sa.Column(
            "must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column("platform_audit_log", sa.Column("target_admin_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_platform_audit_log_target_admin_id_platform_admin"),
        "platform_audit_log",
        "platform_admin",
        ["target_admin_id"],
        ["id"],
    )
    op.execute("UPDATE platform_admin SET role = 'super_admin'")
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.drop_constraint(
        op.f("fk_platform_audit_log_target_admin_id_platform_admin"),
        "platform_audit_log",
        type_="foreignkey",
    )
    op.drop_column("platform_audit_log", "target_admin_id")
    op.drop_column("platform_admin", "must_change_password")
    op.drop_column("platform_admin", "role")
    op.drop_column("platform_admin", "mobile")
