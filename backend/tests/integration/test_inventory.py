"""FM6: inventory analytics, replenishment, NRV and write-downs, cement age and shrinkage.

The shop's history, counted back from today (all quantities in base units):
  TMT (kg)    purchase 1 ton day 35 at ₹55 · opening 25,000 kg day 30 at ₹55
              sales 1 ton on days 25, 15 and 5          -> on hand 25,000 + 1,000 - 3,000 = 23,000 kg
              sold 3,000 kg in 30 days = 100 kg a day; reorder = 100 x 7 + 100 x 2 = 900 kg
              cover = 23,000 ÷ 100 = 230 days; sold on 3 days: slow (needs 15 to be fast)
  Cement (bags) purchases 40 on day 100 and 50 on day 35, opening 100 on day 30, all at ₹350;
              30 bags sold on day 10, oldest first: 10 + 50 + 100 = 160 on hand
  Old Pipe    40 pieces at ₹350 in the opening stock 200 days ago: nothing since -> ₹14,000 unmoved
  Wire        1,000 kg billed at ₹70, 994 kg on the weighbridge: short 6 kg = 0.60 % = ₹420
ABC on what was sold in 90 days: TMT 3,000 kg x ₹55 = ₹1,65,000; cement 30 x ₹350 = ₹10,500;
the share before cement is 1,65,000 ÷ 1,75,500 = 94 %: TMT A, cement B.
NRV: TMT market ₹54 against cost ₹55: (55 - 54) x 23,000 = ₹23,000.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today_ist
from app.services import verify
from tests.conftest import login
from tests.integration.test_sales import (  # noqa: F401 - the world fixture is shared
    ACCOUNTANT,
    COUNTER,
    body,
    day,
    line,
    post,
    world,
)

pytestmark = pytest.mark.integration

PERIOD = today_ist().strftime("%Y-%m")


def make_item(client, world, name, category, base_unit, hsn, gst="18", whole=False):
    made = client.post(
        "/api/v1/items",
        headers=world["owner"],
        json={
            "name": name,
            "category": category,
            "hsn": hsn,
            "gst_rate": gst,
            "base_unit": base_unit,
            "base_whole_only": whole,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


def buy(
    client, world, item, unit, quantity, rate, when, bill_no, received=None, supplier=None, **extra
):
    line_body = {"item_id": item["id"], "unit": unit, "quantity": quantity, "rate": rate} | extra
    if received:
        line_body["received_quantity"] = received
    made = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": (supplier or world["supplier"])["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": bill_no,
            "bill_date": when,
            "lines": [line_body],
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


@pytest.fixture
def shop(client, world):
    owner = world["owner"]
    client.put(
        "/api/v1/rates/market",
        headers=owner,
        json={
            "effective_date": day(40),
            "rates": [
                {"item_id": world["tmt"]["id"], "rate": "56000", "unit": "ton"},
                {"item_id": world["cement"]["id"], "rate": "380.45"},
            ],
        },
    )
    buy(client, world, world["tmt"], "ton", "1", "55000", day(35), "T-1")
    buy(client, world, world["cement"], "bag", "40", "350", day(100), "C-1")
    buy(client, world, world["cement"], "bag", "50", "350", day(35), "C-2")
    for n in (25, 15, 5):
        sold = post(
            client, world, body(world, [line(world, "tmt", "1", "ton")], invoice_date=day(n))
        )
        assert sold.status_code == 201, sold.text
    sold = post(client, world, body(world, [line(world, "cement", "30")], invoice_date=day(10)))
    assert sold.status_code == 201, sold.text
    pipe = make_item(client, world, "Old Pipe", "pipe", "piece", "73063090", whole=True)
    client.post(
        "/api/v1/opening",
        headers=owner,
        json={
            "kind": "stock",
            "as_of": day(200),
            "item_id": pipe["id"],
            "location_id": world["loc"]["S1"],
            "quantity": "40",
            "unit_cost": "350",
        },
    )
    posted = client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["stock"]})
    assert posted.status_code == 200, posted.text
    wire = make_item(client, world, "Binding wire", "wire", "kg", "72171010")
    other = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Wire Co", "type": "supplier", "state_code": "33"},
    ).json()
    buy(
        client,
        world,
        wire,
        "kg",
        "1000",
        "70",
        day(35),
        "W-1",
        received="994",
        supplier=other,
        weight_note="Short on the weighbridge",
    )
    world |= {"pipe": pipe, "wire": wire, "wire_co": other}
    return world


def analytics(client, headers):
    r = client.get("/api/v1/inventory/analytics", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def by_name(report):
    return {x["item_name"]: x for x in report["rows"]}


def test_abc_fsn_cover_reorder_and_age_match_the_hand_worked_shop(client, shop):
    r = analytics(client, shop["owner"])
    assert r["enough_data"] is True and r["data_note"] is None and r["history_days"] >= 100
    rows = by_name(r)
    tmt = rows["TMT 12 mm"]
    assert (tmt["on_hand"], tmt["avg_cost"], tmt["value"]) == ("23000.000", "55.0000", "1265000.00")
    assert (tmt["days_sold"], tmt["consumption"], tmt["abc"], tmt["fsn"]) == (
        3,
        "165000.00",
        "A",
        "S",
    )
    assert (tmt["avg_daily_sales"], tmt["cover_days"]) == ("100.000", "230.0")
    assert (tmt["lead_days"], tmt["safety_days"]) == (7, 2)
    assert (tmt["reorder_point"], tmt["short_by"], tmt["reorder_now"]) == (
        "900.000",
        "0.000",
        False,
    )
    assert (tmt["last_movement"], tmt["age_days"], tmt["age_bucket"]) == (day(5), 5, "0-30")
    cement = rows["Cement PPC"]
    assert (cement["on_hand"], cement["consumption"], cement["abc"]) == ("160.000", "10500.00", "B")
    assert (cement["avg_daily_sales"], cement["cover_days"], cement["reorder_point"]) == (
        "1.000",
        "160.0",
        "9.000",
    )
    pipe = rows["Old Pipe"]  # nothing has touched it for 200 days
    assert (pipe["on_hand"], pipe["value"], pipe["age_days"], pipe["age_bucket"]) == (
        "40.000",
        "14000.00",
        200,
        "180+",
    )
    assert (pipe["fsn"], pipe["abc"], pipe["avg_daily_sales"], pipe["reorder_point"]) == (
        "N",
        None,
        "0.000",
        None,
    )
    assert r["dead_stock_value"] == "14000.00"
    aging = {a["bucket"]: (a["value"], a["items"]) for a in r["aging"]}
    assert aging["180+"] == ("14000.00", 1)
    assert [a["bucket"] for a in r["aging"]] == ["0-30", "31-90", "91-180", "180+"]


def test_lead_time_and_safety_days_come_from_the_item_then_the_supplier_then_the_shop(client, shop):
    owner = shop["owner"]
    # Cement's own days: 200 days' lead, 5 days' safety -> 1 x 200 + 1 x 5 = 205 bags; 160 on
    # hand, so it is 45 bags short and shown first.
    patched = client.patch(
        f"/api/v1/items/{shop['cement']['id']}",
        headers=owner,
        json={"lead_time_days": 200, "safety_days": 5},
    )
    assert patched.status_code == 200, patched.text
    r = analytics(client, owner)
    cement = by_name(r)["Cement PPC"]
    assert (cement["lead_days"], cement["safety_days"], cement["reorder_point"]) == (
        200,
        5,
        "205.000",
    )
    assert (cement["short_by"], cement["reorder_now"]) == ("45.000", True)
    assert r["rows"][0]["item_name"] == "Cement PPC"  # reorder-now items come first
    # TMT has no days of its own: its last supplier (Mills) has 10 days' lead -> 100 x 10 + 200.
    assert (
        client.patch(
            f"/api/v1/parties/{shop['supplier']['id']}", headers=owner, json={"lead_time_days": 10}
        ).status_code
        == 200
    )
    tmt = by_name(analytics(client, owner))["TMT 12 mm"]
    assert (tmt["lead_days"], tmt["reorder_point"]) == (10, "1200.000")
    # An item's own value wins, even zero: 100 x 0 + 100 x 2 = 200 kg.
    client.patch(f"/api/v1/items/{shop['tmt']['id']}", headers=owner, json={"lead_time_days": 0})
    assert by_name(analytics(client, owner))["TMT 12 mm"]["reorder_point"] == "200.000"
    # And the shop's default applies when neither is set (wire has no sales: no reorder point).
    settings = client.get("/api/v1/settings", headers=owner).json()
    settings.pop("id")
    settings |= {"default_lead_time_days": 3, "default_safety_days": 1, "fsn_fast_min_days": 3}
    assert client.put("/api/v1/settings", headers=owner, json=settings).status_code == 200
    r = analytics(client, owner)
    assert r["default_lead_days"] == 3 and r["fsn_fast_min_days"] == 3
    assert by_name(r)["TMT 12 mm"]["fsn"] == "F"  # 3 days is now fast


def test_too_little_history_says_so_and_invents_nothing(client, world):
    # One purchase 5 days ago: the shop's records start there.
    bought = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "N-1",
            "bill_date": day(5),
            "lines": [
                {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": "1", "rate": "55000"}
            ],
        },
    )
    assert bought.status_code == 201, bought.text
    r = analytics(client, world["owner"])
    assert r["enough_data"] is False and r["history_days"] == 6
    assert r["data_note"].startswith("Not enough data yet (needs 30 days")
    for row in r["rows"]:
        for key in ("abc", "fsn", "avg_daily_sales", "cover_days", "reorder_point", "short_by"):
            assert row[key] is None, key
        assert row["reorder_now"] is False
    assert all(row["age_bucket"] for row in r["rows"])  # but the age is known


def test_a_theft_adjustment_does_not_make_dead_stock_look_alive(client, shop):
    owner = shop["owner"]
    before = by_name(analytics(client, owner))["Old Pipe"]
    adjusted = client.post(
        "/api/v1/stock-adjustments",
        headers=owner,
        json={
            "location_id": shop["loc"]["S1"],
            "reason": "theft",
            "lines": [{"item_id": shop["pipe"]["id"], "quantity": "2"}],
        },
    )
    assert adjusted.status_code == 201, adjusted.text
    after = by_name(analytics(client, owner))["Old Pipe"]
    assert after["on_hand"] == "38.000"
    assert (after["last_movement"], after["age_days"], after["fsn"]) == (
        before["last_movement"],
        200,
        "N",
    )


# ---------------------------------------------------------------- NRV and write-downs


def drop_tmt_rate(client, shop):
    client.put(
        "/api/v1/rates/market",
        headers=shop["owner"],
        json={
            "effective_date": day(0),
            "rates": [{"item_id": shop["tmt"]["id"], "rate": "54000", "unit": "ton"}],
        },
    )


def nrv(client, headers):
    r = client.get("/api/v1/inventory/nrv", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_nrv_report_shows_the_loss_when_the_market_is_below_cost(client, shop):
    drop_tmt_rate(client, shop)
    r = nrv(client, shop["owner"])
    rows = {x["item_name"]: x for x in r["rows"]}
    tmt = rows["TMT 12 mm"]
    assert (tmt["market_rate"], tmt["nrv"], tmt["avg_cost"]) == ("54.000000", "54.0000", "55.0000")
    assert tmt["nrv_loss"] == "23000.00"  # (55 - 54) x 23,000 kg
    assert (tmt["replacement_cost"], tmt["holding_gain_loss"]) == ("55.0000", "0.00")
    cement = rows["Cement PPC"]  # ₹380.45 a bag against a cost of ₹350: no loss
    assert (cement["nrv_loss"], cement["replacement_cost"]) == ("0.00", "350.0000")
    assert cement["holding_gain_loss"] == "0.00"
    pipe = rows["Old Pipe"]  # no rate on the board: nothing is guessed
    assert (pipe["market_rate"], pipe["nrv"], pipe["nrv_loss"], pipe["holding_gain_loss"]) == (
        None,
        None,
        "0.00",
        None,
    )
    assert r["nrv_loss"] == "23000.00" and r["writedown_enabled"] is True
    assert r["rows"][0]["item_name"] == "TMT 12 mm"  # biggest loss first


def test_selling_costs_lower_the_nrv(client, shop):
    drop_tmt_rate(client, shop)
    settings = client.get("/api/v1/settings", headers=shop["owner"]).json()
    settings.pop("id")
    settings |= {"nrv_selling_cost_pct": "1"}
    assert client.put("/api/v1/settings", headers=shop["owner"], json=settings).status_code == 200
    tmt = next(x for x in nrv(client, shop["owner"])["rows"] if x["item_name"] == "TMT 12 mm")
    # 54 x 0.99 = 53.46; (55 - 53.46) x 23,000 = ₹35,420
    assert (tmt["nrv"], tmt["nrv_loss"]) == ("53.4600", "35420.00")


def writedown(client, shop, item_keys=("tmt",), headers=None, **extra):
    return client.post(
        "/api/v1/inventory/writedowns",
        headers=headers or shop["owner"],
        json={
            "location_id": shop["loc"]["S1"],
            "item_ids": [shop[k]["id"] for k in item_keys],
            "note": "Market fell",
        }
        | extra,
    )


def tmt_stock(client, headers, shop):
    rows = client.get("/api/v1/stock", headers=headers).json()
    row = next(r for r in rows if r["item_id"] == shop["tmt"]["id"])
    return {x["code"]: x["quantity"] for x in row["locations"]}


def test_a_write_down_changes_the_value_but_no_quantity_and_reverses_no_tax(client, shop, seeded):
    owner = shop["owner"]
    drop_tmt_rate(client, shop)
    stock_before = tmt_stock(client, owner, shop)
    assert stock_before == {"S1": "3000.000", "G1": "20000.000"}  # 5,000 + 1,000 - 3,000 and 20,000
    pnl_before = client.get(f"/api/v1/reports/pnl?period={PERIOD}", headers=owner).json()
    itc_before = client.get(f"/api/v1/reports/itc-reversal?period={PERIOD}", headers=owner).json()
    made = writedown(client, shop)
    assert made.status_code == 201, made.text
    w = made.json()
    assert (
        w["number"].startswith("S1N/")
        and w["number"].endswith("/00001")
        and w["note"] == "Market fell"
    )
    assert w["total"] == "23000.00"
    assert [(x["quantity"], x["old_cost"], x["new_cost"], x["value"]) for x in w["lines"]] == [
        ("23000.000", "55.0000", "54.0000", "23000.00")
    ]
    # Same quantity in both places, new average, stock worth ₹23,000 less.
    assert tmt_stock(client, owner, shop) == stock_before
    after = {x["item_name"]: x for x in nrv(client, owner)["rows"]}["TMT 12 mm"]
    assert (after["on_hand"], after["avg_cost"], after["value"], after["nrv_loss"]) == (
        "23000.000",
        "54.0000",
        "1242000.00",
        "0.00",
    )
    # The loss is in the month's net profit, not in gross profit, and no tax is reversed.
    pnl = client.get(f"/api/v1/reports/pnl?period={PERIOD}", headers=owner).json()
    assert pnl["write_downs"] == "23000.00" and pnl_before["write_downs"] == "0.00"
    assert float(pnl_before["net_profit"]) - float(pnl["net_profit"]) == 23000.0
    assert (
        pnl["gross_profit"] == pnl_before["gross_profit"]
        and pnl["stock_loss"] == pnl_before["stock_loss"]
    )
    assert (
        client.get(f"/api/v1/reports/itc-reversal?period={PERIOD}", headers=owner).json()
        == itc_before
    )
    # It is not movement: the item's last movement, its sales days and its age are unchanged.
    tmt = by_name(analytics(client, owner))["TMT 12 mm"]
    assert (tmt["last_movement"], tmt["days_sold"], tmt["age_days"]) == (day(5), 3, 5)
    assert tmt["avg_cost"] == "54.0000"
    # The books still agree with themselves (cost of goods identity, ledger, numbering).
    seeded.rollback()
    assert verify.run_checks(seeded).ok
    listed = client.get("/api/v1/inventory/writedowns", headers=owner).json()
    assert [x["number"] for x in listed] == [w["number"]]


def test_a_second_write_down_has_nothing_left_to_write_down(client, shop):
    drop_tmt_rate(client, shop)
    assert writedown(client, shop).status_code == 201
    again = writedown(client, shop)
    assert again.status_code == 409 and again.json()["code"] == "NOTHING_TO_WRITE_DOWN"
    assert "TMT 12 mm" in again.json()["message"]
    # A bigger fall is a second document, so the trail shows both.
    client.put(
        "/api/v1/rates/market",
        headers=shop["owner"],
        json={
            "effective_date": day(0),
            "rates": [{"item_id": shop["tmt"]["id"], "rate": "53000", "unit": "ton"}],
        },
    )
    second = writedown(client, shop)
    assert second.status_code == 201 and second.json()["number"].endswith("/00002")
    assert second.json()["total"] == "23000.00"  # 23,000 kg x (54 - 53)


def test_a_write_down_needs_a_loss_a_rate_and_the_setting(client, shop):
    owner = shop["owner"]
    no_loss = writedown(client, shop)  # TMT still lists at ₹56, above its cost
    assert no_loss.status_code == 409 and no_loss.json()["code"] == "NOTHING_TO_WRITE_DOWN"
    no_rate = writedown(client, shop, ("pipe",))
    assert no_rate.status_code == 409 and no_rate.json()["code"] == "NO_MARKET_RATE"
    twice = writedown(client, shop, ("tmt", "tmt"))
    assert twice.json()["code"] == "DUPLICATE_ITEM"
    assert writedown(client, shop, location_id=99999).status_code == 404
    drop_tmt_rate(client, shop)
    settings = client.get("/api/v1/settings", headers=owner).json()
    settings.pop("id")
    assert (
        client.put(
            "/api/v1/settings", headers=owner, json=settings | {"nrv_writedown_enabled": False}
        ).status_code
        == 200
    )
    off = writedown(client, shop)
    assert off.status_code == 409 and off.json()["code"] == "WRITEDOWN_DISABLED"
    assert nrv(client, owner)["writedown_enabled"] is False  # the report still shows the loss
    assert client.get("/api/v1/inventory/writedowns", headers=owner).json() == []


def test_write_downs_are_permanent(client, shop, seeded):
    drop_tmt_rate(client, shop)
    assert writedown(client, shop).status_code == 201
    for sql in (
        "UPDATE stock_writedown SET note = 'x'",
        "DELETE FROM stock_writedown",
        "UPDATE stock_writedown_line SET value = 1",
        "DELETE FROM stock_writedown_line",
        "UPDATE stock_ledger SET qty_out = 1 WHERE ref_type = 'stock_writedown'",
    ):
        with pytest.raises(DBAPIError), seeded.begin_nested():
            seeded.execute(text(sql))


# ---------------------------------------------------------------- cement age, shrinkage, roles


def test_cement_age_takes_the_oldest_stock_first(client, shop):
    r = client.get("/api/v1/inventory/fifo-age", headers=shop["owner"])
    assert r.status_code == 200, r.text
    f = r.json()
    assert "estimate" in f["note"]
    assert [x["item_name"] for x in f["items"]] == ["Cement PPC"]  # only cement is aged this way
    cement = f["items"][0]
    # 40 bags came in 100 days ago, 50 35 days ago and 100 30 days ago; 30 sold, oldest first.
    assert [(x["quantity"], x["age_days"]) for x in cement["layers"]] == [
        ("10.000", 100),
        ("50.000", 35),
        ("100.000", 30),
    ]
    assert cement["on_hand"] == "160.000" and cement["oldest_age_days"] == 100
    assert {k: Decimal(v) for k, v in cement["buckets"].items()} == {
        "0-30": Decimal("100"),
        "31-60": Decimal("50"),
        "61-90": Decimal("0"),
        "90+": Decimal("10"),
    }
    assert cement["over_90_value"] == "3500.00"  # 10 bags at ₹350


def test_shrinkage_lists_weight_shortages_by_supplier_with_a_claims_list(client, shop):
    r = client.get("/api/v1/inventory/shrinkage", headers=shop["owner"])
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["shortage_value"] == "420.00"  # 70,000 x 6 ÷ 1,000
    suppliers = {x["party_name"]: x for x in s["suppliers"]}
    wire = suppliers["Wire Co"]
    assert (
        wire["goods_value"],
        wire["shortage_value"],
        wire["shortage_pct"],
        wire["short_lines"],
    ) == (
        "70000.00",
        "420.00",
        "0.60",
        1,
    )
    assert suppliers["Mills"]["shortage_value"] == "0.00" and suppliers["Mills"]["short_lines"] == 0
    assert s["suppliers"][0]["party_name"] == "Wire Co"  # worst first
    claim = s["claims"][0]
    assert (claim["bill_no"], claim["item_name"], claim["billed_qty"], claim["received_qty"]) == (
        "W-1",
        "Binding wire",
        "1000.000",
        "994.000",
    )
    assert (claim["shortage_qty"], claim["loss_pct"], claim["value"]) == ("6.000", "0.60", "420.00")
    assert len(s["claims"]) == 1
    # A narrower window leaves it out; a backwards one is refused.
    none = client.get(
        f"/api/v1/inventory/shrinkage?date_from={day(10)}&date_to={day(0)}", headers=shop["owner"]
    ).json()
    assert none["claims"] == [] and none["shortage_value"] == "0.00"
    bad = client.get(
        f"/api/v1/inventory/shrinkage?date_from={day(0)}&date_to={day(10)}", headers=shop["owner"]
    )
    assert bad.status_code == 409 and bad.json()["code"] == "BAD_RANGE"


def test_roles_the_accountant_reads_value_reports_and_the_counter_sees_none(client, shop):
    acct, counter = login(client, *ACCOUNTANT), login(client, *COUNTER)
    for path in ("/inventory/nrv", "/inventory/writedowns", "/inventory/shrinkage"):
        assert client.get(f"/api/v1{path}", headers=acct).status_code == 200, path
        assert client.get(f"/api/v1{path}", headers=counter).status_code == 403, path
    for path in ("/inventory/analytics", "/inventory/fifo-age"):
        assert client.get(f"/api/v1{path}", headers=acct).status_code == 403, path
        assert client.get(f"/api/v1{path}", headers=counter).status_code == 403, path
    drop_tmt_rate(client, shop)
    for headers in (acct, counter):
        assert writedown(client, shop, headers=headers).status_code == 403
