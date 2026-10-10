"""FM5: receivables aged from the due date, the provision, and bad-debt write-offs.

Customers with opening balances (due the day the balance starts, so the age is exact):
  Ten Days Ltd   ₹2,000, 10 days ago   -> 1-15 days late
  Twenty Days    ₹3,000, 20 days ago   -> 16-30
  Forty Days     ₹5,000, 40 days ago   -> 31-60
  Larry          ₹10,000, 100 days ago -> 60+
Overdue = 2,000 + 3,000 + 5,000 + 10,000 = ₹20,000.
Provision at 1 / 2 / 10 / 50 % = 20 + 60 + 500 + 5,000 = ₹5,580.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today_ist
from app.services import verify
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

PERIOD = today_ist().strftime("%Y-%m")


def customer(client, world, name):
    made = client.post(
        "/api/v1/parties",
        headers=world["owner"],
        json={"name": name, "type": "customer", "state_code": "33"},
    )
    assert made.status_code == 201, made.text
    return made.json()


@pytest.fixture
def late(client, world):
    owner = world["owner"]
    people = {}
    for name, ago, amount in (
        ("Ten Days Ltd", 10, "2000"),
        ("Twenty Days", 20, "3000"),
        ("Forty Days", 40, "5000"),
        ("Larry", 100, "10000"),
    ):
        party = customer(client, world, name)
        people[name] = party
        added = client.post(
            "/api/v1/opening",
            headers=owner,
            json={
                "kind": "receivable",
                "as_of": day(ago),
                "party_id": party["id"],
                "amount": amount,
            },
        )
        assert added.status_code == 201, added.text
    posted = client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["receivable"]})
    assert posted.status_code == 200, posted.text
    world["people"] = people
    return world


def report(client, headers):
    r = client.get("/api/v1/reports/receivables", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_aging_counts_from_the_due_date_and_the_provision_follows_the_settings(client, late):
    r = report(client, late["owner"])
    assert r["buckets"] == {
        "current": "0.00",
        "days_1_15": "2000.00",
        "days_16_30": "3000.00",
        "days_31_60": "5000.00",
        "over_60": "10000.00",
    }
    assert (r["total"], r["overdue"], r["advances"]) == ("20000.00", "20000.00", "0.00")
    assert r["provision"] == "5580.00"
    assert r["provision_pct"]["over_60"] == "50.00" and r["provision_pct"]["days_1_15"] == "1.00"
    rows = {x["party_name"]: x for x in r["rows"]}
    assert [x["party_name"] for x in r["rows"]] == [
        "Larry",
        "Forty Days",
        "Twenty Days",
        "Ten Days Ltd",
    ]
    larry = rows["Larry"]
    assert (larry["balance"], larry["overdue"], larry["days_late"]) == ("10000.00", "10000.00", 100)
    assert larry["oldest_due_date"] == day(100) and larry["credit_limit"] is None
    assert larry["utilisation_pct"] is None and larry["dso_days"] is None  # no credit sales
    assert larry["last_payment_date"] is None


def test_the_accountant_sees_the_aging_but_not_the_provision(client, late):
    r = report(client, login(client, *ACCOUNTANT))
    assert r["overdue"] == "20000.00"
    assert "provision" not in r and "provision_pct" not in r
    assert (
        client.get("/api/v1/reports/receivables", headers=login(client, *COUNTER)).status_code
        == 403
    )


def test_a_bill_is_due_on_its_due_date_not_its_bill_date(client, world):
    # Ravi has 30 days; a bill dated today is not late, so it is all "current".
    ok = post(client, world, body(world, [line(world, "tmt", "1", "ton")]))
    assert ok.status_code == 201
    r = report(client, world["owner"])
    ravi = next(x for x in r["rows"] if x["party_name"] == "Ravi Builders")
    assert ravi["buckets"]["current"] == "66080.00" and ravi["overdue"] == "0.00"
    assert ravi["days_late"] is None and ravi["oldest_due_date"] is None
    # 66,080 of a ₹1,00,00,000 limit = 0.66 %.
    assert (ravi["credit_limit"], ravi["utilisation_pct"]) == ("10000000.00", "0.66")
    # He bought on credit today: over the last 90 days his DSO is the average owed over the
    # credit sales: (0 + 66,080) ÷ 2 ÷ 66,080 x 90 = 45.0 days.
    assert ravi["dso_days"] == "45.0"
    assert r["overdue"] == "0.00" and r["provision"] == "0.00"


def test_the_provision_percentages_come_from_the_settings(client, late):
    settings = client.get("/api/v1/settings", headers=late["owner"]).json()
    settings.pop("id")
    settings |= {"provision_pct_over_60": "100", "provision_pct_31_60": "20"}
    assert client.put("/api/v1/settings", headers=late["owner"], json=settings).status_code == 200
    # 20 + 60 + 5,000 x 20% + 10,000 x 100% = ₹11,080.
    assert report(client, late["owner"])["provision"] == "11080.00"


# ---------------------------------------------------------------- write-offs


def writeoff(client, world, party, amount, headers=None, **extra):
    return client.post(
        "/api/v1/write-offs",
        headers=headers or world["owner"],
        json={
            "location_id": world["loc"]["S1"],
            "party_id": party["id"],
            "amount": amount,
            "reason": "Contractor untraceable",
        }
        | extra,
    )


def test_a_write_off_clears_the_oldest_debt_with_no_gst_effect(client, late, seeded):
    larry = late["people"]["Larry"]
    gst_before = client.get(f"/api/v1/gst/gstr1?period={PERIOD}", headers=late["owner"]).json()[
        "totals"
    ]
    made = writeoff(client, late, larry, "10000")
    assert made.status_code == 201, made.text
    w = made.json()
    assert w["number"].startswith("S1W/") and w["number"].endswith("/00001")
    assert (w["amount"], w["balance_before"], w["party_name"]) == ("10000.00", "10000.00", "Larry")
    # The account is credited: Larry owes nothing, so he drops out of the report.
    r = report(client, late["owner"])
    assert "Larry" not in [x["party_name"] for x in r["rows"]]
    assert r["buckets"]["over_60"] == "0.00" and r["overdue"] == "10000.00"
    # 20 + 60 + 500 = ₹580 of provision remains.
    assert r["provision"] == "580.00"
    # No GST document: GSTR-1 and GSTR-3B are untouched, and there is no credit note.
    assert (
        client.get(f"/api/v1/gst/gstr1?period={PERIOD}", headers=late["owner"]).json()["totals"]
        == gst_before
    )
    assert client.get("/api/v1/credit-notes", headers=late["owner"]).json()["total"] == 0
    statement = client.get(f"/api/v1/parties/{larry['id']}/statement", headers=late["owner"]).json()
    assert statement["receivable"]["balance"] == "0.00"
    assert statement["receivable"]["entries"][-1]["ref_type"] == "write_off"
    listed = client.get(f"/api/v1/write-offs?party_id={larry['id']}", headers=late["owner"]).json()
    assert [x["number"] for x in listed] == [w["number"]]
    assert verify.run_checks(seeded).ok


def test_a_part_write_off_takes_the_oldest_bill_first(client, late):
    larry = late["people"]["Larry"]
    assert writeoff(client, late, larry, "4000").status_code == 201
    row = next(x for x in report(client, late["owner"])["rows"] if x["party_name"] == "Larry")
    assert (row["balance"], row["buckets"]["over_60"]) == ("6000.00", "6000.00")
    second = writeoff(client, late, larry, "6000")
    assert second.json()["number"].endswith("/00002")  # gapless
    assert second.json()["balance_before"] == "6000.00"


def test_a_write_off_cannot_exceed_the_balance_or_name_a_supplier(client, late):
    larry = late["people"]["Larry"]
    too_much = writeoff(client, late, larry, "10000.01")
    assert too_much.status_code == 409 and too_much.json()["code"] == "WRITEOFF_TOO_MUCH"
    assert "Larry" in too_much.json()["message"]
    assert too_much.json()["field"] == "amount"
    supplier = writeoff(client, late, late["supplier"], "10")
    assert supplier.status_code == 409 and supplier.json()["code"] == "NOT_A_CUSTOMER"
    assert writeoff(client, late, larry, "0").status_code == 422
    assert writeoff(client, late, larry, "10", reason="x").status_code == 422
    assert writeoff(client, late, {"id": 99999}, "10").status_code == 404
    gone = writeoff(client, late, larry, "10", location_id=99999)
    assert gone.status_code == 404
    assert client.get("/api/v1/write-offs", headers=late["owner"]).json() == []  # nothing saved


def test_only_the_owner_writes_off_and_the_accountant_reads(client, late):
    larry = late["people"]["Larry"]
    for creds in (COUNTER, ACCOUNTANT):
        assert writeoff(client, late, larry, "10", headers=login(client, *creds)).status_code == 403
    assert writeoff(client, late, larry, "10").status_code == 201
    assert client.get("/api/v1/write-offs", headers=login(client, *ACCOUNTANT)).status_code == 200
    assert client.get("/api/v1/write-offs", headers=login(client, *COUNTER)).status_code == 403


def test_a_write_off_is_permanent(client, late, seeded):
    assert writeoff(client, late, late["people"]["Larry"], "100").status_code == 201
    for sql in (
        "UPDATE bad_debt_writeoff SET amount = 1",
        "DELETE FROM bad_debt_writeoff",
        "UPDATE party_ledger SET credit = 1 WHERE ref_type = 'write_off'",
        "DELETE FROM party_ledger WHERE ref_type = 'write_off'",
    ):
        with pytest.raises(DBAPIError), seeded.begin_nested():
            seeded.execute(text(sql))


def test_bad_debts_come_off_the_months_profit(client, late):
    owner = late["owner"]
    before = client.get(f"/api/v1/reports/pnl?period={PERIOD}", headers=owner).json()
    assert before["bad_debts"] == "0.00"
    assert writeoff(client, late, late["people"]["Larry"], "5000").status_code == 201
    after = client.get(f"/api/v1/reports/pnl?period={PERIOD}", headers=owner).json()
    assert after["bad_debts"] == "5000.00"
    assert float(before["net_profit"]) - float(after["net_profit"]) == 5000.0
    assert after["ebitda"] == before["ebitda"] and after["gross_profit"] == before["gross_profit"]
    assert after["break_even_sales"] == before["break_even_sales"]
    shop = client.get(
        f"/api/v1/reports/pnl?period={PERIOD}&location_id={late['loc']['G1']}", headers=owner
    ).json()
    assert shop["bad_debts"] == "0.00"  # written off at S1, not at the godown
