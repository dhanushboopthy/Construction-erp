"""Milestone 11: weight checks (B14), attachments (B17) and supplier schemes (B15)."""

import io
from datetime import timedelta

import pytest

from app.core.clock import today_ist
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

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def purchase(
    client,
    world,
    quantity="10",
    received=None,
    note=None,
    bill_no="W-1",
    location="S1",
    mode=None,
    rate="55000",
    supplier=None,
):
    item = {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": quantity, "rate": rate}
    if received:
        item["received_quantity"] = received
    if note:
        item["weight_note"] = note
    payload = {
        "supplier_id": (supplier or world["supplier"])["id"],
        "location_id": world["loc"][location],
        "bill_no": bill_no,
        "bill_date": day(1),
        "lines": [item],
    }
    if mode:
        payload["mode"] = mode
    return client.post("/api/v1/purchases", headers=world["owner"], json=payload)


# ------------------------------------------------------------------ weight check (B14)


def test_a_short_delivery_over_the_limit_needs_a_note_on_a_purchase(client, world):
    # 10 ton billed, 9.9 ton on the weighbridge: 1.00% short, over the 0.50% limit.
    refused = purchase(client, world, received="9.9")
    assert refused.status_code == 409 and refused.json()["code"] == "WEIGHT_NOTE_REQUIRED"
    assert refused.json()["field"] == "lines[0].weight_note"
    preview = client.post(
        "/api/v1/purchases/preview",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "W-P",
            "bill_date": day(1),
            "lines": [
                {
                    "item_id": world["tmt"]["id"],
                    "unit": "ton",
                    "quantity": "10",
                    "received_quantity": "9.9",
                    "rate": "55000",
                }
            ],
        },
    ).json()["lines"][0]
    # 100 kg short at ₹55 a kg on the bill = ₹5,500.
    assert (
        preview["weight_variance_pct"],
        preview["weight_flagged"],
        preview["shortage_value"],
    ) == (
        "1.00",
        True,
        "5500.00",
    )
    saved = purchase(client, world, received="9.9", note="Slip says 9,900 kg; supplier agreed")
    assert saved.status_code == 201, saved.text
    row = saved.json()["lines"][0]
    assert row["weight_flagged"] is True and row["shortage_value"] == "5500.00"
    assert row["weight_note"].startswith("Slip says")


def test_a_small_difference_needs_no_note_and_staff_never_see_the_value(client, world, seeded):
    # 9.97 of 10 ton is 0.30% short: inside the limit.
    ok = purchase(client, world, received="9.97", bill_no="W-2")
    assert ok.status_code == 201 and ok.json()["lines"][0]["weight_flagged"] is False
    flagged = purchase(client, world, received="9.9", note="short", bill_no="W-3").json()
    counter = login(client, *COUNTER)
    text = client.get(f"/api/v1/purchases/{flagged['id']}", headers=counter).text
    assert '"weight_flagged":true' in text.replace(" ", "")
    assert "shortage_value" not in text and "unit_cost" not in text


def test_slip_weight_on_a_sale_is_checked_against_the_bill(client, world):
    # 1,000 kg billed, 980 kg on the slip: 2.00% off.
    lines = [line(world, "tmt", "1000", "kg", slip_weight="980")]
    preview = client.post(
        "/api/v1/invoices/preview", headers=world["owner"], json=body(world, lines)
    ).json()
    assert preview["lines"][0]["weight_flagged"] is True
    assert preview["lines"][0]["weight_variance_pct"] == "2.00"
    assert any("note" in p for p in preview["lines"][0]["problems"]) or preview["invoice_problems"]
    refused = post(client, world, body(world, lines))
    assert refused.status_code == 409 and refused.json()["code"] == "WEIGHT_NOTE_REQUIRED"
    lines[0]["weight_note"] = "Customer's truck, slip weight"
    saved = post(client, world, body(world, lines))
    assert saved.status_code == 201, saved.text
    got = saved.json()["lines"][0]
    assert (got["slip_weight"], got["weight_flagged"], got["weight_note"]) == (
        "980.000",
        True,
        "Customer's truck, slip weight",
    )
    # A slip within the limit passes with no note, and no slip means no check.
    close = post(client, world, body(world, [line(world, "tmt", "1000", "kg", slip_weight="998")]))
    assert close.status_code == 201 and close.json()["lines"][0]["weight_flagged"] is False
    plain = post(client, world, body(world, [line(world, "tmt", "10", "kg")]))
    assert plain.json()["lines"][0]["slip_weight"] is None


# ------------------------------------------------------------------ attachments (B17)


def upload(client, headers, ref_type, ref_id, data=PDF, name="slip.pdf", kind="weighbridge"):
    return client.post(
        "/api/v1/attachments",
        headers=headers,
        data={"ref_type": ref_type, "ref_id": str(ref_id), "kind": kind, "note": "slip"},
        files={"file": (name, io.BytesIO(data), "application/octet-stream")},
    )


def test_slips_are_stored_by_what_they_really_are_and_served_back(client, world):
    bought = purchase(client, world).json()
    made = upload(client, world["owner"], "purchase", bought["id"], name="../../evil name.pdf")
    assert made.status_code == 201, made.text
    meta = made.json()
    assert meta["content_type"] == "application/pdf" and meta["size_bytes"] == len(PDF)
    assert "/" not in meta["file_name"] and ".." not in meta["file_name"]
    served = client.get(f"/api/v1/attachments/{meta['id']}/file", headers=world["owner"])
    assert served.status_code == 200 and served.content == PDF
    assert served.headers["content-type"] == "application/pdf"
    assert served.headers["x-content-type-options"] == "nosniff"
    # The type comes from the bytes, whatever name or type the client claimed.
    png = upload(
        client, world["owner"], "purchase", bought["id"], data=PNG, name="notes.pdf"
    ).json()
    assert png["content_type"] == "image/png"
    listed = client.get(
        f"/api/v1/attachments?ref_type=purchase&ref_id={bought['id']}", headers=world["owner"]
    )
    assert [a["id"] for a in listed.json()] == [meta["id"], png["id"]]


def test_unsafe_empty_and_huge_files_are_refused(client, world, monkeypatch):
    bought = purchase(client, world).json()
    owner = world["owner"]
    script = upload(
        client, owner, "purchase", bought["id"], data=b"<script>alert(1)</script>", name="x.pdf"
    )
    assert script.status_code == 400 and script.json()["code"] == "FILE_TYPE_NOT_ALLOWED"
    assert upload(client, owner, "purchase", bought["id"], data=b"").json()["code"] == "FILE_EMPTY"
    assert upload(client, owner, "purchase", 99999).status_code == 404
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "max_upload_mb", 0)
    big = upload(client, owner, "purchase", bought["id"], data=PDF)
    assert big.status_code == 413 and big.json()["code"] == "FILE_TOO_LARGE"


def test_attachment_roles_and_scope(client, world, seeded):
    inv = post(client, world, body(world, [line(world, "cement", "1")])).json()
    owner, counter = world["owner"], login(client, *COUNTER)
    other_shop, accountant = login(client, *COUNTER2), login(client, *ACCOUNTANT)
    mine = upload(
        client, counter, "sales_invoice", inv["id"], data=JPEG, name="delivery.jpg", kind="delivery"
    )
    assert mine.status_code == 201, mine.text
    file_id = mine.json()["id"]
    assert upload(client, other_shop, "sales_invoice", inv["id"]).status_code == 404
    assert upload(client, accountant, "sales_invoice", inv["id"]).status_code == 403
    assert client.get(f"/api/v1/attachments/{file_id}/file", headers=other_shop).status_code == 404
    assert client.get(f"/api/v1/attachments/{file_id}/file", headers=accountant).status_code == 200
    assert (
        client.get(
            f"/api/v1/attachments?ref_type=sales_invoice&ref_id={inv['id']}", headers=other_shop
        ).status_code
        == 404
    )
    assert client.get("/api/v1/attachments/99999/file", headers=owner).status_code == 404

    # Trip papers are the owner's; the accountant may read them, counter staff may not.
    car = client.post(
        "/api/v1/vehicles", headers=owner, json={"number": "TN09AB1234", "owner_name": "Murugan"}
    ).json()
    trip = client.post(
        "/api/v1/trips",
        headers=owner,
        json={
            "vehicle_id": car["id"],
            "location_id": world["loc"]["S1"],
            "from_place": "Mill",
            "to_place": "Site",
            "freight_amount": "0",
        },
    ).json()
    assert upload(client, counter, "trip", trip["id"]).status_code == 403
    assert upload(client, accountant, "trip", trip["id"]).status_code == 403
    proof = upload(client, owner, "trip", trip["id"], data=PNG, name="proof.png", kind="delivery")
    assert proof.status_code == 201
    assert (
        client.get(f"/api/v1/attachments/{proof.json()['id']}/file", headers=accountant).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/attachments/{proof.json()['id']}/file", headers=counter).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/attachments?ref_type=trip&ref_id={trip['id']}", headers=counter
        ).status_code
        == 403
    )


def test_a_document_holds_up_to_twenty_files_and_a_tampered_file_is_caught(client, world, seeded):
    bought = purchase(client, world).json()
    for _ in range(20):
        assert upload(client, world["owner"], "purchase", bought["id"]).status_code == 201
    over = upload(client, world["owner"], "purchase", bought["id"])
    assert over.status_code == 409 and over.json()["code"] == "TOO_MANY_FILES"
    first = client.get(
        f"/api/v1/attachments?ref_type=purchase&ref_id={bought['id']}", headers=world["owner"]
    ).json()[0]
    from sqlalchemy import select

    from app.models.documents import Attachment
    from app.services.storage import get_storage

    row_key = seeded.execute(
        select(Attachment.storage_key).where(Attachment.id == first["id"])
    ).scalar_one()
    get_storage().put(row_key, PDF + b"tampered")
    bad = client.get(f"/api/v1/attachments/{first['id']}/file", headers=world["owner"])
    assert bad.status_code == 400 and bad.json()["code"] == "FILE_CORRUPT"
    get_storage().put(row_key, PDF)
    assert (
        client.get(f"/api/v1/attachments/{first['id']}/file", headers=world["owner"]).status_code
        == 200
    )
    from app.services.storage import LocalStorage, StorageError

    with pytest.raises(StorageError):
        get_storage().get("attachments/1/missing.pdf")
    with pytest.raises(StorageError):
        LocalStorage(get_storage().root).put("../escape.pdf", b"x")  # type: ignore[attr-defined]


# ------------------------------------------------------------------ supplier schemes (B15)


def make_scheme(client, world, **extra):
    payload = {
        "party_id": world["supplier"]["id"],
        "name": "H2 volume rebate",
        "item_id": world["tmt"]["id"],
        "target_qty": "20000",
        "period_start": day(10),
        "period_end": (today_ist() + timedelta(days=60)).isoformat(),
        "rebate_rule": "percent",
        "rebate_value": "2",
    } | extra
    return client.post("/api/v1/schemes", headers=world["owner"], json=payload)


def test_scheme_progress_alert_and_booking_the_rebate(client, world):
    # Target 20,000 kg. 10 ton bought = 50%; another 7 ton = 85% -> alert; a further 4 ton = 110%.
    made = make_scheme(client, world)
    assert made.status_code == 201, made.text
    scheme = made.json()
    assert (scheme["achieved"], scheme["pct"], scheme["alert"], scheme["unit"]) == (
        "0.000",
        "0.00",
        False,
        "kg",
    )
    purchase(client, world, quantity="10", bill_no="S-1")
    half = client.get("/api/v1/schemes", headers=world["owner"]).json()[0]
    assert (half["achieved"], half["pct"], half["alert"], half["reached"]) == (
        "10000.000",
        "50.00",
        False,
        False,
    )
    purchase(client, world, quantity="7", bill_no="S-2")
    near = client.get("/api/v1/schemes?alerts_only=true", headers=world["owner"]).json()
    assert [(s["pct"], s["remaining"]) for s in near] == [("85.00", "3000.000")]
    early = client.post(f"/api/v1/schemes/{scheme['id']}/book-rebate", headers=world["owner"])
    assert early.status_code == 409 and early.json()["code"] == "TARGET_NOT_MET"

    purchase(client, world, quantity="4", bill_no="S-3")
    # 21 ton at 55,000 = ₹11,55,000 goods; 2% = ₹23,100.
    done = client.get("/api/v1/schemes", headers=world["owner"]).json()[0]
    assert (done["reached"], done["alert"], done["projected_rebate"]) == (True, False, "23100.00")
    owed_before = client.get(
        f"/api/v1/parties/{world['supplier']['id']}/statement", headers=world["owner"]
    ).json()["payable"]["balance"]
    booked = client.post(f"/api/v1/schemes/{scheme['id']}/book-rebate", headers=world["owner"])
    assert booked.status_code == 200 and booked.json()["rebate_amount"] == "23100.00"
    owed_after = client.get(
        f"/api/v1/parties/{world['supplier']['id']}/statement", headers=world["owner"]
    ).json()["payable"]["balance"]
    assert float(owed_before) - float(owed_after) == 23100.0
    again = client.post(f"/api/v1/schemes/{scheme['id']}/book-rebate", headers=world["owner"])
    assert again.status_code == 409 and again.json()["code"] == "REBATE_BOOKED"


def test_returns_lower_progress_and_other_periods_and_suppliers_do_not_count(client, world):
    scheme = make_scheme(client, world).json()
    bought = purchase(client, world, quantity="10", bill_no="R-1").json()
    other = client.post(
        "/api/v1/parties",
        headers=world["owner"],
        json={"name": "Other mill", "type": "supplier", "state_code": "33"},
    ).json()
    purchase(client, world, quantity="9", bill_no="R-2", supplier=other)
    old = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "R-OLD",
            "bill_date": day(30),
            "lines": [
                {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": "8", "rate": "55000"}
            ],
        },
    )
    assert old.status_code == 201
    row = client.get("/api/v1/schemes", headers=world["owner"]).json()[0]
    assert row["achieved"] == "10000.000"
    client.post(
        "/api/v1/debit-notes",
        headers=world["owner"],
        json={
            "purchase_id": bought["id"],
            "reason": "Rusted",
            "lines": [{"line_id": bought["lines"][0]["id"], "quantity": "2"}],
        },
    )
    after = client.get("/api/v1/schemes", headers=world["owner"]).json()[0]
    assert after["achieved"] == "8000.000" and after["id"] == scheme["id"]


def test_category_and_per_unit_schemes_and_validation(client, world):
    category = make_scheme(
        client,
        world,
        item_id=None,
        category="tmt",
        unit="kg",
        rebate_rule="per_unit",
        rebate_value="0.5",
        target_qty="5000",
    )
    assert category.status_code == 201, category.text
    purchase(client, world, quantity="6", bill_no="C-1")
    row = client.get(
        f"/api/v1/schemes?party_id={world['supplier']['id']}", headers=world["owner"]
    ).json()[0]
    # ₹0.50 a kg on 6,000 kg.
    assert (row["reached"], row["projected_rebate"], row["item_name"]) == (True, "3000.00", None)
    assert (
        make_scheme(client, world, category="tmt").status_code == 422
    )  # item and category together
    assert make_scheme(client, world, item_id=None).status_code == 422  # neither
    assert make_scheme(client, world, item_id=None, category="tmt").status_code == 422  # no unit
    assert make_scheme(client, world, period_end=day(20)).status_code == 422
    assert make_scheme(client, world, rebate_value="150").status_code == 422
    assert make_scheme(client, world, party_id=world["ravi"]["id"]).status_code == 404  # a customer
    assert make_scheme(client, world, item_id=99999).status_code == 404
    flat = make_scheme(
        client, world, rebate_rule="flat", rebate_value="0", target_qty="1000", name="Zero flat"
    )
    assert flat.status_code == 201
    purchase(client, world, quantity="2", bill_no="C-2")
    zero = client.post(f"/api/v1/schemes/{flat.json()['id']}/book-rebate", headers=world["owner"])
    assert zero.json()["code"] == "REBATE_ZERO"
    off = client.patch(
        f"/api/v1/schemes/{category.json()['id']}",
        headers=world["owner"],
        json={"is_active": False, "name": "Closed scheme"},
    )
    assert off.json()["is_active"] is False and off.json()["alert"] is False
    assert client.patch("/api/v1/schemes/99999", headers=world["owner"], json={}).status_code == 404


def test_scheme_roles(client, world, seeded):
    scheme = make_scheme(client, world).json()
    counter, accountant = login(client, *COUNTER), login(client, *ACCOUNTANT)
    for who in (counter, accountant):
        assert client.post("/api/v1/schemes", headers=who, json={}).status_code == 403
        assert (
            client.patch(f"/api/v1/schemes/{scheme['id']}", headers=who, json={}).status_code == 403
        )
        assert (
            client.post(f"/api/v1/schemes/{scheme['id']}/book-rebate", headers=who).status_code
            == 403
        )
    assert client.get("/api/v1/schemes", headers=counter).status_code == 403
    assert client.get("/api/v1/schemes", headers=accountant).status_code == 200
