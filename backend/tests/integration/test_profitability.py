"""FM8: profit per ton by brand, shop and user, and ITC at risk
(docs/FINANCE_REVIEW.md F19, F29).

October, hand-worked (net sales excl. GST; cost at the average cost on the day):
  Tata TMT (brand "Tata", bought at ₹50/kg):   bill 1 by the owner at S1, 2 t at ₹56/kg
      = 1,12,000; cost 1,00,000; freight 3,000 -> profit 9,000 = ₹4,500 a ton
  JSW TMT (brand "JSW", bought at ₹52/kg):     bill 2 by the counter at S1, 1 t at ₹57/kg
      = 57,000; cost 52,000 -> profit 5,000 = ₹5,000 a ton
  Mills TMT (no brand, ₹55/kg opening stock):  bill 3 by the owner at G1, 1 t at ₹56/kg
      = 56,000; cost 55,000 -> profit 1,000
  Cement (no brand): bill 4 by the counter at S1, 7 bags at ₹380.45 = 2,663.15, cost 7 x 350
      = 2,450; then 1 bag returned: -380.45 sales, -350 cost
      -> net 2,282.70, cost 2,100, profit 182.70 on 6 bags = ₹30.45 a bag
  Total gross profit before stock lost = 9,000 + 5,000 + 1,000 + 182.70 = 15,182.70
  Stock lost: 20 kg of Tata TMT broken, 20 x 50 = ₹1,000 -> gross profit 14,182.70 (P&L).
By shop: S1 14,182.70 before the loss (9,000 + 5,000 + 182.70), 13,182.70 after; G1 1,000.
By user: owner 10,000 (bills 1 and 3); counter 5,182.70 (bills 2 and 4).
"""

import pytest

from app.core.clock import today_ist
from app.domain.gst import gstin_checksum
from tests.conftest import login
from tests.integration.test_adjustments import adjust
from tests.integration.test_returns import note_body
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


def tmt(client, world, key, name, brand, cost_per_ton, rate_per_ton):
    owner = world["owner"]
    item = client.post(
        "/api/v1/items",
        headers=owner,
        json={
            "name": name,
            "category": "tmt",
            "brand": brand,
            "hsn": "72142090",
            "gst_rate": "18",
            "base_unit": "kg",
            "units": [{"unit": "ton", "factor_to_base": "1000"}],
        },
    ).json()
    bought = client.post(
        "/api/v1/purchases",
        headers=owner,
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": f"P-{key}",
            "bill_date": day(5),
            "lines": [
                {"item_id": item["id"], "unit": "ton", "quantity": "10", "rate": cost_per_ton}
            ],
        },
    )
    assert bought.status_code == 201, bought.text
    rates = client.put(
        "/api/v1/rates/market",
        headers=owner,
        json={
            "effective_date": day(1),
            "rates": [{"item_id": item["id"], "rate": rate_per_ton, "unit": "ton"}],
        },
    )
    assert rates.status_code in (200, 201), rates.text
    world[key] = item


@pytest.fixture
def october(client, world):
    owner = world["owner"]
    counter = login(client, *COUNTER)
    tmt(client, world, "tata", "TMT 12 Tata", "Tata", "50000", "56000")
    tmt(client, world, "jsw", "TMT 12 JSW", "JSW", "52000", "57000")
    # The market board is replaced as a whole, so put the world's own rates back.
    client.put(
        "/api/v1/rates/market",
        headers=owner,
        json={
            "effective_date": day(1),
            "rates": [
                {"item_id": world["tata"]["id"], "rate": "56000", "unit": "ton"},
                {"item_id": world["jsw"]["id"], "rate": "57000", "unit": "ton"},
                {"item_id": world["tmt"]["id"], "rate": "56000", "unit": "ton"},
                {"item_id": world["cement"]["id"], "rate": "380.45"},
            ],
        },
    )
    one = post(client, world, body(world, [line(world, "tata", "2", "ton")]))
    two = post(client, world, body(world, [line(world, "jsw", "1", "ton")]), headers=counter)
    three = post(client, world, body(world, [line(world, "tmt", "1", "ton")], location="G1"))
    four = post(client, world, body(world, [line(world, "cement", "7")]), headers=counter)
    for r in (one, two, three, four):
        assert r.status_code == 201, r.text
    car = client.post(
        "/api/v1/vehicles", headers=owner, json={"number": "TN 09 AB 1234", "owner_name": "Murugan"}
    ).json()
    trip = client.post(
        "/api/v1/trips",
        headers=owner,
        json={
            "vehicle_id": car["id"],
            "location_id": world["loc"]["S1"],
            "invoice_id": one.json()["id"],
            "from_place": "Shop",
            "to_place": "Site",
            "freight_amount": "3000",
        },
    )
    assert trip.status_code == 201, trip.text
    note = client.post(
        "/api/v1/credit-notes", headers=owner, json=note_body(four.json(), [(0, "1")])
    )
    assert note.status_code == 201, note.text
    broke = adjust(client, owner, world, "breakage", [("tata", "20")])
    assert broke.status_code == 201, broke.text
    return world


def cut(client, headers, by, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(
        f"/api/v1/reports/profitability?by={by}&period={PERIOD}" + (f"&{query}" if query else ""),
        headers=headers,
    )


def rows(report):
    return {r["key"]: r for r in report["rows"]}


def test_profit_per_ton_by_brand_equals_the_hand_totals(client, october):
    r = cut(client, october["owner"], "brand").json()
    by = rows(r)
    assert set(by) == {"Tata", "JSW", "No brand"}
    tata = by["Tata"]
    assert (tata["net_sales"], tata["cogs"], tata["freight"], tata["gross_profit"]) == (
        "112000.00",
        "100000.00",
        "3000.00",
        "9000.00",
    )
    assert (tata["tons"], tata["profit_per_ton"]) == ("2.000", "4500.00")
    assert tata["margin_pct"] == "8.04" and tata["share_pct"] == "59.28"
    assert tata["units"] == "0.000" and tata["profit_per_unit"] is None
    assert tata["margin_per_base_unit"] == "4.5000"
    jsw = by["JSW"]
    assert (jsw["gross_profit"], jsw["tons"], jsw["profit_per_ton"]) == (
        "5000.00",
        "1.000",
        "5000.00",
    )
    nb = by["No brand"]
    assert (nb["net_sales"], nb["cogs"], nb["gross_profit"]) == ("58282.70", "57100.00", "1182.70")
    # Steel by weight and cement by the bag stay apart.
    assert (nb["tons"], nb["profit_per_ton"]) == ("1.000", "1000.00")
    assert (nb["units"], nb["unit_label"], nb["profit_per_unit"]) == ("6.000", "bag", "30.45")
    assert nb["margin_per_base_unit"] is None  # kg and bags in one row: no single unit
    assert r["gross_profit_before_loss"] == "15182.70" and r["stock_lost"] == "1000.00"
    assert r["gross_profit"] == "14182.70"
    assert (r["tons"], r["profit_per_ton"]) == ("4.000", "3750.00")
    assert r["contribution_per_ton"] is None and "bag or piece" in r["data_note"]
    assert [x["key"] for x in r["rows"]] == ["Tata", "JSW", "No brand"]  # best profit first


def test_every_cut_adds_up_to_the_profit_and_loss(client, october):
    owner = october["owner"]
    pnl = client.get(f"/api/v1/reports/pnl?period={PERIOD}", headers=owner).json()
    assert pnl["gross_profit"] == "14182.70"
    for by in ("brand", "shop", "user", "item", "customer"):
        r = cut(client, owner, by).json()
        total = sum(float(x["gross_profit"]) for x in r["rows"])
        assert total == pytest.approx(float(r["gross_profit_before_loss"]))
        assert r["gross_profit"] == pnl["gross_profit"], by
        assert (r["net_sales"], r["cogs"], r["freight"]) == (
            pnl["net_sales"],
            pnl["cogs"],
            pnl["freight"],
        ), by
    # The same holds for one shop.
    s1 = october["loc"]["S1"]
    pnl_s1 = client.get(
        f"/api/v1/reports/pnl?period={PERIOD}&location_id={s1}", headers=owner
    ).json()
    r = cut(client, owner, "brand", location_id=s1).json()
    assert r["gross_profit"] == pnl_s1["gross_profit"] == "13182.70"  # S1 bore the loss
    g1 = october["loc"]["G1"]
    pnl_g1 = client.get(
        f"/api/v1/reports/pnl?period={PERIOD}&location_id={g1}", headers=owner
    ).json()
    assert (
        cut(client, owner, "brand", location_id=g1).json()["gross_profit"] == pnl_g1["gross_profit"]
    )


def test_profit_by_shop_and_by_user(client, october):
    owner = october["owner"]
    shops = rows(cut(client, owner, "shop").json())
    assert {k.split()[0]: v["gross_profit"] for k, v in shops.items()} == {
        "S1": "14182.70",  # before the 1,000 stock lost there
        "G1": "1000.00",
    }
    people = rows(cut(client, owner, "user").json())
    assert people["Shop Owner"]["gross_profit"] == "10000.00"
    assert people["Counter, Shop 1"]["gross_profit"] == "5182.70"
    assert people["Shop Owner"]["tons"] == "3.000"
    items = rows(cut(client, owner, "item").json())
    assert items["TMT 12 JSW"]["profit_per_ton"] == "5000.00"
    assert items["Cement PPC"]["profit_per_unit"] == "30.45"
    assert items["Cement PPC"]["margin_per_base_unit"] == "30.4500"
    customers = rows(cut(client, owner, "customer").json())
    assert set(customers) == {"Ravi Builders"}


def test_contribution_per_ton_when_everything_is_sold_by_weight(client, world):
    # Only steel sold: 1 t at ₹56/kg, cost ₹55/kg -> profit 1,000; loading ₹100 -> 900 a ton.
    owner = world["owner"]
    assert post(client, world, body(world, [line(world, "tmt", "1", "ton")])).status_code == 201
    heads = {
        r["name"]: r["id"] for r in client.get("/api/v1/expense-categories", headers=owner).json()
    }
    client.post(
        "/api/v1/cash-book",
        headers=owner,
        json={
            "location_id": world["loc"]["S1"],
            "kind": "expense",
            "mode": "cash",
            "amount": "100",
            "category_id": heads["Loading and unloading labour"],
        },
    )
    r = cut(client, owner, "brand").json()
    assert (r["profit_per_ton"], r["variable_expenses"], r["contribution_per_ton"]) == (
        "1000.00",
        "100.00",
        "900.00",
    )
    assert r["data_note"] is None


def test_an_empty_month_says_not_enough_data_and_roles_are_enforced(client, world):
    owner = world["owner"]
    r = cut(client, owner, "brand").json()
    assert r["rows"] == [] and r["enough_data"] is False
    assert r["profit_per_ton"] is None and r["contribution_per_ton"] is None
    assert "Not enough data" in r["data_note"]
    for who in (COUNTER, ACCOUNTANT):
        assert cut(client, login(client, *who), "brand").status_code == 403
    assert client.get("/api/v1/reports/profitability?by=colour", headers=owner).status_code == 422
    nxt = f"{today_ist().year + 1}-01"
    future = client.get(f"/api/v1/reports/profitability?by=brand&period={nxt}", headers=owner)
    assert future.json()["code"] == "FUTURE_PERIOD"


# ---------------------------------------------------------------- ITC at risk

SUPPLIER_GSTIN = "33BBBBB1234B1Z" + gstin_checksum("33BBBBB1234B1Z")


def bill(client, world, no, rate="55000", quantity="10", date=None):
    r = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": no,
            "bill_date": date or today_ist().isoformat(),
            "lines": [
                {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": quantity, "rate": rate}
            ],
        },
    )
    assert r.status_code == 201, r.text


def itc(client, headers, period=PERIOD):
    return client.get(f"/api/v1/gst/itc-at-risk?period={period}", headers=headers)


def upload_2b(client, world, rows, period=PERIOD):
    text = "gstin,supplier,invoice_no,invoice_date,taxable,igst,cgst,sgst\n" + "".join(rows)
    r = client.post(
        "/api/v1/gst/gstr2b",
        headers=world["owner"],
        data={"period": period},
        files={"file": ("2b.csv", text, "text/csv")},
    )
    assert r.status_code == 201, r.text


def test_itc_at_risk_is_the_in_books_not_in_2b_sum(client, world):
    """Three bills from Mills (GSTIN set): B-1 ₹5,50,000 + 18% = ITC 99,000 (in 2B, matches);
    B-2 ₹1,00,000 -> ITC 18,000 (missing from 2B); B-3 ₹2,00,000 -> ITC 36,000, but the supplier
    reported 35,980 (mismatch: 20 at risk). At risk: 18,000 missing + 20 mismatch = 18,020."""
    owner = world["owner"]
    client.patch(
        f"/api/v1/parties/{world['supplier']['id']}", headers=owner, json={"gstin": SUPPLIER_GSTIN}
    )
    no_2b = itc(client, owner).json()
    assert no_2b["has_2b"] is False and no_2b["note"] == "No GSTR-2B imported for this month"
    assert no_2b["at_risk_total"] is None and no_2b["missing_itc"] is None
    bill(client, world, "B-1", "55000", "10")
    bill(client, world, "B-2", "50000", "2")
    bill(client, world, "B-3", "50000", "4")
    upload_2b(
        client,
        world,
        [
            f"{SUPPLIER_GSTIN},Mills,B-1,01-10-2026,550000,0,49500,49500\n",
            f"{SUPPLIER_GSTIN},Mills,B-3,01-10-2026,200000,0,17990,17990\n",
            "29ABCDE1234F1Z5,Other mill,Z-77,02-10-2026,1000,0,90,90\n",
        ],
    )
    r = itc(client, owner).json()
    assert r["has_2b"] is True and r["note"] is None
    assert r["missing_itc"] == "18000.00" and len(r["missing"]) == 1
    assert (r["missing"][0]["number"], r["missing"][0]["itc"], r["missing"][0]["taxable"]) == (
        "B-2",
        "18000.00",
        "100000.00",
    )
    assert r["mismatch_itc"] == "20.00"
    assert (r["mismatches"][0]["number"], r["mismatches"][0]["portal_itc"]) == ("B-3", "35980.00")
    assert r["at_risk_total"] == "18020.00"
    # It is the same figure the GSTR-2B matching shows for "in books, not in 2B".
    m = client.get(f"/api/v1/gst/gstr2b?period={PERIOD}", headers=owner).json()
    in_books = [x for x in m["rows"] if x["status"] == "missing_in_2b"]
    assert sum(float(x["books_tax"]) for x in in_books) == pytest.approx(float(r["missing_itc"]))
    # GST payable estimate: no sales, so 3B shows only the input credit. 99,000 + 18,000 + 36,000 =
    # 1,53,000 of input tax; payable is minus that, and 18,020 less credit if the risk is lost.
    assert r["payable_estimate"] == "-153000.00"
    assert r["payable_if_unclaimed"] == "-134980.00"
    assert r["payable_to_date"] is True
    year, month = today_ist().year, today_ist().month
    assert r["due_date"] == f"{year + (month == 12)}-{month % 12 + 1:02d}-20"
    # The accountant sees it too; the counter does not.
    assert itc(client, login(client, *ACCOUNTANT)).status_code == 200
    assert itc(client, login(client, *COUNTER)).status_code == 403
    assert itc(client, owner, "2026-13").json()["code"] == "BAD_PERIOD"


def test_bills_from_suppliers_with_no_gstin_are_shown_apart(client, world):
    owner = world["owner"]
    bill(client, world, "N-1", "50000", "2")  # ₹1,00,000 + 18% = ITC 18,000, supplier has no GSTIN
    upload_2b(client, world, ["29ABCDE1234F1Z5,Other,Z-1,02-10-2026,1000,0,90,90\n"])
    r = itc(client, owner).json()
    assert r["at_risk_total"] == "0.00" and r["no_gstin_itc"] == "18000.00"


def test_last_months_bill_is_judged_by_its_own_months_2b(client, world):
    owner = world["owner"]
    client.patch(
        f"/api/v1/parties/{world['supplier']['id']}", headers=owner, json={"gstin": SUPPLIER_GSTIN}
    )
    earlier = today_ist().replace(day=1)
    prev_end = earlier.replace(day=1) - __import__("datetime").timedelta(days=1)
    prev = prev_end.strftime("%Y-%m")
    bill(client, world, "OLD-1", "50000", "2", date=prev_end.isoformat())
    bill(client, world, "NEW-1", "50000", "2")
    upload_2b(client, world, [f"{SUPPLIER_GSTIN},Mills,NEW-1,01-10-2026,100000,0,9000,9000\n"])
    # No 2B for last month was imported, so its bill cannot be judged: it is not counted.
    assert itc(client, owner).json()["at_risk_total"] == "0.00"
    # Last month's 2B listed OLD-1: still nothing at risk.
    upload_2b(
        client,
        world,
        [f"{SUPPLIER_GSTIN},Mills,OLD-1,30-09-2026,100000,0,9000,9000\n"],
        period=prev,
    )
    assert itc(client, owner).json()["at_risk_total"] == "0.00"
    # Last month's 2B imported without it: it is at risk.
    upload_2b(client, world, ["29ABCDE1234F1Z5,Other,Z-1,02-09-2026,1000,0,90,90\n"], period=prev)
    r = itc(client, owner).json()
    assert r["missing_itc"] == "18000.00" and r["missing"][0]["number"] == "OLD-1"
