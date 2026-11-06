"""a user's own keyboard shortcuts

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-13 09:00:00.000000+00:00

Each user can change the keyboard shortcuts of the company app (Ctrl+Shift+Alt+1 opens the
editor). Only the changes are stored, one row per action; the defaults stay in the frontend.

- `user_shortcut` belongs to a company, so it carries `tenant_id`, row-level security
  (`tenant_isolation`, as in 0024) and the `platform_admin` policy (as in 0025).
- A user has at most one shortcut per action and at most one action per combination.
- Removing a user removes their shortcuts (ON DELETE CASCADE).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "user_shortcut"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.String(length=60), nullable=False),
        sa.Column("combo", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name=op.f("fk_user_shortcut_tenant_id_tenant")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_shortcut_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_shortcut")),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "action_id",
            name=op.f("uq_user_shortcut_tenant_id_user_id_action_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "combo", name=op.f("uq_user_shortcut_tenant_id_user_id_combo")
        ),
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


def downgrade() -> None:
    op.drop_table(TABLE)
