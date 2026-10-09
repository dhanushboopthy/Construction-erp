"""Milestone 7: credit checks, owner PIN approvals, receipts and allocation."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.clock import now_utc, today_ist
from app.models.approvals import Approval
from app.models.audit import AuditLog
from app.models.enums import AuditAction
from tests.conftest import login

pytestmark = pytest.mark.integration

OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")  # S1
COUNTER2 = ("counter2", "counter-pass-123")  # S2
ACCOUNTANT = ("accounts", "accounts-pass-123")
PIN = "4821"


def day(offset: int = 0) -> str:
    return (today_ist() - timedelta(days=offset)).isoformat()


@pytest.fixture
def world(client):
    owner = login(client, *OWNER)
    loc = {x["code"]: x["id"] for x in client.get("/api/v1/locations", headers=owner).json()}
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
            "item_id": cement["id"],
            "location_id": loc["S1"],
            "quantity": "1000",
            "unit_cost": "300",
        },
    )
    client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["stock"]})
    client.put(
        "/api/v1/rates/market",
        headers=owner,
        json={"effective_date": day(1), "rates": [{"item_id": cement["id"], "rate": "380.45"}]},
    )
    ravi = client.post(
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
    client.patch(
        f"/api/v1/parties/{ravi['id']}",
        headers=owner,
        json={"credit_allowed": True, "credit_limit": "10000", "credit_days": 7},
    )
    walkin = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Walk-in", "type": "customer", "state_code": "33"},
    ).json()
    other = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Kumar Co", "type": "customer", "state_code": "33"},
    ).json()
    client.patch(
        f"/api/v1/parties/{other['id']}",
        headers=owner,
        json={"credit_allowed": True, "credit_limit": "10000"},
    )
    supplier = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Mills", "type": "supplier", "state_code": "33"},
    ).json()
    return {
        "owner": owner,
        "loc": loc,
        "cement": cement,
        "ravi": ravi,
        "walkin": walkin,
        "other": other,
        "supplier": supplier,
        "sites": {s["name"]: s["id"] for s in ravi["sites"]},
    }


def bill(world, bags="10", party="ravi", site=None, **extra):
    # 10 bags x 380.45 = 3,804.50; GST 28% = 1,065.26; total 4,869.76 -> 4,870.00.
    return {
        "location_id": world["loc"]["S1"],
        "party_id": world[party]["id"],
        "site_id": world["sites"][site] if site else None,
        "lines": [{"item_id": world["cement"]["id"], "quantity": bags}],
    } | extra


def post(client, world, payload, headers=None, key=None):
    h = dict(headers or world["owner"])
    if key:
        h["Idempotency-Key"] = key
    return client.post("/api/v1/invoices", headers=h, json=payload)


def set_pin(client, world, pin=PIN):
    return client.post(
        "/api/v1/auth/pin", headers=world["owner"], json={"current_password": OWNER[1], "pin": pin}
    )


# ---------------------------------------------------------------- credit rules (B8)


def test_credit_is_for_approved_customers_within_limit_and_not_overdue(client, world):
    counter = login(client, *COUNTER)

    # A customer who is not approved for credit must pay: unpaid bills are blocked.
    blocked = post(client, world, bill(world, party="walkin"), headers=counter)
    assert blocked.status_code == 409 and blocked.json()["code"] == "CREDIT_NOT_ALLOWED"
    assert blocked.json()["requires_owner_approval"] is True
    paid = post(
        client,
        world,
        bill(
            world, party="walkin", payments=[{"mode": "upi", "amount": "4870", "reference": "UPI1"}]
        ),
        headers=counter,
    )
    assert paid.status_code == 201 and paid.json()["paid_at_billing"] == "4870.00"

    # Ravi: limit 10,000. Two bills of 4,870 are within it (9,740); a third would not be.
    assert post(client, world, bill(world), headers=counter).status_code == 201
    assert post(client, world, bill(world), headers=counter).status_code == 201
    over = post(client, world, bill(world), headers=counter)
    assert over.status_code == 409 and over.json()["code"] == "CREDIT_LIMIT_EXCEEDED"
    assert "9,740.00" in over.json()["message"] and "260.00" in over.json()["message"]
    # The check is on the unpaid part only: paying 4,870 of the 4,870 leaves nothing unpaid.
    ok = post(
        client, world, bill(world, payments=[{"mode": "cash", "amount": "4870"}]), headers=counter
    )
    assert ok.status_code == 201
    # Paying only 4,000 leaves 870 unpaid; 9,740 + 870 is still over the limit.
    part = post(
        client, world, bill(world, payments=[{"mode": "cash", "amount": "4000"}]), headers=counter
    )
    assert part.json()["code"] == "CREDIT_LIMIT_EXCEEDED"
    # Paying 4,740 leaves 130 unpaid: 9,740 + 130 = 9,870, within the limit.
    fits = post(
        client, world, bill(world, payments=[{"mode": "cash", "amount": "4740"}]), headers=counter
    )
    assert fits.status_code == 201 and fits.json()["pending_balance_at_billing"] == "9740.00"


def test_overdue_bills_block_new_credit_and_the_owner_can_override_with_a_trail(
    client, world, seeded
):
    owner = world["owner"]
    # Ravi owes 1,000 from 20 days ago; his terms are 7 days, so it is 13 days overdue.
    client.post(
        "/api/v1/opening",
        headers=owner,
        json={
            "kind": "receivable",
            "as_of": day(20),
            "party_id": world["ravi"]["id"],
            "amount": "1000",
        },
    )
    client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["receivable"]})
    counter = login(client, *COUNTER)
    blocked = post(client, world, bill(world, bags="1"), headers=counter)
    assert blocked.status_code == 409 and blocked.json()["code"] == "OVERDUE_INVOICES"
    assert "Opening" in blocked.json()["message"]
    # Paying cash for the whole bill needs no credit, so overdue dues do not block it.
    assert (
        post(
            client,
            world,
            bill(world, bags="1", payments=[{"mode": "cash", "amount": "487"}]),
            headers=counter,
        ).status_code
        == 201
    )
    # The owner may bill on credit anyway; the waived rule is recorded.
    forced = post(client, world, bill(world, bags="1"))
    assert forced.status_code == 201
    event = seeded.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.OVERRIDE, AuditLog.entity == "sales_invoice"
        )
    ).scalar_one()
    assert (
        event.changes["waived"] == ["OVERDUE_INVOICES"]
        and event.changes["number"] == forced.json()["number"]
    )


def test_preview_tells_the_counter_why_a_bill_is_blocked(client, world):
    counter = login(client, *COUNTER)
    preview = client.post(
        "/api/v1/invoices/preview", headers=counter, json=bill(world, party="walkin")
    ).json()
    assert preview["can_save"] is False and preview["needs_owner"] is True
    assert preview["approvals_needed"] == ["credit_override"]
    assert preview["invoice_problems"] == [
        "This customer is not approved for credit. Take payment, or ask the owner."
    ]
    paid = client.post(
        "/api/v1/invoices/preview",
        headers=counter,
        json=bill(world, party="walkin", payments=[{"mode": "upi", "amount": "4870"}]),
    ).json()
    assert paid["can_save"] is True and (paid["paid_now"], paid["balance_due"]) == (
        "4870.00",
        "0.00",
    )
    over = client.post(
        "/api/v1/invoices/preview",
        headers=counter,
        json=bill(world, payments=[{"mode": "upi", "amount": "6000"}]),
    ).json()
    assert over["can_save"] is False and over["invoice_problems"] == [
        "More money was entered than the bill total."
    ]
    assert over["needs_owner"] is False


# ---------------------------------------------------------------- owner PIN approvals (G18)


def test_owner_pin_approves_one_bill_once(client, world, seeded):
    counter = login(client, *COUNTER)
    ask = {
        "action": "credit_override",
        "reason": "regular customer, paying Friday",
        "party_id": world["walkin"]["id"],
    }
    no_pin_yet = client.post("/api/v1/approvals", headers=counter, json=ask | {"pin": PIN})
    assert no_pin_yet.status_code == 401 and "No owner has set" in no_pin_yet.json()["message"]
    assert set_pin(client, world).status_code == 204
    assert (
        client.post(
            "/api/v1/auth/pin", headers=counter, json={"current_password": "x" * 8, "pin": PIN}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/pin",
            headers=world["owner"],
            json={"current_password": "wrong", "pin": PIN},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/pin",
            headers=world["owner"],
            json={"current_password": OWNER[1], "pin": "12"},
        ).status_code
        == 422
    )

    wrong = client.post("/api/v1/approvals", headers=counter, json=ask | {"pin": "0000"})
    assert wrong.status_code == 401 and wrong.json()["field"] == "pin"
    granted = client.post("/api/v1/approvals", headers=counter, json=ask | {"pin": PIN})
    assert granted.status_code == 201 and granted.json()["approved_by_name"] == "Shop Owner"
    approval_id = granted.json()["id"]

    # The approval is aimed at one customer: it does not open credit for anyone else.
    elsewhere = post(
        client, world, bill(world, party="other", approval_ids=[approval_id]), headers=counter
    )
    assert elsewhere.status_code == 409 and elsewhere.json()["code"] == "APPROVAL_INVALID"
    # Nor can another user use it.
    assert post(
        client,
        world,
        bill(world, party="walkin", approval_ids=[approval_id]),
        headers=login(client, *COUNTER2),
    ).status_code in (403, 409)
    ok = post(
        client, world, bill(world, party="walkin", approval_ids=[approval_id]), headers=counter
    )
    assert ok.status_code == 201, ok.text
    again = post(
        client, world, bill(world, party="walkin", approval_ids=[approval_id]), headers=counter
    )
    assert again.json()["code"] == "APPROVAL_INVALID"  # one approval, one bill

    row = seeded.get(Approval, approval_id)
    assert row.used_ref == ok.json()["number"] and row.reason.startswith("regular customer")
    trail = (
        seeded.execute(
            select(AuditLog).where(
                AuditLog.entity == "approval", AuditLog.action == AuditAction.OVERRIDE
            )
        )
        .scalars()
        .all()
    )
    assert trail and trail[0].changes["approved_by"] == row.approved_by
    assert "pin" not in str(trail[0].changes).lower() or "approved_by" in trail[0].changes

    # An approval that has run out is refused.
    stale = client.post("/api/v1/approvals", headers=counter, json=ask | {"pin": PIN}).json()["id"]
    seeded.get(Approval, stale).expires_at = now_utc() - timedelta(minutes=1)
    seeded.flush()
    expired = post(
        client, world, bill(world, party="walkin", approval_ids=[stale]), headers=counter
    )
    assert expired.json()["code"] == "APPROVAL_INVALID"
    assert (
        post(
            client, world, bill(world, party="walkin", approval_ids=[999999]), headers=counter
        ).json()["code"]
        == "APPROVAL_INVALID"
    )


def test_pin_approval_unlocks_discounts_below_cost_and_back_dating(client, world):
    set_pin(client, world)
    counter = login(client, *COUNTER)

    def approve(action):
        r = client.post(
            "/api/v1/approvals",
            headers=counter,
            json={"pin": PIN, "action": action, "reason": "owner agreed on the phone"},
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    discounted = bill(world, bags="1")
    discounted["lines"][0] |= {"discount": "20", "discount_reason": "regular"}
    assert post(client, world, discounted, headers=counter).json()["code"] == "DISCOUNT_NEEDS_OWNER"
    ok = post(
        client,
        world,
        discounted
        | {"approval_ids": [approve("discount")], "payments": [{"mode": "cash", "amount": "400"}]},
        headers=counter,
    )
    # 380.45 - 20 = 360.45 taxable; GST 28% = 100.93 (50.46 + 50.47? 14% each = 50.463 -> 50.46); total 461.37 -> 461.00.
    assert ok.status_code == 201, ok.text
    assert ok.json()["lines"][0]["discount"] == "20.00" and ok.json()["taxable_value"] == "360.45"

    client.put(
        "/api/v1/rates/market",
        headers=world["owner"],
        json={
            "effective_date": day(0),
            "rates": [{"item_id": world["cement"]["id"], "rate": "290"}],
        },
    )  # cost is 300 a bag
    below = bill(world, bags="1", payments=[{"mode": "cash", "amount": "371"}])
    assert post(client, world, below, headers=counter).json()["code"] == "BELOW_COST"
    assert (
        post(
            client, world, below | {"approval_ids": [approve("below_cost")]}, headers=counter
        ).status_code
        == 201
    )

    old = bill(world, bags="1", payments=[{"mode": "cash", "amount": "371"}], invoice_date=day(1))
    assert post(client, world, old, headers=counter).json()["code"] == "BACKDATE_NEEDS_OWNER"
    assert (
        post(
            client, world, old | {"approval_ids": [approve("backdate")]}, headers=counter
        ).status_code
        == 201
    )


def test_wrong_pins_lock_the_counter_for_a_while(client, world):
    set_pin(client, world)
    counter = login(client, *COUNTER)
    ask = {"action": "discount", "reason": "just trying", "pin": "1111"}
    codes = [
        client.post("/api/v1/approvals", headers=counter, json=ask).status_code for _ in range(6)
    ]
    assert codes == [401, 401, 401, 401, 401, 423]
    right = client.post("/api/v1/approvals", headers=counter, json=ask | {"pin": PIN})
    assert right.status_code == 423  # even the right PIN waits out the lock
    assert (
        client.post("/api/v1/approvals", headers=login(client, *ACCOUNTANT), json=ask).status_code
        == 403
    )


# ---------------------------------------------------------------- receipts and allocation


def two_bills(client, world, site=None):
    a = post(client, world, bill(world, site=site), headers=login(client, *COUNTER)).json()
    b = post(client, world, bill(world, site=site), headers=login(client, *COUNTER)).json()
    return a, b


def receipt(client, world, amount, headers=None, **extra):
    body = {
        "direction": "received",
        "party_id": world["ravi"]["id"],
        "location_id": world["loc"]["S1"],
        "amount": amount,
        "mode": "upi",
        "reference": "UTR9",
        "payment_date": day(0),
    } | extra
    return client.post("/api/v1/payments", headers=headers or login(client, *COUNTER), json=body)


def statement(client, world, site=None):
    path = f"/api/v1/parties/{world['ravi']['id']}/statement" + (
        f"?site_id={world['sites'][site]}" if site else ""
    )
    return client.get(path, headers=world["owner"]).json()["receivable"]


def test_a_receipt_clears_the_oldest_bill_first(client, world):
    a, b = two_bills(client, world)
    response = receipt(client, world, "6000")
    assert response.status_code == 201, response.text
    paid = response.json()
    assert paid["number"] == "S1R/26-27/00001"
    # 6,000 clears bill A (4,870) and 1,130 of bill B.
    assert [(x["bill_no"], x["amount"]) for x in paid["applied"]] == [
        (a["number"], "4870.00"),
        (b["number"], "1130.00"),
    ]
    assert paid["advance"] == "0.00"
    bills = client.get(
        f"/api/v1/parties/{world['ravi']['id']}/open-bills?account=receivable",
        headers=world["owner"],
    ).json()
    assert [(x["bill_no"], x["remaining"]) for x in bills["bills"]] == [(b["number"], "3740.00")]
    assert statement(client, world)["balance"] == "3740.00"


def test_a_receipt_can_pick_the_bill_it_pays(client, world):
    a, b = two_bills(client, world)
    picked = receipt(
        client, world, "4870", allocations=[{"bill_no": b["number"], "amount": "4870"}]
    )
    assert picked.status_code == 201, picked.text
    assert [(x["bill_no"], x["amount"]) for x in picked.json()["applied"]] == [
        (b["number"], "4870.00")
    ]
    bills = client.get(
        f"/api/v1/parties/{world['ravi']['id']}/open-bills?account=receivable",
        headers=world["owner"],
    ).json()
    # The newer bill B is paid; the older bill A stays open (it was not first in line this time).
    assert [x["bill_no"] for x in bills["bills"]] == [a["number"]]


def test_extra_money_stays_as_an_advance_and_the_next_bill_uses_it(client, world):
    a, _ = two_bills(client, world)
    big = receipt(client, world, "12000")
    assert big.json()["advance"] == "2260.00"  # 12,000 less two bills of 4,870
    state = statement(client, world)
    assert (state["balance"], state["advance"]) == ("-2260.00", "2260.00")
    nxt = post(
        client, world, bill(world, bags="5"), headers=login(client, *COUNTER)
    ).json()  # 2,435
    assert nxt["pending_balance_at_billing"] == "-2260.00"
    state = statement(client, world)
    assert (state["balance"], state["advance"]) == ("175.00", "0.00")  # the advance paid most of it
    del a


def test_receipt_rules(client, world):
    two_bills(client, world)
    a_number = client.get("/api/v1/invoices", headers=world["owner"]).json()["items"][-1]["number"]
    cases = [
        ({"allocations": [{"bill_no": "NOPE", "amount": "100"}]}, "ALLOCATION_INVALID"),
        (
            {"allocations": [{"bill_no": a_number, "amount": "9999"}], "amount": "20000"},
            "ALLOCATION_INVALID",
        ),
        (
            {
                "allocations": [
                    {"bill_no": a_number, "amount": "3000"},
                    {"bill_no": a_number, "amount": "100"},
                ]
            },
            "ALLOCATION_INVALID",
        ),
        (
            {"allocations": [{"bill_no": a_number, "amount": "300"}], "amount": "100"},
            "ALLOCATION_INVALID",
        ),
        ({"party_id": world["supplier"]["id"]}, "WRONG_PARTY_TYPE"),
        ({"site_id": 99999}, "SITE_MISMATCH"),
    ]
    for extra, code in cases:
        extra = {"amount": "1000"} | extra
        response = receipt(client, world, extra.pop("amount"), **extra)
        assert response.status_code == 409 and response.json()["code"] == code, (
            extra,
            response.text,
        )
    assert receipt(client, world, "1000", party_id=99999).status_code == 404
    assert (
        receipt(client, world, "1000", headers=world["owner"], location_id=99999).status_code == 404
    )


def test_cash_from_one_customer_is_capped_each_day(client, world):
    owner = world["owner"]
    # Cash of 2,00,000 or more from one person in a day is not allowed (G14).
    assert receipt(client, world, "150000", mode="cash").status_code == 201
    capped = receipt(client, world, "50000", mode="cash")
    assert capped.status_code == 409 and capped.json()["code"] == "CASH_LIMIT_REACHED"
    assert "UPI" in capped.json()["message"]
    assert (
        receipt(client, world, "49999", mode="cash").status_code == 201
    )  # 1,99,999 is under the cap
    assert receipt(client, world, "300000", mode="upi").status_code == 201  # UPI and bank are fine
    # Cash taken with a bill counts toward the same cap.
    client.put(
        "/api/v1/settings",
        headers=owner,
        json={
            **{
                k: v
                for k, v in client.get("/api/v1/settings", headers=owner).json().items()
                if k != "id"
            },
            "cash_receipt_limit": "5000",
        },
    )
    blocked = post(
        client,
        world,
        bill(world, party="other", payments=[{"mode": "cash", "amount": "4870"}]),
        headers=owner,
    )
    assert blocked.status_code == 201  # 4,870 < 5,000
    again = post(
        client,
        world,
        bill(world, party="other", payments=[{"mode": "cash", "amount": "200"}]),
        headers=owner,
    )
    assert again.status_code == 409 and again.json()["code"] == "CASH_LIMIT_REACHED"


def test_receipts_are_idempotent_and_role_checked(client, world):
    counter = login(client, *COUNTER)
    first = receipt(client, world, "1000", headers=counter | {"Idempotency-Key": "r-1"})
    again = receipt(client, world, "1000", headers=counter | {"Idempotency-Key": "r-1"})
    assert (
        first.status_code == 201
        and again.status_code == 200
        and again.json()["id"] == first.json()["id"]
    )
    clash = receipt(client, world, "2000", headers=counter | {"Idempotency-Key": "r-1"})
    assert clash.status_code == 409 and clash.json()["code"] == "IDEMPOTENCY_CONFLICT"
    # Counter staff record receipts for their own shop only, and never pay suppliers.
    assert receipt(client, world, "1000", headers=login(client, *COUNTER2)).status_code == 403
    pay_supplier = client.post(
        "/api/v1/payments",
        headers=counter,
        json={
            "direction": "paid",
            "party_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "100",
            "mode": "bank",
            "payment_date": day(0),
        },
    )
    assert pay_supplier.status_code == 403
    assert receipt(client, world, "100", headers=login(client, *ACCOUNTANT)).status_code == 403
    assert len(client.get("/api/v1/payments", headers=counter).json()) == 1
    assert client.get("/api/v1/payments", headers=login(client, *COUNTER2)).json() == []
    assert len(client.get("/api/v1/payments", headers=login(client, *ACCOUNTANT)).json()) == 1
    # Counter staff cannot list suppliers' open bills; customers' are fine.
    assert (
        client.get(
            f"/api/v1/parties/{world['supplier']['id']}/open-bills?account=payable", headers=counter
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/parties/{world['ravi']['id']}/open-bills?account=receivable", headers=counter
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/parties/99999/open-bills?account=receivable", headers=counter
        ).status_code
        == 404
    )


def test_statements_balance_per_site_and_together(client, world):
    counter = login(client, *COUNTER)
    post(client, world, bill(world, site="Anna Nagar"), headers=counter)
    post(client, world, bill(world, bags="5", site="Adyar"), headers=counter)
    # A payment can be recorded against a site: Anna Nagar pays 3,000 of its 4,870.
    paid = receipt(client, world, "3000", site_id=world["sites"]["Anna Nagar"])
    assert paid.status_code == 201, paid.text
    assert statement(client, world, "Anna Nagar")["balance"] == "1870.00"  # 4,870 - 3,000
    assert statement(client, world, "Adyar")["balance"] == "2435.00"
    # Together: 4,870 + 2,435 - 3,000 = 4,305, the sum of the two sites.
    assert statement(client, world)["balance"] == "4305.00"
    rows = statement(client, world, "Anna Nagar")["entries"]
    assert [r["running_balance"] for r in rows] == ["4870.00", "1870.00"]
    assert rows[1]["doc_no"] == paid.json()["number"] and rows[1]["credit"] == "3000.00"


def test_money_taken_with_the_bill_makes_receipts_and_prints_on_the_pdf(client, world):
    inv = post(
        client,
        world,
        bill(
            world,
            payments=[
                {"mode": "cash", "amount": "2000"},
                {"mode": "upi", "amount": "2870", "reference": "UPI77"},
            ],
        ),
        headers=login(client, *COUNTER),
    ).json()
    assert inv["paid_at_billing"] == "4870.00"
    receipts = client.get("/api/v1/payments", headers=world["owner"]).json()
    assert sorted(p["number"] for p in receipts) == ["S1R/26-27/00001", "S1R/26-27/00002"]
    assert {p["mode"] for p in receipts} == {"cash", "upi"}
    assert statement(client, world)["balance"] == "0.00"  # paid in full, nothing owed
    pdf = client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=world["owner"])
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
