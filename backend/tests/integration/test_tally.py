"""FM4: the Tally day-book export, hand-worked for one month at the shop.

All documents are dated today, so they fall in the current calendar month (a whole GST period).

  Bill A, Ravi Builders: 1 ton TMT at ₹56,000 + 18% GST = ₹66,080, ₹20,000 cash with the bill
  Bill B, Walk-in: 10 bags cement at ₹380.45 + 28% GST = ₹4,870, paid in full by UPI
  Credit note on A for 0.5 ton: taxable 28,000 + GST 5,040 = ₹33,040
  Ravi pays ₹10,000 by UPI later
    receivable moves by 66,080 - 20,000 - 33,040 - 10,000 = ₹3,040 (B nets to nothing)
  Supplier bill: 10 ton at ₹55,000 + 18% = ₹6,49,000 payable
  Debit note for 2 ton: taxable 1,10,000 + GST 19,800 = ₹1,29,800
  We pay the supplier ₹1,00,000 by bank
  Rebate booked: target met, 2% of the 8 ton kept = 2% of ₹4,40,000 = ₹8,800 (we owe less)
  Freight ₹3,000 owed to a transporter (we owe more)
    payable moves by 6,49,000 - 1,29,800 - 1,00,000 - 8,800 + 3,000 = ₹4,13,400
  Cash book: ₹2,000 loading labour in cash, ₹1,50,000 taken to the bank
GSTR-1 taxable = 56,000 + 3,804.50 - 28,000 = ₹31,804.50
Input tax (CGST and SGST each) = 49,500 - 9,900 = ₹39,600
"""

from datetime import timedelta
from decimal import Decimal
from xml.etree import ElementTree

import pytest
from sqlalchemy import text

from app.core.clock import today_ist
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

FIRST = today_ist().replace(day=1)
LAST = (FIRST + timedelta(days=32)).replace(day=1) - timedelta(days=1)
RANGE = f"date_from={FIRST.isoformat()}&date_to={LAST.isoformat()}"


@pytest.fixture
def month(client, world):
    owner = world["owner"]
    a = post(
        client,
        world,
        body(
            world,
            [line(world, "tmt", "1", "ton")],
            payments=[{"mode": "cash", "amount": "20000"}],
        ),
    )
    assert a.status_code == 201, a.text
    b = post(
        client,
        world,
        body(
            world,
            [line(world, "cement", "10")],
            party="walkin",
            payments=[{"mode": "upi", "amount": "4870", "reference": "UPI-1"}],
        ),
    )
    assert b.status_code == 201, b.text
    bill = a.json()
    note = client.post(
        "/api/v1/credit-notes",
        headers=owner,
        json={
            "invoice_id": bill["id"],
            "reason": "Wrong size",
            "lines": [{"line_id": bill["lines"][0]["id"], "quantity": "0.5"}],
        },
    )
    assert note.status_code == 201, note.text
    pay = {
        "location_id": world["loc"]["S1"],
        "payment_date": day(0),
    }
    assert (
        client.post(
            "/api/v1/payments",
            headers=owner,
            json=pay
            | {
                "direction": "received",
                "party_id": world["ravi"]["id"],
                "amount": "10000",
                "mode": "upi",
            },
        ).status_code
        == 201
    )
    bought = client.post(
        "/api/v1/purchases",
        headers=owner,
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "M-77",
            "bill_date": day(0),
            "lines": [
                {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": "10", "rate": "55000"}
            ],
        },
    )
    assert bought.status_code == 201, bought.text
    purchase = bought.json()
    dn = client.post(
        "/api/v1/debit-notes",
        headers=owner,
        json={
            "purchase_id": purchase["id"],
            "reason": "Rusted bars",
            "lines": [{"line_id": purchase["lines"][0]["id"], "quantity": "2"}],
        },
    )
    assert dn.status_code == 201, dn.text
    assert (
        client.post(
            "/api/v1/payments",
            headers=owner,
            json=pay
            | {
                "direction": "paid",
                "party_id": world["supplier"]["id"],
                "amount": "100000",
                "mode": "bank",
                "reference": "NEFT-9",
            },
        ).status_code
        == 201
    )
    scheme = client.post(
        "/api/v1/schemes",
        headers=owner,
        json={
            "party_id": world["supplier"]["id"],
            "name": "Q3 rebate",
            "item_id": world["tmt"]["id"],
            "target_qty": "5000",
            "period_start": day(5),
            "period_end": (today_ist() + timedelta(days=60)).isoformat(),
            "rebate_rule": "percent",
            "rebate_value": "2",
        },
    ).json()
    booked = client.post(f"/api/v1/schemes/{scheme['id']}/book-rebate", headers=owner)
    assert booked.json()["rebate_amount"] == "8800.00", booked.text
    car = client.post(
        "/api/v1/vehicles",
        headers=owner,
        json={"number": "TN 09 AB 1234", "owner_name": "Murugan Transport"},
    ).json()
    trip = client.post(
        "/api/v1/trips",
        headers=owner,
        json={
            "vehicle_id": car["id"],
            "location_id": world["loc"]["S1"],
            "from_place": "Mill",
            "to_place": "Shop",
            "freight_amount": "3000",
        },
    )
    assert trip.status_code == 201, trip.text
    heads = {
        r["name"]: r["id"] for r in client.get("/api/v1/expense-categories", headers=owner).json()
    }
    for kind, amount, extra in (
        ("expense", "2000", {"category_id": heads["Loading and unloading labour"]}),
        ("bank_deposit", "150000", {}),
    ):
        entry = client.post(
            "/api/v1/cash-book",
            headers=owner,
            json={
                "location_id": world["loc"]["S1"],
                "kind": kind,
                "mode": "cash",
                "amount": amount,
            }
            | extra,
        )
        assert entry.status_code == 201, entry.text
    return world


def export(client, headers, query=RANGE):
    return client.get(f"/api/v1/tally/export?{query}", headers=headers)


def test_the_export_agrees_with_gstr1_and_the_dues_reports(client, month):
    owner = month["owner"]
    r = client.get(f"/api/v1/tally/preview?{RANGE}", headers=owner)
    assert r.status_code == 200, r.text
    p = r.json()
    kinds = {k["kind"]: (k["count"], k["total"]) for k in p["kinds"]}
    # Debits of each kind: Sales 66,080 + 4,870; Credit Note 33,040; Purchase 6,49,000;
    # Debit Note 1,29,800; Receipts (cash 20,000 + UPI 4,870 + UPI 10,000) = 34,870 in the bank
    # and drawer; Payment: supplier 1,00,000 + labour 2,000; Contra 1,50,000; Journals 8,800 + 3,000.
    assert kinds == {
        "Sales": (2, "70950.00"),
        "Credit Note": (1, "33040.00"),
        "Purchase": (1, "649000.00"),
        "Debit Note": (1, "129800.00"),
        "Receipt": (3, "34870.00"),
        "Payment": (2, "102000.00"),
        "Contra": (1, "150000.00"),
        "Journal": (2, "11800.00"),
    }
    assert p["voucher_count"] == 13 and p["gst_checked"] is True and p["note"] is None
    checks = {c["code"]: c for c in p["checks"]}
    assert all(c["ok"] for c in p["checks"]), p["checks"]
    assert checks["gstr1_taxable"]["vouchers"] == checks["gstr1_taxable"]["report"] == "31804.50"
    assert checks["itc_cgst"]["vouchers"] == checks["itc_sgst"]["vouchers"] == "39600.00"
    assert checks["receivable"]["vouchers"] == "3040.00"
    assert checks["payable"]["vouchers"] == "413400.00"
    # ... and they are the figures the other reports show.
    gstr1 = client.get(f"/api/v1/gst/gstr1?period={FIRST:%Y-%m}", headers=owner).json()["totals"]
    assert gstr1["taxable"] == "31804.50"
    dues = {
        a: client.get(f"/api/v1/reports/dues?account={a}", headers=owner).json()["total"]
        for a in ("receivable", "payable")
    }
    assert dues == {"receivable": "3040.00", "payable": "413400.00"}


def test_the_xml_is_well_formed_balanced_and_carries_the_masters(client, month):
    response = export(client, month["owner"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.headers["content-disposition"].endswith('.xml"')
    root = ElementTree.fromstring(response.text)
    assert root.findtext(".//SVCURRENTCOMPANY") == "Demo Construction Materials"
    vouchers = root.findall(".//VOUCHER")
    assert len(vouchers) == 13
    for v in vouchers:  # Tally's convention: debits are negative, credits positive; they cancel
        assert (
            sum(Decimal(e.findtext("AMOUNT") or "0") for e in v.findall("ALLLEDGERENTRIES.LIST"))
            == 0
        )
    sales = next(v for v in vouchers if v.findtext("NARRATION", "").startswith("Sales bill S1/"))
    entries = {
        e.findtext("LEDGERNAME"): Decimal(e.findtext("AMOUNT") or "0")
        for e in sales.findall("ALLLEDGERENTRIES.LIST")
    }
    assert entries["Ravi Builders"] == Decimal("-66080") and entries["Sales"] == Decimal("56000")
    assert entries["Output CGST"] == entries["Output SGST"] == Decimal("5040")
    masters = {m.findtext("NAME"): m.findtext("PARENT") for m in root.findall(".//LEDGER")}
    assert masters["Ravi Builders"] == "Sundry Debtors" and masters["Mills"] == "Sundry Creditors"
    assert masters["Loading and unloading labour"] == "Indirect Expenses"
    assert masters["Sales"] == "Sales Accounts" and masters["Cash"] == "Cash-in-Hand"
    assert (
        masters["Transport: Murugan Transport (TN09AB1234)"] == "Sundry Creditors"
    )  # the transporter's account
    # Every ledger a voucher uses has a master.
    used = {e.findtext("LEDGERNAME") for v in vouchers for e in v.findall("ALLLEDGERENTRIES.LIST")}
    assert used <= set(masters), used - set(masters)
    without = export(client, month["owner"], RANGE + "&masters=false")
    assert ElementTree.fromstring(without.text).findall(".//LEDGER") == []


def test_ledger_names_are_the_accountants_and_used_in_the_file(client, month):
    acct = login(client, *ACCOUNTANT)
    before = client.get("/api/v1/tally/ledgers", headers=acct).json()
    assert before["company"] == "Demo Construction Materials"
    assert {x["purpose"]: x["name"] for x in before["ledgers"]}["sales"] == "Sales"
    assert not any(x["is_custom"] for x in before["ledgers"])
    saved = client.put(
        "/api/v1/tally/ledgers",
        headers=acct,
        json={
            "company": "DCM Traders (2026-27)",
            "names": {"sales": "Sales - Steel & Cement", "cash": "Cash at Shop"},
        },
    )
    assert saved.status_code == 200, saved.text
    custom = {x["purpose"]: x for x in saved.json()["ledgers"]}
    assert custom["sales"]["is_custom"] and custom["sales"]["default"] == "Sales"
    assert not custom["bank"]["is_custom"]
    root = ElementTree.fromstring(export(client, month["owner"]).text)
    assert root.findtext(".//SVCURRENTCOMPANY") == "DCM Traders (2026-27)"
    used = {e.findtext("LEDGERNAME") for e in root.iter("ALLLEDGERENTRIES.LIST")}
    assert "Sales - Steel & Cement" in used and "Cash at Shop" in used and "Sales" not in used
    # A blank goes back to the default; leaving the company out keeps the shop's name.
    back = client.put("/api/v1/tally/ledgers", headers=acct, json={"names": {"sales": " "}}).json()
    assert back["company"] == "Demo Construction Materials"
    assert not any(x["is_custom"] for x in back["ledgers"])
    assert export(client, acct).status_code == 200


def test_ledger_names_must_be_known_and_distinct(client, world):
    owner = world["owner"]
    put = lambda names: client.put("/api/v1/tally/ledgers", headers=owner, json={"names": names})
    unknown = put({"nonsense": "X"})
    assert unknown.status_code == 409 and unknown.json()["code"] == "UNKNOWN_LEDGER"
    twice = put({"sales": "GST", "output_cgst": "gst"})
    assert twice.status_code == 409 and twice.json()["code"] == "DUPLICATE_LEDGER_NAME"
    assert "CGST on sales" in twice.json()["message"]
    assert put({"sales": "Sales"}).status_code == 200


def test_a_range_that_is_not_whole_months_checks_only_the_dues(client, month):
    narrow = f"date_from={today_ist().isoformat()}&date_to={today_ist().isoformat()}"
    p = client.get(f"/api/v1/tally/preview?{narrow}", headers=month["owner"]).json()
    assert p["gst_checked"] is False and "whole calendar months" in p["note"]
    assert {c["code"] for c in p["checks"]} == {"receivable", "payable"}
    empty = client.get(
        f"/api/v1/tally/preview?date_from={day(400)}&date_to={day(380)}", headers=month["owner"]
    ).json()
    assert empty["voucher_count"] == 0 and empty["kinds"] == []


def test_a_bad_range_is_refused(client, world):
    owner = world["owner"]
    backwards = client.get(
        f"/api/v1/tally/preview?date_from={day(0)}&date_to={day(5)}", headers=owner
    )
    assert backwards.status_code == 409 and backwards.json()["code"] == "BAD_RANGE"
    long = client.get(f"/api/v1/tally/export?date_from={day(400)}&date_to={day(0)}", headers=owner)
    assert long.status_code == 409 and long.json()["code"] == "RANGE_TOO_LONG"


def test_the_export_is_refused_when_it_disagrees_with_the_books(client, month, monkeypatch):
    from app.services import tally

    real = tally._movement
    monkeypatch.setattr(tally, "_movement", lambda *a: real(*a) + 1)  # the dues drift by ₹1
    refused = export(client, month["owner"])
    assert refused.status_code == 409 and refused.json()["code"] == "EXPORT_MISMATCH"
    shown = client.get(f"/api/v1/tally/preview?{RANGE}", headers=month["owner"]).json()
    assert [c["code"] for c in shown["checks"] if not c["ok"]] == ["receivable", "payable"]


def test_only_the_owner_and_the_accountant_may_export_and_every_export_is_logged(
    client, month, seeded
):
    counter = login(client, *COUNTER)
    for path in (
        f"/api/v1/tally/preview?{RANGE}",
        f"/api/v1/tally/export?{RANGE}",
        "/api/v1/tally/ledgers",
    ):
        assert client.get(path, headers=counter).status_code == 403
    assert client.put("/api/v1/tally/ledgers", headers=counter, json={}).status_code == 403
    assert (
        client.get(f"/api/v1/tally/preview?{RANGE}", headers=login(client, *ACCOUNTANT)).status_code
        == 200
    )
    seeded.rollback()
    assert (
        seeded.execute(text("select count(*) from audit_log where action = 'export'")).scalar() == 0
    )
    assert export(client, login(client, *ACCOUNTANT)).status_code == 200
    export(client, month["owner"])
    seeded.rollback()
    logged = seeded.execute(
        text("select user_id, entity, changes from audit_log where action = 'export' order by id")
    ).all()
    assert len(logged) == 2 and logged[0][1] == "tally"
    assert logged[0][2]["vouchers"] == 13


def test_a_reversed_voucher_is_exported_both_ways(client, month):
    owner = month["owner"]
    entries = client.get(f"/api/v1/cash-book?{RANGE}", headers=owner).json()["entries"]
    labour = next(e for e in entries if e["kind"] == "expense")
    undone = client.post(
        f"/api/v1/cash-book/{labour['id']}/reverse", headers=owner, json={"reason": "typo"}
    )
    assert undone.status_code == 200, undone.text
    root = ElementTree.fromstring(export(client, owner).text)
    pairs = [
        v
        for v in root.findall(".//VOUCHER")
        if v.findtext("VOUCHERNUMBER") in (labour["number"], undone.json()["number"])
    ]
    assert len(pairs) == 2
    signed = {
        v.findtext("VOUCHERNUMBER"): {
            e.findtext("LEDGERNAME"): Decimal(e.findtext("AMOUNT") or "0")
            for e in v.findall("ALLLEDGERENTRIES.LIST")
        }
        for v in pairs
    }
    assert signed[labour["number"]]["Cash"] == Decimal("2000")  # a credit to Cash (Tally: positive)
    assert signed[undone.json()["number"]]["Cash"] == Decimal(
        "-2000"
    )  # the reversal debits Cash again
