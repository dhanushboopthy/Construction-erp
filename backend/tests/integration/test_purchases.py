"""Milestone 4: purchases with landed cost, supplier payments, transfers and stock counts."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.clock import today_ist
from app.models.setup import ShopSettings
from tests.conftest import login

pytestmark = pytest.mark.integration

OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")  # works at S1
COUNTER2 = ("counter2", "counter-pass-123")  # works at S2
ACCOUNTANT = ("accounts", "accounts-pass-123")

MONEY_FIELDS = (
    "unit_cost",
    "total_cost",
    "goods_value",
    "gst_amount",
    "charges_total",
    "supplier_payable",
    "rate",
    "avg_cost",
    "value",
)


def day(offset: int = 0) -> str:
    return (today_ist() - timedelta(days=offset)).isoformat()


@pytest.fixture
def world(client):
    owner = login(client, *OWNER)
    locations = {x["code"]: x["id"] for x in client.get("/api/v1/locations", headers=owner).json()}
    tmt = client.post(
        "/api/v1/items",
        headers=owner,
        json={
            "name": "TMT 12 mm",
            "category": "tmt",
            "hsn": "72142090",
            "gst_rate": "18",
            "base_unit": "kg",
            "weight_per_piece_kg": "10.656",
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
    supplier = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Steel Mills", "type": "supplier", "state_code": "33"},
    ).json()
    components = {
        c["name"]: c["id"] for c in client.get("/api/v1/cost-components", headers=owner).json()
    }
    return {
        "owner": owner,
        "loc": locations,
        "tmt": tmt,
        "cement": cement,
        "supplier": supplier,
        "comp": components,
    }


def bill(world, bill_no="B-1", location="S1", lines=None, **extra):
    default_lines = [
        {
            "item_id": world["tmt"]["id"],
            "unit": "ton",
            "quantity": "10",
            "rate": "55000",
            "charges": [
                {"component_id": world["comp"]["Unloading"], "amount": "250"},
                {"component_id": world["comp"]["Weighbridge"], "amount": "150"},
                {"component_id": world["comp"]["Transport rent"], "amount": "4000"},
            ],
        }
    ]
    return {
        "supplier_id": world["supplier"]["id"],
        "location_id": world["loc"][location],
        "bill_no": bill_no,
        "bill_date": day(1),
        "lines": default_lines if lines is None else lines,
    } | extra


def post_purchase(client, world, headers=None, **kw):
    return client.post(
        "/api/v1/purchases", headers=headers or world["owner"], json=bill(world, **kw)
    )


# ------------------------------------------------------- acceptance: landed and average cost


def test_sample_purchases_give_the_hand_calculated_landed_and_average_cost(client, world):
    owner = world["owner"]
    first = post_purchase(client, world)
    assert first.status_code == 201, first.text
    p1 = first.json()
    # 10 ton at 55,000 = 5,50,000 + charges (250 x 10 ton = 2,500; 150; 4,000 = 6,650) = 5,56,650.
    # Per kg: 556,650 / 10,000 kg = 55.6650. GST 18% = 99,000 goes to the supplier, not into cost.
    line = p1["lines"][0]
    assert (line["goods_value"], line["charges_total"], line["total_cost"], line["unit_cost"]) == (
        "550000.00",
        "6650.00",
        "556650.00",
        "55.6650",
    )
    assert (p1["gst_amount"], p1["supplier_payable"]) == ("99000.00", "649000.00")
    assert p1["number"] == "S1P/26-27/00001" and len(p1["number"]) <= 16
    assert [c["total"] for c in line["costs"]] == ["2500.00", "150.00", "4000.00"]

    # A second bill with a weighbridge shortage: billed 5 ton, received 4.950 ton (weight 4,950 kg).
    # Cost (285,000 + 150) / 4,950 kg = 57.6061 per kg: the shortage raises the unit cost.
    second = post_purchase(
        client,
        world,
        bill_no="B-2",
        location="G1",
        lines=[
            {
                "item_id": world["tmt"]["id"],
                "unit": "ton",
                "quantity": "5",
                "received_quantity": "4.95",
                "rate": "57000",
                "charges": [{"component_id": world["comp"]["Weighbridge"], "amount": "150"}],
            }
        ],
    )
    assert second.json()["lines"][0]["unit_cost"] == "57.6061"
    assert second.json()["lines"][0]["received_qty"] == "4950.000"
    assert second.json()["number"] == "G1P/26-27/00001"

    # Company-wide average: (10,000 x 55.6650 + 4,950 x 57.6061) / 14,950 = 56.3077;
    # value 14,950 x 56.3077 = 8,41,800.12.
    stock = client.get("/api/v1/stock", headers=owner).json()[0]
    assert (stock["quantity"], stock["avg_cost"], stock["value"]) == (
        "14950.000",
        "56.3077",
        "841800.12",
    )
    assert {x["code"]: x["quantity"] for x in stock["locations"]} == {
        "S1": "10000.000",
        "G1": "4950.000",
    }

    # The supplier is owed 6,49,000 + (2,85,000 + 51,300 GST = 3,36,300) = 9,85,300.
    statement = client.get(
        f"/api/v1/parties/{world['supplier']['id']}/statement", headers=owner
    ).json()
    assert statement["payable"]["balance"] == "985300.00"


def test_gst_goes_into_cost_only_when_the_setting_says_so(client, world, seeded):
    row = seeded.execute(select(ShopSettings)).scalar_one()
    row.include_gst_in_cost = True
    seeded.commit()
    unit_cost = post_purchase(client, world).json()["lines"][0]["unit_cost"]
    # (550,000 + 6,650 + GST 99,000) / 10,000 = 65.5650
    assert unit_cost == "65.5650"


def test_preview_matches_what_is_saved_and_is_for_the_owner_only(client, world):
    body = bill(world)
    preview = client.post("/api/v1/purchases/preview", headers=world["owner"], json=body).json()
    saved = client.post("/api/v1/purchases", headers=world["owner"], json=body).json()
    assert preview["supplier_payable"] == saved["supplier_payable"] == "649000.00"
    assert preview["lines"][0]["unit_cost"] == saved["lines"][0]["unit_cost"]
    assert client.get("/api/v1/stock", headers=world["owner"]).json()[0]["quantity"] == "10000.000"
    for who in (COUNTER, ACCOUNTANT):
        headers = login(client, *who)
        assert (
            client.post("/api/v1/purchases/preview", headers=headers, json=body).status_code == 403
        )


def test_charges_on_the_suppliers_bill_are_payable_to_the_supplier(client, world):
    lines = [
        {
            "item_id": world["tmt"]["id"],
            "unit": "kg",
            "quantity": "1000",
            "rate": "55",
            "charges": [
                {
                    "component_id": world["comp"]["Transport rent"],
                    "amount": "1000",
                    "on_supplier_bill": True,
                },
                {"name": "Tea for the labour", "basis": "flat", "amount": "100"},
            ],
        }
    ]
    saved = post_purchase(client, world, lines=lines).json()
    # Goods 55,000 + GST 9,900 + transport 1,000 on the bill = 65,900 payable.
    # Cost: 55,000 + 1,000 + 100 = 56,100 / 1,000 kg = 56.1000. The tea is ours, not the supplier's.
    assert saved["supplier_payable"] == "65900.00"
    assert saved["lines"][0]["unit_cost"] == "56.1000"


def test_direct_purchases_add_no_stock_but_still_owe_the_supplier(client, world):
    saved = post_purchase(client, world, mode="direct").json()
    assert client.get("/api/v1/stock", headers=world["owner"]).json() == []
    statement = client.get(
        f"/api/v1/parties/{world['supplier']['id']}/statement", headers=world["owner"]
    ).json()
    assert statement["payable"]["balance"] == saved["supplier_payable"]


# ---------------------------------------------------------------- roles and costs


def test_counter_enters_for_own_shop_and_never_sees_cost(client, world):
    counter = login(client, *COUNTER)
    response = post_purchase(client, world, headers=counter)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["lines"][0]["received_qty"] == "10000.000"
    for name in MONEY_FIELDS:
        assert name not in body and name not in body["lines"][0], name
    text = client.get(f"/api/v1/purchases/{body['id']}", headers=counter).text
    assert "55.665" not in text and "550000" not in text and "649000" not in text

    listing = client.get("/api/v1/purchases", headers=counter)
    assert listing.json()["total"] == 1 and "supplier_payable" not in listing.text
    # The other shop's counter staff cannot see it, enter for S1, or open it by number.
    other = login(client, *COUNTER2)
    assert client.get("/api/v1/purchases", headers=other).json()["total"] == 0
    assert client.get(f"/api/v1/purchases/{body['id']}", headers=other).status_code == 404
    assert post_purchase(client, world, headers=other, bill_no="X").status_code == 403

    accountant = login(client, *ACCOUNTANT)
    assert "supplier_payable" not in client.get("/api/v1/purchases", headers=accountant).text
    assert (
        client.post("/api/v1/purchases", headers=accountant, json=bill(world, "Y")).status_code
        == 403
    )
    assert client.get("/api/v1/purchases", headers=world["owner"]).json()["items"][0][
        "supplier_payable"
    ]


def test_owner_can_switch_off_purchase_entry_for_counter_staff(client, world):
    headers = world["owner"]
    current = client.get("/api/v1/settings", headers=headers).json()
    body = {k: v for k, v in current.items() if k != "id"} | {"counter_can_enter_purchases": False}
    assert client.put("/api/v1/settings", headers=headers, json=body).status_code == 200
    counter = login(client, *COUNTER)
    denied = post_purchase(client, world, headers=counter)
    assert denied.status_code == 403
    assert post_purchase(client, world).status_code == 201


def test_purchase_rules(client, world):
    owner = world["owner"]
    assert post_purchase(client, world).status_code == 201
    dup = post_purchase(client, world)  # same supplier and bill number
    assert dup.status_code == 409 and dup.json()["code"] == "DUPLICATE_BILL"
    # The failed attempt must not burn a document number (gapless, B16).
    nxt = post_purchase(client, world, bill_no="B-2").json()["number"]
    assert nxt == "S1P/26-27/00002"

    cases = [
        (bill(world, "C1") | {"supplier_id": world["loc"]["S1"] + 9999}, 404, "supplier_id"),
        (bill(world, "C2") | {"location_id": 99999}, 404, "location_id"),
        (
            bill(
                world, "C3", lines=[{"item_id": 99999, "unit": "kg", "quantity": "1", "rate": "1"}]
            ),
            404,
            "item_id",
        ),
        (
            bill(
                world,
                "C4",
                lines=[
                    {"item_id": world["tmt"]["id"], "unit": "bag", "quantity": "1", "rate": "1"}
                ],
            ),
            409,
            "unit",
        ),
        (
            bill(
                world,
                "C5",
                lines=[
                    {
                        "item_id": world["cement"]["id"],
                        "unit": "bag",
                        "quantity": "10.5",
                        "rate": "380",
                    }
                ],
            ),
            409,
            "quantity",
        ),
        (
            bill(
                world,
                "C6",
                lines=[
                    {
                        "item_id": world["cement"]["id"],
                        "unit": "bag",
                        "quantity": "10",
                        "rate": "380",
                        "charges": [{"component_id": world["comp"]["Unloading"], "amount": "250"}],
                    }
                ],
            ),
            409,
            "charges",
        ),
        (bill(world, "C7") | {"due_date": day(10)}, 422, "due_date"),
        (bill(world, "C8", lines=[]), 422, "lines"),
        (
            bill(
                world,
                "C9",
                lines=[
                    {
                        "item_id": world["tmt"]["id"],
                        "unit": "kg",
                        "quantity": "1",
                        "rate": "1",
                        "charges": [{"amount": "5"}],
                    }
                ],
            ),
            422,
            None,
        ),
        (
            bill(
                world,
                "C10",
                lines=[
                    {
                        "item_id": world["tmt"]["id"],
                        "unit": "kg",
                        "quantity": "1",
                        "rate": "1",
                        "charges": [{"component_id": 99999, "amount": "5"}],
                    }
                ],
            ),
            404,
            "component_id",
        ),
    ]
    for body, status, field in cases:
        response = client.post("/api/v1/purchases", headers=owner, json=body)
        assert response.status_code == status, (body["bill_no"], response.text)
        if field:
            assert response.json()["field"] in (field, f"lines.0.{field}", f"{field}"), (
                response.text
            )
    customer = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "A Customer", "type": "customer", "state_code": "33"},
    ).json()
    wrong = client.post(
        "/api/v1/purchases",
        headers=owner,
        json=bill(world, "C11") | {"supplier_id": customer["id"]},
    )
    assert wrong.status_code == 409 and wrong.json()["code"] == "WRONG_PARTY_TYPE"
    # Cement is bought by the bag, and a per-bag charge is fine on an item that is not weighed.
    ok = post_purchase(
        client,
        world,
        bill_no="C12",
        lines=[
            {
                "item_id": world["cement"]["id"],
                "unit": "bag",
                "quantity": "200",
                "rate": "380",
                "charges": [{"name": "Unloading per bag", "basis": "per_base_unit", "amount": "3"}],
            }
        ],
    )
    # 200 x 380 = 76,000 + 600 unloading = 76,600 / 200 bags = 383.0000.
    assert ok.json()["lines"][0]["unit_cost"] == "383.0000"
    assert client.get("/api/v1/purchases/99999", headers=owner).status_code == 404
    listing = client.get(
        f"/api/v1/purchases?supplier_id={world['supplier']['id']}", headers=owner
    ).json()
    assert listing["total"] == 3


def test_charge_types_are_owner_managed(client, world):
    owner = world["owner"]
    created = client.post(
        "/api/v1/cost-components",
        headers=owner,
        json={"name": "Crane hire", "basis": "per_trip", "default_amount": "1500"},
    )
    assert created.status_code == 201
    assert (
        client.post(
            "/api/v1/cost-components", headers=owner, json={"name": "crane hire", "basis": "flat"}
        ).status_code
        == 409
    )
    off = client.patch(
        f"/api/v1/cost-components/{created.json()['id']}", headers=owner, json={"is_active": False}
    )
    assert off.json()["is_active"] is False
    names = [c["name"] for c in client.get("/api/v1/cost-components", headers=owner).json()]
    assert "Crane hire" not in names
    assert "Crane hire" in [
        c["name"]
        for c in client.get("/api/v1/cost-components?include_inactive=true", headers=owner).json()
    ]
    counter = login(client, *COUNTER)
    assert client.get("/api/v1/cost-components", headers=counter).status_code == 200
    assert (
        client.post(
            "/api/v1/cost-components", headers=counter, json={"name": "x", "basis": "flat"}
        ).status_code
        == 403
    )
    assert client.patch("/api/v1/cost-components/1", headers=counter, json={}).status_code == 403
    assert (
        client.get("/api/v1/cost-components", headers=login(client, *ACCOUNTANT)).status_code == 403
    )


# ---------------------------------------------------------------- supplier advance and payments


def test_supplier_advance_is_used_by_the_next_bill_and_payments_are_idempotent(client, world):
    owner = world["owner"]
    supplier = world["supplier"]["id"]
    advance = {
        "party_id": supplier,
        "location_id": world["loc"]["S1"],
        "amount": "200000",
        "mode": "bank",
        "reference": "UTR123",
        "payment_date": day(5),
    }
    first = client.post("/api/v1/payments", headers=owner | {"Idempotency-Key": "k1"}, json=advance)
    assert first.status_code == 201 and first.json()["number"] == "S1R/26-27/00001"
    again = client.post("/api/v1/payments", headers=owner | {"Idempotency-Key": "k1"}, json=advance)
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    clash = client.post(
        "/api/v1/payments",
        headers=owner | {"Idempotency-Key": "k1"},
        json=advance | {"amount": "5"},
    )
    assert clash.status_code == 409 and clash.json()["code"] == "IDEMPOTENCY_CONFLICT"

    statement = client.get(f"/api/v1/parties/{supplier}/statement", headers=owner).json()["payable"]
    assert (statement["balance"], statement["advance"]) == (
        "-200000.00",
        "200000.00",
    )  # we hold an advance

    post_purchase(client, world)  # payable 6,49,000
    statement = client.get(f"/api/v1/parties/{supplier}/statement", headers=owner).json()["payable"]
    # The 2,00,000 advance is used first: 6,49,000 - 2,00,000 = 4,49,000 still owed.
    assert (statement["balance"], statement["advance"]) == ("449000.00", "0.00")
    assert len(client.get("/api/v1/stock", headers=owner).json()) == 1

    listed = client.get(f"/api/v1/payments?party_id={supplier}", headers=owner).json()
    assert [p["number"] for p in listed] == ["S1R/26-27/00001"]
    assert client.get("/api/v1/payments", headers=login(client, *ACCOUNTANT)).status_code == 200


def test_payment_rules_and_roles(client, world):
    owner = world["owner"]
    base = {
        "party_id": world["supplier"]["id"],
        "location_id": world["loc"]["S1"],
        "amount": "100",
        "mode": "cash",
        "payment_date": day(0),
    }
    for who in (COUNTER, ACCOUNTANT):
        headers = login(client, *who)
        assert client.post("/api/v1/payments", headers=headers, json=base).status_code == 403
    assert client.get("/api/v1/payments", headers=login(client, *COUNTER)).status_code == 403
    customer = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Cust", "type": "customer", "state_code": "33"},
    ).json()
    assert (
        client.post(
            "/api/v1/payments", headers=owner, json=base | {"party_id": customer["id"]}
        ).json()["code"]
        == "WRONG_PARTY_TYPE"
    )
    assert (
        client.post("/api/v1/payments", headers=owner, json=base | {"party_id": 99999}).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/payments", headers=owner, json=base | {"location_id": 99999}
        ).status_code
        == 404
    )
    assert (
        client.post("/api/v1/payments", headers=owner, json=base | {"amount": "0"}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/payments", headers=owner, json=base | {"mode": "cheque"}).status_code
        == 422
    )
    received = client.post("/api/v1/payments", headers=owner, json=base | {"direction": "received"})
    assert received.status_code == 409 and received.json()["code"] == "NOT_AVAILABLE"


# ---------------------------------------------------------------- transfers


def _stock(client, headers):
    return {r["name"]: r for r in client.get("/api/v1/stock", headers=headers).json()}


def test_transfers_move_quantity_but_never_value(client, world):
    owner = world["owner"]
    post_purchase(client, world, location="G1")  # 10,000 kg at the godown
    before = _stock(client, owner)["TMT 12 mm"]

    moved = client.post(
        "/api/v1/transfers",
        headers=owner,
        json={
            "from_location_id": world["loc"]["G1"],
            "to_location_id": world["loc"]["S1"],
            "lines": [{"item_id": world["tmt"]["id"], "quantity": "3", "unit": "ton"}],
            "note": "for the shop",
        },
    )
    assert moved.status_code == 201, moved.text
    assert moved.json()["number"] == "G1DC/26-27/00001" and len(moved.json()["number"]) == 16
    assert moved.json()["lines"][0]["quantity"] == "3000.000"

    after = _stock(client, owner)["TMT 12 mm"]
    assert (after["quantity"], after["avg_cost"], after["value"]) == (
        before["quantity"],
        before["avg_cost"],
        before["value"],
    )
    assert {x["code"]: x["quantity"] for x in after["locations"]} == {
        "G1": "7000.000",
        "S1": "3000.000",
    }

    # B13: the shop holds 3,000 kg and cannot give out 3,001.
    counter = login(client, *COUNTER)
    too_many = client.post(
        "/api/v1/transfers",
        headers=counter,
        json={
            "from_location_id": world["loc"]["S1"],
            "to_location_id": world["loc"]["G1"],
            "lines": [{"item_id": world["tmt"]["id"], "quantity": "3001"}],
        },
    )
    assert too_many.status_code == 409 and too_many.json()["code"] == "INSUFFICIENT_STOCK"
    ok = client.post(
        "/api/v1/transfers",
        headers=counter,
        json={
            "from_location_id": world["loc"]["S1"],
            "to_location_id": world["loc"]["G1"],
            "lines": [{"item_id": world["tmt"]["id"], "quantity": "3000"}],
        },
    )
    assert ok.status_code == 201 and ok.json()["number"] == "S1DC/26-27/00001"
    # Counter staff cannot move stock out of the godown, and cannot read other shops' transfers.
    denied = client.post(
        "/api/v1/transfers",
        headers=counter,
        json={
            "from_location_id": world["loc"]["G1"],
            "to_location_id": world["loc"]["S1"],
            "lines": [{"item_id": world["tmt"]["id"], "quantity": "1"}],
        },
    )
    assert denied.status_code == 403
    other = login(client, *COUNTER2)
    assert client.get("/api/v1/transfers", headers=other).json() == []
    assert client.get(f"/api/v1/transfers/{moved.json()['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/transfers/{moved.json()['id']}", headers=counter).status_code == 200
    assert len(client.get("/api/v1/transfers", headers=counter).json()) == 2
    assert client.get("/api/v1/transfers/99999", headers=owner).status_code == 404
    assert "avg_cost" not in client.get("/api/v1/transfers", headers=counter).text


def test_transfer_validation(client, world):
    owner = world["owner"]
    post_purchase(client, world, location="G1")
    base = {"from_location_id": world["loc"]["G1"], "to_location_id": world["loc"]["S1"]}
    tmt = world["tmt"]["id"]
    bad = [
        (
            {
                **base,
                "to_location_id": world["loc"]["G1"],
                "lines": [{"item_id": tmt, "quantity": "1"}],
            },
            422,
        ),
        ({**base, "lines": []}, 422),
        ({**base, "lines": [{"item_id": 99999, "quantity": "1"}]}, 404),
        ({**base, "lines": [{"item_id": tmt, "quantity": "1", "unit": "bag"}]}, 409),
        ({**base, "to_location_id": 99999, "lines": [{"item_id": tmt, "quantity": "1"}]}, 404),
        ({**base, "lines": [{"item_id": world["cement"]["id"], "quantity": "1.5"}]}, 409),
    ]
    for body, status in bad:
        assert client.post("/api/v1/transfers", headers=owner, json=body).status_code == status, (
            body
        )
    # The same item twice in one transfer is added up before the stock check.
    twice = client.post(
        "/api/v1/transfers",
        headers=owner,
        json={
            **base,
            "lines": [{"item_id": tmt, "quantity": "6000"}, {"item_id": tmt, "quantity": "5000"}],
        },
    )
    assert twice.status_code == 409 and twice.json()["code"] == "INSUFFICIENT_STOCK"


# ---------------------------------------------------------------- stock counts


def test_stock_count_turns_variances_into_adjustments_at_average_cost(client, world):
    owner = world["owner"]
    post_purchase(client, world)  # 10,000 kg at 55.6650 in S1
    counter = login(client, *COUNTER)

    opened = client.post(
        "/api/v1/stock-counts", headers=counter, json={"location_id": world["loc"]["S1"]}
    )
    assert opened.status_code == 201, opened.text
    count = opened.json()
    assert count["status"] == "draft" and count["lines"][0]["system_qty"] == "10000.000"
    assert "variance_value" not in count["lines"][0]

    entered = client.put(
        f"/api/v1/stock-counts/{count['id']}/lines",
        headers=counter,
        json={"lines": [{"item_id": world["tmt"]["id"], "counted_qty": "9980"}]},
    )
    assert entered.status_code == 200 and entered.json()["lines"][0]["counted_qty"] == "9980.000"
    assert (
        client.post(f"/api/v1/stock-counts/{count['id']}/post", headers=counter).status_code == 403
    )
    assert (
        client.get(
            f"/api/v1/stock-counts/{count['id']}", headers=login(client, *COUNTER2)
        ).status_code
        == 404
    )

    posted = client.post(f"/api/v1/stock-counts/{count['id']}/post", headers=owner)
    assert posted.status_code == 200, posted.text
    line = posted.json()["lines"][0]
    # 20 kg short at 55.6650 = 1,113.30 written off.
    assert (line["variance"], line["variance_value"]) == ("-20.000", "-1113.30")
    assert posted.json()["total_variance_value"] == "-1113.30"
    assert _stock(client, owner)["TMT 12 mm"]["quantity"] == "9980.000"
    # Staff still see the variance in kilos, never in rupees.
    staff_view = client.get(f"/api/v1/stock-counts/{count['id']}", headers=counter).json()
    assert (
        staff_view["lines"][0]["variance"] == "-20.000"
        and "variance_value" not in staff_view["lines"][0]
    )
    assert "total_variance_value" not in staff_view
    assert (
        client.get("/api/v1/stock-counts", headers=owner).json()[0]["total_variance_value"]
        == "-1113.30"
    )
    assert len(client.get("/api/v1/stock-counts", headers=counter).json()) == 1
    # A posted count is locked.
    again = client.put(
        f"/api/v1/stock-counts/{count['id']}/lines",
        headers=counter,
        json={"lines": [{"item_id": world["tmt"]["id"], "counted_qty": "1"}]},
    )
    assert again.status_code == 409 and again.json()["code"] == "COUNT_POSTED"
    assert (
        client.post(f"/api/v1/stock-counts/{count['id']}/post", headers=owner).json()["code"]
        == "COUNT_POSTED"
    )


def test_count_rules(client, world):
    owner = world["owner"]
    nothing = client.post(
        "/api/v1/stock-counts", headers=owner, json={"location_id": world["loc"]["S2"]}
    )
    assert nothing.status_code == 409 and nothing.json()["code"] == "NOTHING_TO_COUNT"
    picked = client.post(
        "/api/v1/stock-counts",
        headers=owner,
        json={"location_id": world["loc"]["S2"], "item_ids": [world["cement"]["id"]]},
    )
    assert picked.status_code == 201 and picked.json()["lines"][0]["system_qty"] == "0.000"
    count_id = picked.json()["id"]
    empty_post = client.post(f"/api/v1/stock-counts/{count_id}/post", headers=owner)
    assert empty_post.status_code == 409 and empty_post.json()["code"] == "NOTHING_COUNTED"
    wrong = client.put(
        f"/api/v1/stock-counts/{count_id}/lines",
        headers=owner,
        json={"lines": [{"item_id": world["tmt"]["id"], "counted_qty": "1"}]},
    )
    assert wrong.status_code == 404
    # A surplus is added at the average cost (0 when the item was never bought).
    client.put(
        f"/api/v1/stock-counts/{count_id}/lines",
        headers=owner,
        json={"lines": [{"item_id": world["cement"]["id"], "counted_qty": "12"}]},
    )
    surplus = client.post(f"/api/v1/stock-counts/{count_id}/post", headers=owner).json()
    assert surplus["lines"][0]["variance"] == "12.000"
    assert (
        client.post(
            "/api/v1/stock-counts",
            headers=login(client, *COUNTER),
            json={"location_id": world["loc"]["S2"]},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/stock-counts/99999", headers=owner).status_code == 404
    assert (
        client.post("/api/v1/stock-counts", headers=owner, json={"location_id": 99999}).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/stock-counts",
            headers=owner,
            json={"location_id": world["loc"]["S2"], "item_ids": [99999]},
        ).status_code
        == 404
    )
