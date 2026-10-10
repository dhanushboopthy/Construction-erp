"""FM5: working capital for a month, hand-worked from the documents below.

Dates are days of the month, counted from `b`: day 1 when at least 8 days of this month have
passed, otherwise day 10 of last month, so a month always has a week or more of bills and the
opening stock (30 days ago) is always earlier than every bill.

  b      we pay Mills ₹1,00,000 by bank before any bill: a supplier advance
  b+1    Mills bills 10 ton TMT at ₹55,000: ₹5,50,000 + 18% GST = ₹6,49,000 payable
         (the advance is used: Mills is owed ₹5,49,000)
  b+4    bill to Ravi: 1 ton TMT = ₹66,080, ₹20,000 cash with the bill
  b+5    bill to Walk-in: 10 bags cement = ₹4,870, paid in full by UPI
  b+6    Ravi pays ₹10,000 by UPI; we pay Mills ₹3,00,000 (owed ₹2,49,000) and a second supplier
         a ₹50,000 advance

  credit sales = 66,080 - 20,000 + 4,870 - 4,870 = ₹46,080
  receivables 0 -> 36,080 (66,080 - 20,000 - 10,000); average 18,040
  purchases = ₹6,49,000; payables 0 -> 2,49,000, average 1,24,500; advances 0 -> 50,000, average 25,000
  COGS = 1,000 kg x ₹55 + 10 bags x ₹350 = ₹58,500
  collections (not taken with a bill) = ₹10,000
  DSO = 18,040 ÷ 46,080 x days · DPO = 1,24,500 ÷ 6,49,000 x days · advance days = 25,000 ÷ 6,49,000 x days
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import text

from app.core.clock import today_ist
from app.services import verify
from tests.conftest import login
from tests.integration.test_sales import (  # noqa: F401 - the world fixture is shared
    ACCOUNTANT,
    COUNTER,
    body,
    line,
    post,
    world,
)

pytestmark = pytest.mark.integration

TODAY = today_ist()
if TODAY.day >= 8:
    FIRST = TODAY.replace(day=1)
    B = 1
else:
    FIRST = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
    B = 10
PERIOD = FIRST.strftime("%Y-%m")
NEXT = (FIRST + timedelta(days=32)).replace(day=1)
END = min(NEXT - timedelta(days=1), TODAY)
DAYS = (END - FIRST).days + 1


def on(n: int) -> str:
    return (FIRST + timedelta(days=n - 1)).isoformat()


def tenth(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), ROUND_HALF_UP)


@pytest.fixture
def month(client, world):
    owner = world["owner"]
    client.put(
        "/api/v1/rates/market",
        headers=owner,
        json={
            "effective_date": on(1),
            "rates": [
                {"item_id": world["tmt"]["id"], "rate": "56000", "unit": "ton"},
                {"item_id": world["cement"]["id"], "rate": "380.45"},
            ],
        },
    )
    other = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Mills Two", "type": "supplier", "state_code": "33"},
    ).json()

    def pay(direction, party, amount, mode, when):
        r = client.post(
            "/api/v1/payments",
            headers=owner,
            json={
                "direction": direction,
                "party_id": party["id"],
                "location_id": world["loc"]["S1"],
                "amount": amount,
                "mode": mode,
                "payment_date": when,
            },
        )
        assert r.status_code == 201, r.text

    pay("paid", world["supplier"], "100000", "bank", on(B))
    bought = client.post(
        "/api/v1/purchases",
        headers=owner,
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "WC-1",
            "bill_date": on(B + 1),
            "lines": [
                {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": "10", "rate": "55000"}
            ],
        },
    )
    assert bought.status_code == 201, bought.text
    a = post(
        client,
        world,
        body(
            world,
            [line(world, "tmt", "1", "ton")],
            invoice_date=on(B + 4),
            payments=[{"mode": "cash", "amount": "20000"}],
        ),
    )
    assert a.status_code == 201, a.text
    b = post(
        client,
        world,
        body(
            world,
            [line(world, "cement", "10")],
            party="walkin",
            invoice_date=on(B + 5),
            payments=[{"mode": "upi", "amount": "4870", "reference": "U1"}],
        ),
    )
    assert b.status_code == 201, b.text
    pay("received", world["ravi"], "10000", "upi", on(B + 6))
    pay("paid", world["supplier"], "300000", "bank", on(B + 6))
    pay("paid", other, "50000", "bank", on(B + 6))
    return world


def wc(client, headers, period=PERIOD):
    return client.get(f"/api/v1/reports/working-capital?period={period}", headers=headers)


def test_the_month_gives_the_hand_worked_balances_flows_and_days(client, month, seeded):
    r = wc(client, month["owner"])
    assert r.status_code == 200, r.text
    w = r.json()
    assert (w["credit_sales"], w["purchases"], w["cogs"], w["collections"]) == (
        "46080.00",
        "649000.00",
        "58500.00",
        "10000.00",
    )
    assert (w["receivables_start"], w["receivables_end"]) == ("0.00", "36080.00")
    assert (w["payables_start"], w["payables_end"]) == ("0.00", "249000.00")
    assert (w["advances_start"], w["advances_end"]) == ("0.00", "50000.00")
    assert w["enough_data"] is True and w["data_note"] is None and w["days"] == DAYS
    # DSO, DPO and advance days: the average of the start and end balances over the flow.
    assert w["dso_days"] == str(tenth(Decimal("18040") / Decimal("46080") * DAYS))
    assert w["dpo_days"] == str(tenth(Decimal("124500") / Decimal("649000") * DAYS))
    assert w["advance_days"] == str(tenth(Decimal("25000") / Decimal("649000") * DAYS))
    # Stock moved by purchases 5,50,000 less COGS 58,500 (plus opening stock, when it is dated
    # inside the month): the same identity the integrity check enforces.
    opening_in_month = seeded.execute(
        text(
            "select coalesce(sum(qty_in * unit_cost), 0) from stock_ledger "
            "where ref_type = 'opening' and entry_date >= :a and entry_date <= :b"
        ),
        {"a": FIRST, "b": END},
    ).scalar_one()
    moved = Decimal(w["stock_end"]) - Decimal(w["stock_start"])
    assert abs(moved - (Decimal("550000") - Decimal("58500") + opening_in_month)) < Decimal("1")
    avg_stock = (Decimal(w["stock_start"]) + Decimal(w["stock_end"])) / 2
    assert w["dio_days"] == str(tenth(avg_stock / Decimal("58500") * DAYS))
    assert w["inventory_turnover"] == str(
        (Decimal("58500") / avg_stock).quantize(Decimal("0.01"), ROUND_HALF_UP)
    )
    # The cycle is the days as shown: DIO + DSO + advance days - DPO.
    ccc = (
        Decimal(w["dio_days"])
        + Decimal(w["dso_days"])
        + Decimal(w["advance_days"])
        - Decimal(w["dpo_days"])
    )
    assert Decimal(w["ccc_days"]) == ccc
    # Collections 10,000 ÷ (opening 0 + credit sales 46,080) = 21.70 %.
    assert w["collection_efficiency_pct"] == "21.70"
    tied = Decimal(w["stock_end"]) + Decimal("36080") + Decimal("50000")
    assert Decimal(w["cash_tied_up"]) == tied
    assert Decimal(w["working_capital"]) == tied - Decimal("249000")


def test_the_trend_lists_six_months_ending_with_this_one(client, month):
    w = wc(client, month["owner"]).json()
    periods = [p["period"] for p in w["trend"]]
    assert len(periods) == 6 and periods[-1] == PERIOD and periods == sorted(periods)
    last = w["trend"][-1]
    assert (last["dio_days"], last["dso_days"], last["ccc_days"]) == (
        w["dio_days"],
        w["dso_days"],
        w["ccc_days"],
    )
    assert last["cash_tied_up"] == w["cash_tied_up"]
    # Months before any bill show no days at all (not zero), only the cash tied up in stock.
    first = w["trend"][0]
    assert first["enough_data"] is False and first["dio_days"] is None and first["ccc_days"] is None


def test_a_month_with_no_history_says_not_enough_data_instead_of_inventing_figures(client, month):
    earlier = (FIRST - timedelta(days=60)).strftime("%Y-%m")
    w = wc(client, month["owner"], earlier).json()
    assert w["enough_data"] is False and "Not enough data yet" in w["data_note"]
    for key in (
        "dio_days",
        "dso_days",
        "dpo_days",
        "advance_days",
        "ccc_days",
        "inventory_turnover",
    ):
        assert w[key] is None, key
    assert w["collection_efficiency_pct"] is None


def test_a_month_with_bills_but_under_a_week_of_them_is_not_enough(client, world):
    # One bill today, nothing earlier: a month of history is needed before dividing by it.
    post(client, world, body(world, [line(world, "cement", "2")]))
    w = wc(client, world["owner"], TODAY.strftime("%Y-%m")).json()
    if TODAY.day < 7:  # a young month cannot have a week of history
        assert w["enough_data"] is False and w["dso_days"] is None
    assert w["credit_sales"] != "0.00"  # the flows are still shown


def test_bad_periods_and_roles(client, month):
    owner = month["owner"]
    assert wc(client, owner, "nope").json()["code"] == "BAD_PERIOD"
    assert wc(client, owner, "2099-01").json()["code"] == "FUTURE_PERIOD"
    for creds in (COUNTER, ACCOUNTANT):
        assert wc(client, login(client, *creds)).status_code == 403


def test_the_cost_check_ties_opening_stock_purchases_and_cost_of_goods_to_closing_stock(
    client, month, seeded
):
    check = next(c for c in verify.run_checks(seeded).checks if c.name == "Cost of goods")
    assert check.state == "ok", check.detail
    assert "equals closing stock" in check.detail


def test_the_cost_check_catches_a_wrong_cost_on_a_bill(client, month, seeded):
    seeded.execute(text("ALTER TABLE sales_line DISABLE TRIGGER sales_line_no_edit"))
    # A costing bug: every line's cost recorded ₹5 a unit too low.
    seeded.execute(text("UPDATE sales_line SET cost_per_unit = cost_per_unit - 5"))
    seeded.execute(text("ALTER TABLE sales_line ENABLE TRIGGER sales_line_no_edit"))
    check = next(c for c in verify.run_checks(seeded).checks if c.name == "Cost of goods")
    assert check.state == "fail" and "cost of goods sold" in check.detail
    assert "stock ledger shows" in check.detail


def test_the_cost_check_reports_unreplayable_stock_and_quiet_months(world, seeded):
    from app.services.verify import cogs_check

    quiet = cogs_check(seeded, today=date(2001, 5, 15))  # no stock moved then
    assert quiet.state == "ok" and "nothing to check" in quiet.detail
    seeded.execute(text("ALTER TABLE stock_ledger DISABLE TRIGGER stock_ledger_append_only"))
    seeded.execute(
        text(
            "INSERT INTO stock_ledger (tenant_id, item_id, location_id, entry_date, qty_in, qty_out, "
            "unit_cost, ref_type) SELECT 1, id, (SELECT id FROM location LIMIT 1), CURRENT_DATE, 0, 99999999, 1, "
            "'adjustment' FROM item LIMIT 1"
        )
    )
    seeded.execute(text("ALTER TABLE stock_ledger ENABLE TRIGGER stock_ledger_append_only"))
    broken = cogs_check(seeded)
    assert broken.state == "fail" and "cannot be replayed" in broken.detail
