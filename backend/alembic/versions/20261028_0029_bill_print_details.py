"""bill print details

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-28 15:00:00.000000+00:00

The owner's bill layout prints the bank branch and the court jurisdiction ("Subject to X
jurisdiction"); both are shop settings.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("shop_settings", sa.Column("bank_branch", sa.String(length=100), nullable=True))
    op.add_column("shop_settings", sa.Column("jurisdiction", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("shop_settings", "jurisdiction")
    op.drop_column("shop_settings", "bank_branch")
