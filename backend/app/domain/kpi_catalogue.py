"""The single KPI catalogue (docs/FINANCE_REVIEW.md, section 5). It feeds
GET /api/v1/kpis/definitions, the tooltips and "what this means" lines in the app, and
docs/GLOSSARY.md, so the docs, the API and the screens never disagree. Each finance milestone
adds the metrics it builds; code names match the functions in domain/finance.py."""

from dataclasses import dataclass
from enum import StrEnum


class Direction(StrEnum):
    UP = "up"  # higher is better
    DOWN = "down"  # lower is better
    RANGE = "range"  # neither too low nor too high
    NONE = "none"  # a fact, not a score


class Refresh(StrEnum):
    LIVE = "live"
    DAILY = "daily"
    MONTHLY = "monthly"


@dataclass(frozen=True)
class Kpi:
    code: str
    name: str
    formula: str
    meaning: str  # the one-line "what this means" shown under the figure
    example: str  # worked example from this business
    sources: str
    owner_only: bool
    refresh: Refresh
    good: Direction
    unit: str  # "₹", "%", "days", "count"


CATALOGUE: tuple[Kpi, ...] = (
    Kpi(
        "net_sales",
        "Net sales",
        "Bills (taxable, excl. GST) - credit notes (taxable)",
        "What you sold this period after returns, without GST.",
        "Bills ₹20,00,000 - returns ₹50,000 = ₹19,50,000",
        "sales_line.taxable, credit_note_line.taxable",
        False,
        Refresh.LIVE,
        Direction.UP,
        "₹",
    ),
    Kpi(
        "cogs",
        "Cost of goods sold (COGS)",
        "Σ (quantity issued x weighted-average cost at issue), less returns at their cost",
        "What the goods you sold cost you, including landed charges.",
        "33.4 t TMT x ₹55,665/t landed = ₹18,60,000 (rounded)",
        "sales_line.cost_per_unit, drop_ship_link.unit_cost, credit_note_line",
        True,
        Refresh.LIVE,
        Direction.NONE,
        "₹",
    ),
    Kpi(
        "gross_profit",
        "Gross profit",
        "Net sales - COGS - freight on sales",
        "What trading earned before rent, salaries and other running costs.",
        "₹19,50,000 - ₹18,60,000 - ₹20,000 = ₹70,000",
        "net_sales, cogs, trip.freight_amount",
        True,
        Refresh.LIVE,
        Direction.UP,
        "₹",
    ),
    Kpi(
        "gross_margin_pct",
        "Gross margin",
        "Gross profit ÷ net sales x 100",
        "How many paise of every rupee sold are left after the cost of the goods.",
        "₹70,000 ÷ ₹19,50,000 = 3.59 %",
        "gross_profit, net_sales",
        True,
        Refresh.LIVE,
        Direction.UP,
        "%",
    ),
    Kpi(
        "opex",
        "Operating expenses",
        "Σ expense vouchers in the cash book, excluding interest",
        "Running costs of the shop: rent, salaries, power, loading labour, vehicle.",
        "Rent ₹25,000 + salaries ₹60,000 + power ₹6,000 + loading ₹8,000 = ₹99,000",
        "cash_entry (kind expense), expense_category",
        True,
        Refresh.LIVE,
        Direction.DOWN,
        "₹",
    ),
    Kpi(
        "ebitda",
        "EBITDA",
        "Gross profit - operating expenses (before interest)",
        "What the business earns from trading and running the shop, before interest.",
        "₹70,000 - ₹99,000 = -₹29,000",
        "gross_profit, opex",
        True,
        Refresh.MONTHLY,
        Direction.UP,
        "₹",
    ),
    Kpi(
        "net_profit",
        "Net profit",
        "EBITDA - interest",
        "What the business really made this period after every cost booked.",
        "-₹29,000 - interest ₹12,000 = -₹41,000",
        "ebitda, cash_entry (interest category)",
        True,
        Refresh.MONTHLY,
        Direction.UP,
        "₹",
    ),
    Kpi(
        "break_even_sales",
        "Break-even sales",
        "Fixed costs ÷ (contribution ÷ net sales); contribution = net sales - COGS - freight "
        "- variable expenses",
        "The sales you need in the period before you start making a profit.",
        "₹1,03,000 ÷ (₹62,000 ÷ ₹19,50,000) = ₹32,39,516",
        "net_sales, cogs, freight, cash_entry by expense nature",
        True,
        Refresh.MONTHLY,
        Direction.DOWN,
        "₹",
    ),
)


def definitions(*, owner: bool) -> list[Kpi]:
    """Metrics this role may see. Owner-only metrics never reach counter staff."""
    return [k for k in CATALOGUE if owner or not k.owner_only]


def get(code: str) -> Kpi:
    for kpi in CATALOGUE:
        if kpi.code == code:
            return kpi
    raise KeyError(code)
