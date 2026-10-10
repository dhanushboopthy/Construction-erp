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
        "Net sales - COGS - freight on sales - stock lost through adjustments",
        "What trading earned before rent, salaries and other running costs.",
        "₹19,50,000 - ₹18,60,000 - ₹20,000 = ₹70,000 (no stock lost)",
        "net_sales, cogs, trip.freight_amount, stock_loss",
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
        "- variable expenses - stock lost",
        "The sales you need in the period before you start making a profit.",
        "₹1,03,000 ÷ (₹62,000 ÷ ₹19,50,000) = ₹32,39,516",
        "net_sales, cogs, freight, cash_entry by expense nature",
        True,
        Refresh.MONTHLY,
        Direction.DOWN,
        "₹",
    ),
    # FM2: stock adjustments
    Kpi(
        "stock_loss",
        "Stock lost",
        "Σ adjustments out x average cost - Σ adjustments in x average cost (counts included)",
        "Stock that left without a bill: breakage, rust, theft, shortages, free samples.",
        "Breakage ₹760 + theft ₹15,000 + count short ₹1,140 - weighbridge gain ₹240 = ₹16,660",
        "stock_ledger (ref adjustment, stock_adjustment), stock_ledger.reason",
        True,
        Refresh.LIVE,
        Direction.DOWN,
        "₹",
    ),
    Kpi(
        "itc_to_reverse",
        "ITC to reverse",
        "Σ value of goods lost x the item's GST rate (CGST Act s.17(5)(h))",
        "Input tax you claimed on goods that were lost or given away; pay it back in GSTR-3B.",
        "Theft ₹15,000 x 18% = ₹2,700",
        "stock_ledger.reason, item.gst_rate, shop_settings.itc_reverse_shortages",
        False,
        Refresh.MONTHLY,
        Direction.DOWN,
        "₹",
    ),
    # FM5: working capital and receivables
    Kpi(
        "dio_days",
        "Days inventory outstanding",
        "Average stock at cost ÷ COGS x days in the month",
        "How many days of sales your stock would last: the longer, the more cash sits on shelves.",
        "₹1.2 crore ÷ ₹1.93 crore x 30 = 18.7 days",
        "stock_ledger replay, cogs",
        True,
        Refresh.MONTHLY,
        Direction.DOWN,
        "days",
    ),
    Kpi(
        "dso_days",
        "Days sales outstanding",
        "Average receivables ÷ credit sales x days in the month",
        "How many days customers take to pay on credit bills.",
        "₹45,00,000 ÷ ₹60,00,000 x 30 = 22.5 days",
        "party_ledger (receivable), sales_invoice (grand total less paid at billing)",
        False,
        Refresh.MONTHLY,
        Direction.DOWN,
        "days",
    ),
    Kpi(
        "dpo_days",
        "Days payables outstanding",
        "Average payables ÷ purchases x days in the month",
        "How many days you take to pay suppliers; more is cash kept, within their terms.",
        "₹20,00,000 ÷ ₹1.95 crore x 30 = 3.1 days",
        "party_ledger (payable), purchase",
        True,
        Refresh.MONTHLY,
        Direction.UP,
        "days",
    ),
    Kpi(
        "advance_days",
        "Supplier advance days",
        "Average supplier advances ÷ purchases x days in the month",
        "How many days of buying you have paid for before the goods arrive.",
        "₹40,00,000 ÷ ₹1.95 crore x 30 = 6.2 days",
        "party_ledger (payable, debit balances), purchase",
        True,
        Refresh.MONTHLY,
        Direction.DOWN,
        "days",
    ),
    Kpi(
        "ccc_days",
        "Cash conversion cycle",
        "DIO + DSO + advance days - DPO",
        "How many days your money is out of your hands between paying for goods and being paid.",
        "18.7 + 22.5 + 6.2 - 3.1 = 44.3 days",
        "dio_days, dso_days, advance_days, dpo_days",
        True,
        Refresh.MONTHLY,
        Direction.DOWN,
        "days",
    ),
    Kpi(
        "inventory_turnover",
        "Inventory turnover",
        "COGS ÷ average stock at cost",
        "How many times the stock was sold through in the month.",
        "₹1.93 crore ÷ ₹1.2 crore = 1.61 times",
        "cogs, stock_ledger replay",
        True,
        Refresh.MONTHLY,
        Direction.UP,
        "times",
    ),
    Kpi(
        "cash_tied_up",
        "Cash tied up",
        "Stock at cost + receivables + supplier advances, at the end of the month",
        "Money you have already spent that has not come back as cash yet.",
        "₹1.2 crore + ₹45 lakh + ₹40 lakh = ₹2.05 crore",
        "stock_ledger replay, party_ledger",
        True,
        Refresh.DAILY,
        Direction.DOWN,
        "₹",
    ),
    Kpi(
        "working_capital",
        "Working capital",
        "Cash tied up - payables (cash and bank balances are not counted yet)",
        "What the trading cycle ties up after suppliers' credit; your own money in the business.",
        "₹2.05 crore - ₹20 lakh = ₹1.85 crore",
        "cash_tied_up, party_ledger (payable)",
        True,
        Refresh.DAILY,
        Direction.NONE,
        "₹",
    ),
    Kpi(
        "collection_efficiency_pct",
        "Collection efficiency",
        "Collections ÷ (opening receivables + credit sales) x 100",
        "How much of what customers owed you in the month actually came in.",
        "₹90,000 ÷ (₹1,00,000 + ₹60,000) = 56.25 %",
        "party_ledger (receivable), payment",
        False,
        Refresh.MONTHLY,
        Direction.UP,
        "%",
    ),
    Kpi(
        "credit_utilisation_pct",
        "Credit utilisation",
        "Outstanding ÷ credit limit x 100",
        "How much of a customer's credit limit is used; near 100 means the next bill is blocked.",
        "₹4,00,000 ÷ ₹5,00,000 = 80 %",
        "party_ledger (receivable), party.credit_limit",
        False,
        Refresh.LIVE,
        Direction.RANGE,
        "%",
    ),
    Kpi(
        "overdue_receivables",
        "Overdue receivables",
        "Σ open bills past their due date (due date, not bill date)",
        "Money customers should already have paid you.",
        "₹10,000 + ₹15,000 + ₹30,000 + ₹40,000 = ₹95,000 past due on 20 Oct",
        "sales_invoice.due_date, party_ledger",
        False,
        Refresh.LIVE,
        Direction.DOWN,
        "₹",
    ),
    Kpi(
        "provision_doubtful",
        "Provision for doubtful debts",
        "Σ overdue bucket x provision % (set in Settings; accountant to confirm)",
        "Money to set aside for bills that may never be paid; shown as a report, not booked.",
        "₹10,000 x 1% + ₹15,000 x 2% + ₹30,000 x 10% + ₹40,000 x 50% = ₹23,400",
        "overdue aging, shop_settings.provision_pct_*",
        True,
        Refresh.MONTHLY,
        Direction.NONE,
        "₹",
    ),
    Kpi(
        "bad_debts",
        "Bad debts written off",
        "Σ write-off documents in the period (no GST effect)",
        "Customer money you have given up on; it reduces net profit when you write it off.",
        "₹5,000 written off: net profit -₹41,000 becomes -₹46,000",
        "bad_debt_writeoff.amount",
        True,
        Refresh.LIVE,
        Direction.DOWN,
        "₹",
    ),
    # FM3: labelled rate overrides
    Kpi(
        "discount_leakage",
        "Discount leakage",
        "Σ (list rate - billed rate) x quantity on lines whose price was set by hand, where "
        "positive, + bill discounts",
        "Money given away by cutting a price at the counter instead of changing the rate.",
        "1,000 kg TMT billed ₹60 against ₹62 listed = ₹2,000; + discount ₹500 = ₹2,500",
        "sales_line.list_rate, rate, base_qty, discount (rate_source override)",
        True,
        Refresh.LIVE,
        Direction.DOWN,
        "₹",
    ),
    Kpi(
        "price_realisation_pct",
        "Price realisation",
        "Billed value ÷ list value x 100, on lines whose price was set by hand",
        "How much of the listed price you really collected on hand-priced lines.",
        "₹60,000 billed ÷ ₹62,000 listed = 96.77 %",
        "sales_line.list_rate, rate, base_qty (rate_source override)",
        True,
        Refresh.LIVE,
        Direction.UP,
        "%",
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
