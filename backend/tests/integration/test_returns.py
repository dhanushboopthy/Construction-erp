"""Milestone 8: credit notes, debit notes, return window, stock and balance effects, roles."""

import pytest

from tests.conftest import login
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

PIN = "4821"


def sell(client, world, lines=None, **extra):
    lines = lines or [line(world, "tmt", "2.5", "ton"), line(world, "cement", "7")]
    response = post(client, world, body(world, lines, **extra))
    assert response.status_code == 201, response.text
    return response.json()


def note_body(invoice, picks, reason="Wrong size", **extra):
    return {
        "invoice_id": invoice["id"],
        "reason": reason,
        "lines": [{"line_id": invoice["lines"][i]["id"], "quantity": q} for i, q in picks],
    } | extra


def stock_at(client, world, item, code):
    rows = client.get("/api/v1/stock", headers=world["owner"]).json()
    row = next(r for r in rows if r["item_id"] == world[item]["id"])
    return next(x for x in row["locations"] if x["code"] == code)["quantity"]


def receivable(client, world, party="ravi"):
    statement = client.get(
        f"/api/v1/parties/{world[party]['id']}/statement", headers=world["owner"]
    ).json()
    return statement["receivable"]["balance"]


# ------------------------------------------------------------------ credit notes


def test_credit_note_maths_stock_and_balance(client, world):
    # The sample bill is 1,68,609.00 (see test_sales). Return 1 ton of the 2.5 ton TMT and 3 of 7 bags:
    # TMT taxable 1,40,000 x 1000/2500 = 56,000.00; GST 18% = 10,080 (5,040 CGST + 5,040 SGST).
    # Cement taxable 2,663.15 x 3/7 = 1,141.35; GST 14% = 159.789 -> 159.79 each.
    # Taxable 57,141.35; CGST = SGST = 5,040 + 159.79 = 5,199.79; before round-off 57,141.35 + 10,399.58 = 67,540.93 -> 67,541.00.
    inv = sell(client, world)
    assert stock_at(client, world, "tmt", "S1") == "2500.000"
    response = client.post(
        "/api/v1/credit-notes",
        headers=world["owner"],
        json=note_body(inv, [(0, "1"), (1, "3")]) | {},
    )
    # The first line is in tons, so a quantity of 1 means 1 ton.
    assert response.status_code == 201, response.text
    cn = response.json()
    assert cn["number"] == "S1C/26-27/00001"
    assert len(cn["number"]) <= 16 and cn["invoice_number"] == inv["number"]
    assert (cn["taxable_value"], cn["cgst"], cn["sgst"], cn["igst"]) == (
        "57141.35",
        "5199.79",
        "5199.79",
        "0.00",
    )
    assert (cn["round_off"], cn["grand_total"]) == ("0.07", "67541.00")
    tmt, cement = cn["lines"]
    assert (tmt["base_qty"], tmt["taxable"], tmt["cgst"], tmt["line_total"]) == (
        "1000.000",
        "56000.00",
        "5040.00",
        "66080.00",
    )
    assert (cement["base_qty"], cement["taxable"], cement["cgst"]) == (
        "3.000",
        "1141.35",
        "159.79",
    )
    # Back in stock at the shop it left from; the customer owes 1,68,609.00 - 67,541.00.
    assert stock_at(client, world, "tmt", "S1") == "3500.000"
    assert stock_at(client, world, "cement", "S1") == "96.000"
    assert receivable(client, world) == "101068.00"
    again = client.get(f"/api/v1/invoices/{inv['id']}", headers=world["owner"]).json()
    assert [x["returned_qty"] for x in again["lines"]] == ["1000.000", "3.000"]
    # The owner's invoice shows cost, but the credit note never carries it.
    assert "cost" not in str(cn)


def test_cannot_return_more_than_was_sold_and_full_return_is_exact(client, world):
    inv = sell(client, world)
    owner = world["owner"]
    first = client.post("/api/v1/credit-notes", headers=owner, json=note_body(inv, [(0, "1")]))
    assert first.status_code == 201
    too_much = client.post("/api/v1/credit-notes", headers=owner, json=note_body(inv, [(0, "1.6")]))
    assert too_much.status_code == 422 or too_much.status_code == 409
    assert too_much.json()["code"] == "RETURN_TOO_MUCH"
    assert too_much.json()["field"] == "lines[0].quantity"
    rest = client.post("/api/v1/credit-notes", headers=owner, json=note_body(inv, [(0, "1.5")]))
    assert rest.status_code == 201
    # 1 ton + 1.5 ton of 140,000 taxable = 56,000 + 84,000 exactly.
    total_taxable = float(first.json()["taxable_value"]) + float(rest.json()["taxable_value"])
    assert total_taxable == 140000.0
    gone = client.post("/api/v1/credit-notes", headers=owner, json=note_body(inv, [(0, "0.001")]))
    assert gone.json()["code"] == "RETURN_TOO_MUCH"
    repeated = note_body(inv, [(0, "0.1")])
    repeated["lines"].append(repeated["lines"][0])
    assert (
        client.post("/api/v1/credit-notes", headers=owner, json=repeated).json()["code"]
        == "RETURN_LINE_REPEATED"
    )
    wrong_line = {
        "invoice_id": inv["id"],
        "reason": "x y z",
        "lines": [{"line_id": 0, "quantity": "1"}],
    }
    assert client.post("/api/v1/credit-notes", headers=owner, json=wrong_line).status_code == 404


def test_late_returns_need_the_owner(client, world, seeded):
    owner = world["owner"]
    client.put(
        "/api/v1/rates/market",
        headers=owner,
        json={
            "effective_date": day(10),
            "rates": [{"item_id": world["cement"]["id"], "rate": "380.45"}],
        },
    )
    old = post(
        client,
        world,
        body(world, [line(world, "cement", "10")], invoice_date=day(5)),
    ).json()
    counter = login(client, *COUNTER)
    blocked = client.post("/api/v1/credit-notes", headers=counter, json=note_body(old, [(0, "2")]))
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "RETURN_WINDOW_CLOSED"
    assert blocked.json()["requires_owner_approval"] is True

    client.post(
        "/api/v1/auth/pin", headers=owner, json={"current_password": "owner-pass-123", "pin": PIN}
    )
    approval = client.post(
        "/api/v1/approvals",
        headers=counter,
        json={
            "pin": PIN,
            "action": "late_return",
            "reason": "damaged on delivery",
            "party_id": world["ravi"]["id"],
        },
    )
    assert approval.status_code == 201, approval.text
    ok = client.post(
        "/api/v1/credit-notes",
        headers=counter,
        json=note_body(old, [(0, "2")]) | {"approval_ids": [approval.json()["id"]]},
    )
    assert ok.status_code == 201 and ok.json()["approved_by"] is not None
    # One approval, one return.
    reused = client.post(
        "/api/v1/credit-notes",
        headers=counter,
        json=note_body(old, [(0, "1")]) | {"approval_ids": [approval.json()["id"]]},
    )
    assert reused.json()["code"] == "APPROVAL_INVALID"
    # The owner needs no approval.
    assert (
        client.post(
            "/api/v1/credit-notes", headers=owner, json=note_body(old, [(0, "1")])
        ).status_code
        == 201
    )


def test_credit_note_roles_and_shop_scope(client, world, seeded):
    inv = sell(client, world)
    payload = note_body(inv, [(1, "1")])
    accountant = login(client, *ACCOUNTANT)
    assert client.post("/api/v1/credit-notes", headers=accountant, json=payload).status_code == 403
    other_shop = login(client, *COUNTER2)
    assert client.post("/api/v1/credit-notes", headers=other_shop, json=payload).status_code == 404
    counter = login(client, *COUNTER)
    made = client.post("/api/v1/credit-notes", headers=counter, json=payload)
    assert made.status_code == 201, made.text
    note_id = made.json()["id"]
    assert client.get(f"/api/v1/credit-notes/{note_id}", headers=counter).status_code == 200
    assert client.get(f"/api/v1/credit-notes/{note_id}", headers=other_shop).status_code == 404
    assert client.get(f"/api/v1/credit-notes/{note_id}/pdf", headers=other_shop).status_code == 404
    assert client.get("/api/v1/credit-notes", headers=other_shop).json()["total"] == 0
    assert client.get("/api/v1/credit-notes", headers=accountant).json()["total"] == 1
    assert (
        client.get(f"/api/v1/credit-notes?invoice_id={inv['id']}", headers=counter).json()["total"]
        == 1
    )
    pdf = client.get(f"/api/v1/credit-notes/{note_id}/pdf", headers=counter)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # Counter staff never see cost.
    assert "cost" not in made.text


def test_inter_state_credit_note_uses_igst_and_direct_lines_do_not_restock(client, world):
    inv = sell(client, world, [line(world, "cement", "4")], site="Hosur site")
    assert inv["supply_kind"] == "inter_state"
    cn = client.post(
        "/api/v1/credit-notes", headers=world["owner"], json=note_body(inv, [(0, "4")])
    ).json()
    # 4 bags x 380.45 = 1,521.80; IGST 28% = 426.104 -> 426.10; total 1,947.90 -> 1,948.00.
    assert (cn["cgst"], cn["sgst"], cn["igst"], cn["grand_total"]) == (
        "0.00",
        "0.00",
        "426.10",
        "1948.00",
    )
    assert stock_at(client, world, "cement", "S1") == "100.000"


# ------------------------------------------------------------------ debit notes


def buy(client, world, location="S1", quantity="10", bill_no="B-1"):
    response = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"][location],
            "bill_no": bill_no,
            "bill_date": day(1),
            "lines": [
                {
                    "item_id": world["tmt"]["id"],
                    "unit": "ton",
                    "quantity": quantity,
                    "rate": "55000",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def payable(client, world):
    s = client.get(
        f"/api/v1/parties/{world['supplier']['id']}/statement", headers=world["owner"]
    ).json()
    return s["payable"]["balance"]


def test_debit_note_sends_goods_back_at_landed_cost(client, world):
    # 10 ton at 55,000 = 5,50,000 + 18% GST. Returning 2 ton: taxable 1,10,000, CGST = SGST = 9,900.
    purchase = buy(client, world)
    before_stock = stock_at(client, world, "tmt", "S1")
    before_payable = payable(client, world)
    response = client.post(
        "/api/v1/debit-notes",
        headers=world["owner"],
        json={
            "purchase_id": purchase["id"],
            "reason": "Rusted bars",
            "lines": [{"line_id": purchase["lines"][0]["id"], "quantity": "2"}],
        },
    )
    assert response.status_code == 201, response.text
    dn = response.json()
    assert (dn["taxable_value"], dn["cgst"], dn["sgst"], dn["grand_total"]) == (
        "110000.00",
        "9900.00",
        "9900.00",
        "129800.00",
    )
    assert dn["supplier_bill_no"] == "B-1" and dn["lines"][0]["base_qty"] == "2000.000"
    assert float(before_stock) - float(stock_at(client, world, "tmt", "S1")) == 2000.0
    assert float(before_payable) - float(payable(client, world)) == 129800.0
    pdf = client.get(f"/api/v1/debit-notes/{dn['id']}/pdf", headers=world["owner"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # More than was bought is refused: 8 ton are left to send back.
    over = client.post(
        "/api/v1/debit-notes",
        headers=world["owner"],
        json={
            "purchase_id": purchase["id"],
            "reason": "Too many",
            "lines": [{"line_id": purchase["lines"][0]["id"], "quantity": "8.5"}],
        },
    )
    assert over.json()["code"] == "RETURN_TOO_MUCH"


def test_goods_already_sold_cannot_be_sent_back(client, world):
    purchase = buy(client, world, location="S2", quantity="1", bill_no="B-2")
    sold = post(client, world, body(world, [line(world, "tmt", "800", "kg")], location="S2"))
    assert sold.status_code == 201, sold.text
    refused = client.post(
        "/api/v1/debit-notes",
        headers=world["owner"],
        json={
            "purchase_id": purchase["id"],
            "reason": "Wrong grade",
            "lines": [{"line_id": purchase["lines"][0]["id"], "quantity": "0.5"}],
        },
    )
    assert refused.status_code == 409 and refused.json()["code"] == "INSUFFICIENT_STOCK"


def test_debit_note_roles(client, world, seeded):
    purchase = buy(client, world)
    payload = {
        "purchase_id": purchase["id"],
        "reason": "Short weight",
        "lines": [{"line_id": purchase["lines"][0]["id"], "quantity": "1"}],
    }
    counter = login(client, *COUNTER)
    accountant = login(client, *ACCOUNTANT)
    assert client.post("/api/v1/debit-notes", headers=counter, json=payload).status_code == 403
    assert client.post("/api/v1/debit-notes", headers=accountant, json=payload).status_code == 403
    made = client.post("/api/v1/debit-notes", headers=world["owner"], json=payload)
    note_id = made.json()["id"]
    for headers, expected in ((counter, 403), (accountant, 200), (world["owner"], 200)):
        assert client.get("/api/v1/debit-notes", headers=headers).status_code == expected
        assert client.get(f"/api/v1/debit-notes/{note_id}", headers=headers).status_code == expected
        pdf = client.get(f"/api/v1/debit-notes/{note_id}/pdf", headers=headers)
        assert pdf.status_code == expected
    assert client.get("/api/v1/debit-notes/99999", headers=world["owner"]).status_code == 404
    assert client.get("/api/v1/credit-notes/99999", headers=world["owner"]).status_code == 404
