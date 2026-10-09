"""Milestone 9: direct (drop-ship) sales, vehicles, trips and freight."""

import pytest

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


def direct_purchase(client, world, quantity="5", bill_no="DS-1"):
    response = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": bill_no,
            "bill_date": day(1),
            "mode": "direct",
            "lines": [
                {
                    "item_id": world["tmt"]["id"],
                    "unit": "ton",
                    "quantity": quantity,
                    "rate": "52000",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def direct_sale(client, world, quantity="2", purchase=None, headers=None):
    extra = {"purchase_line_id": purchase["lines"][0]["id"]} if purchase else {}
    return post(
        client,
        world,
        body(
            world,
            [line(world, "tmt", quantity, "ton", source="direct", **extra)],
            site="Chennai site",
        ),
        headers=headers,
    )


def stock_at(client, world, item, code):
    rows = client.get("/api/v1/stock", headers=world["owner"]).json()
    row = next(r for r in rows if r["item_id"] == world[item]["id"])
    return next(x for x in row["locations"] if x["code"] == code)["quantity"]


def vehicle(client, world, number="TN 09 AB 1234", **extra):
    response = client.post(
        "/api/v1/vehicles",
        headers=world["owner"],
        json={"number": number, "owner_name": "Murugan Transport"} | extra,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_direct_sale_moves_no_stock_and_profit_is_sale_less_purchase_less_freight(client, world):
    # Bought 5 ton at 52,000 a ton = ₹52/kg landed (no charges). Sold 2 ton at 56,000 a ton:
    # sale 1,12,000 - purchase 2,000 kg x 52 = 1,04,000 = 8,000. Freight ₹3,000 -> profit 5,000.
    purchase = direct_purchase(client, world)
    before = stock_at(client, world, "tmt", "S1")
    sale = direct_sale(client, world, "2", purchase)
    assert sale.status_code == 201, sale.text
    inv = sale.json()
    assert stock_at(client, world, "tmt", "S1") == before
    assert inv["lines"][0]["cost_per_unit"] == "52.0000"
    assert inv["lines"][0]["drop_ship_purchase"] == purchase["number"]
    assert inv["profit"] == "8000.00" and inv["freight"] == "0.00"

    car = vehicle(client, world)
    trip = client.post(
        "/api/v1/trips",
        headers=world["owner"],
        json={
            "vehicle_id": car["id"],
            "location_id": world["loc"]["S1"],
            "invoice_id": inv["id"],
            "from_place": "Steel mills, Hosur",
            "to_place": "Chennai site",
            "freight_amount": "3000",
        },
    )
    assert trip.status_code == 201, trip.text
    again = client.get(f"/api/v1/invoices/{inv['id']}", headers=world["owner"]).json()
    assert (again["freight"], again["profit"]) == ("3000.00", "5000.00")

    report = client.get("/api/v1/reports/drop-ship", headers=world["owner"]).json()
    assert report["unlinked"] == 0 and report["profit_total"] == "5000.00"
    row = report["rows"][0]
    assert (row["goods_cost"], row["freight"], row["profit"]) == ("104000.00", "3000.00", "5000.00")


def test_a_direct_sale_can_be_linked_later_and_never_over_claims_a_purchase(client, world):
    purchase = direct_purchase(client, world, quantity="3", bill_no="DS-2")
    sale = direct_sale(client, world, "2").json()  # no purchase named yet
    report = client.get("/api/v1/reports/drop-ship", headers=world["owner"]).json()
    assert report["unlinked"] == 1 and report["rows"][0]["profit"] is None

    open_lines = client.get(
        f"/api/v1/drop-ship/open-purchases?item_id={world['tmt']['id']}", headers=world["owner"]
    ).json()
    assert open_lines[0]["free_qty"] == "3000.000" and "cost" not in str(open_lines)
    linked = client.post(
        "/api/v1/drop-ship/links",
        headers=world["owner"],
        json={
            "sales_line_id": sale["lines"][0]["id"],
            "purchase_line_id": purchase["lines"][0]["id"],
        },
    )
    assert linked.status_code == 201 and linked.json()["unit_cost"] == "52.0000"
    after = client.get(f"/api/v1/invoices/{sale['id']}", headers=world["owner"]).json()
    assert after["lines"][0]["cost_per_unit"] == "52.0000" and after["profit"] == "8000.00"
    twice = client.post(
        "/api/v1/drop-ship/links",
        headers=world["owner"],
        json={
            "sales_line_id": sale["lines"][0]["id"],
            "purchase_line_id": purchase["lines"][0]["id"],
        },
    )
    assert twice.status_code == 409 and twice.json()["code"] == "LINK_EXISTS"

    # 1,000 kg are free; a second 2-ton sale cannot claim them.
    greedy = direct_sale(client, world, "2", purchase)
    assert greedy.status_code == 409 and greedy.json()["code"] == "DIRECT_LINK_INVALID"
    fits = direct_sale(client, world, "1", purchase)
    assert fits.status_code == 201
    assert client.get("/api/v1/drop-ship/open-purchases", headers=world["owner"]).json() == []


def test_link_rules(client, world):
    stock_purchase = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "ST-1",
            "bill_date": day(1),
            "lines": [
                {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": "1", "rate": "50000"}
            ],
        },
    ).json()
    shop_sale = post(client, world, body(world, [line(world, "tmt", "100", "kg")])).json()
    direct = direct_sale(client, world, "1").json()
    link = lambda sale, purchase: client.post(
        "/api/v1/drop-ship/links",
        headers=world["owner"],
        json={
            "sales_line_id": sale["lines"][0]["id"],
            "purchase_line_id": purchase["lines"][0]["id"],
        },
    )
    assert link(shop_sale, stock_purchase).json()["code"] == "LINK_NOT_DIRECT_LINE"
    assert link(direct, stock_purchase).json()["code"] == "LINK_NOT_DIRECT"
    cement_direct = post(
        client,
        world,
        body(world, [line(world, "cement", "5", source="direct")], site="Chennai site"),
    ).json()
    other = direct_purchase(client, world, bill_no="DS-3")
    assert link(cement_direct, other).json()["code"] == "LINK_WRONG_ITEM"
    misuse = post(
        client,
        world,
        body(world, [line(world, "tmt", "1", "ton", purchase_line_id=other["lines"][0]["id"])]),
    )
    assert misuse.status_code == 409 and misuse.json()["code"] == "LINK_NEEDS_DIRECT"
    missing = {"sales_line_id": 0, "purchase_line_id": 0}
    assert (
        client.post("/api/v1/drop-ship/links", headers=world["owner"], json=missing).status_code
        == 404
    )


def test_freight_is_payable_to_the_vehicle_owner_with_a_cash_warning(client, world):
    car = vehicle(client, world)
    assert car["party_id"] is not None
    assert (
        client.post(
            "/api/v1/vehicles",
            headers=world["owner"],
            json={"number": "tn09ab1234", "owner_name": "Someone"},
        ).json()["code"]
        == "VEHICLE_EXISTS"
    )
    trip = client.post(
        "/api/v1/trips",
        headers=world["owner"],
        json={
            "vehicle_id": car["id"],
            "location_id": world["loc"]["S1"],
            "from_place": "Mill",
            "to_place": "Shop",
            "freight_amount": "40000",
        },
    ).json()
    assert trip["pay_ref"] == f"TRIP-{trip['id']}" and trip["paid_amount"] == "0.00"
    owed = client.get(f"/api/v1/parties/{car['party_id']}/statement", headers=world["owner"]).json()
    assert owed["payable"]["balance"] == "40000.00"

    paid = client.post(
        "/api/v1/payments",
        headers=world["owner"],
        json={
            "direction": "paid",
            "party_id": car["party_id"],
            "location_id": world["loc"]["S1"],
            "amount": "36000",
            "mode": "cash",
            "payment_date": day(0),
            "allocations": [{"bill_no": trip["pay_ref"], "amount": "36000"}],
        },
    )
    assert paid.status_code == 201, paid.text
    assert "not deductible" in paid.json()["warnings"][0]
    listed = client.get("/api/v1/trips", headers=world["owner"]).json()["items"][0]
    assert listed["paid_amount"] == "36000.00"
    upi = client.post(
        "/api/v1/payments",
        headers=world["owner"],
        json={
            "direction": "paid",
            "party_id": car["party_id"],
            "location_id": world["loc"]["S1"],
            "amount": "4000",
            "mode": "upi",
            "payment_date": day(0),
        },
    )
    assert upi.json()["warnings"] == []


def test_trip_and_vehicle_rules(client, world):
    own = vehicle(client, world, number="TN01AA0001", is_own=True)
    assert own["party_id"] is None
    base = {
        "vehicle_id": own["id"],
        "location_id": world["loc"]["S1"],
        "from_place": "A1",
        "to_place": "B1",
    }
    paid_own = client.post(
        "/api/v1/trips", headers=world["owner"], json=base | {"freight_amount": "10"}
    )
    assert paid_own.json()["code"] == "OWN_VEHICLE_FREIGHT"
    assert (
        client.post(
            "/api/v1/trips", headers=world["owner"], json=base | {"freight_amount": "0"}
        ).status_code
        == 201
    )
    inv = post(client, world, body(world, [line(world, "cement", "1")])).json()
    purchase = direct_purchase(client, world, bill_no="DS-4")
    both = client.post(
        "/api/v1/trips",
        headers=world["owner"],
        json=base | {"freight_amount": "0", "invoice_id": inv["id"], "purchase_id": purchase["id"]},
    )
    assert both.json()["code"] == "TRIP_ONE_DOCUMENT"
    missing = client.post(
        "/api/v1/trips",
        headers=world["owner"],
        json=base | {"freight_amount": "0", "invoice_id": 0},
    )
    assert missing.status_code == 404
    off = client.patch(
        f"/api/v1/vehicles/{own['id']}", headers=world["owner"], json={"is_active": False}
    )
    assert off.json()["is_active"] is False
    after_off = client.post(
        "/api/v1/trips", headers=world["owner"], json=base | {"freight_amount": "0"}
    )
    assert after_off.json()["code"] == "VEHICLE_INACTIVE"
    assert client.get("/api/v1/vehicles", headers=world["owner"]).json() == []
    assert (
        len(client.get("/api/v1/vehicles?include_inactive=true", headers=world["owner"]).json())
        == 1
    )
    by_invoice = client.get(
        f"/api/v1/trips?invoice_id={inv['id']}&vehicle_id={own['id']}", headers=world["owner"]
    )
    assert by_invoice.json()["total"] == 0
    assert (
        client.patch("/api/v1/vehicles/99999", headers=world["owner"], json={}).status_code == 404
    )


def test_transport_roles_and_counter_never_sees_cost(client, world, seeded):
    purchase = direct_purchase(client, world, bill_no="DS-5")
    counter = login(client, *COUNTER)
    accountant = login(client, *ACCOUNTANT)
    car = vehicle(client, world)
    trip_body = {
        "vehicle_id": car["id"],
        "location_id": world["loc"]["S1"],
        "from_place": "Mill",
        "to_place": "Site",
        "freight_amount": "100",
    }
    for who in (counter, accountant):
        assert (
            client.post(
                "/api/v1/vehicles", headers=who, json={"number": "TN01XX9999", "owner_name": "Ab"}
            ).status_code
            == 403
        )
        assert (
            client.patch(f"/api/v1/vehicles/{car['id']}", headers=who, json={}).status_code == 403
        )
        assert client.post("/api/v1/trips", headers=who, json=trip_body).status_code == 403
        assert (
            client.post(
                "/api/v1/drop-ship/links",
                headers=who,
                json={"sales_line_id": 1, "purchase_line_id": 1},
            ).status_code
            == 403
        )
        assert client.get("/api/v1/reports/drop-ship", headers=who).status_code == 403
    assert client.get("/api/v1/vehicles", headers=counter).status_code == 403
    assert client.get("/api/v1/trips", headers=counter).status_code == 403
    assert client.get("/api/v1/vehicles", headers=accountant).status_code == 200
    assert client.get("/api/v1/trips", headers=accountant).status_code == 200
    assert client.get("/api/v1/drop-ship/open-purchases", headers=accountant).status_code == 403

    # The counter can name the supplier purchase on a direct sale and sees no cost on the result.
    sale = direct_sale(client, world, "1", purchase, headers=counter)
    assert sale.status_code == 201, sale.text
    assert "cost" not in sale.text and "profit" not in sale.text and "drop_ship" not in sale.text
    assert client.get("/api/v1/drop-ship/open-purchases", headers=counter).status_code == 200
