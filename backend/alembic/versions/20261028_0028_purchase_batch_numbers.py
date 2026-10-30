"""purchase batch numbers

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-28 10:00:00.000000+00:00

R6: a purchase line may carry the supplier's batch, lot or heat number, for any item. Sales take
the oldest lot first for every item (FM10 did this for cement only) and show the batch.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("purchase_line", sa.Column("batch_no", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("purchase_line", "batch_no")
