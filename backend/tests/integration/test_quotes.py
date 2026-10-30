"""Quotations and proforma invoices: priced like a bill, numbered in their own series, no stock
or account effect, and billed once."""

import pytest

from tests.conftest import login
from tests.integration.test_returns import receivable, stock_at
from tests.integration.test_sales import (  # noqa: F401 - the world fixture is shared
    ACCOUNTANT,
    COUNTER,
    COUNTER2,
    body,
    line,
    post,
    world,
)

pytestmark = pytest.mark.integration


def sample(world, kind="quotation", **extra):
    lines = [line(world, "tmt", "2.5", "ton"), line(world, "cement", "7")]
    return body(world, lines) | {"kind": kind} | extra


def test_quotation_is_priced_like_a_bill_and_moves_nothing(client, world):
    owner = world["owner"]
    # More cement than the shop holds is fine on a quotation: it moves no stock.
    big = sample(world)
    big["lines"][1]["quantity"] = "500"
    preview = client.post("/api/v1/quotes/preview", headers=owner, json=big).json()
    assert preview["can_save"] is True

    made = client.post("/api/v1/quotes", headers=owner, json=sample(world))
    assert made.status_code == 201, made.text
    quote = made.json()
    # The same figures as the sample bill in test_sales (1,68,609.00).
    assert quote["number"] == "S1Q/26-27/00001"
    assert (quote["taxable_value"], quote["grand_total"]) == ("142663.15", "168609.00")
    assert quote["invoice_id"] is None and len(quote["lines"]) == 2
    assert stock_at(client, world, "tmt", "S1") == "5000.000"
    assert float(receivable(client, world)) == 0

    proforma = client.post("/api/v1/quotes", headers=owner, json=sample(world, kind="proforma"))
    assert proforma.json()["number"] == "S1PI/26-27/00001"
    listed = client.get("/api/v1/quotes?kind=proforma", headers=owner).json()
    assert [x["number"] for x in listed["items"]] == ["S1PI/26-27/00001"]

    pdf = client.get(f"/api/v1/quotes/{quote['id']}/pdf", headers=owner)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_a_quotation_becomes_one_bill(client, world):
    owner = world["owner"]
    quote = client.post("/api/v1/quotes", headers=owner, json=sample(world)).json()
    payload = body(world, [line(world, "tmt", "2.5", "ton"), line(world, "cement", "7")])
    billed = post(client, world, payload | {"quote_id": quote["id"]})
    assert billed.status_code == 201, billed.text
    again = client.get(f"/api/v1/quotes/{quote['id']}", headers=owner).json()
    assert again["invoice_id"] == billed.json()["id"]
    assert again["invoice_number"] == billed.json()["number"]

    twice = post(client, world, payload | {"quote_id": quote["id"]})
    assert twice.status_code == 409 and twice.json()["code"] == "QUOTE_ALREADY_BILLED"
    # Nothing of the refused bill was kept.
    assert client.get("/api/v1/invoices", headers=owner).json()["total"] == 1
    assert stock_at(client, world, "tmt", "S1") == "2500.000"

    other = client.post("/api/v1/quotes", headers=owner, json=sample(world)).json()
    walkin = body(world, [line(world, "cement", "1")], party="walkin")
    wrong = post(client, world, walkin | {"quote_id": other["id"]})
    assert wrong.status_code == 409 and wrong.json()["code"] == "QUOTE_OTHER_CUSTOMER"


def test_quotation_roles_and_rules(client, world):
    counter = login(client, *COUNTER)
    made = client.post("/api/v1/quotes", headers=counter, json=sample(world))
    assert made.status_code == 201, made.text
    quote_id = made.json()["id"]
    # Counter staff cannot discount on a quotation either (B4).
    discounted = sample(world)
    discounted["lines"][0] |= {"discount": "500", "discount_reason": "bulk"}
    refused = client.post("/api/v1/quotes", headers=counter, json=discounted)
    assert refused.status_code == 409 and refused.json()["code"] == "DISCOUNT_NEEDS_OWNER"
    # Another shop's counter does not see it; an old valid-until date is refused.
    other_shop = login(client, *COUNTER2)
    assert client.get(f"/api/v1/quotes/{quote_id}", headers=other_shop).status_code == 404
    assert client.get("/api/v1/quotes", headers=other_shop).json()["total"] == 0
    past = client.post(
        "/api/v1/quotes", headers=counter, json=sample(world, valid_until="2020-01-01")
    )
    assert past.status_code == 409 and past.json()["code"] == "VALID_UNTIL_PAST"
    assert "cost" not in made.text
    # The accountant reads quotations but does not make them; nobody signed out sees any.
    accountant = login(client, *ACCOUNTANT)
    assert client.post("/api/v1/quotes", headers=accountant, json=sample(world)).status_code == 403
    assert client.get(f"/api/v1/quotes/{quote_id}", headers=accountant).status_code == 200
    assert client.get("/api/v1/quotes").status_code == 401
