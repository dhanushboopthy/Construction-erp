"""app update generation

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-05 09:00:00.000000+00:00

M29: the ERP installs as an app, and Duolink can ask every open browser to look for a new build.

- `platform_app_update` is one row for the whole platform (a CHECK keeps it at id 1): the release
  generation, when it was last forced and by whom. No company owns it, so it has no `tenant_id`
  and no row-level security, like `platform_plan` (0033). Every company reads the generation from
  GET /tenant; only the admin API (Super Admin) changes it.
- The row is created here at generation 0.
- The CHECK on `platform_audit_log.action` is widened by hand for `app_update_force`; the
  downgrade narrows it with NOT VALID because the log is append-only (see 0030).
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
    "maintenance_on",
    "maintenance_off",
    "audit_export",
    "backup_create",
    "backup_download",
    "backup_upload",
    "backup_delete",
    "backup_restore",
    "backup_restore_failed",
    "backup_schedule_update",
    "numbering_set",
    "company_data_deleted",
    "company_data_deleted_all",
    "company_data_delete_failed",
    "integration_connect",
    "integration_test",
    "integration_disconnect",
    "integration_limits",
    "gstin_lookup",
    "bill_template_upload",
    "bill_template_activate",
    "bill_template_deactivate",
    "bill_template_delete",
    "secondary_logo_set",
    "secondary_logo_remove",
)
ACTIONS_NEW = ACTIONS_OLD + ("app_update_force",)
CHECK_NAME = "ck_platform_audit_log_platform_action"


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_app_update",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("forced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forced_by", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_platform_app_update_singleton")),
        sa.CheckConstraint(
            "generation >= 0", name=op.f("ck_platform_app_update_generation_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["forced_by"],
            ["platform_admin.id"],
            name=op.f("fk_platform_app_update_forced_by_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_app_update")),
    )
    op.execute("INSERT INTO platform_app_update (id, generation) VALUES (1, 0)")

    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    op.drop_table("platform_app_update")
