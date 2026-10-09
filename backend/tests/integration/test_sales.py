"""Milestone 6: sales invoices, GST maths, stock and balance effects, roles, PDF."""

from datetime import timedelta

import pytest

from app.core.clock import today_ist
from tests.conftest import login

pytestmark = pytest.mark.integration

OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")  # S1
COUNTER2 = ("counter2", "counter-pass-123")  # S2
ACCOUNTANT = ("accounts", "accounts-pass-123")


def day(offset: int = 0) -> str:
    return (today_ist() - timedelta(days=offset)).isoformat()


@pytest.fixture
def world(client):
    owner = login(client, *OWNER)
    loc = {x["code"]: x["id"] for x in client.get("/api/v1/locations", headers=owner).json()}
    tmt = client.post(
        "/api/v1/items",
        headers=owner,
        json={
            "name": "TMT 12 mm",
            "category": "tmt",
            "hsn": "72142090",
            "gst_rate": "18",
            "base_unit": "kg",
            "units": [{"unit": "ton", "factor_to_base": "1000"}],
        },
    ).json()
    cement = client.post(
        "/api/v1/items",
        headers=owner,
        json={
            "name": "Cement PPC",
            "category": "cement",
            "hsn": "25232930",
            "gst_rate": "28",
            "base_unit": "bag",
            "base_whole_only": True,
        },
    ).json()
    client.post(
        "/api/v1/opening",
        headers=owner,
        json={
            "kind": "stock",
            "as_of": day(30),
            "item_id": tmt["id"],
            "location_id": loc["S1"],
            "quantity": "5000",
            "unit_cost": "55",
        },
    )
    client.post(
        "/api/v1/opening",
        headers=owner,
        json={
            "kind": "stock",
            "as_of": day(30),
            "item_id": tmt["id"],
            "location_id": loc["G1"],
            "quantity": "20000",
            "unit_cost": "55",
        },
    )
    client.post(
        "/api/v1/opening",
        headers=owner,
        json={
            "kind": "stock",
            "as_of": day(30),
            "item_id": cement["id"],
            "location_id": loc["S1"],
            "quantity": "100",
            "unit_cost": "350",
        },
    )
    assert (
        client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["stock"]}).status_code
        == 200
    )
    client.put(
        "/api/v1/rates/market",
        headers=owner,
        json={
            "effective_date": day(1),
            "rates": [
                {"item_id": tmt["id"], "rate": "56000", "unit": "ton"},
                {"item_id": cement["id"], "rate": "380.45"},
            ],
        },
    )
    ravi = client.post(
        "/api/v1/parties",
        headers=owner,
        json={
            "name": "Ravi Builders",
            "type": "customer",
            "state_code": "33",
            "gstin": "33AAPFU0939F1Z2",
            "address": "12 Main Road, Chennai",
            "sites": [
                {"name": "Chennai site", "state_code": "33"},
                {"name": "Hosur site", "state_code": "29", "address": "Plot 4, Hosur"},
            ],
        },
    ).json()
    walkin = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Walk-in", "type": "customer", "state_code": "33"},
    ).json()
    for party in (ravi, walkin):  # approved for credit, so M6 bills need no payment
        client.patch(
            f"/api/v1/parties/{party['id']}",
            headers=owner,
            json={"credit_allowed": True, "credit_limit": "10000000", "credit_days": 30},
        )
    supplier = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Mills", "type": "supplier", "state_code": "33"},
    ).json()
    return {
        "owner": owner,
        "loc": loc,
        "tmt": tmt,
        "cement": cement,
        "ravi": ravi,
        "walkin": walkin,
        "supplier": supplier,
        "sites": {s["name"]: s["id"] for s in ravi["sites"]},
    }


def body(world, lines, party="ravi", location="S1", site=None, **extra):
    return {
        "location_id": world["loc"][location],
        "party_id": world[party]["id"],
        "site_id": world["sites"][site] if site else None,
        "lines": lines,
    } | extra


def line(world, item, quantity, unit=None, **extra):
    return {"item_id": world[item]["id"], "quantity": quantity, "unit": unit} | extra


def post(client, world, payload, headers=None, key=None):
    h = dict(headers or world["owner"])
    if key:
        h["Idempotency-Key"] = key
    return client.post("/api/v1/invoices", headers=h, json=payload)


# ---------------------------------------------------------------- acceptance: totals


def test_totals_match_a_manual_calculation(client, world):
    # 2.5 ton TMT at 56,000 a ton: 2,500 kg x 56 = 1,40,000.00; GST 18% = 25,200 (9% + 9% = 12,600 each).
    # 7 bags cement at 380.45 = 2,663.15; GST 28%: 14% = 372.841 -> 372.84 each, 745.68 in all.
    # Taxable 1,42,663.15; CGST 12,600 + 372.84 = 12,972.84; SGST the same.
    # Before round-off 1,42,663.15 + 25,945.68 = 1,68,608.83; the bill is rounded to 1,68,609.00 (+0.17).
    response = post(
        client, world, body(world, [line(world, "tmt", "2.5", "ton"), line(world, "cement", "7")])
    )
    assert response.status_code == 201, response.text
    inv = response.json()
    assert inv["number"] == "S1/26-27/00001" and len(inv["number"]) <= 16
    assert (inv["taxable_value"], inv["cgst"], inv["sgst"], inv["igst"]) == (
        "142663.15",
        "12972.84",
        "12972.84",
        "0.00",
    )
    assert (inv["round_off"], inv["grand_total"]) == ("0.17", "168609.00")
    first, second = inv["lines"]
    assert (
        first["base_qty"],
        first["rate"],
        first["taxable"],
        first["cgst"],
        first["line_total"],
    ) == ("2500.000", "56.000000", "140000.00", "12600.00", "165200.00")
    assert (second["base_qty"], second["taxable"], second["cgst"], second["line_total"]) == (
        "7.000",
        "2663.15",
        "372.84",
        "3408.83",
    )
    assert inv["supply_type"] == "B2B" and inv["supply_kind"] == "intra_state"
    assert inv["bill_to_gstin"] == "33AAPFU0939F1Z2" and inv["place_of_supply"] == "33"
    # What was printed is kept as text and stock left is on the line.
    assert first["stock_after"] == "2500.000" and second["stock_after"] == "93.000"


def test_inter_state_delivery_uses_igst_and_ship_to_state(client, world):
    inv = post(
        client, world, body(world, [line(world, "tmt", "2.5", "ton")], site="Hosur site")
    ).json()
    # Delivered to Karnataka (29): IGST 18% of 1,40,000 = 25,200, no CGST or SGST.
    assert (inv["cgst"], inv["sgst"], inv["igst"], inv["grand_total"]) == (
        "0.00",
        "0.00",
        "25200.00",
        "165200.00",
    )
    assert inv["supply_kind"] == "inter_state" and inv["place_of_supply"] == "29"
    assert inv["ship_to_name"] == "Hosur site" and inv["ship_to_gstin"] is None  # prints URP


def test_walk_in_sale_is_a_normal_b2c_tax_invoice(client, world):
    inv = post(client, world, body(world, [line(world, "cement", "10")], party="walkin")).json()
    # 10 bags x 380.45 = 3,804.50; GST 28% = 1,065.26 (532.63 each); total 4,869.76 -> 4,870.00.
    assert (inv["supply_type"], inv["taxable_value"], inv["cgst"], inv["grand_total"]) == (
        "B2C",
        "3804.50",
        "532.63",
        "4870.00",
    )
    assert (
        inv["bill_to_gstin"] is None
        and inv["due_date"] == (today_ist() + timedelta(days=30)).isoformat()
    )


def test_saving_moves_stock_and_adds_to_what_the_customer_owes(client, world):
    owner = world["owner"]
    first = post(client, world, body(world, [line(world, "tmt", "1", "ton")])).json()
    assert first["pending_balance_at_billing"] == "0.00"
    second = post(client, world, body(world, [line(world, "tmt", "1", "ton")])).json()
    # The second bill shows what the customer already owed: the first bill (1,000 x 56 x 1.18 = 66,080).
    assert second["pending_balance_at_billing"] == "66080.00"
    stock = {r["name"]: r for r in client.get("/api/v1/stock", headers=owner).json()}["TMT 12 mm"]
    assert {x["code"]: x["quantity"] for x in stock["locations"]} == {
        "S1": "3000.000",
        "G1": "20000.000",
    }
    statement = client.get(
        f"/api/v1/parties/{world['ravi']['id']}/statement", headers=owner
    ).json()["receivable"]
    assert statement["balance"] == "132160.00"
    assert [e["doc_no"] for e in statement["entries"]] == [first["number"], second["number"]]
    assert second["number"] == "S1/26-27/00002"


def test_due_date_follows_the_customers_credit_days(client, world):
    owner = world["owner"]
    client.patch(
        f"/api/v1/parties/{world['ravi']['id']}",
        headers=owner,
        json={"credit_allowed": True, "credit_limit": "500000", "credit_days": 10},
    )
    inv = post(client, world, body(world, [line(world, "cement", "1")])).json()
    assert inv["due_date"] == (today_ist() + timedelta(days=10)).isoformat()


# ---------------------------------------------------------------- fulfilment and stock


def test_godown_and_direct_lines(client, world):
    owner = world["owner"]
    # More than the shop holds can come from the godown (B10); the shop's stock is untouched.
    from_godown = post(
        client,
        world,
        body(
            world,
            [
                line(
                    world,
                    "tmt",
                    "10",
                    "ton",
                    source="godown",
                    source_location_id=world["loc"]["G1"],
                )
            ],
        ),
    ).json()
    assert from_godown["lines"][0]["stock_after"] == "10000.000"
    stock = {r["name"]: r for r in client.get("/api/v1/stock", headers=owner).json()}["TMT 12 mm"]
    assert {x["code"]: x["quantity"] for x in stock["locations"]} == {
        "S1": "5000.000",
        "G1": "10000.000",
    }
    # A direct line (supplier to site) moves no stock, even for more than anyone holds.
    direct = post(client, world, body(world, [line(world, "tmt", "100", "ton", source="direct")]))
    assert direct.status_code == 201 and direct.json()["lines"][0]["stock_after"] is None
    assert {
        x["code"]: x["quantity"]
        for x in {r["name"]: r for r in client.get("/api/v1/stock", headers=owner).json()}[
            "TMT 12 mm"
        ]["locations"]
    } == {"S1": "5000.000", "G1": "10000.000"}


def test_stock_cannot_go_negative(client, world):
    short = post(client, world, body(world, [line(world, "cement", "101")]))
    assert short.status_code == 409 and short.json()["code"] == "INSUFFICIENT_STOCK"
    assert "100" in short.json()["message"]
    # The same item twice on one bill is added up before the check.
    twice = post(
        client, world, body(world, [line(world, "cement", "60"), line(world, "cement", "60")])
    )
    assert twice.status_code == 409 and twice.json()["code"] == "INSUFFICIENT_STOCK"
    assert post(client, world, body(world, [line(world, "cement", "100")])).status_code == 201
    none_left = post(client, world, body(world, [line(world, "cement", "1")]))
    assert none_left.json()["code"] == "INSUFFICIENT_STOCK"
    no_place = post(client, world, body(world, [line(world, "tmt", "1", source="godown")]))
    assert no_place.status_code == 409 and no_place.json()["code"] == "GODOWN_NEEDS_PLACE"


def test_a_line_without_a_rate_is_blocked(client, world):
    owner = world["owner"]
    pipe = client.post(
        "/api/v1/items",
        headers=owner,
        json={
            "name": "Pipe",
            "category": "pipe",
            "hsn": "73064000",
            "gst_rate": "18",
            "base_unit": "kg",
        },
    ).json()
    world["pipe"] = pipe
    client.post(
        "/api/v1/opening",
        headers=owner,
        json={
            "kind": "stock",
            "as_of": day(5),
            "item_id": pipe["id"],
            "location_id": world["loc"]["S1"],
            "quantity": "100",
            "unit_cost": "50",
        },
    )
    client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["stock"]})
    blocked = post(client, world, body(world, [line(world, "pipe", "10")]))
    assert blocked.status_code == 409 and blocked.json()["code"] == "PRICE_NOT_SET"


# ---------------------------------------------------------------- roles, discounts, below cost


def test_counter_bills_own_shop_and_never_sees_cost_or_profit(client, world):
    counter = login(client, *COUNTER)
    response = post(client, world, body(world, [line(world, "tmt", "1", "ton")]), headers=counter)
    assert response.status_code == 201, response.text
    inv = response.json()
    assert "profit" not in inv and "cost_per_unit" not in inv["lines"][0]
    text = client.get(f"/api/v1/invoices/{inv['id']}", headers=counter).text
    assert "cost_per_unit" not in text and "profit" not in text and "55.0000" not in text

    owner_view = client.get(f"/api/v1/invoices/{inv['id']}", headers=world["owner"]).json()
    # Sold 1,000 kg at 56.00 = 56,000; cost 55.0000 a kg = 55,000: profit 1,000.00.
    assert (
        owner_view["lines"][0]["cost_per_unit"],
        owner_view["lines"][0]["profit"],
        owner_view["profit"],
    ) == ("55.0000", "1000.00", "1000.00")

    other = login(client, *COUNTER2)
    assert (
        post(client, world, body(world, [line(world, "tmt", "1")]), headers=other).status_code
        == 403
    )
    assert client.get(f"/api/v1/invoices/{inv['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=other).status_code == 404
    assert client.get("/api/v1/invoices", headers=other).json()["total"] == 0
    assert client.get("/api/v1/invoices", headers=counter).json()["total"] == 1
    accountant = login(client, *ACCOUNTANT)
    assert client.get("/api/v1/invoices", headers=accountant).json()["total"] == 1
    assert "profit" not in client.get(f"/api/v1/invoices/{inv['id']}", headers=accountant).text
    assert (
        post(client, world, body(world, [line(world, "tmt", "1")]), headers=accountant).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/invoices/preview",
            headers=accountant,
            json=body(world, [line(world, "tmt", "1")]),
        ).status_code
        == 403
    )
    assert client.get("/api/v1/invoices").status_code == 401


def test_staff_cannot_discount_or_change_the_price_but_the_owner_can(client, world):
    counter = login(client, *COUNTER)
    for extra in ({"discount": "500", "discount_reason": "regular"}, {"rate_override": "50000"}):
        denied = post(
            client, world, body(world, [line(world, "tmt", "1", "ton", **extra)]), headers=counter
        )
        assert denied.status_code == 409
        assert (
            denied.json()["code"] == "DISCOUNT_NEEDS_OWNER"
            and denied.json()["requires_owner_approval"] is True
        )
    # Owner: Rs 500 off 56,000 taxable -> 55,500; GST 18% = 9,990; total 65,490.
    ok = post(
        client,
        world,
        body(world, [line(world, "tmt", "1", "ton", discount="500", discount_reason="bulk")]),
    ).json()
    assert (ok["lines"][0]["discount"], ok["taxable_value"], ok["grand_total"]) == (
        "500.00",
        "55500.00",
        "65490.00",
    )
    no_reason = post(client, world, body(world, [line(world, "tmt", "1", "ton", discount="500")]))
    assert no_reason.json()["code"] == "DISCOUNT_REASON"
    too_big = post(
        client,
        world,
        body(world, [line(world, "cement", "1", discount="999", discount_reason="x")]),
    )
    assert too_big.json()["code"] == "DISCOUNT_TOO_BIG"
    # The owner may set a one-off price: 54,000 a ton -> 1,000 kg = 54,000 taxable.
    custom = post(
        client, world, body(world, [line(world, "tmt", "1", "ton", rate_override="54000")])
    ).json()
    assert custom["taxable_value"] == "54000.00"


def test_selling_below_cost_needs_the_owner_and_never_reveals_the_cost(client, world):
    owner = world["owner"]
    client.put(
        "/api/v1/rates/market",
        headers=owner,
        json={
            "effective_date": day(0),
            "rates": [{"item_id": world["tmt"]["id"], "rate": "54000", "unit": "ton"}],
        },
    )  # cost is 55,000 a ton
    counter = login(client, *COUNTER)
    blocked = post(client, world, body(world, [line(world, "tmt", "1", "ton")]), headers=counter)
    assert blocked.status_code == 409 and blocked.json()["code"] == "BELOW_COST"
    assert blocked.json()["requires_owner_approval"] is True
    assert "55" not in blocked.json()["message"]
    assert (
        post(client, world, body(world, [line(world, "tmt", "1", "ton")])).status_code == 201
    )  # owner


def test_back_dating_is_the_owners_alone_and_future_dates_are_refused(client, world):
    counter = login(client, *COUNTER)
    backdated = post(
        client,
        world,
        body(world, [line(world, "cement", "1")], invoice_date=day(3)),
        headers=counter,
    )
    assert backdated.status_code == 409 and backdated.json()["code"] == "BACKDATE_NEEDS_OWNER"
    tomorrow = (today_ist() + timedelta(days=1)).isoformat()
    assert (
        post(
            client, world, body(world, [line(world, "cement", "1")], invoice_date=tomorrow)
        ).json()["code"]
        == "FUTURE_DATE"
    )
    assert (
        post(
            client, world, body(world, [line(world, "cement", "1")], invoice_date=day(1))
        ).status_code
        == 201
    )


def test_validation(client, world):
    cases = [
        (body(world, [line(world, "tmt", "1")], party="supplier"), 409, "WRONG_PARTY_TYPE"),
        (body(world, [line(world, "tmt", "1")]) | {"party_id": 99999}, 404, None),
        (body(world, [line(world, "tmt", "1")]) | {"location_id": 99999}, 404, None),
        (body(world, [line(world, "tmt", "1")]) | {"site_id": 99999}, 409, "SITE_MISMATCH"),
        (body(world, [{"item_id": 99999, "quantity": "1"}]), 404, None),
        (body(world, [line(world, "tmt", "1", "bag")]), 409, "UNKNOWN_UNIT"),
        (body(world, [line(world, "cement", "1.5")]), 409, "UNIT_NOT_WHOLE"),
        (body(world, []), 422, None),
        (body(world, [line(world, "tmt", "0")]), 422, None),
        (
            body(world, [line(world, "tmt", "1", source="godown", source_location_id=99999)]),
            404,
            None,
        ),
    ]
    for payload, status, code in cases:
        response = post(client, world, payload)
        assert response.status_code == status, (payload, response.text)
        if code:
            assert response.json()["code"] == code


# ---------------------------------------------------------------- idempotency, preview, reading, PDF


def test_a_retried_save_returns_the_first_bill(client, world):
    payload = body(world, [line(world, "tmt", "1", "ton")])
    first = post(client, world, payload, key="abc-123")
    again = post(client, world, payload, key="abc-123")
    assert first.status_code == 201 and again.status_code == 200
    assert (
        again.json()["id"] == first.json()["id"]
        and again.json()["number"] == first.json()["number"]
    )
    other = post(
        client, world, body(world, [line(world, "tmt", "1")], party="walkin"), key="abc-123"
    )
    assert other.status_code == 409 and other.json()["code"] == "IDEMPOTENCY_CONFLICT"
    stock = {r["name"]: r for r in client.get("/api/v1/stock", headers=world["owner"]).json()}[
        "TMT 12 mm"
    ]
    assert {x["code"]: x["quantity"] for x in stock["locations"]}["S1"] == "4000.000"  # sold once
    # A failed save leaves no gap: the next bill takes the next number.
    assert post(client, world, body(world, [line(world, "cement", "9999")])).status_code == 409
    assert post(client, world, payload).json()["number"] == "S1/26-27/00002"


def test_preview_shows_totals_and_problems_without_saving(client, world):
    counter = login(client, *COUNTER)
    payload = body(world, [line(world, "tmt", "1", "ton"), line(world, "cement", "500")])
    preview = client.post("/api/v1/invoices/preview", headers=counter, json=payload)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["can_save"] is False
    assert data["lines"][0]["problems"] == [] and data["lines"][0]["line_total"] == "66080.00"
    assert data["lines"][1]["problems"] and "Only 100" in data["lines"][1]["problems"][0]
    assert data["lines"][1]["stock_available"] == "100.000"
    assert client.get("/api/v1/invoices", headers=world["owner"]).json()["total"] == 0
    good = client.post(
        "/api/v1/invoices/preview",
        headers=counter,
        json=body(world, [line(world, "tmt", "1", "ton")]),
    ).json()
    assert (
        good["can_save"] is True
        and good["grand_total"] == "66080.00"
        and good["pending_balance"] == "0.00"
    )
    text = str(good)
    assert "cost" not in text.lower()


def test_list_filters_and_pdf(client, world):
    owner = world["owner"]
    first = post(client, world, body(world, [line(world, "cement", "2")])).json()
    post(client, world, body(world, [line(world, "cement", "3")], party="walkin"))
    assert client.get("/api/v1/invoices", headers=owner).json()["total"] == 2
    by_party = client.get(f"/api/v1/invoices?party_id={world['ravi']['id']}", headers=owner).json()
    assert [i["number"] for i in by_party["items"]] == [first["number"]]
    assert client.get("/api/v1/invoices?q=walk", headers=owner).json()["total"] == 1
    assert (
        client.get(f"/api/v1/invoices?date_from={day(0)}&date_to={day(0)}", headers=owner).json()[
            "total"
        ]
        == 2
    )
    assert client.get(f"/api/v1/invoices?date_to={day(5)}", headers=owner).json()["total"] == 0
    assert client.get("/api/v1/invoices/99999", headers=owner).status_code == 404

    pdf = client.get(f"/api/v1/invoices/{first['id']}/pdf?copy=duplicate", headers=owner)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:5] == b"%PDF-" and len(pdf.content) > 3000
    assert "S1-26-27-00001.pdf" in pdf.headers["content-disposition"]
    counter = login(client, *COUNTER)
    assert client.get(f"/api/v1/invoices/{first['id']}/pdf", headers=counter).status_code == 200
