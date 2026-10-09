"""Declarative base, constraint naming convention and shared column mixins."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Integer, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable constraint names make Alembic migrations predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Column type aliases. Money and quantities are NUMERIC, never float (see ADR 0002).
Money = Annotated[Decimal, mapped_column(Numeric(14, 2))]
Quantity = Annotated[Decimal, mapped_column(Numeric(14, 3))]
UnitCost = Annotated[Decimal, mapped_column(Numeric(14, 4))]
Percent = Annotated[Decimal, mapped_column(Numeric(5, 2))]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantMixin:
    """Every business table carries tenant_id (default 1) so multi-tenant SaaS can be added
    later without rewriting the schema. Do not build tenant logic yet (ADR 0004)."""

    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ActorMixin:
    """Filled from Session.info['actor_id'] by the audit listener."""

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Audited:
    """Marker: inserts, updates and deletes of these models are written to audit_log."""

    __audit_exclude__: frozenset[str] = frozenset()


BigIntPK = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]
IntPK = Annotated[int, mapped_column(Integer, primary_key=True, autoincrement=True)]
