"""tenants and row level security

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-24 09:00:00.000000+00:00

M15 (ADR 0011): many companies in one database.

- New table `tenant`. Today's company becomes tenant 1 (slug DEFAULT_TENANT_SLUG, else "main"),
  named after its shop settings, active on the pro plan.
- Every `tenant_id` column loses its default of 1 and gets a foreign key to `tenant`.
- Row-level security on every table with `tenant_id`: a row is visible and writable only when
  it belongs to the company in `app.tenant_id`, which the app sets in every transaction.
  FORCE makes the policy apply to the table owner as well.
- `user_location` rows (written by the ORM's many-to-many link) take their user's company in a
  BEFORE INSERT trigger.
- Role `erp_app` (no login, no superuser): the app's connections switch to it so the policies
  apply (superusers always skip them). Migrations keep running as the connecting user.

Hand-written: Alembic does not diff policies, grants or roles. Downgrade removes the policies,
grants and foreign keys and restores the default of 1; the role is left in place because other
databases on the server (the test database) may still use it.
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "erp_app"
POLICY = "tenant_isolation"


def _tenant_tables() -> list[str]:
    rows = op.get_bind().execute(
        sa.text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'tenant_id' "
            "AND table_name <> 'tenant' ORDER BY table_name"
        )
    )
    return [r[0] for r in rows]


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "trial",
                "active",
                "suspended",
                "cancelled",
                name="tenant_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
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
            ),
            nullable=False,
        ),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_users", sa.Integer(), nullable=True),
        sa.Column("max_locations", sa.Integer(), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenant_slug")),
    )

    slug = (os.environ.get("DEFAULT_TENANT_SLUG") or "main").strip().lower()
    op.execute(
        sa.text(
            "INSERT INTO tenant (id, slug, name, status, plan) VALUES (1, :slug, "
            "coalesce((SELECT coalesce(trade_name, legal_name) FROM shop_settings "
            "WHERE tenant_id = 1), 'Main'), 'active', 'pro')"
        ).bindparams(slug=slug)
    )
    op.execute("SELECT setval(pg_get_serial_sequence('tenant', 'id'), 1)")

    for table in _tenant_tables():
        op.alter_column(table, "tenant_id", server_default=None)
        op.create_foreign_key(
            op.f(f"fk_{table}_tenant_id_tenant"), table, "tenant", ["tenant_id"], ["id"]
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {POLICY} ON {table} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::int)"
        )

    # user_location rows are written by the ORM's many-to-many relationship, which knows nothing
    # of tenant_id: they take the company of their user.
    op.execute(
        """
        CREATE FUNCTION user_location_tenant() RETURNS trigger AS $$
        BEGIN
            IF NEW.tenant_id IS NULL THEN
                NEW.tenant_id := (SELECT tenant_id FROM app_user WHERE id = NEW.user_id);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER user_location_tenant BEFORE INSERT ON user_location "
        "FOR EACH ROW EXECUTE FUNCTION user_location_tenant()"
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )
    op.execute(f"GRANT {APP_ROLE} TO CURRENT_USER")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    # Tables and sequences made by later migrations get the same grants.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {APP_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT, UPDATE ON SEQUENCES FROM {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute("DROP TRIGGER IF EXISTS user_location_tenant ON user_location")
    op.execute("DROP FUNCTION IF EXISTS user_location_tenant()")

    for table in _tenant_tables():
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_constraint(op.f(f"fk_{table}_tenant_id_tenant"), table, type_="foreignkey")
        op.alter_column(table, "tenant_id", server_default="1")

    op.drop_table("tenant")
