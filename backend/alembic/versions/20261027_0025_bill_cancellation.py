"""bill cancellation

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-27 10:00:00.000000+00:00

The owner can cancel a whole bill. The bill row is never changed or deleted (B16, migration
0014); a full credit note marked `cancels_invoice` reverses it, and the bill reads as cancelled.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "credit_note",
        sa.Column("cancels_invoice", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("credit_note", "cancels_invoice")
