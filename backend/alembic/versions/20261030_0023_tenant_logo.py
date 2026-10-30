"""tenant logo

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-30 08:05:18.561248+00:00

UI refresh T10: the shop's logo. Three nullable columns on shop_settings (storage key, type and
SHA-256), with a CHECK that they are all set or all empty. Adding nullable columns rewrites no
row. Downgrading drops the references; the stored files are left where they are.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALL_OR_NONE = (
    "(logo_key IS NULL AND logo_type IS NULL AND logo_sha256 IS NULL) "
    "OR (logo_key IS NOT NULL AND logo_type IS NOT NULL AND logo_sha256 IS NOT NULL)"
)


def upgrade() -> None:
    op.add_column("shop_settings", sa.Column("logo_key", sa.String(length=200), nullable=True))
    op.add_column("shop_settings", sa.Column("logo_type", sa.String(length=20), nullable=True))
    op.add_column("shop_settings", sa.Column("logo_sha256", sa.String(length=64), nullable=True))
    op.create_check_constraint("logo_all_or_none", "shop_settings", ALL_OR_NONE)


def downgrade() -> None:
    op.drop_constraint("logo_all_or_none", "shop_settings", type_="check")
    op.drop_column("shop_settings", "logo_sha256")
    op.drop_column("shop_settings", "logo_type")
    op.drop_column("shop_settings", "logo_key")
