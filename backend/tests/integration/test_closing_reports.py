"""Milestone 12: daily closing, the day lock, Today figures, profit and segment reports."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.clock import today_ist
from app.services.storage import StorageError, get_storage
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


def cash_bill(client, world, quantity="7", paid="1000", mode="cash", **extra):
    payload = body(world, [line(world, "cement", quantity)], **extra)
    payload["payments"] = [{"mode": mode, "amount": paid}] if paid else []
    response = post(client, world, payload)
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, headers, world, location="S1", on=None):
    return client.get(
        f"/api/v1/closings/preview?location_id={world['loc'][location]}&closing_date={on or day(0)}",
        headers=headers,
    )


def close(client, headers, world, counted, location="S1", on=None, **extra):
    return client.post(
        "/api/v1/closings",
        headers=headers,
        json={
            "location_id": world["loc"][location],
            "closing_date": on or day(0),
            "counted_cash": counted,
        }
        | extra,
    )


def test_figures_cash_drawer_pdf_and_storage(client, world):
    # 7 bags at 380.45 = 2,663.15 + 28% GST (372.84 x 2) = 3,408.83, rounded to 3,409.00.
    first = cash_bill(client, world, paid="1000")
    second = cash_bill(client, world, quantity="1", paid="200", mode="upi")
    owed = client.post(
        "/api/v1/payments",
        headers=world["owner"],
        json={
            "direction": "paid",
            "party_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "300",
            "mode": "cash",
            "payment_date": day(0),
        },
    )
    assert owed.status_code == 201, owed.text
    shown = preview(client, world["owner"], world).json()
    fig = shown["figures"]
    assert fig["invoices_count"] == 2
    assert (fig["first_invoice"], fig["last_invoice"]) == (first["number"], second["number"])
    assert Decimal(fig["sales_total"]) == Decimal(first["grand_total"]) + Decimal(
        second["grand_total"]
    )
    assert (fig["receipts"]["cash"], fig["receipts"]["upi"], fig["receipts"]["total"]) == (
        "1000.00",
        "200.00",
        "1200.00",
    )
    assert fig["cash_out"] == "300.00" and fig["top_items"][0]["description"] == "Cement PPC"
    # Drawer: opening 0 + cash 1,000 - paid out 300 = 700.
    assert (shown["opening_cash"], shown["expected_cash"], shown["locked"]) == (
        "0.00",
        "700.00",
        False,
    )
    assert shown["profit"] is not None  # the owner sees profit; the PDF never does

    short = close(client, world["owner"], world, "650")
    assert short.status_code == 409 and short.json()["code"] == "CASH_NOTE_REQUIRED"
    done = close(client, world["owner"], world, "650", note="Rs 50 given as change to a customer")
    assert done.status_code == 201, done.text
    closed = done.json()
    assert (closed["status"], closed["difference"], closed["expected_cash"], closed["has_pdf"]) == (
        "closed",
        "-50.00",
        "700.00",
        True,
    )
    pdf = client.get(f"/api/v1/closings/{closed['id']}/pdf", headers=world["owner"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    key = f"closing/S1/{today_ist():%Y/%m}/{today_ist().isoformat()}.pdf"
    assert get_storage().exists(key)
    again = close(client, world["owner"], world, "650", note="again")
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_CLOSED"


def test_a_closed_day_refuses_new_documents_until_the_owner_reopens_it(client, world, seeded):
    inv = cash_bill(client, world)
    assert close(client, world["owner"], world, "1000").status_code == 201
    locked = preview(client, world["owner"], world).json()["locked"]
    assert locked is True

    refused = post(client, world, body(world, [line(world, "cement", "1")]))
    assert refused.status_code == 409 and refused.json()["code"] == "DAY_CLOSED"
    assert "S1" in refused.json()["message"]
    assert (
        client.post(
            "/api/v1/invoices/preview",
            headers=world["owner"],
            json=body(world, [line(world, "cement", "1")]),
        ).status_code
        == 409
    )
    purchase = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "L-1",
            "bill_date": day(0),
            "lines": [
                {"item_id": world["cement"]["id"], "unit": "bag", "quantity": "5", "rate": "300"}
            ],
        },
    )
    assert purchase.json()["code"] == "DAY_CLOSED"
    receipt = client.post(
        "/api/v1/payments",
        headers=world["owner"],
        json={
            "direction": "received",
            "party_id": world["ravi"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "10",
            "mode": "upi",
            "payment_date": day(0),
        },
    )
    assert receipt.json()["code"] == "DAY_CLOSED"
    credit = client.post(
        "/api/v1/credit-notes",
        headers=world["owner"],
        json={
            "invoice_id": inv["id"],
            "reason": "Late return",
            "lines": [{"line_id": inv["lines"][0]["id"], "quantity": "1"}],
        },
    )
    assert credit.json()["code"] == "DAY_CLOSED"
    transfer = client.post(
        "/api/v1/transfers",
        headers=world["owner"],
        json={
            "from_location_id": world["loc"]["S1"],
            "to_location_id": world["loc"]["G1"],
            "lines": [{"item_id": world["cement"]["id"], "quantity": "1"}],
        },
    )
    assert transfer.json()["code"] == "DAY_CLOSED"
    # The other shop and other days are not affected.
    assert post(
        client, world, body(world, [line(world, "cement", "1")], location="G1")
    ).status_code in (201, 409)
    other_day = post(client, world, body(world, [line(world, "cement", "1")], invoice_date=day(1)))
    assert other_day.status_code == 201

    counter = login(client, *COUNTER)
    row = client.get("/api/v1/closings", headers=world["owner"]).json()["items"][0]
    assert (
        client.post(
            f"/api/v1/closings/{row['id']}/reopen",
            headers=counter,
            json={"reason": "forgot a bill"},
        ).status_code
        == 403
    )
    reopened = client.post(
        f"/api/v1/closings/{row['id']}/reopen",
        headers=world["owner"],
        json={"reason": "forgot a bill"},
    )
    assert reopened.status_code == 200 and reopened.json()["status"] == "reopened"
    assert (
        client.post(
            f"/api/v1/closings/{row['id']}/reopen", headers=world["owner"], json={"reason": "twice"}
        ).json()["code"]
        == "NOT_CLOSED"
    )
    assert post(client, world, body(world, [line(world, "cement", "1")])).status_code == 201
    ok = close(client, world["owner"], world, "1000")  # the extra bill took no cash
    assert ok.status_code == 201 and ok.json()["times_closed"] == 2


def test_opening_cash_follows_the_last_count_and_rules(client, world, seeded):
    first = close(client, world["owner"], world, "5000", on=day(1), opening_cash="5000")
    assert first.status_code == 201, first.text
    assert preview(client, world["owner"], world).json()["opening_cash"] == "5000.00"
    assert (
        close(
            client, world["owner"], world, "0", on=(today_ist() + timedelta(days=1)).isoformat()
        ).json()["code"]
        == "FUTURE_DATE"
    )
    counter, other_shop, accountant = (
        login(client, *COUNTER),
        login(client, *COUNTER2),
        login(client, *ACCOUNTANT),
    )
    assert preview(client, other_shop, world).status_code == 404
    assert close(client, other_shop, world, "0").status_code == 404
    assert close(client, accountant, world, "0").status_code == 403
    assert preview(client, accountant, world).status_code == 200
    assert preview(client, accountant, world).json()["profit"] is None
    assert preview(client, counter, world).json()["profit"] is None
    mine = close(client, counter, world, "5000", on=day(0))
    assert mine.status_code == 201, mine.text
    assert client.get("/api/v1/closings", headers=other_shop).json()["total"] == 0
    assert client.get("/api/v1/closings", headers=counter).json()["total"] == 2
    row_id = mine.json()["id"]
    assert client.get(f"/api/v1/closings/{row_id}/pdf", headers=other_shop).status_code == 404
    assert client.get(f"/api/v1/closings/{row_id}/pdf", headers=accountant).status_code == 200
    assert client.get("/api/v1/closings/99999/pdf", headers=world["owner"]).status_code == 404
    assert (
        client.post(
            "/api/v1/closings/99999/reopen", headers=world["owner"], json={"reason": "none"}
        ).status_code
        == 404
    )


def test_a_failed_save_to_storage_leaves_the_day_open(client, world, monkeypatch):
    class Broken:
        def put(self, key, data):
            raise StorageError("down")

    monkeypatch.setattr("app.services.closing.get_storage", lambda: Broken())
    cash_bill(client, world)
    failed = close(client, world["owner"], world, "1000")
    assert failed.status_code == 400 and failed.json()["code"] == "STORAGE_FAILED"
    assert preview(client, world["owner"], world).json()["locked"] is False
    assert client.get("/api/v1/closings", headers=world["owner"]).json()["total"] == 0


def test_today_strip_by_role(client, world, seeded):
    cash_bill(client, world, paid="1000")
    owner = client.get("/api/v1/reports/today", headers=world["owner"]).json()
    assert owner["sales_today"] == "3409.00" and owner["items_in_stock"] == 2
    assert owner["we_owe"] is not None and owner["profit_today"] is not None
    # 7 bags sold at ₹380.45 (taxable 2,663.15) from stock costing ₹350: profit 2,663.15 - 2,450 = 213.15.
    assert owner["profit_today"] == "213.15"
    assert owner["customers_owe"] == "2409.00"  # 3,409 less the 1,000 paid with the bill
    counter = client.get("/api/v1/reports/today", headers=login(client, *COUNTER)).json()
    assert (
        counter["we_owe"] is None
        and counter["profit_today"] is None
        and counter["sales_today"] == "3409.00"
    )
    other = client.get("/api/v1/reports/today", headers=login(client, *COUNTER2)).json()
    assert other["sales_today"] == "0.00"
    accountant = client.get("/api/v1/reports/today", headers=login(client, *ACCOUNTANT)).json()
    assert accountant["we_owe"] is not None and accountant["profit_today"] is None


def test_profit_by_item_customer_and_site_with_returns_and_freight(client, world, seeded):
    # 1 ton TMT at ₹56 a kg against ₹55 cost: 1,000 profit. A 400 kg return reverses 40%.
    inv = post(
        client, world, body(world, [line(world, "tmt", "1", "ton")], site="Chennai site")
    ).json()
    credit = client.post(
        "/api/v1/credit-notes",
        headers=world["owner"],
        json={
            "invoice_id": inv["id"],
            "reason": "Too much",
            "lines": [{"line_id": inv["lines"][0]["id"], "quantity": "0.4"}],
        },
    )
    assert credit.status_code == 201, credit.text
    car = client.post(
        "/api/v1/vehicles",
        headers=world["owner"],
        json={"number": "TN09AB1234", "owner_name": "Murugan"},
    ).json()
    trip = client.post(
        "/api/v1/trips",
        headers=world["owner"],
        json={
            "vehicle_id": car["id"],
            "location_id": world["loc"]["S1"],
            "invoice_id": inv["id"],
            "from_place": "Shop",
            "to_place": "Site",
            "freight_amount": "300",
        },
    )
    assert trip.status_code == 201
    url = f"/api/v1/reports/profit?date_from={day(0)}&date_to={day(0)}&group="
    by_item = client.get(url + "item", headers=world["owner"]).json()
    # Net of the return: taxable 33,600, cost 33,000, freight 300 -> 300.
    assert (by_item["taxable"], by_item["cost"], by_item["freight"], by_item["profit"]) == (
        "33600.00",
        "33000.00",
        "300.00",
        "300.00",
    )
    row = by_item["rows"][0]
    assert row["key"] == "TMT 12 mm" and row["margin_pct"] == "0.89"
    by_customer = client.get(url + "customer", headers=world["owner"]).json()["rows"]
    assert [r["key"] for r in by_customer] == ["Ravi Builders"]
    by_site = client.get(url + "site", headers=world["owner"]).json()["rows"]
    assert by_site[0]["key"] == "Ravi Builders: Chennai site"
    for who in (login(client, *COUNTER), login(client, *ACCOUNTANT)):
        assert client.get(url + "item", headers=who).status_code == 403
    bad = client.get(
        f"/api/v1/reports/profit?date_from={day(0)}&date_to={day(5)}&group=item",
        headers=world["owner"],
    )
    assert bad.json()["code"] == "BAD_RANGE"
    long = client.get(
        f"/api/v1/reports/profit?date_from={day(400)}&date_to={day(0)}&group=item",
        headers=world["owner"],
    )
    assert long.json()["code"] == "RANGE_TOO_LONG"


def test_sales_by_segment_per_month(client, world, seeded):
    empty = client.get("/api/v1/reports/sales-by-segment", headers=world["owner"]).json()
    assert len(empty["months"]) == 12 and empty["total"] == "0.00"
    contractor = client.post(
        "/api/v1/parties",
        headers=world["owner"],
        json={
            "name": "Big Contractor",
            "type": "customer",
            "state_code": "33",
            "segment": "contractor",
        },
    ).json()
    world["bigc"] = contractor
    client.patch(
        f"/api/v1/parties/{contractor['id']}",
        headers=world["owner"],
        json={"credit_allowed": True, "credit_limit": "1000000", "credit_days": 30},
    )
    bill = post(client, world, body(world, [line(world, "cement", "10")], party="bigc")).json()
    post(client, world, body(world, [line(world, "cement", "3")]))  # Ravi has no segment yet
    client.post(
        "/api/v1/credit-notes",
        headers=world["owner"],
        json={
            "invoice_id": bill["id"],
            "reason": "Short",
            "lines": [{"line_id": bill["lines"][0]["id"], "quantity": "2"}],
        },
    )
    report = client.get("/api/v1/reports/sales-by-segment", headers=world["owner"]).json()
    month = next(m for m in report["months"] if m["month"] == today_ist().strftime("%Y-%m"))
    # 10 bags at 380.45 = 3,804.50 less 2 returned = 3,043.60; Ravi's 3 bags = 1,141.35.
    assert (month["contractor"], month["unassigned"], month["retail"], month["bulk"]) == (
        "3043.60",
        "1141.35",
        "0.00",
        "0.00",
    )
    assert month["total"] == "4184.95" and report["total"] == "4184.95"
    accountant = client.get("/api/v1/reports/sales-by-segment", headers=login(client, *ACCOUNTANT))
    assert accountant.status_code == 200
    assert (
        client.get("/api/v1/reports/sales-by-segment", headers=login(client, *COUNTER)).status_code
        == 403
    )
    prior = client.get(
        f"/api/v1/reports/sales-by-segment?start_year={today_ist().year - 5}",
        headers=world["owner"],
    ).json()
    assert prior["total"] == "0.00"
