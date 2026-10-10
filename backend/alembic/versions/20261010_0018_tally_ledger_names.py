"""tally ledger names

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-10 02:21:05.975236+00:00

FM4 (docs/FINANCE_REVIEW.md F5): the accountant's Tally ledger names, and an 'export' audit
action so every export of the books is on record. Hand edit: the audit action CHECK is widened
(Alembic does not diff CHECKs) and narrowed again on downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTION_OLD = (
    "action IN ('insert', 'update', 'delete', 'login', 'login_failed', 'logout', "
    "'token_reuse', 'override')"
)
ACTION_NEW = (
    "action IN ('insert', 'update', 'delete', 'login', 'login_failed', 'logout', "
    "'token_reuse', 'override', 'export')"
)


def _swap_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    _swap_check("ck_audit_log_audit_action", "audit_log", ACTION_NEW)
    op.create_table(
        "tally_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tally_ledger")),
        sa.UniqueConstraint("tenant_id", "purpose", name=op.f("uq_tally_ledger_tenant_id_purpose")),
    )


def downgrade() -> None:
    op.drop_table("tally_ledger")
    op.execute("DELETE FROM audit_log WHERE action = 'export'")
    _swap_check("ck_audit_log_audit_action", "audit_log", ACTION_OLD)
