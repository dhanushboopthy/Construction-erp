"""backup and recovery

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-06 09:00:00.000000+00:00

M25: backup and recovery from the admin, including one company.

- `platform_backup`, `platform_backup_job` and `platform_backup_schedule` are platform-only (no
  `tenant_id`; the company a backup belongs to is `company_id`), so they have no row-level
  security and a company session never reads them. The schedule row is inserted here.
- The purge switch. `forbid_ledger_change()`, `forbid_issued_delete()` and `forbid_issued_edit()`
  are redefined to let a row go (or change) only when BOTH `app.platform` and `app.data_purge`
  are `on` in the transaction. Only the company restore (and M26's data management) sets
  `app.data_purge`, with `set_config(..., true)`. Every other session is refused as before.
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
    "maintenance_on",
    "maintenance_off",
    "audit_export",
)
ACTIONS_NEW = ACTIONS_OLD + (
    "backup_create",
    "backup_download",
    "backup_upload",
    "backup_delete",
    "backup_restore",
    "backup_restore_failed",
    "backup_schedule_update",
)
CHECK_NAME = "ck_platform_audit_log_platform_action"


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PURGE_ON = (
    "current_setting('app.platform', true) = 'on' "
    "AND current_setting('app.data_purge', true) = 'on'"
)


def upgrade() -> None:
    op.create_table(
        "platform_backup",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", _enum("backup_kind", "platform", "company"), nullable=False),
        sa.Column(
            "source",
            _enum("backup_source", "scheduled", "manual", "safety", "uploaded"),
            nullable=False,
        ),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("files_name", sa.String(length=200), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("schema_revision", sa.String(length=32), nullable=True),
        sa.Column(
            "status", _enum("backup_status", "running", "verified", "failed"), nullable=False
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("protected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind = 'platform' OR company_id IS NOT NULL",
            name=op.f("ck_platform_backup_company_named"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["tenant.id"], name=op.f("fk_platform_backup_company_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_platform_backup_created_by_admin_id_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_backup")),
        sa.UniqueConstraint("file_name", name=op.f("uq_platform_backup_file_name")),
    )
    op.create_index(op.f("ix_platform_backup_company_id"), "platform_backup", ["company_id"])
    op.create_index("ix_platform_backup_started_at", "platform_backup", ["started_at"])

    op.create_table(
        "platform_backup_job",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "kind",
            _enum("backup_job_kind", "backup_platform", "backup_company", "restore_company"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("backup_job_status", "queued", "running", "succeeded", "failed"),
            nullable=False,
        ),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("backup_id", sa.Integer(), nullable=True),
        sa.Column("safety_backup_id", sa.Integer(), nullable=True),
        sa.Column("requested_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("step", sa.String(length=100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["company_id"], ["tenant.id"], name=op.f("fk_platform_backup_job_company_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["backup_id"],
            ["platform_backup.id"],
            name=op.f("fk_platform_backup_job_backup_id_platform_backup"),
        ),
        sa.ForeignKeyConstraint(
            ["safety_backup_id"],
            ["platform_backup.id"],
            name=op.f("fk_platform_backup_job_safety_backup_id_platform_backup"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_platform_backup_job_requested_by_admin_id_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_backup_job")),
    )
    op.create_index(op.f("ix_platform_backup_job_company_id"), "platform_backup_job", ["company_id"])

    op.create_table(
        "platform_backup_schedule",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("daily_time", sa.String(length=5), server_default="02:30", nullable=False),
        sa.Column("keep_daily", sa.Integer(), server_default="30", nullable=False),
        sa.Column("keep_weekly", sa.Integer(), server_default="8", nullable=False),
        sa.Column("keep_monthly", sa.Integer(), server_default="12", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("updated_by_admin_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_platform_backup_schedule_singleton")),
        sa.ForeignKeyConstraint(
            ["updated_by_admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_platform_backup_schedule_updated_by_admin_id_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_backup_schedule")),
    )
    op.execute("INSERT INTO platform_backup_schedule (id) VALUES (1)")

    # The purge switch: ledgers, issued documents and their edits may be removed only inside a
    # platform session that has also set app.data_purge (company restore, M26 data management).
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION forbid_ledger_change() RETURNS trigger AS $$
        BEGIN
            IF {PURGE_ON} THEN
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END IF;
            RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION forbid_issued_delete() RETURNS trigger AS $$
        BEGIN
            IF {PURGE_ON} THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION '% is an issued document: it cannot be deleted. Use a credit or debit note.',
                TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION forbid_issued_edit() RETURNS trigger AS $$
        BEGIN
            IF {PURGE_ON} THEN
                RETURN NEW;
            END IF;
            IF (to_jsonb(NEW) - 'updated_at' - 'updated_by')
               IS DISTINCT FROM (to_jsonb(OLD) - 'updated_at' - 'updated_by') THEN
                RAISE EXCEPTION '% is an issued document: it cannot be changed. Use a credit or debit note.',
                    TG_TABLE_NAME;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
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

    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_ledger_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_issued_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is an issued document: it cannot be deleted. Use a credit or debit note.',
                TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION forbid_issued_edit() RETURNS trigger AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'updated_at' - 'updated_by')
               IS DISTINCT FROM (to_jsonb(OLD) - 'updated_at' - 'updated_by') THEN
                RAISE EXCEPTION '% is an issued document: it cannot be changed. Use a credit or debit note.',
                    TG_TABLE_NAME;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    op.drop_table("platform_backup_schedule")
    op.drop_table("platform_backup_job")
    op.drop_table("platform_backup")
