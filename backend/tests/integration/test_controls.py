"""FM7: period lock, bank statement matching and the exception report
(docs/FINANCE_REVIEW.md F16, F17, F18)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today_ist
from tests.conftest import login
from tests.integration.test_adjustments import adjust, new_item
from tests.integration.test_returns import note_body, sell
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


def ddmmyyyy(offset: int) -> str:
    return (today_ist() - __import__("datetime").timedelta(days=offset)).strftime("%d/%m/%Y")


def lock(client, headers, through, reason="October return filed"):
    return client.put(
        "/api/v1/period-lock", headers=headers, json={"locked_through": through, "reason": reason}
    )


# ---------------------------------------------------------------- period lock


def test_a_credit_note_dated_in_a_locked_month_is_refused(client, world, seeded):
    owner = world["owner"]
    inv = sell(client, world)
    assert lock(client, owner, day(0)).status_code == 200

    refused = client.post("/api/v1/credit-notes", headers=owner, json=note_body(inv, [(1, "1")]))
    assert refused.status_code == 409 and refused.json()["code"] == "PERIOD_LOCKED"
    assert "locked" in refused.json()["message"]
    # Every dated document is covered: bills, receipts, cash-book vouchers, write-offs, adjustments.
    assert post(client, world, body(world, [line(world, "cement", "1")])).json()["code"] == (
        "PERIOD_LOCKED"
    )
    paid = client.post(
        "/api/v1/payments",
        headers=owner,
        json={
            "direction": "received",
            "party_id": world["ravi"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "100",
            "mode": "upi",
            "payment_date": day(0),
        },
    )
    assert paid.json()["code"] == "PERIOD_LOCKED"
    written = client.post(
        "/api/v1/write-offs",
        headers=owner,
        json={
            "party_id": world["ravi"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "10",
            "reason": "Gone",
        },
    )
    assert written.json()["code"] == "PERIOD_LOCKED"

    # Reopening needs the owner and a reason, and is audited.
    assert lock(client, login(client, *ACCOUNTANT), None).status_code == 403
    assert lock(client, owner, None, reason="x").status_code == 422
    assert lock(client, owner, None, reason="Credit note for a returned load").status_code == 200
    assert (
        client.post(
            "/api/v1/credit-notes", headers=owner, json=note_body(inv, [(1, "1")])
        ).status_code
        == 201
    )
    events = client.get("/api/v1/audit-log?entity=period_lock", headers=owner).json()["items"]
    assert [e["changes"]["reason"] for e in events] == [
        "Credit note for a returned load",
        "October return filed",
    ]
    assert events[0]["changes"]["reopens"] is True and events[1]["changes"]["reopens"] is False


def test_lock_rules_and_who_may_read(client, world):
    owner = world["owner"]
    tomorrow = (today_ist().replace(year=today_ist().year + 1)).isoformat()
    assert lock(client, owner, tomorrow).json()["code"] == "LOCK_IN_FUTURE"
    assert lock(client, owner, day(40)).status_code == 200
    again = lock(client, owner, day(40))
    assert again.json()["code"] == "LOCK_UNCHANGED"
    state = client.get("/api/v1/period-lock", headers=login(client, *ACCOUNTANT)).json()
    assert state["locked_through"] == day(40) and state["reason"] == "October return filed"
    assert client.get("/api/v1/period-lock", headers=login(client, *COUNTER)).status_code == 403
    assert lock(client, login(client, *COUNTER), day(40)).status_code == 403
    # The settings form never carries the lock, so saving settings cannot move it.
    settings = client.get("/api/v1/settings", headers=owner).json()
    assert "locked_through" in settings
    saved = client.put("/api/v1/settings", headers=owner, json=settings | {"locked_through": None})
    assert saved.status_code == 200
    assert client.get("/api/v1/period-lock", headers=owner).json()["locked_through"] == day(40)
    # A bill dated before the lock is refused even though today is open.
    old = post(client, world, body(world, [line(world, "cement", "1")], invoice_date=day(45)))
    assert old.json()["code"] == "PERIOD_LOCKED"


def test_month_end_checklist(client, world):
    owner = world["owner"]
    sell(client, world)
    period = today_ist().strftime("%Y-%m")
    done = client.get(f"/api/v1/period-lock/checklist?period={period}", headers=owner).json()
    states = {i["code"]: i["state"] for i in done["items"]}
    assert states["days_closed"] == "warn" and states["gstr2b"] == "warn"
    assert states["bank"] == "warn" and done["ready"] is False
    assert (
        client.get(
            f"/api/v1/period-lock/checklist?period={period}", headers=login(client, *COUNTER)
        )
    ).status_code == 403


# ---------------------------------------------------------------- bank statements

HEADER = "Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"


def csv_row(offset, narration, ref="", debit="", credit="", balance=""):
    d = ddmmyyyy(offset)
    return f"{d},{narration},{ref},{d},{debit},{credit},{balance}\n"


def upi(client, world, amount, ref, mode="upi", party="ravi"):
    r = client.post(
        "/api/v1/payments",
        headers=world["owner"],
        json={
            "direction": "received",
            "party_id": world[party]["id"],
            "location_id": world["loc"]["S1"],
            "amount": amount,
            "mode": mode,
            "reference": ref,
            "payment_date": day(0),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def upload(client, headers, account_id, text_, name="oct.csv"):
    return client.post(
        "/api/v1/bank/statements",
        headers=headers,
        data={"bank_account_id": str(account_id)},
        files={"file": (name, text_.encode(), "text/csv")},
    )


def test_fm7_acceptance_ten_bank_rows_eight_match_two_are_listed(client, world, seeded):
    owner = world["owner"]
    account = client.post("/api/v1/bank/accounts", headers=owner, json={"name": "SBI current"})
    assert account.status_code == 201, account.text
    aid = account.json()["id"]

    # The books: five UPI receipts, a NEFT receipt, a supplier payment, a cash deposit, and one
    # UPI receipt (₹8,000) that never reached the bank.
    upi(client, world, "25000", "412345678901")
    upi(client, world, "50000", None, mode="bank", party="walkin")
    upi(client, world, "12400", "412345678902")
    upi(client, world, "25000", "412345678903")
    upi(client, world, "9900", "412345678904")
    upi(client, world, "7500", "412345678905")
    upi(client, world, "8000", "999999999999")
    paid = client.post(
        "/api/v1/payments",
        headers=owner,
        json={
            "direction": "paid",
            "party_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "300000",
            "mode": "bank",
            "payment_date": day(0),
        },
    )
    assert paid.status_code == 201, paid.text
    deposit = client.post(
        "/api/v1/cash-book",
        headers=owner,
        json={
            "location_id": world["loc"]["S1"],
            "kind": "bank_deposit",
            "mode": "cash",
            "amount": "150000",
        },
    )
    assert deposit.status_code == 201, deposit.text

    statement = (
        HEADER
        + csv_row(
            1,
            "UPI/RAVI/412345678901",
            "412345678901",
            credit='"25,000.00"',
            balance='"5,25,000.00"',
        )
        + csv_row(1, "NEFT SHARMA TRADERS", credit="50000.00", balance="575000.00")
        + csv_row(
            0, "UPI/SURESH/412345678902", "412345678902", credit="12400.00", balance="587400.00"
        )
        + csv_row(0, "CASH DEPOSIT S1", credit="150000.00", balance="737400.00")
        + csv_row(
            0, "UPI/RAVI/412345678903", "412345678903", credit="25000.00", balance="762400.00"
        )
        + csv_row(0, "NEFT SUPPLIER MILLS", debit="300000.00", balance="462400.00")
        + csv_row(
            0, "UPI/MOHAN/412345678904", "412345678904", credit="9900.00", balance="472300.00"
        )
        + csv_row(0, "CHQ DEP UNKNOWN", credit="18750.00", balance="491050.00")
        + csv_row(0, "UPI/ANIL/412345678905", "412345678905", credit="7500.00", balance="498550.00")
        + csv_row(0, "BANK CHARGES", debit="590.00", balance="497960.00")
    )
    imported = upload(client, owner, aid, statement)
    assert imported.status_code == 201, imported.text
    assert imported.json()["row_count"] == 10 and imported.json()["closing_balance"] == "497960.00"

    rec = client.get(
        f"/api/v1/bank/reconciliation?date_from={day(5)}&date_to={day(0)}", headers=owner
    ).json()
    assert (rec["line_count"], rec["matched_count"], rec["unmatched_count"]) == (10, 8, 2)
    unmatched = {x["narration"] for x in rec["lines"] if not x["matched"]}
    assert unmatched == {"CHQ DEP UNKNOWN", "BANK CHARGES"}
    assert (rec["unmatched_in"], rec["unmatched_out"]) == ("18750.00", "590.00")
    # The fake or failed UPI: recorded as received, never on the statement.
    assert [(x["amount"], x["reference"]) for x in rec["not_in_bank"]] == [
        ("8000.00", "999999999999")
    ]
    assert rec["not_in_bank_total"] == "8000.00"
    by_ref = {x["narration"]: x for x in rec["lines"]}
    assert by_ref["UPI/RAVI/412345678901"]["matched_how"] == "reference"
    assert by_ref["NEFT SHARMA TRADERS"]["matched_how"] == "amount"
    assert by_ref["CASH DEPOSIT S1"]["matched_label"].startswith("Cash deposit")
    assert (rec["last_balance"], rec["last_balance_date"]) == ("497960.00", day(0))

    # The books move, the report follows: a late receipt for the unknown cheque now matches.
    upi(client, world, "18750", None, mode="bank", party="walkin")
    again = client.get(
        f"/api/v1/bank/reconciliation?date_from={day(5)}&date_to={day(0)}", headers=owner
    ).json()
    assert again["matched_count"] == 9 and again["unmatched_count"] == 1

    # Statements are permanent.
    with pytest.raises(DBAPIError), seeded.begin_nested():
        seeded.execute(text("UPDATE bank_statement_line SET credit = credit + 1"))
    with pytest.raises(DBAPIError), seeded.begin_nested():
        seeded.execute(text("DELETE FROM bank_statement"))


def test_import_rules(client, world):
    owner = world["owner"]
    accountant = login(client, *ACCOUNTANT)
    counter = login(client, *COUNTER)
    aid = client.post("/api/v1/bank/accounts", headers=owner, json={"name": "HDFC"}).json()["id"]
    dup = client.post("/api/v1/bank/accounts", headers=owner, json={"name": "HDFC"})
    assert dup.status_code == 409 and dup.json()["code"] == "DUPLICATE_NAME"
    first = (
        HEADER
        + csv_row(2, "A", credit="100.00", balance="100.00")
        + csv_row(1, "B", credit="200.00", balance="300.00")
    )
    assert upload(client, accountant, aid, first).status_code == 201  # the accountant imports
    assert upload(client, counter, aid, first).status_code == 403
    same = upload(client, owner, aid, first)
    assert same.status_code == 409 and same.json()["code"] == "STATEMENT_IMPORTED"

    # An overlapping download repeats old rows: they are skipped, new ones kept.
    overlap = first + csv_row(0, "C", credit="50.00", balance="350.00")
    second = upload(client, owner, aid, overlap, "oct2.csv").json()
    assert (second["row_count"], second["skipped_count"]) == (3, 2)
    rec = client.get(
        f"/api/v1/bank/reconciliation?date_from={day(5)}&date_to={day(0)}", headers=owner
    ).json()
    assert rec["line_count"] == 3  # no line is held twice

    # A bad file saves nothing and names its lines.
    bad = upload(
        client, owner, aid, "Date,Narration,Debit,Credit\n99/99/2026,x,,1\n03/10/2026,y,,\n"
    )
    assert bad.status_code == 409 and bad.json()["code"] == "STATEMENT_UNREADABLE"
    assert "Line 2" in bad.json()["message"] and "Line 3" in bad.json()["message"]
    assert len(client.get("/api/v1/bank/statements", headers=owner).json()) == 2
    # Roles on the rest.
    for path in ("/bank/accounts", "/bank/statements", "/bank/reconciliation"):
        assert client.get(f"/api/v1{path}", headers=counter).status_code == 403
        assert client.get(f"/api/v1{path}", headers=accountant).status_code == 200
    made = client.post("/api/v1/bank/accounts", headers=accountant, json={"name": "Z"})
    assert made.status_code == 403
    off = client.patch(f"/api/v1/bank/accounts/{aid}", headers=owner, json={"is_active": False})
    assert off.json()["is_active"] is False
    assert upload(client, owner, aid, "Date,Debit\n", "e.csv").status_code == 409
    renamed = client.patch(f"/api/v1/bank/accounts/{aid}", headers=owner, json={"name": "HDFC 2"})
    assert renamed.json()["name"] == "HDFC 2"
    assert client.patch("/api/v1/bank/accounts/9999", headers=owner, json={}).status_code == 404


def test_a_reversed_voucher_is_not_expected_in_the_bank(client, world):
    owner = world["owner"]
    made = client.post(
        "/api/v1/cash-book",
        headers=owner,
        json={
            "location_id": world["loc"]["S1"],
            "kind": "bank_deposit",
            "mode": "cash",
            "amount": "5000",
        },
    ).json()
    undone = client.post(
        f"/api/v1/cash-book/{made['id']}/reverse", headers=owner, json={"reason": "Keyed twice"}
    )
    assert undone.status_code == 200, undone.text
    rec = client.get(
        f"/api/v1/bank/reconciliation?date_from={day(2)}&date_to={day(0)}", headers=owner
    ).json()
    assert rec["not_in_bank"] == []


# ---------------------------------------------------------------- exception report


def exceptions(client, headers, days=29):
    return client.get(
        f"/api/v1/reports/exceptions?date_from={day(days)}&date_to={day(0)}", headers=headers
    )


def test_fm7_acceptance_exception_report(client, world):
    owner = world["owner"]
    new_item(client, world, "wire", "Binding wire 20g", "kg", "50", "500", "72171010")

    # A round-number adjustment (20 kg x ₹50 = ₹1,000) the day before a count.
    done = adjust(client, owner, world, "breakage", [("wire", "20")], adjustment_date=day(1))
    assert done.status_code == 201, done.text
    count = client.post(
        "/api/v1/stock-counts", headers=owner, json={"location_id": world["loc"]["S1"]}
    )
    assert count.status_code == 201, count.text
    # A not-round one is not flagged for being round.
    adjust(client, owner, world, "breakage", [("wire", "3")], adjustment_date=day(10))

    # One customer with four returns in 30 days: four credit notes on one bill.
    inv = sell(client, world, lines=[line(world, "cement", "7")])
    for _ in range(4):
        made = client.post("/api/v1/credit-notes", headers=owner, json=note_body(inv, [(0, "1")]))
        assert made.status_code == 201, made.text

    # A bill back-dated by the owner, and cash close to the ₹2,00,000 daily limit.
    assert (
        post(
            client, world, body(world, [line(world, "cement", "1")], invoice_date=day(1))
        ).status_code
        == 201
    )
    cash = client.post(
        "/api/v1/payments",
        headers=owner,
        json={
            "direction": "received",
            "party_id": world["ravi"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "170000",
            "mode": "cash",
            "payment_date": day(0),
        },
    )
    assert cash.status_code == 201, cash.text

    report = exceptions(client, owner).json()
    counts = {c["code"]: c["count"] for c in report["counts"]}
    assert counts["round_adjustment"] == 1
    assert counts["adjustment_before_count"] == 1
    assert counts["repeat_returns"] == 1
    assert counts["back_dated"] >= 1 and counts["cash_near_limit"] == 1
    by_code = {r["code"]: r for r in report["rows"]}
    round_row = by_code["round_adjustment"]
    assert round_row["value"] == "1000.00" and round_row["on"] == day(1)
    assert round_row["document"].startswith("S1A/")
    assert "1 day" in by_code["adjustment_before_count"]["detail"]
    assert "4 credit notes" in by_code["repeat_returns"]["detail"]
    assert "Ravi Builders" in by_code["repeat_returns"]["detail"]

    # Thresholds are settings; zero switches a rule off.
    settings = client.get("/api/v1/settings", headers=owner).json()
    off = client.put(
        "/api/v1/settings",
        headers=owner,
        json=settings
        | {
            "exception_round_amount": "0",
            "exception_returns_count": 0,
            "exception_cash_near_pct": "0",
            "exception_count_days": 0,
        },
    )
    assert off.status_code == 200, off.text
    counts = {c["code"]: c["count"] for c in exceptions(client, owner).json()["counts"]}
    assert (
        counts["round_adjustment"],
        counts["adjustment_before_count"],
        counts["repeat_returns"],
        counts["cash_near_limit"],
    ) == (0, 0, 0, 0)

    # Owner only.
    assert exceptions(client, login(client, *COUNTER)).status_code == 403
    assert exceptions(client, login(client, *ACCOUNTANT)).status_code == 403
    assert (
        client.get(
            f"/api/v1/reports/exceptions?date_from={day(0)}&date_to={day(3)}", headers=owner
        ).json()["code"]
        == "BAD_RANGE"
    )


def test_repeated_weighbridge_shortages_from_one_supplier(client, world):
    owner = world["owner"]
    for n in range(3):
        r = client.post(
            "/api/v1/purchases",
            headers=owner,
            json={
                "supplier_id": world["supplier"]["id"],
                "location_id": world["loc"]["S1"],
                "bill_no": f"SH-{n}",
                "bill_date": day(2),
                "lines": [
                    {
                        "item_id": world["tmt"]["id"],
                        "unit": "ton",
                        "quantity": "10",
                        "rate": "55000",
                        "received_quantity": "9.95",
                        "weight_note": "short",
                    }
                ],
            },
        )
        assert r.status_code == 201, r.text
    rows = exceptions(client, owner).json()["rows"]
    short = [r for r in rows if r["code"] == "repeat_shortage"]
    assert len(short) == 1 and "Mills" in short[0]["detail"]
