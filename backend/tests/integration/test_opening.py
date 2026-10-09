"""Milestone 3: opening stock and balances reach the ledgers and the reports."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today_ist
from tests.conftest import login

pytestmark = pytest.mark.integration

OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")
ACCOUNTANT = ("accounts", "accounts-pass-123")


def ago(days: int) -> str:
    return (today_ist() - timedelta(days=days)).isoformat()


@pytest.fixture
def world(client):
    """Two items, a customer with a site, a supplier, and the seeded S1/S2/G1 locations."""
    owner = login(client, *OWNER)
    locations = {
        loc["code"]: loc["id"] for loc in client.get("/api/v1/locations", headers=owner).json()
    }
    tmt = client.post(
        "/api/v1/items",
        headers=owner,
        json={
            "name": "TMT 12 mm",
            "category": "tmt",
            "hsn": "72142090",
            "gst_rate": "18",
            "base_unit": "kg",
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
    customer = client.post(
        "/api/v1/parties",
        headers=owner,
        json={
            "name": "Ravi Builders",
            "type": "customer",
            "state_code": "33",
            "sites": [
                {"name": "Anna Nagar", "state_code": "33"},
                {"name": "Adyar", "state_code": "33"},
            ],
        },
    ).json()
    supplier = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Steel Mills", "type": "supplier", "state_code": "33"},
    ).json()
    return {
        "owner": owner,
        "loc": locations,
        "tmt": tmt,
        "cement": cement,
        "customer": customer,
        "supplier": supplier,
        "sites": {s["name"]: s["id"] for s in customer["sites"]},
    }


def stock_row(world, item, code, qty, cost, note=None):
    return {
        "kind": "stock",
        "as_of": ago(30),
        "item_id": world[item]["id"],
        "location_id": world["loc"][code],
        "quantity": qty,
        "unit_cost": cost,
        "note": note,
    }


def money_row(world, kind, party, amount, days, site=None):
    return {
        "kind": kind,
        "as_of": ago(days),
        "party_id": world[party]["id"],
        "site_id": world["sites"][site] if site else None,
        "amount": amount,
    }


def add(client, world, body):
    response = client.post("/api/v1/opening", headers=world["owner"], json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- roles


def test_opening_routes_are_owner_only(client):
    for who in (COUNTER, ACCOUNTANT):
        headers = login(client, *who)
        assert client.get("/api/v1/opening", headers=headers).status_code == 403
        assert client.post("/api/v1/opening", headers=headers, json={}).status_code == 403
        assert client.patch("/api/v1/opening/1", headers=headers, json={}).status_code == 403
        assert client.delete("/api/v1/opening/1", headers=headers).status_code == 403
        assert (
            client.post(
                "/api/v1/opening/post", headers=headers, json={"kinds": ["stock"]}
            ).status_code
            == 403
        )
    assert client.get("/api/v1/opening").status_code == 401
    assert client.get("/api/v1/stock").status_code == 401
    assert client.get("/api/v1/reports/dues?account=receivable").status_code == 401
    assert client.get("/api/v1/parties/1/statement").status_code == 401


# ---------------------------------------------------------------- opening stock


def test_opening_stock_posts_to_the_ledger_and_the_cost_stays_with_the_owner(client, world):
    # TMT: 4,000 kg at S1 @ 55.00 and 6,000 kg at G1 @ 56.50.
    # Average = (4,000 x 55 + 6,000 x 56.5) / 10,000 = (220,000 + 339,000) / 10,000 = 55.9.
    # Value = 10,000 x 55.9 = 5,59,000.00.
    add(client, world, stock_row(world, "tmt", "S1", "4000", "55"))
    add(client, world, stock_row(world, "tmt", "G1", "6000", "56.5"))
    add(client, world, stock_row(world, "cement", "S1", "200", "380"))

    assert client.get("/api/v1/stock", headers=world["owner"]).json() == []  # drafts are not stock

    posted = client.post("/api/v1/opening/post", headers=world["owner"], json={"kinds": ["stock"]})
    assert posted.json() == {"posted": 3, "stock_rows": 3, "party_rows": 0}

    owner_rows = {r["name"]: r for r in client.get("/api/v1/stock", headers=world["owner"]).json()}
    tmt = owner_rows["TMT 12 mm"]
    assert (tmt["quantity"], tmt["avg_cost"], tmt["value"]) == ("10000.000", "55.9000", "559000.00")
    assert {loc["code"]: loc["quantity"] for loc in tmt["locations"]} == {
        "G1": "6000.000",
        "S1": "4000.000",
    }
    assert owner_rows["Cement PPC"]["value"] == "76000.00"  # 200 bags x 380

    for who in (COUNTER, ACCOUNTANT):
        headers = login(client, *who)
        rows = client.get("/api/v1/stock", headers=headers).json()
        assert {r["name"] for r in rows} == {"TMT 12 mm", "Cement PPC"}
        for row in rows:
            assert "avg_cost" not in row and "value" not in row
        assert "55.9" not in client.get("/api/v1/stock", headers=headers).text

    shop = client.get(
        f"/api/v1/stock?location_id={world['loc']['S1']}", headers=world["owner"]
    ).json()
    assert {r["name"]: r["quantity"] for r in shop} == {
        "TMT 12 mm": "4000.000",
        "Cement PPC": "200.000",
    }
    assert [
        r["name"] for r in client.get("/api/v1/stock?q=cement", headers=world["owner"]).json()
    ] == ["Cement PPC"]


def test_posted_rows_are_locked_and_the_database_refuses_edits(client, world, seeded):
    row = add(client, world, stock_row(world, "tmt", "S1", "100", "50"))
    edited = client.patch(
        f"/api/v1/opening/{row['id']}", headers=world["owner"], json={"quantity": "120"}
    )
    assert edited.status_code == 200 and edited.json()["quantity"] == "120.000"
    client.post("/api/v1/opening/post", headers=world["owner"], json={"kinds": ["stock"]})

    for response in (
        client.patch(
            f"/api/v1/opening/{row['id']}", headers=world["owner"], json={"quantity": "1"}
        ),
        client.delete(f"/api/v1/opening/{row['id']}", headers=world["owner"]),
    ):
        assert response.status_code == 409 and response.json()["code"] == "OPENING_POSTED"

    # Below the application, the ledger itself rejects UPDATE and DELETE (ADR 0003).
    for sql in ("UPDATE stock_ledger SET qty_in = 1", "DELETE FROM stock_ledger"):
        with pytest.raises(DBAPIError, match="append-only"):
            seeded.execute(text(sql))
        seeded.rollback()


def test_opening_row_rules(client, world):
    owner = world["owner"]
    add(client, world, stock_row(world, "tmt", "S1", "100", "50"))
    again = client.post(
        "/api/v1/opening", headers=owner, json=stock_row(world, "tmt", "S1", "5", "9")
    )
    assert again.status_code == 409 and again.json()["code"] == "OPENING_EXISTS"

    bad = [
        ({"kind": "stock", "as_of": ago(1), "item_id": world["tmt"]["id"]}, 422),  # missing fields
        ({**stock_row(world, "tmt", "S2", "0", "5")}, 422),  # zero quantity
        ({**stock_row(world, "tmt", "S2", "5", "5"), "amount": "10"}, 422),  # stray amount
        ({"kind": "receivable", "as_of": ago(1), "party_id": world["customer"]["id"]}, 422),
        ({**money_row(world, "receivable", "customer", "100", 1), "quantity": "5"}, 422),
        ({**stock_row(world, "tmt", "S2", "5", "5"), "item_id": 99999}, 404),
        ({**stock_row(world, "tmt", "S2", "5", "5"), "location_id": 99999}, 404),
        (money_row(world, "receivable", "supplier", "100", 1), 409),  # supplier owing us
        (money_row(world, "payable", "customer", "100", 1), 409),  # we owe a customer
        (money_row(world, "receivable", "customer", "100", 1) | {"party_id": 99999}, 404),
    ]
    for body, status in bad:
        response = client.post("/api/v1/opening", headers=owner, json=body)
        assert response.status_code == status, (body, response.text)

    other_site = client.post(
        "/api/v1/parties",
        headers=owner,
        json={
            "name": "Other Co",
            "type": "customer",
            "state_code": "33",
            "sites": [{"name": "Elsewhere", "state_code": "33"}],
        },
    ).json()["sites"][0]["id"]
    wrong_site = money_row(world, "receivable", "customer", "100", 1) | {"site_id": other_site}
    assert (
        client.post("/api/v1/opening", headers=owner, json=wrong_site).json()["code"]
        == "SITE_MISMATCH"
    )
    site_on_supplier = money_row(world, "payable", "supplier", "100", 1) | {
        "site_id": world["sites"]["Adyar"]
    }
    assert client.post("/api/v1/opening", headers=owner, json=site_on_supplier).status_code == 409

    nothing = client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["payable"]})
    assert nothing.status_code == 409 and nothing.json()["code"] == "NOTHING_TO_POST"
    assert (
        client.get("/api/v1/opening?kind=stock&status=draft", headers=owner).json()[0]["item_name"]
        == "TMT 12 mm"
    )

    row = add(client, world, money_row(world, "receivable", "customer", "500", 5, "Adyar"))
    bad_edit = client.patch(f"/api/v1/opening/{row['id']}", headers=owner, json={"quantity": "3"})
    assert bad_edit.status_code == 409 and bad_edit.json()["code"] == "WRONG_FIELD"
    fixed = client.patch(
        f"/api/v1/opening/{row['id']}", headers=owner, json={"amount": "750.50", "note": "checked"}
    )
    assert fixed.json()["amount"] == "750.50" and fixed.json()["site_name"] == "Adyar"
    stock_id = client.get("/api/v1/opening?kind=stock", headers=owner).json()[0]["id"]
    wrong = client.patch(f"/api/v1/opening/{stock_id}", headers=owner, json={"amount": "5"})
    assert wrong.status_code == 409
    assert client.patch("/api/v1/opening/99999", headers=owner, json={}).status_code == 404
    gone = client.delete(f"/api/v1/opening/{row['id']}", headers=owner)
    assert gone.status_code == 204
    assert client.get("/api/v1/opening?kind=receivable", headers=owner).json() == []


# ---------------------------------------------------------------- opening dues


def test_customer_and_supplier_balances_reach_statements_and_dues(client, world):
    owner = world["owner"]
    # Customer owes 10,000 at Anna Nagar (100 days old) and 4,000 at Adyar (10 days old);
    # they also paid 1,000 in advance. Net 13,000 owed; the advance clears the oldest bill.
    add(client, world, money_row(world, "receivable", "customer", "10000", 100, "Anna Nagar"))
    add(client, world, money_row(world, "receivable", "customer", "4000", 10, "Adyar"))
    add(client, world, money_row(world, "customer_advance", "customer", "1000", 5))
    # We owe the supplier 25,000, and we hold a 3,000 advance with the same supplier: net 22,000.
    add(client, world, money_row(world, "payable", "supplier", "25000", 40))
    add(client, world, money_row(world, "supplier_advance", "supplier", "3000", 3))
    posted = client.post(
        "/api/v1/opening/post",
        headers=owner,
        json={"kinds": ["receivable", "customer_advance", "payable", "supplier_advance"]},
    )
    assert posted.json() == {"posted": 5, "stock_rows": 0, "party_rows": 5}

    statement = client.get(
        f"/api/v1/parties/{world['customer']['id']}/statement", headers=owner
    ).json()
    receivable = statement["receivable"]
    assert statement["payable"] is None  # a customer has no payable side
    assert (receivable["balance"], receivable["advance"]) == ("13000.00", "0.00")
    # FIFO: the 1,000 advance (5 days ago) comes after both bills, so it clears the oldest one:
    # open = 9,000 (100 days old, over 60) + 4,000 (10 days old, 0-30).
    assert receivable["aging"] == {
        "up_to_30": "4000.00",
        "days_31_60": "0.00",
        "over_60": "9000.00",
    }
    assert [line["running_balance"] for line in receivable["entries"]] == [
        "10000.00",
        "14000.00",
        "13000.00",
    ]

    per_site = client.get(
        f"/api/v1/parties/{world['customer']['id']}/statement?site_id={world['sites']['Adyar']}",
        headers=owner,
    ).json()["receivable"]
    assert per_site["balance"] == "4000.00" and len(per_site["entries"]) == 1

    dues = client.get("/api/v1/reports/dues?account=receivable", headers=owner).json()
    assert dues["total"] == "13000.00"
    assert [(r["party_name"], r["balance"]) for r in dues["rows"]] == [
        ("Ravi Builders", "13000.00")
    ]

    payable = client.get("/api/v1/reports/dues?account=payable", headers=owner).json()
    assert payable["total"] == "22000.00"
    row = payable["rows"][0]
    # The 3,000 advance (3 days ago) is paid after the 25,000 bill (40 days ago), so it settles part
    # of it: 25,000 - 3,000 = 22,000 still owed, in the 31-60 day bucket.
    assert (row["balance"], row["advance"], row["aging"]["days_31_60"]) == (
        "22000.00",
        "0.00",
        "22000.00",
    )
    sup = client.get(f"/api/v1/parties/{world['supplier']['id']}/statement", headers=owner).json()
    assert sup["receivable"] is None and sup["payable"]["balance"] == "22000.00"

    # Roles: counter sees customers' dues but never what we owe suppliers.
    counter = login(client, *COUNTER)
    assert client.get("/api/v1/reports/dues?account=receivable", headers=counter).status_code == 200
    assert client.get("/api/v1/reports/dues?account=payable", headers=counter).status_code == 403
    both = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Both Co", "type": "both", "state_code": "33"},
    ).json()
    add(
        client, world, {"kind": "payable", "as_of": ago(2), "party_id": both["id"], "amount": "100"}
    )
    client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["payable"]})
    seen = client.get(f"/api/v1/parties/{both['id']}/statement", headers=counter).json()
    assert seen["payable"] is None and seen["receivable"]["balance"] == "0.00"
    acct = login(client, *ACCOUNTANT)
    assert (
        client.get(f"/api/v1/parties/{both['id']}/statement", headers=acct).json()["payable"][
            "balance"
        ]
        == "100.00"
    )
    assert client.get("/api/v1/parties/99999/statement", headers=owner).status_code == 404


def test_an_advance_larger_than_the_bills_is_reported_as_an_advance(client, world):
    owner = world["owner"]
    add(client, world, money_row(world, "customer_advance", "customer", "2500", 3))
    client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["customer_advance"]})
    receivable = client.get(
        f"/api/v1/parties/{world['customer']['id']}/statement", headers=owner
    ).json()["receivable"]
    assert (receivable["balance"], receivable["advance"]) == ("-2500.00", "2500.00")
    dues = client.get("/api/v1/reports/dues?account=receivable", headers=owner).json()
    assert dues["total"] == "-2500.00" and dues["rows"][0]["advance"] == "2500.00"
