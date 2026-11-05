"""bill templates per company

Revision ID: 0041
Revises: 0035
Create Date: 2026-11-10 09:00:00.000000+00:00

Parallel branch: before merging, set `down_revision` to the head of the branch merged before it,
and make `ACTIONS_OLD` in this migration equal that head's `ACTIONS_NEW`.

M28: Duolink gives a company its own bill design (tax invoice, proforma, quotation, credit note,
debit note) as uploaded HTML, and a second logo.

- `bill_template` and `bill_template_asset` belong to a company, so each carries `tenant_id`,
  row-level security (`tenant_isolation`, as in 0024) and the `platform_admin` policy (as in
  0025). One active design per slot per company is a partial unique index.
- `bill_template_id` is added to `sales_invoice`, `sales_quote`, `credit_note` and `debit_note`:
  nullable, no default, so no row is rewritten and the issued-document triggers of 0014 are not
  fired. It is set once, at insert, to the design the document was issued with; null is the
  built-in layout. A design a document points at cannot be deleted (RESTRICT).
- `shop_settings` gets the second logo columns.
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
    "subscription_renew",
    "subscription_cancel",
    "payment_reverse",
    "support_reply",
    "support_update",
)
ACTIONS_NEW = ACTIONS_OLD + (
    "bill_template_upload",
    "bill_template_activate",
    "bill_template_deactivate",
    "bill_template_delete",
    "secondary_logo_set",
    "secondary_logo_remove",
)
CHECK_NAME = "ck_platform_audit_log_platform_action"
TABLES = ("bill_template", "bill_template_asset")
PINNED = ("sales_invoice", "sales_quote", "credit_note", "debit_note")


def _in_list(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{v}'" for v in values) + ")"


revision: str = "0041"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bill_template",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "slot",
            sa.Enum(
                "tax_invoice",
                "proforma",
                "quotation",
                "credit_note",
                "debit_note",
                name="bill_slot",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("html_key", sa.String(length=200), nullable=False),
        sa.Column("html_sha256", sa.String(length=64), nullable=False),
        sa.Column("html_size", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("uploaded_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("removed", sa.JSON(), nullable=False),
        sa.Column("secondary_logo_key", sa.String(length=200), nullable=True),
        sa.Column("secondary_logo_type", sa.String(length=20), nullable=True),
        sa.Column("secondary_logo_sha256", sa.String(length=64), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_bill_template_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_admin_id"],
            ["platform_admin.id"],
            name=op.f("fk_bill_template_uploaded_by_admin_id_platform_admin"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bill_template")),
        sa.UniqueConstraint(
            "tenant_id", "slot", "version", name=op.f("uq_bill_template_tenant_id_slot_version")
        ),
    )
    op.create_index(
        "uq_bill_template_active_slot",
        "bill_template",
        ["tenant_id", "slot"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "bill_template_asset",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_bill_template_asset_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["bill_template.id"],
            name=op.f("fk_bill_template_asset_template_id_bill_template"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bill_template_asset")),
        sa.UniqueConstraint(
            "template_id", "name", name=op.f("uq_bill_template_asset_template_id_name")
        ),
    )
    op.create_index(
        op.f("ix_bill_template_asset_template_id"), "bill_template_asset", ["template_id"]
    )

    for table in PINNED:
        op.add_column(table, sa.Column("bill_template_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_bill_template_id_bill_template"),
            table,
            "bill_template",
            ["bill_template_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.add_column("shop_settings", sa.Column("secondary_logo_key", sa.String(200), nullable=True))
    op.add_column("shop_settings", sa.Column("secondary_logo_type", sa.String(20), nullable=True))
    op.add_column(
        "shop_settings", sa.Column("secondary_logo_sha256", sa.String(64), nullable=True)
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

    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.create_check_constraint(op.f(CHECK_NAME), "platform_audit_log", _in_list(ACTIONS_NEW))


def downgrade() -> None:
    op.drop_constraint(op.f(CHECK_NAME), "platform_audit_log", type_="check")
    op.execute(
        f"ALTER TABLE platform_audit_log ADD CONSTRAINT {CHECK_NAME} "
        f"CHECK ({_in_list(ACTIONS_OLD)}) NOT VALID"
    )
    for column in ("secondary_logo_sha256", "secondary_logo_type", "secondary_logo_key"):
        op.drop_column("shop_settings", column)
    for table in PINNED:
        op.drop_constraint(
            op.f(f"fk_{table}_bill_template_id_bill_template"), table, type_="foreignkey"
        )
        op.drop_column(table, "bill_template_id")
    op.drop_table("bill_template_asset")
    op.drop_table("bill_template")
