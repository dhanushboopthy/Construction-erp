"""platform maintenance

Revision ID: 0037
Revises: 0035
Create Date: 2026-11-05 09:00:00.000000+00:00

M24: system health, the notifications bell, maintenance mode and the audit log.

- `platform_maintenance` is the operator's maintenance switch: one row (CHECK id = 1), inserted
  here switched off. It is platform-only (no tenant_id, no company owns it), like
  `platform_plan`, so it has no row-level security; the app role reads it before any company is
  known.
- The CHECK on `platform_audit_log.action` is widened by hand for `maintenance_on`,
  `maintenance_off` and `audit_export`; the downgrade narrows it with NOT VALID because the log is
  append-only (see 0030).

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
ACTIONS_NEW = ACTIONS_OLD + ("maintenance_on", "maintenance_off", "audit_export")
CHECK_NAME = "ck_platform_audit_log_platform_action"


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0037"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_maintenance",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(length=200), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_platform_maintenance_singleton")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_maintenance")),
    )
    op.execute("INSERT INTO platform_maintenance (id, enabled) VALUES (1, false)")

    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.drop_table("platform_maintenance")
