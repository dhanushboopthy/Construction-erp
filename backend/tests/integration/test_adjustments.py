"""FM2: stock adjustments with reasons and approval, ITC to reverse
(docs/FINANCE_REVIEW.md F3, F15)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today_ist
from app.services import verify
from tests.conftest import login
from tests.integration.test_credit import PIN, set_pin
from tests.integration.test_returns import stock_at
from tests.integration.test_sales import (  # noqa: F401 - the world fixture is shared
    ACCOUNTANT,
    COUNTER,
    COUNTER2,
    day,
    world,
)

pytestmark = pytest.mark.integration

PERIOD = today_ist().strftime("%Y-%m")


def new_item(client, world, key, name, base_unit, cost, quantity, hsn, whole=False):
    """An 18% item bought into S1 at a known cost, so values come out round."""
    item = client.post(
        "/api/v1/items",
        headers=world["owner"],
        json={
            "name": name,
            "category": "cement" if base_unit == "bag" else "wire",
            "hsn": hsn,
            "gst_rate": "18",
            "base_unit": base_unit,
            "base_whole_only": whole,
        },
    ).json()
    bought = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": f"B-{key}",
            "bill_date": day(1),
            "lines": [
                {"item_id": item["id"], "unit": base_unit, "quantity": quantity, "rate": cost}
            ],
        },
    )
    assert bought.status_code == 201, bought.text
    world[key] = item
    return item


@pytest.fixture
def stocked(client, world):
    new_item(client, world, "opc", "Cement OPC 53", "bag", "380", "100", "25232930", whole=True)
    new_item(client, world, "wire", "Binding wire 20g", "kg", "75", "500", "72171010")
    return world


def adjust(client, headers, world, reason, lines, location="S1", **extra):
    payload = {
        "location_id": world["loc"][location],
        "reason": reason,
        "lines": [
            {"item_id": world[key]["id"], "quantity": qty} | more
            for key, qty, *rest in lines
            for more in [rest[0] if rest else {}]
        ],
    } | extra
    return client.post("/api/v1/stock-adjustments", headers=headers, json=payload)


def itc(client, headers):
    return client.get(f"/api/v1/reports/itc-reversal?period={PERIOD}", headers=headers)


def test_fm2_acceptance_breakage_and_theft(client, stocked, seeded):
    world = stocked
    counter = login(client, *COUNTER)

    # A breakage of 2 bags of cement (₹760) posts with reason "breakage".
    broken = adjust(client, counter, world, "breakage", [("opc", "2")], note="Torn in unloading")
    assert broken.status_code == 201, broken.text
    doc = broken.json()
    assert doc["number"].startswith("S1A/") and doc["reason"] == "breakage"
    assert "value" not in doc and "unit_cost" not in doc["lines"][0]  # counter sees no cost
    assert stock_at(client, world, "opc", "S1") == "98.000"
    owner_view = client.get(f"/api/v1/stock-adjustments/{doc['id']}", headers=world["owner"]).json()
    assert (owner_view["value"], owner_view["itc_to_reverse"]) == ("760.00", "136.80")

    # A ₹15,000 theft is above the ₹10,000 limit: refused without the owner's PIN.
    theft = adjust(client, counter, world, "theft", [("wire", "200")])
    assert theft.status_code == 409
    assert (theft.json()["code"], theft.json()["requires_owner_approval"]) == (
        "ADJUSTMENT_NEEDS_OWNER",
        True,
    )
    assert "15,000" not in theft.json()["message"]  # the value stays with the owner
    assert stock_at(client, world, "wire", "S1") == "500.000"
    assert set_pin(client, world).status_code == 204
    granted = client.post(
        "/api/v1/approvals",
        headers=counter,
        json={"action": "stock_adjustment", "reason": "Wire stolen overnight", "pin": PIN},
    )
    assert granted.status_code == 201, granted.text
    theft = adjust(
        client, counter, world, "theft", [("wire", "200")], approval_ids=[granted.json()["id"]]
    )
    assert theft.status_code == 201, theft.text
    assert theft.json()["approved"] is True

    # Both are listed in ITC to reverse: 15,000 x 18% = 2,700 and 760 x 18% = 136.80.
    report = itc(client, world["owner"]).json()
    by_doc = {r["document"]: r for r in report["rows"]}
    stolen = by_doc[theft.json()["number"]]
    assert (stolen["reason"], stolen["value"], stolen["gst_rate"], stolen["itc"]) == (
        "theft",
        "15000.00",
        "18.00",
        "2700.00",
    )
    assert by_doc[doc["number"]]["itc"] == "136.80"
    assert (report["total_value"], report["total_itc"]) == ("15760.00", "2836.80")

    # The ledger rows carry the reason, and nothing was edited.
    reasons = seeded.execute(
        text(
            "SELECT reason, qty_out FROM stock_ledger WHERE ref_type = 'stock_adjustment' "
            "ORDER BY id"
        )
    ).all()
    assert [(r, str(q)) for r, q in reasons] == [("breakage", "2.000"), ("theft", "200.000")]


def test_adjustments_are_permanent(client, stocked, seeded):
    world = stocked
    made = adjust(client, world["owner"], world, "damage", [("opc", "1")])
    assert made.status_code == 201, made.text
    with pytest.raises(DBAPIError, match="issued document"), seeded.begin_nested():
        seeded.execute(
            text("UPDATE stock_adjustment SET reason = 'theft' WHERE id = :i"),
            {"i": made.json()["id"]},
        )
    with pytest.raises(DBAPIError, match="issued document"), seeded.begin_nested():
        seeded.execute(
            text("DELETE FROM stock_adjustment_line WHERE adjustment_id = :i"),
            {"i": made.json()["id"]},
        )
    with pytest.raises(DBAPIError), seeded.begin_nested():
        seeded.execute(text("UPDATE stock_ledger SET reason = 'theft' WHERE reason = 'damage'"))
    with pytest.raises(DBAPIError, match="reason_on_adjustments"), seeded.begin_nested():
        seeded.execute(
            text(
                "INSERT INTO stock_ledger (tenant_id, item_id, location_id, entry_date, "
                "qty_in, qty_out, unit_cost, ref_type, reason) "
                "VALUES (1, :i, :l, CURRENT_DATE, 1, 0, 1, 'purchase', 'theft')"
            ),
            {"i": world["opc"]["id"], "l": world["loc"]["S1"]},
        )


def test_who_may_adjust(client, stocked):
    world = stocked
    counter2 = login(client, *COUNTER2)
    accountant = login(client, *ACCOUNTANT)
    counter = login(client, *COUNTER)
    assert adjust(client, accountant, world, "breakage", [("opc", "1")]).status_code == 403
    assert adjust(client, counter2, world, "breakage", [("opc", "1")]).status_code == 403
    backdated = adjust(client, counter, world, "breakage", [("opc", "1")], adjustment_date=day(1))
    assert backdated.status_code == 409 and backdated.json()["code"] == "BACKDATE_NEEDS_OWNER"
    by_owner = adjust(
        client, world["owner"], world, "breakage", [("opc", "1")], adjustment_date=day(1)
    )
    assert by_owner.status_code == 201, by_owner.text
    assert "value" in by_owner.json()

    # The owner needs no PIN at any value.
    big = adjust(client, world["owner"], world, "free_sample", [("wire", "400")])
    assert big.status_code == 201, big.text
    assert big.json()["value"] == "30000.00"

    book = client.get("/api/v1/stock-adjustments", headers=counter)
    assert book.status_code == 200
    assert "net_loss" not in book.json() and "value" not in book.json()["entries"][0]
    assert (
        client.get(
            f"/api/v1/stock-adjustments?location_id={world['loc']['S2']}", headers=counter
        ).status_code
        == 403
    )
    assert len(client.get("/api/v1/stock-adjustments", headers=counter2).json()["entries"]) == 0
    assert itc(client, counter).status_code == 403
    assert itc(client, accountant).status_code == 200  # the accountant files GSTR-3B


@pytest.mark.parametrize(
    ("reason", "lines", "code"),
    [
        ("weighbridge_gain", [("wire", "5", {"direction": "out"})], "WRONG_DIRECTION"),
        ("theft", [("wire", "5", {"direction": "in"})], "WRONG_DIRECTION"),
        ("count_correction", [("wire", "5")], "DIRECTION_REQUIRED"),
        ("breakage", [("opc", "101")], "INSUFFICIENT_STOCK"),
        ("breakage", [("opc", "1.5")], "UNIT_NOT_WHOLE"),
        ("breakage", [("opc", "1"), ("opc", "2")], "DUPLICATE_ITEM"),
    ],
)
def test_adjustment_validation(client, stocked, reason, lines, code):
    response = adjust(client, stocked["owner"], stocked, reason, lines)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == code


def test_gains_and_count_corrections(client, stocked):
    world = stocked
    gain = adjust(client, world["owner"], world, "weighbridge_gain", [("wire", "40")])
    assert gain.status_code == 201, gain.text
    assert gain.json()["value"] == "-3000.00"  # gained, at the average cost of ₹75
    assert stock_at(client, world, "wire", "S1") == "540.000"
    both = adjust(
        client,
        world["owner"],
        world,
        "count_correction",
        [("wire", "10", {"direction": "out"}), ("opc", "3", {"direction": "in"})],
    )
    assert both.status_code == 201, both.text
    assert both.json()["value"] == "-390.00"  # 10 kg x 75 out, 3 bags x 380 in

    book = client.get("/api/v1/stock-adjustments", headers=world["owner"]).json()
    assert book["net_loss"] == "-3390.00"
    totals = {r["reason"]: r["value"] for r in book["by_reason"]}
    assert totals == {"weighbridge_gain": "-3000.00", "count_correction": "-390.00"}
    # A gain is never ITC to reverse; the 10 kg short is (shortages default to reversed).
    report = itc(client, world["owner"]).json()
    assert [(r["reason"], r["itc"]) for r in report["rows"]] == [("count_correction", "135.00")]
    assert report["includes_shortages"] is True

    # The accountant decides; turning shortages off drops them from the list.
    settings = client.get("/api/v1/settings", headers=world["owner"]).json()
    changed = client.put(
        "/api/v1/settings", headers=world["owner"], json=settings | {"itc_reverse_shortages": False}
    )
    assert changed.status_code == 200, changed.text
    assert itc(client, world["owner"]).json()["rows"] == []


def test_a_posted_count_is_a_count_correction(client, stocked):
    world = stocked
    opened = client.post(
        "/api/v1/stock-counts",
        headers=world["owner"],
        json={"location_id": world["loc"]["S1"], "item_ids": [world["opc"]["id"]]},
    ).json()
    client.put(
        f"/api/v1/stock-counts/{opened['id']}/lines",
        headers=world["owner"],
        json={"lines": [{"item_id": world["opc"]["id"], "counted_qty": "95"}]},
    )
    posted = client.post(f"/api/v1/stock-counts/{opened['id']}/post", headers=world["owner"])
    assert posted.status_code == 200, posted.text
    report = itc(client, world["owner"]).json()
    assert [(r["document"], r["reason"], r["value"], r["itc"]) for r in report["rows"]] == [
        (f"Count {opened['id']}", "count_correction", "1900.00", "342.00")
    ]
    book = client.get("/api/v1/stock-adjustments", headers=world["owner"]).json()
    assert book["entries"] == [] and book["net_loss"] == "1900.00"  # counts are in the totals


def test_stock_lost_lowers_gross_profit(client, stocked):
    world = stocked
    before = client.get(f"/api/v1/reports/pnl?period={PERIOD}", headers=world["owner"]).json()
    assert before["stock_loss"] == "0.00"
    adjust(client, world["owner"], world, "breakage", [("opc", "2")])
    after = client.get(f"/api/v1/reports/pnl?period={PERIOD}", headers=world["owner"]).json()
    assert after["stock_loss"] == "760.00"
    assert float(after["gross_profit"]) == pytest.approx(float(before["gross_profit"]) - 760)
    assert float(after["contribution"]) == pytest.approx(float(before["contribution"]) - 760)


def test_numbers_and_guards_pass_the_integrity_check(client, stocked, seeded):
    world = stocked
    for reason, key in (("breakage", "opc"), ("theft", "wire")):
        assert adjust(client, world["owner"], world, reason, [(key, "1")]).status_code == 201
    assert verify.triggers_check(seeded).state == "ok"
    numbers = verify.numbering_check(seeded)
    assert numbers.state == "ok", numbers.detail
