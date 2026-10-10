"""Cash book, profit and loss, and KPI definitions (FM1)."""

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.domain.finance import CashEntryKind, ExpenseNature
from app.models.enums import PaymentMode
from app.schemas.common import Schema


class ExpenseCategoryIn(Schema):
    name: str = Field(min_length=2, max_length=60)
    nature: ExpenseNature


class ExpenseCategoryUpdate(Schema):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    nature: ExpenseNature | None = None
    is_active: bool | None = None


class ExpenseCategoryOut(Schema):
    id: int
    name: str
    nature: ExpenseNature
    is_active: bool


class CashEntryCreate(Schema):
    location_id: int
    entry_date: date | None = None  # today when blank; earlier days need the owner
    kind: CashEntryKind
    mode: PaymentMode
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    category_id: int | None = None
    paid_to: str | None = Field(default=None, max_length=100)
    reference: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=200)
    approval_ids: list[int] = Field(default_factory=list)


class CashReverse(Schema):
    reason: str = Field(min_length=3, max_length=200)


class CashEntryOut(Schema):
    id: int
    number: str
    location_id: int
    location_code: str
    entry_date: date
    kind: CashEntryKind
    mode: PaymentMode
    amount: Decimal
    category_id: int | None
    category_name: str | None
    paid_to: str | None
    reference: str | None
    note: str | None
    reverses_id: int | None
    reverses_number: str | None
    reversed_by_number: str | None
    drawer_effect: Decimal  # + into the drawer, - out of it
    created_by_name: str | None


class CashBookOut(Schema):
    location_id: int | None
    date_from: date
    date_to: date
    entries: list[CashEntryOut]
    drawer_in: Decimal
    drawer_out: Decimal
    expenses: Decimal  # all modes, net of reversals


class PnlExpense(Schema):
    category: str
    nature: ExpenseNature
    amount: Decimal


class PnlOut(Schema):
    """Profit and loss for one calendar month (owner only)."""

    period: str  # "2026-10"
    date_from: date
    date_to: date
    location_id: int | None  # None = the whole business
    sales: Decimal  # bills, taxable
    returns: Decimal  # credit notes, taxable
    net_sales: Decimal
    cogs: Decimal
    freight: Decimal
    stock_loss: Decimal  # stock lost (+) or gained (-) through adjustments and counts
    gross_profit: Decimal
    gross_margin_pct: Decimal | None
    expenses: list[PnlExpense]
    opex: Decimal  # excluding interest
    ebitda: Decimal
    interest: Decimal
    net_profit: Decimal
    net_margin_pct: Decimal | None
    fixed_costs: Decimal
    variable_costs: Decimal
    contribution: Decimal
    break_even_sales: Decimal | None
    enough_data: bool
    data_note: str | None


class KpiDefinitionOut(Schema):
    code: str
    name: str
    formula: str
    meaning: str
    example: str
    sources: str
    owner_only: bool
    refresh: str
    good: str
    unit: str


class OverrideLineOut(Schema):
    """One bill line whose price the owner set by hand (FM3). Owner only."""

    invoice_id: int
    invoice_number: str
    invoice_date: date
    location_id: int
    item_name: str
    user_id: int | None
    user_name: str | None
    base_qty: Decimal
    base_unit: str
    list_rate: Decimal | None  # blank on bills issued before FM3
    billed_rate: Decimal
    effect: Decimal | None  # rupees given away (+) or charged extra (-), excl. GST
    reason: str | None


class OverrideUserOut(Schema):
    user_id: int | None
    user_name: str | None
    lines: int
    cut: Decimal
    raised: Decimal
    net: Decimal
    discounts: Decimal


class RateOverridesOut(Schema):
    """Who set prices by hand, and what it cost, for one calendar month (owner only)."""

    period: str
    date_from: date
    date_to: date
    location_id: int | None
    lines: int
    unpriced: int  # lines with no list rate to compare with
    cut: Decimal
    raised: Decimal
    net: Decimal
    discounts: Decimal  # bill discounts in the period (all lines)
    leakage: Decimal  # cut + discounts
    realisation_pct: Decimal | None
    by_user: list[OverrideUserOut]
    rows: list[OverrideLineOut]
