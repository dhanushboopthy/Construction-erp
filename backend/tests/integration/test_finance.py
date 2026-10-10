"""FM1: cash book, expenses and profit and loss (docs/FINANCE_REVIEW.md F1, F2, F6)."""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today_ist
from tests.conftest import login
from tests.integration.test_closing_reports import cash_bill, close, preview
from tests.integration.test_credit import PIN, set_pin
from tests.integration.test_sales import (  # noqa: F401 - the world fixture is shared
    ACCOUNTANT,
    COUNTER,
    COUNTER2,
    day,
    world,
)

pytestmark = pytest.mark.integration


def heads(client, headers) -> dict[str, int]:
    rows = client.get("/api/v1/expense-categories", headers=headers).json()
    return {r["name"]: r["id"] for r in rows}


def voucher(client, headers, world, kind="expense", amount="100", **extra):
    payload = {
        "location_id": world["loc"]["S1"],
        "kind": kind,
        "mode": "cash",
        "amount": amount,
    } | extra
    if kind == "expense" and "category_id" not in extra:
        payload["category_id"] = heads(client, headers)["Loading and unloading labour"]
    return client.post("/api/v1/cash-book", headers=headers, json=payload)


def test_fm1_acceptance_a_normal_day_closes_with_no_difference(client, world):
    """Opening ₹20,000; a customer pays ₹1,80,000 in cash; the counter pays ₹2,000 loading
    labour in cash and takes ₹1,50,000 to the bank. Drawer should be
    20,000 + 1,80,000 - 2,000 - 1,50,000 = ₹48,000, and counting ₹48,000 closes clean."""
    counter = login(client, *COUNTER)
    paid_in = client.post(
        "/api/v1/payments",
        headers=counter,
        json={
            "direction": "received",
            "party_id": world["ravi"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "180000",
            "mode": "cash",
            "payment_date": day(0),
        },
    )
    assert paid_in.status_code == 201, paid_in.text
    labour = voucher(client, counter, world, amount="2000", paid_to="Loading gang")
    assert labour.status_code == 201, labour.text
    assert (
        labour.json()["number"].startswith("S1V/") and labour.json()["drawer_effect"] == "-2000.00"
    )
    deposit = voucher(client, counter, world, kind="bank_deposit", amount="150000")
    assert deposit.status_code == 201, deposit.text  # deposits need no PIN: the bank checks them

    shown = preview(client, counter, world).json()
    fig = shown["figures"]
    assert (fig["cash_expenses"], fig["bank_deposits"], fig["cash_in"], fig["cash_out"]) == (
        "2000.00",
        "150000.00",
        "180000.00",
        "152000.00",
    )
    done = close(client, counter, world, "48000", opening_cash="20000")
    assert done.status_code == 201, done.text
    assert (done.json()["expected_cash"], done.json()["difference"]) == ("48000.00", "0.00")

    # The shop-day is now locked for vouchers too.
    late = voucher(client, counter, world, amount="50")
    assert late.status_code == 409 and late.json()["code"] == "DAY_CLOSED"


def test_who_may_write_the_cash_book(client, world):
    counter = login(client, *COUNTER)
    counter2 = login(client, *COUNTER2)
    accountant = login(client, *ACCOUNTANT)

    drawing = voucher(client, counter, world, kind="owner_drawing", amount="500")
    assert drawing.status_code == 403
    other_shop = voucher(client, counter2, world, amount="50")  # S1 is not counter2's shop
    assert other_shop.status_code == 403
    assert voucher(client, accountant, world, amount="50").status_code == 403
    owners = voucher(client, world["owner"], world, kind="owner_drawing", amount="500")
    assert owners.status_code == 201

    ok = voucher(client, counter, world, amount="40")
    assert ok.status_code == 201
    mine = client.get("/api/v1/cash-book", headers=counter).json()
    # S1's book, including the owner's drawing: that cash left this drawer too.
    assert [e["number"] for e in mine["entries"]] == [
        owners.json()["number"],
        ok.json()["number"],
    ]
    assert (
        client.get(
            f"/api/v1/cash-book?location_id={world['loc']['S2']}", headers=counter
        ).status_code
        == 403
    )
    books = client.get("/api/v1/cash-book", headers=accountant).json()
    assert len(books["entries"]) == 2  # the accountant reads every shop


def test_expenses_above_the_limit_need_the_owners_pin(client, world):
    counter = login(client, *COUNTER)
    big = voucher(client, counter, world, amount="6000")
    assert big.status_code == 409
    assert (big.json()["code"], big.json()["requires_owner_approval"]) == (
        "EXPENSE_NEEDS_OWNER",
        True,
    )
    assert voucher(client, counter, world, amount="5000").status_code == 201  # at the limit
    assert set_pin(client, world).status_code == 204
    granted = client.post(
        "/api/v1/approvals",
        headers=counter,
        json={"action": "expense", "reason": "Monthly loading contract", "pin": PIN},
    )
    assert granted.status_code == 201, granted.text
    approved = voucher(client, counter, world, amount="6000", approval_ids=[granted.json()["id"]])
    assert approved.status_code == 201, approved.text
    reused = voucher(client, counter, world, amount="6000", approval_ids=[granted.json()["id"]])
    assert reused.status_code == 409 and reused.json()["code"] == "APPROVAL_INVALID"
    # The owner needs no PIN.
    assert voucher(client, world["owner"], world, amount="25000").status_code == 201


def test_reversal_is_a_new_voucher_and_the_original_is_permanent(client, world, seeded):
    counter = login(client, *COUNTER)
    wrong = voucher(client, counter, world, amount="300")
    entry_id = wrong.json()["id"]
    assert (
        client.post(
            f"/api/v1/cash-book/{entry_id}/reverse", headers=counter, json={"reason": "typo"}
        ).status_code
        == 403
    )
    undo = client.post(
        f"/api/v1/cash-book/{entry_id}/reverse",
        headers=world["owner"],
        json={"reason": "Typed 300 for 30"},
    )
    assert undo.status_code == 200, undo.text
    rev = undo.json()
    assert (rev["reverses_number"], rev["drawer_effect"]) == (wrong.json()["number"], "300.00")
    assert rev["note"].startswith(f"Reverses {wrong.json()['number']}")
    again = client.post(
        f"/api/v1/cash-book/{entry_id}/reverse", headers=world["owner"], json={"reason": "x2x"}
    )
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_REVERSED"
    of_reversal = client.post(
        f"/api/v1/cash-book/{rev['id']}/reverse", headers=world["owner"], json={"reason": "no!"}
    )
    assert of_reversal.status_code == 409 and of_reversal.json()["code"] == "IS_REVERSAL"
    book = client.get("/api/v1/cash-book", headers=world["owner"]).json()
    assert book["expenses"] == "0.00" and book["drawer_in"] == book["drawer_out"] == "300.00"
    listed = {e["number"]: e for e in book["entries"]}
    assert listed[wrong.json()["number"]]["reversed_by_number"] == rev["number"]

    # The database itself refuses to change or delete a voucher (ADR 0010).
    for sql in (
        "UPDATE cash_entry SET amount = 1 WHERE id = :id",
        "DELETE FROM cash_entry WHERE id = :id",
    ):
        with pytest.raises(DBAPIError), seeded.begin_nested():
            seeded.execute(text(sql), {"id": entry_id})


def test_validation(client, world):
    owner = world["owner"]
    upi_deposit = voucher(client, owner, world, kind="bank_deposit", mode="upi")
    assert upi_deposit.json()["code"] == "CASH_ONLY"
    no_head = voucher(client, owner, world, category_id=None)
    assert no_head.json()["code"] == "CATEGORY_REQUIRED"
    head = heads(client, owner)["Rent"]
    with_head = voucher(client, owner, world, kind="bank_deposit", category_id=head)
    assert with_head.json()["code"] == "CATEGORY_NOT_ALLOWED"
    future = voucher(client, owner, world, entry_date=day(-1))
    assert future.json()["code"] == "FUTURE_DATE"
    counter = login(client, *COUNTER)
    back = voucher(client, counter, world, entry_date=day(1))
    assert back.json()["code"] == "BACKDATE_NEEDS_OWNER"
    assert voucher(client, owner, world, entry_date=day(1)).status_code == 201
    assert voucher(client, owner, world, amount="0").status_code == 422


def test_expense_heads(client, world):
    owner = world["owner"]
    counter = login(client, *COUNTER)
    assert "Interest and bank charges" in heads(client, counter)  # seeded, readable by all
    made = client.post(
        "/api/v1/expense-categories", headers=owner, json={"name": "Security", "nature": "fixed"}
    )
    assert made.status_code == 201
    dup = client.post(
        "/api/v1/expense-categories", headers=owner, json={"name": "Security", "nature": "fixed"}
    )
    assert dup.status_code == 409
    assert (
        client.post(
            "/api/v1/expense-categories", headers=counter, json={"name": "Tips", "nature": "fixed"}
        ).status_code
        == 403
    )
    retired = client.patch(
        f"/api/v1/expense-categories/{made.json()['id']}", headers=owner, json={"is_active": False}
    )
    assert retired.json()["is_active"] is False
    assert "Security" not in heads(client, owner)
    used = voucher(client, owner, world, category_id=made.json()["id"])
    assert used.json()["code"] == "CATEGORY_INACTIVE"


def test_profit_and_loss_for_the_month(client, world):
    """7 bags of cement at ₹380.45 = taxable ₹2,663.15; cost 7 x ₹350 = ₹2,450; gross profit
    ₹213.15 (8.00 %). Expenses: rent ₹1,000 (fixed), loading ₹100 (variable), interest ₹50.
    Opex ₹1,100 -> EBITDA -₹886.85 -> net profit -₹936.85. Contribution 2,663.15 - 2,450 - 100
    = ₹113.15; fixed costs ₹1,050; break-even = 1,050 x 2,663.15 / 113.15 = ₹24,713.28."""
    owner = world["owner"]
    cash_bill(client, world, paid="3409")
    h = heads(client, owner)
    for head, amount in (
        ("Rent", "1000"),
        ("Loading and unloading labour", "100"),
        ("Interest and bank charges", "50"),
    ):
        mode = "bank" if head == "Interest and bank charges" else "cash"
        assert (
            voucher(client, owner, world, amount=amount, category_id=h[head], mode=mode).status_code
            == 201
        )
    pnl = client.get("/api/v1/reports/pnl", headers=owner)
    assert pnl.status_code == 200, pnl.text
    p = pnl.json()
    assert p["period"] == today_ist().strftime("%Y-%m")
    assert (p["net_sales"], p["cogs"], p["gross_profit"], p["gross_margin_pct"]) == (
        "2663.15",
        "2450.00",
        "213.15",
        "8.00",
    )
    assert (p["opex"], p["interest"], p["ebitda"], p["net_profit"]) == (
        "1100.00",
        "50.00",
        "-886.85",
        "-936.85",
    )
    assert (p["contribution"], p["fixed_costs"], p["break_even_sales"]) == (
        "113.15",
        "1050.00",
        "24713.28",
    )
    assert p["enough_data"] is True and p["data_note"] is None
    assert p["expenses"][0]["category"] == "Rent"  # largest head first

    for who in (COUNTER, ACCOUNTANT):
        assert client.get("/api/v1/reports/pnl", headers=login(client, *who)).status_code == 403
    empty = client.get("/api/v1/reports/pnl?period=2026-04", headers=owner).json()
    assert empty["enough_data"] is False and empty["data_note"].startswith("Not enough data")
    assert (
        client.get("/api/v1/reports/pnl?period=april", headers=owner).json()["code"] == "BAD_PERIOD"
    )


def test_today_shows_net_sales_without_gst(client, world):
    # One bill: taxable 2,663.15, total with GST 3,409.00.
    cash_bill(client, world)
    t = client.get("/api/v1/reports/today", headers=world["owner"]).json()
    assert (t["sales_today"], t["net_sales_today"]) == ("3409.00", "2663.15")


def test_kpi_definitions_follow_the_role(client, world):
    owner = {
        k["code"] for k in client.get("/api/v1/kpis/definitions", headers=world["owner"]).json()
    }
    counter = {
        k["code"]
        for k in client.get("/api/v1/kpis/definitions", headers=login(client, *COUNTER)).json()
    }
    assert {"gross_profit", "net_profit", "break_even_sales"} <= owner
    assert "net_sales" in counter and not counter & {"gross_profit", "cogs", "net_profit"}


def test_the_seed_makes_one_shop_and_the_godown_unless_asked_for_two(db):
    from app.models.setup import Location
    from app.scripts.seed import seed

    seed(db)
    codes = sorted(db.execute(text("SELECT code FROM location")).scalars())
    assert codes == ["G1", "S1"]
    seed(db, second_shop=True)  # adding the second shop later is just another seed run
    assert db.query(Location).count() == 3
    assert Decimal(
        str(db.execute(text("SELECT expense_approval_limit FROM shop_settings")).scalar_one())
    ) == Decimal("5000.00")
