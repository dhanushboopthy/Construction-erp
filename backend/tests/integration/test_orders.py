"""FM10: purchase orders, goods received, the three-way match, cement lots oldest week first and
the lost-sales log with fill rate (docs/FINANCE_REVIEW.md F25, F26).

Match (TMT from Mills, order 10 t at ₹55,000 a ton, tolerances 1 % quantity, 0.5 % rate):
  received 9.8 t, bill 10 t -> 200 kg over = 2.04 % -> refused for the counter, needs the PIN
  received 9.95 t, bill 10 t at ₹55,000 -> 0.50 % -> saves
  received 9.95 t, bill 10 t at ₹55,500 -> rate 0.91 % over -> refused; the owner may save it,
  and PPV = (55.50 - 55) x 10,000 kg = ₹5,000

Lots (cement at S1: 100 bags of opening stock, then week 35 x 60 bags, week 30 x 40 bags, and 20
bags with no week printed, in that order of entry): selling 130 bags takes the 100 with no lot
record first, then 30 of week 30; the next 40 take 10 of week 30 and 30 of week 35; the next 50
take 30 of week 35 and the 20 bags received without a week.

Fill rate: 90 bags sold and 10 asked for with none in stock = 90 %; the owner sees 10 x ₹380.45
= ₹3,804.50 lost.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today_ist
from tests.conftest import login
from tests.integration.test_credit import PIN, set_pin
from tests.integration.test_sales import (  # noqa: F401 - the world fixture is shared
    ACCOUNTANT,
    COUNTER,
    COUNTER2,
    body,
    day,
    line,
    post,
    world,
)

pytestmark = pytest.mark.integration


def order(client, world, lines=None, headers=None, **extra):
    payload = {
        "supplier_id": world["supplier"]["id"],
        "location_id": world["loc"]["S1"],
        "lines": lines
        or [{"item_id": world["tmt"]["id"], "unit": "ton", "quantity": "10", "rate": "55000"}],
    } | extra
    return client.post("/api/v1/purchase-orders", headers=headers or world["owner"], json=payload)


def receive(client, world, po, quantity, headers=None):
    return client.post(
        f"/api/v1/purchase-orders/{po['id']}/receipts",
        headers=headers or login(client, *COUNTER),
        json={"lines": [{"order_line_id": po["lines"][0]["id"], "quantity": quantity}]},
    )


def bill(client, world, po, bill_no, rate="55000", quantity="10", headers=None, **extra):
    payload = {
        "supplier_id": world["supplier"]["id"],
        "location_id": world["loc"]["S1"],
        "bill_no": bill_no,
        "bill_date": day(0),
        "purchase_order_id": po["id"],
        "lines": [
            {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": quantity, "rate": rate}
        ],
    } | extra
    return client.post(
        "/api/v1/purchases", headers=headers or login(client, *COUNTER), json=payload
    )


def approval(client, world, counter):
    assert set_pin(client, world).status_code == 204
    granted = client.post(
        "/api/v1/approvals",
        headers=counter,
        json={
            "action": "po_mismatch",
            "reason": "Supplier short-weighed, owner agreed",
            "pin": PIN,
        },
    )
    assert granted.status_code == 201, granted.text
    return granted.json()["id"]


# ---------------------------------------------------------------- orders and goods received


def test_an_order_is_numbered_permanent_and_counter_staff_see_no_rate(client, world, seeded):
    made = order(client, world, note="First load")
    assert made.status_code == 201, made.text
    po = made.json()
    assert po["number"].startswith("S1O/") and po["status"] == "open"
    assert (po["lines"][0]["rate"], po["value"]) == ("55000.0000", "550000.00")

    counter = login(client, *COUNTER)
    listed = client.get("/api/v1/purchase-orders?open_only=true", headers=counter).json()
    assert [x["number"] for x in listed] == [po["number"]]
    assert "rate" not in listed[0]["lines"][0] and "value" not in listed[0]
    accountant = client.get(
        f"/api/v1/purchase-orders/{po['id']}", headers=login(client, *ACCOUNTANT)
    )
    assert accountant.status_code == 200 and "rate" not in accountant.json()["lines"][0]
    # Shop scope: the other shop's counter does not see it.
    other = login(client, *COUNTER2)
    assert client.get("/api/v1/purchase-orders", headers=other).json() == []
    assert client.get(f"/api/v1/purchase-orders/{po['id']}", headers=other).status_code == 404

    assert order(client, world, headers=counter).status_code == 403
    assert order(client, world, headers=login(client, *ACCOUNTANT)).status_code == 403
    with pytest.raises(DBAPIError), seeded.begin_nested():
        seeded.execute(text("UPDATE purchase_order_line SET rate = rate + 1"))
    with pytest.raises(DBAPIError), seeded.begin_nested():
        seeded.execute(text("DELETE FROM purchase_order"))


def test_order_rules(client, world):
    tmt = world["tmt"]["id"]
    assert (
        order(client, world, supplier_id=world["ravi"]["id"]).json()["code"] == "WRONG_PARTY_TYPE"
    )
    bad_unit = order(
        client, world, lines=[{"item_id": tmt, "unit": "bundle", "quantity": "1", "rate": "1"}]
    )
    assert bad_unit.json()["code"] == "UNKNOWN_UNIT"
    whole = order(
        client,
        world,
        lines=[{"item_id": world["cement"]["id"], "unit": "bag", "quantity": "1.5", "rate": "300"}],
    )
    assert whole.json()["code"] == "UNIT_NOT_WHOLE"
    future = order(client, world, order_date=str(today_ist().replace(year=today_ist().year + 1)))
    assert future.json()["code"] == "FUTURE_DATE"
    dates = order(client, world, order_date=day(2), expected_date=day(5))
    assert dates.json()["code"] == "BAD_DATES"


def test_goods_received_are_recorded_against_the_order_and_move_no_stock(client, world):
    po = order(client, world).json()
    before = client.get("/api/v1/stock", headers=world["owner"]).json()
    counter = login(client, *COUNTER)
    got = receive(client, world, po, "9.8", counter)
    assert got.status_code == 201, got.text
    assert (
        got.json()["number"].startswith("S1G/") and got.json()["lines"][0]["base_qty"] == "9800.000"
    )
    assert client.get("/api/v1/stock", headers=world["owner"]).json() == before
    view = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=counter).json()
    assert view["lines"][0]["received_qty"] == "9800.000" and view["status"] == "open"
    assert receive(client, world, po, "0.2", counter).status_code == 201
    done = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=counter).json()
    assert done["status"] == "received" and len(done["receipts"]) == 2

    # Rules: today only for staff; listed twice; foreign line; another shop's counter; accountant.
    dated = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receipts",
        headers=counter,
        json={
            "receipt_date": day(1),
            "lines": [{"order_line_id": po["lines"][0]["id"], "quantity": "1"}],
        },
    )
    assert dated.json()["code"] == "BACKDATE_NEEDS_OWNER"
    twice = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receipts",
        headers=counter,
        json={"lines": [{"order_line_id": po["lines"][0]["id"], "quantity": "1"}] * 2},
    )
    assert twice.json()["code"] == "LINE_REPEATED"
    foreign = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receipts",
        headers=counter,
        json={"lines": [{"order_line_id": 999999, "quantity": "1"}]},
    )
    assert foreign.status_code == 404
    assert receive(client, world, po, "1", login(client, *COUNTER2)).status_code == 404
    assert receive(client, world, po, "1", login(client, *ACCOUNTANT)).status_code == 403
    owner_dated = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receipts",
        headers=world["owner"],
        json={
            "receipt_date": day(0),
            "lines": [{"order_line_id": po["lines"][0]["id"], "quantity": "1"}],
        },
    )
    assert owner_dated.status_code == 201


# ---------------------------------------------------------------- the three-way match


def test_fm10_acceptance_three_way_match_with_tolerance_and_owner_approval(client, world):
    counter = login(client, *COUNTER)
    po = order(client, world).json()
    receive(client, world, po, "9.8", counter)

    refused = bill(client, world, po, "B-1")
    assert refused.status_code == 409, refused.text
    err = refused.json()
    assert err["code"] == "MATCH_EXCEPTION" and err["requires_owner_approval"] is True
    assert "more than was received" in err["message"]
    assert "₹" not in err["message"] and "55" not in err["message"]  # no money for the counter
    assert client.get("/api/v1/purchases", headers=world["owner"]).json()["items"] == []

    pin_id = approval(client, world, counter)
    wrong = bill(client, world, po, "B-1", approval_ids=[999])
    assert wrong.status_code == 409
    saved = bill(client, world, po, "B-1", approval_ids=[pin_id])
    assert saved.status_code == 201, saved.text
    assert saved.json()["purchase_order_number"] == po["number"]
    assert saved.json()["match_approved"] is True
    # The approval is good once.
    again = bill(client, world, po, "B-2", approval_ids=[pin_id])
    assert again.status_code == 409 and again.json()["code"] == "APPROVAL_INVALID"


def test_within_tolerance_saves_and_a_dearer_rate_does_not(client, world):
    counter = login(client, *COUNTER)
    po = order(client, world).json()
    receive(client, world, po, "9.95", counter)
    ok = bill(client, world, po, "B-1")  # 50 kg over = 0.50 % of what was received
    assert ok.status_code == 201, ok.text
    assert ok.json()["match_approved"] is False

    po2 = order(client, world).json()
    receive(client, world, po2, "9.95", counter)
    dear = bill(client, world, po2, "B-2", rate="55500")
    assert dear.status_code == 409 and dear.json()["code"] == "MATCH_EXCEPTION"
    assert "higher than the order rate" in dear.json()["message"]
    owner_bill = bill(client, world, po2, "B-2", rate="55500", headers=world["owner"])
    assert owner_bill.status_code == 201, owner_bill.text  # the owner may go on

    report = client.get(
        f"/api/v1/reports/match-exceptions?date_from={day(1)}&date_to={day(0)}",
        headers=world["owner"],
    ).json()
    assert (report["bills_checked"], report["lines_checked"], report["exceptions"]) == (2, 2, 1)
    row = report["rows"][0]
    assert (row["bill_no"], row["order_number"], row["ppv"]) == ("B-2", po2["number"], "5000.00")
    assert (row["order_rate"], row["bill_rate"], row["rate_variance_pct"]) == (
        "55.0000",
        "55.5000",
        "0.91",
    )
    assert row["entered_by_owner"] is True and row["approved"] is False and row["ok"] is False
    assert report["ppv_total"] == "5000.00"  # over every line checked, not only the exceptions
    everything = client.get(
        f"/api/v1/reports/match-exceptions?date_from={day(1)}&date_to={day(0)}&all_lines=true",
        headers=world["owner"],
    ).json()
    assert len(everything["rows"]) == 2
    assert (everything["qty_tolerance_pct"], everything["rate_tolerance_pct"]) == ("1.00", "0.50")
    for who in (COUNTER, ACCOUNTANT):
        assert (
            client.get("/api/v1/reports/match-exceptions", headers=login(client, *who)).status_code
            == 403
        )


def test_bill_rules_for_an_order(client, world):
    po = order(client, world).json()
    receive(client, world, po, "10", login(client, *COUNTER))
    owner = world["owner"]
    other = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Steel Two", "type": "supplier", "state_code": "33"},
    ).json()
    wrong_supplier = bill(client, world, po, "X-1", supplier_id=other["id"])
    assert wrong_supplier.json()["code"] == "ORDER_SUPPLIER_MISMATCH"
    wrong_place = bill(client, world, po, "X-2", location_id=world["loc"]["G1"], headers=owner)
    assert wrong_place.json()["code"] == "ORDER_PLACE_MISMATCH"
    # An item that is not on the order needs the owner's approval for the counter.
    extra = client.post(
        "/api/v1/purchases",
        headers=login(client, *COUNTER),
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "X-3",
            "bill_date": day(0),
            "purchase_order_id": po["id"],
            "lines": [
                {"item_id": world["cement"]["id"], "unit": "bag", "quantity": "5", "rate": "350"}
            ],
        },
    )
    assert (
        extra.json()["code"] == "MATCH_EXCEPTION" and "not on the order" in extra.json()["message"]
    )
    # Two bills against one order are judged together: 6 t then 6 t is 12 t against 10 t received.
    first = bill(client, world, po, "Y-1", quantity="6", headers=login(client, *COUNTER))
    assert first.status_code == 201, first.text
    second = bill(client, world, po, "Y-2", quantity="6", headers=login(client, *COUNTER))
    assert second.json()["code"] == "MATCH_EXCEPTION"
    # Partly billed, partly received orders: status follows the bills.
    done = client.get(f"/api/v1/purchase-orders/{po['id']}", headers=owner).json()
    assert done["status"] == "received" and [b["bill_no"] for b in done["bills"]] == ["Y-1"]


# ---------------------------------------------------------------- cement lots


def cement_bill(client, world, no, quantity, billed_on, week=None, year=None, item="cement"):
    payload = {
        "supplier_id": world["supplier"]["id"],
        "location_id": world["loc"]["S1"],
        "bill_no": no,
        "bill_date": billed_on,
        "lines": [
            {"item_id": world[item]["id"], "unit": "bag", "quantity": quantity, "rate": "350"}
            | ({"mfg_week": week, "mfg_year": year} if week else {})
        ],
    }
    return client.post("/api/v1/purchases", headers=world["owner"], json=payload)


def sell_bags(client, world, bags):
    r = post(client, world, body(world, [line(world, "cement", bags)]))
    assert r.status_code == 201, r.text
    return r.json()


def lots_of(client, world, invoice):
    full = client.get(f"/api/v1/invoices/{invoice['id']}", headers=login(client, *COUNTER)).json()
    return [(x["label"], x["quantity"]) for x in full["lines"][0]["lots"]]


def test_fm10_acceptance_cement_is_sold_oldest_week_first(client, world):
    assert cement_bill(client, world, "C-35", "60", day(10), 35, 2026).status_code == 201
    assert cement_bill(client, world, "C-30", "40", day(9), 30, 2026).status_code == 201
    assert cement_bill(client, world, "C-NW", "20", day(5)).status_code == 201

    # 100 opening bags with no lot record go first, then the oldest week.
    first = sell_bags(client, world, "130")
    assert lots_of(client, world, first) == [("Week 30, 2026", "30.000")]
    second = sell_bags(client, world, "40")
    assert lots_of(client, world, second) == [
        ("Week 30, 2026", "10.000"),
        ("Week 35, 2026", "30.000"),
    ]
    third = sell_bags(client, world, "50")
    received = day(5)
    label = f"Received {received[8:10]}-{received[5:7]}-{received[:4]}"
    assert lots_of(client, world, third) == [("Week 35, 2026", "30.000"), (label, "20.000")]
    # Lots are quantities only: the bill PDF-facing price fields are untouched.
    owner_view = client.get(f"/api/v1/invoices/{third['id']}", headers=world["owner"]).json()
    assert owner_view["lines"][0]["base_qty"] == "50.000"
    # Selling stock the lots do not account for records nothing.
    cement_bill(client, world, "C-LAST", "5", day(2), 40, 2026)
    assert lots_of(client, world, sell_bags(client, world, "5")) == [("Week 40, 2026", "5.000")]


def test_a_sale_without_lot_stock_records_no_lot(client, world):
    # Only the 100 opening bags exist: nothing to name.
    assert lots_of(client, world, sell_bags(client, world, "10")) == []


def test_lot_rules(client, world):
    wrong_item = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "L-1",
            "bill_date": day(1),
            "lines": [
                {
                    "item_id": world["tmt"]["id"],
                    "unit": "ton",
                    "quantity": "1",
                    "rate": "55000",
                    "mfg_week": 30,
                    "mfg_year": 2026,
                }
            ],
        },
    )
    assert wrong_item.json()["code"] == "LOT_ONLY_CEMENT"
    assert cement_bill(client, world, "L-2", "10", day(1), 53, 2025).json()["code"] == "BAD_LOT"
    after = cement_bill(client, world, "L-3", "10", day(1), 52, 2026)  # Dec 2026 is in the future
    assert after.json()["code"] == "BAD_LOT" and "after the bill date" in after.json()["message"]
    half = cement_bill(client, world, "L-4", "10", day(1))
    assert half.status_code == 201  # no week printed is fine
    only_week = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "L-5",
            "bill_date": day(1),
            "lines": [
                {
                    "item_id": world["cement"]["id"],
                    "unit": "bag",
                    "quantity": "1",
                    "rate": "350",
                    "mfg_week": 30,
                }
            ],
        },
    )
    assert only_week.status_code == 422


# ---------------------------------------------------------------- lost sales and fill rate


def lost(client, headers, world, quantity="10", location="S1", **extra):
    return client.post(
        "/api/v1/lost-sales",
        headers=headers,
        json={
            "location_id": world["loc"][location],
            "item_id": world["cement"]["id"],
            "quantity": quantity,
        }
        | extra,
    )


def test_fm10_acceptance_lost_sales_and_fill_rate(client, world, seeded):
    counter = login(client, *COUNTER)
    sell_bags(client, world, "90")

    logged = lost(client, counter, world, note="Asked for 10 bags, shelf empty")
    assert logged.status_code == 201, logged.text
    entry = logged.json()
    assert entry["quantity"] == "10.000" and entry["entered_by"] == "Counter, Shop 1"
    assert "value" not in entry  # counter staff see quantities only
    owner_view = client.get("/api/v1/lost-sales", headers=world["owner"]).json()
    assert [(e["quantity"], e["value"]) for e in owner_view] == [("10.000", "3804.50")]
    staff_view = client.get("/api/v1/lost-sales", headers=counter).json()
    assert len(staff_view) == 1 and "value" not in staff_view[0]

    rate = client.get("/api/v1/reports/fill-rate", headers=counter).json()
    row = next(r for r in rate["rows"] if r["item_name"] == "Cement PPC")
    assert (row["supplied_qty"], row["lost_qty"], row["requested_qty"], row["fill_rate_pct"]) == (
        "90.000",
        "10.000",
        "100.000",
        "90.00",
    )
    assert row["lost_value"] is None and rate["lost_value"] is None
    assert (rate["lines_supplied"], rate["lines_lost"], rate["line_fill_rate_pct"]) == (
        1,
        1,
        "50.00",
    )
    by_owner = client.get("/api/v1/reports/fill-rate", headers=world["owner"]).json()
    assert by_owner["lost_value"] == "3804.50"

    # Entries are permanent.
    with pytest.raises(DBAPIError), seeded.begin_nested():
        seeded.execute(text("UPDATE lost_sale SET base_qty = base_qty + 1"))
    with pytest.raises(DBAPIError), seeded.begin_nested():
        seeded.execute(text("DELETE FROM lost_sale"))


def test_lost_sale_rules_and_roles(client, world):
    counter = login(client, *COUNTER)
    assert lost(client, counter, world, location="G1").status_code == 404
    other_shop = lost(client, login(client, *COUNTER2), world)
    assert other_shop.status_code == 404  # not their shop
    assert lost(client, counter, world, entry_date=day(1)).json()["code"] == "BACKDATE_NEEDS_OWNER"
    assert lost(client, world["owner"], world, entry_date=day(1)).status_code == 201
    assert lost(client, counter, world, quantity="0").status_code == 422
    assert lost(client, counter, world, quantity="1.5").json()["code"] == "UNIT_NOT_WHOLE"
    assert lost(client, counter, world, unit="pallet").json()["code"] == "UNKNOWN_UNIT"
    tomorrow = str(today_ist().replace(year=today_ist().year + 1))
    assert lost(client, world["owner"], world, entry_date=tomorrow).json()["code"] == "FUTURE_DATE"
    accountant = login(client, *ACCOUNTANT)
    assert lost(client, accountant, world).status_code == 403
    assert client.get("/api/v1/lost-sales", headers=accountant).status_code == 403
    assert client.get("/api/v1/reports/fill-rate", headers=accountant).status_code == 403
    # The other shop's counter sees none of S1's log.
    assert client.get("/api/v1/lost-sales", headers=login(client, *COUNTER2)).json() == []
    nxt = f"{today_ist().year + 1}-01"
    assert (
        client.get(f"/api/v1/reports/fill-rate?period={nxt}", headers=counter).json()["code"]
        == "FUTURE_PERIOD"
    )
