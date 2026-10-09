"""Milestone 10: e-way bills and e-invoices through the (fake) GSP, with roles and failures."""

from datetime import timedelta

import pytest

from app.core.clock import today_ist
from app.domain.gst import gstin_checksum
from app.models.compliance import EwayBill
from app.services import gsp
from app.services.gsp.base import GspError
from tests.conftest import login
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

SHOP_GSTIN = "33ABCDE1234F1Z" + gstin_checksum("33ABCDE1234F1Z")
TRIP = {"distance_km": 120, "from_pincode": "600001", "to_pincode": "600040"}


@pytest.fixture(autouse=True)
def clean_fake():
    fake = gsp.get_client()
    fake.failures.clear()  # type: ignore[attr-defined]
    yield fake
    fake.failures.clear()  # type: ignore[attr-defined]


@pytest.fixture
def shop(client, world):
    """Shop details with a GSTIN, as the owner would enter them in Settings."""
    current = client.get("/api/v1/settings", headers=world["owner"]).json()
    current.pop("id")
    current["gstin"] = SHOP_GSTIN
    assert client.put("/api/v1/settings", headers=world["owner"], json=current).status_code == 200
    return current


def from_godown(world):
    return {"source": "godown", "source_location_id": world["loc"]["G1"]}


def sale(
    client,
    world,
    quantity="2.5",
    party="ravi",
    site="Chennai site",
    unit="ton",
    item="tmt",
    **extra,
):
    response = post(
        client,
        world,
        body(world, [line(world, item, quantity, unit, **extra)], party=party, site=site),
    )
    assert response.status_code == 201, response.text
    return response.json()


def eway(client, headers, invoice, **extra):
    return client.post(
        f"/api/v1/invoices/{invoice['id']}/eway-bill", headers=headers, json=TRIP | extra
    )


def test_generating_an_eway_bill_saves_it_and_prints_it_on_the_bill(client, world, shop):
    inv = sale(client, world)
    status = client.get(f"/api/v1/invoices/{inv['id']}/eway-bill", headers=world["owner"]).json()
    assert (
        status["required"] is True and status["live"] is None and status["threshold"] == "100000.00"
    )

    made = eway(client, world["owner"], inv, vehicle_no="tn 09 ab 1234")
    assert made.status_code == 201, made.text
    bill = made.json()
    assert len(bill["number"]) == 12 and bill["status"] == "generated" and bill["source"] == "gsp"
    assert bill["vehicle_no"] == "TN09AB1234" and bill["can_cancel"] is True
    # 120 km is one day: valid to midnight of the day after generation.
    assert bill["valid_until"] == (today_ist() + timedelta(days=1)).isoformat()
    again = eway(client, world["owner"], inv)
    assert again.status_code == 409 and again.json()["code"] == "EWAY_EXISTS"
    live = client.get(f"/api/v1/invoices/{inv['id']}/eway-bill", headers=world["owner"]).json()[
        "live"
    ]
    assert live["number"] == bill["number"]
    pdf = client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=world["owner"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_input_checks_and_missing_gstin(client, world):
    inv = sale(client, world)
    no_gstin = eway(client, world["owner"], inv)
    assert no_gstin.status_code == 409 and no_gstin.json()["code"] == "SELLER_GSTIN_MISSING"
    bad_pin = eway(client, world["owner"], inv, to_pincode="060040")
    assert bad_pin.status_code == 422
    bad_distance = eway(client, world["owner"], inv, distance_km=0)
    assert bad_distance.status_code == 422
    assert client.get("/api/v1/invoices/99999/eway-bill", headers=world["owner"]).status_code == 404


def test_vehicle_rules_and_part_b_update(client, world, shop):
    inv = sale(client, world)
    bad = eway(client, world["owner"], inv, vehicle_no="1234")
    assert bad.status_code == 409 and bad.json()["code"] == "VEHICLE_INVALID"
    assert eway(client, world["owner"], inv).status_code == 201  # Part A only
    update = client.post(
        f"/api/v1/invoices/{inv['id']}/eway-bill/vehicle",
        headers=world["owner"],
        json={"vehicle_no": "TN 10 CD 5678", "reason": "first time", "from_place": "Chennai"},
    )
    assert update.status_code == 200 and update.json()["vehicle_no"] == "TN10CD5678"
    wrong = client.post(
        f"/api/v1/invoices/{inv['id']}/eway-bill/vehicle",
        headers=world["owner"],
        json={"vehicle_no": "oops", "reason": "first time", "from_place": "Chennai"},
    )
    assert wrong.json()["code"] == "VEHICLE_INVALID"
    other = sale(client, world, quantity="1")
    none_yet = client.post(
        f"/api/v1/invoices/{other['id']}/eway-bill/vehicle",
        headers=world["owner"],
        json={"vehicle_no": "TN10CD5678", "reason": "first time", "from_place": "Chennai"},
    )
    assert none_yet.status_code == 404


def test_a_gsp_failure_saves_nothing_and_a_retry_works(client, world, shop, clean_fake):
    inv = sale(client, world)
    clean_fake.failures.append(GspError("Slow", code="GSP_TIMEOUT", retryable=True))
    failed = eway(client, world["owner"], inv)
    assert failed.status_code == 502 and failed.json()["code"] == "GSP_TIMEOUT"
    assert "Try again" in failed.json()["message"]
    status = client.get(f"/api/v1/invoices/{inv['id']}/eway-bill", headers=world["owner"]).json()
    assert status["live"] is None and status["history"] == []
    assert eway(client, world["owner"], inv).status_code == 201


def test_cancel_within_24_hours_then_make_a_new_one(client, world, shop, seeded):
    inv = sale(client, world)
    first = eway(client, world["owner"], inv).json()
    counter = login(client, *COUNTER)
    reason = {"reason": "wrong consignee"}
    cancel_url = f"/api/v1/invoices/{inv['id']}/eway-bill/cancel"
    assert client.post(cancel_url, headers=counter, json=reason).status_code == 403  # owner only
    done = client.post(cancel_url, headers=world["owner"], json=reason)
    assert done.status_code == 200 and done.json()["status"] == "cancelled"
    second = eway(client, world["owner"], inv)
    assert second.status_code == 201 and second.json()["number"] != first["number"]
    history = client.get(f"/api/v1/invoices/{inv['id']}/eway-bill", headers=world["owner"]).json()[
        "history"
    ]
    assert [h["status"] for h in history] == ["generated", "cancelled"]

    # Past 24 hours the portal refuses a cancel, so we do too.
    row = seeded.query(EwayBill).filter_by(number=second.json()["number"]).one()
    row.generated_at = row.generated_at - timedelta(hours=25)
    seeded.flush()
    late = client.post(cancel_url, headers=world["owner"], json=reason)
    assert late.status_code == 409 and late.json()["code"] == "EWAY_CANCEL_WINDOW_CLOSED"
    nothing = client.post(
        f"/api/v1/invoices/{sale(client, world, quantity='1')['id']}/eway-bill/cancel",
        headers=world["owner"],
        json=reason,
    )
    assert nothing.status_code == 404


def test_manual_fallback_records_a_portal_number(client, world, shop):
    inv = sale(client, world)
    bad = client.post(
        f"/api/v1/invoices/{inv['id']}/eway-bill/manual",
        headers=world["owner"],
        json={"number": "123"},
    )
    assert bad.status_code == 422
    made = client.post(
        f"/api/v1/invoices/{inv['id']}/eway-bill/manual",
        headers=world["owner"],
        json={"number": "391012345678", "vehicle_no": "TN09AB1234"},
    )
    assert made.status_code == 201 and made.json()["source"] == "manual"
    twice = client.post(
        f"/api/v1/invoices/{inv['id']}/eway-bill/manual",
        headers=world["owner"],
        json={"number": "391012345679"},
    )
    assert twice.json()["code"] == "EWAY_EXISTS"
    other = sale(client, world, quantity="1")
    reused = client.post(
        f"/api/v1/invoices/{other['id']}/eway-bill/manual",
        headers=world["owner"],
        json={"number": "391012345678"},
    )
    assert reused.json()["code"] == "EWAY_NUMBER_USED"
    # A bill made by hand is cancelled by hand too: we only record it.
    gone = client.post(
        f"/api/v1/invoices/{inv['id']}/eway-bill/cancel",
        headers=world["owner"],
        json={"reason": "duplicate"},
    )
    assert gone.status_code == 200 and gone.json()["status"] == "cancelled"


def test_eway_roles_and_shop_scope(client, world, shop, seeded):
    inv = sale(client, world)
    accountant = login(client, *ACCOUNTANT)
    other_shop = login(client, *COUNTER2)
    counter = login(client, *COUNTER)
    assert eway(client, accountant, inv).status_code == 403
    assert eway(client, other_shop, inv).status_code == 404
    url = f"/api/v1/invoices/{inv['id']}/eway-bill"
    assert client.get(url, headers=accountant).status_code == 200
    assert client.get(url, headers=other_shop).status_code == 404
    assert (
        client.post(
            url + "/manual", headers=accountant, json={"number": "391012345678"}
        ).status_code
        == 403
    )
    vehicle = {"vehicle_no": "TN09AB1234", "reason": "first time", "from_place": "Chennai"}
    assert client.post(url + "/vehicle", headers=accountant, json=vehicle).status_code == 403
    assert (
        client.post(url + "/cancel", headers=accountant, json={"reason": "none"}).status_code == 403
    )
    assert eway(client, counter, inv).status_code == 201
    assert client.get("/api/v1/eway-bills/pending", headers=other_shop).json() == []


def test_pending_list_and_a_batch_of_fifty(client, world, shop):
    # 50 deliveries of 2 ton TMT each over the threshold; the shop has 5,000 kg + godown stock.
    invoices = []
    for _ in range(50):
        response = post(
            client,
            world,
            body(
                world,
                [
                    line(
                        world,
                        "tmt",
                        "100",
                        "kg",
                        source="godown",
                        source_location_id=world["loc"]["G1"],
                    )
                ],
                site="Chennai site",
            ),
        )
        assert response.status_code == 201, response.text
        invoices.append(response.json())
    # 100 kg is under the threshold: nothing is waiting yet.
    assert client.get("/api/v1/eway-bills/pending", headers=world["owner"]).json() == []
    big = [sale(client, world, quantity="2", **from_godown(world)) for _ in range(3)]
    pending = client.get("/api/v1/eway-bills/pending", headers=world["owner"]).json()
    assert {p["invoice_id"] for p in pending} == {b["id"] for b in big}
    assert eway(client, world["owner"], big[0]).status_code == 201
    left = client.get("/api/v1/eway-bills/pending", headers=world["owner"]).json()
    assert {p["invoice_id"] for p in left} == {b["id"] for b in big[1:]}

    items = [{"invoice_id": i["id"]} | TRIP for i in invoices] + [{"invoice_id": 0} | TRIP]
    result = client.post("/api/v1/eway-bills/batch", headers=world["owner"], json={"items": items})
    assert result.status_code == 200, result.text
    out = result.json()
    assert out["succeeded"] == 50 and out["failed"] == 1
    assert out["results"][-1]["ok"] is False and out["results"][-1]["code"] == "NOT_FOUND"
    numbers = [r["number"] for r in out["results"] if r["ok"]]
    assert len(set(numbers)) == 50 and all(len(n) == 12 for n in numbers)


def test_einvoice_for_b2b_bills_when_switched_on(client, world, shop, seeded):
    inv = sale(client, world)
    walkin = sale(client, world, party="walkin", site=None, quantity="1")
    url = f"/api/v1/invoices/{inv['id']}/einvoice"
    off = client.get(url, headers=world["owner"]).json()
    assert off["enabled"] is False and off["required"] is False
    refused = client.post(url, headers=world["owner"], json=TRIP)
    assert refused.status_code == 409 and refused.json()["code"] == "EINVOICE_NOT_REQUIRED"

    current = client.get("/api/v1/settings", headers=world["owner"]).json()
    current.pop("id")
    client.put(
        "/api/v1/settings", headers=world["owner"], json=current | {"einvoice_enabled": True}
    )
    on = client.get(url, headers=world["owner"]).json()
    assert on["required"] is True and on["einvoice"] is None
    b2c = client.post(
        f"/api/v1/invoices/{walkin['id']}/einvoice", headers=world["owner"], json=TRIP
    )
    assert b2c.json()["code"] == "EINVOICE_NOT_REQUIRED"

    made = client.post(url, headers=world["owner"], json=TRIP)
    assert made.status_code == 201, made.text
    irn = made.json()
    assert len(irn["irn"]) == 64 and irn["status"] == "generated" and irn["can_cancel"] is True
    assert client.post(url, headers=world["owner"], json=TRIP).json()["code"] == "EINVOICE_EXISTS"
    assert "signed_qr" not in made.text
    pdf = client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=world["owner"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    counter = login(client, *COUNTER)
    accountant = login(client, *ACCOUNTANT)
    assert (
        client.post(url + "/cancel", headers=counter, json={"reason": "wrong GSTIN"}).status_code
        == 403
    )
    assert client.post(url, headers=accountant, json=TRIP).status_code == 403
    assert client.get(url, headers=accountant).status_code == 200
    gone = client.post(url + "/cancel", headers=world["owner"], json={"reason": "wrong GSTIN"})
    assert gone.status_code == 200 and gone.json()["status"] == "cancelled"
    assert (
        client.post(url + "/cancel", headers=world["owner"], json={"reason": "again"}).status_code
        == 404
    )


def test_einvoice_cancel_window_and_gsp_failure(client, world, shop, seeded, clean_fake):
    from app.models.compliance import EInvoice

    current = client.get("/api/v1/settings", headers=world["owner"]).json()
    current.pop("id")
    client.put(
        "/api/v1/settings", headers=world["owner"], json=current | {"einvoice_enabled": True}
    )
    inv = sale(client, world)
    url = f"/api/v1/invoices/{inv['id']}/einvoice"
    clean_fake.failures.append(GspError("Portal down", code="GSP_DOWN", retryable=True))
    assert client.post(url, headers=world["owner"], json=TRIP).status_code == 502
    assert client.post(url, headers=world["owner"], json=TRIP).status_code == 201
    row = seeded.query(EInvoice).one()
    row.ack_date = row.ack_date - timedelta(hours=30)
    seeded.flush()
    late = client.post(url + "/cancel", headers=world["owner"], json={"reason": "late"})
    assert late.status_code == 409 and late.json()["code"] == "EINVOICE_CANCEL_WINDOW_CLOSED"
