"""Milestone 2: items, units, import, parties and sites."""

import io

import pytest
from openpyxl import Workbook

from app.services.item_import import COLUMNS
from tests.conftest import login

pytestmark = pytest.mark.integration

OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")
ACCOUNTANT = ("accounts", "accounts-pass-123")

TMT = {
    "name": "TMT bar 12 mm Fe500D",
    "category": "tmt",
    "brand": "Kamachi",
    "hsn": "72142090",
    "gst_rate": "18",
    "base_unit": "kg",
    "size": "12 mm",
    "weight_per_piece_kg": "10.656",
    "min_margin": "1.2500",
    "units": [{"unit": "ton", "factor_to_base": "1000"}],
}
CEMENT = {
    "name": "Cement 50 kg PPC",
    "category": "cement",
    "brand": "Dalmia",
    "hsn": "25232930",
    "gst_rate": "28",
    "base_unit": "bag",
    "base_whole_only": True,
    "units": [{"unit": "ton", "factor_to_base": "20"}],
}


def sheet(rows: list[list[object]], header: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Items"
    ws.append(header or COLUMNS)
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def upload(client, headers, content: bytes, dry_run: bool):
    return client.post(
        f"/api/v1/items/import?dry_run={'true' if dry_run else 'false'}",
        headers=headers,
        files={"file": ("items.xlsx", content, "application/octet-stream")},
    )


def make_item(client, headers, body=TMT):
    response = client.post("/api/v1/items", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------ roles


def test_item_write_routes_are_owner_only(client):
    for who in (COUNTER, ACCOUNTANT):
        headers = login(client, *who)
        assert client.post("/api/v1/items", headers=headers, json=TMT).status_code == 403
        assert client.patch("/api/v1/items/1", headers=headers, json={}).status_code == 403
        assert client.get("/api/v1/items/import/template", headers=headers).status_code == 403
        assert upload(client, headers, sheet([]), True).status_code == 403
    assert client.get("/api/v1/items").status_code == 401


def test_counter_never_receives_margin_fields(client):
    owner = login(client, *OWNER)
    item = make_item(client, owner)
    assert item["min_margin"] == "1.2500"

    for who in (COUNTER, ACCOUNTANT):
        headers = login(client, *who)
        listing = client.get("/api/v1/items", headers=headers).json()
        one = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
        assert listing["total"] == 1
        assert "min_margin" not in listing["items"][0]
        assert "min_margin" not in one and one["name"] == TMT["name"]
        assert "1.25" not in client.get(f"/api/v1/items/{item['id']}", headers=headers).text

    owner_view = client.get(f"/api/v1/items/{item['id']}", headers=owner).json()
    assert owner_view["min_margin"] == "1.2500"


def test_party_routes_by_role(client):
    body = {"name": "Ravi Builders", "type": "customer", "state_code": "33"}
    accountant = login(client, *ACCOUNTANT)
    assert client.post("/api/v1/parties", headers=accountant, json=body).status_code == 403
    assert client.patch("/api/v1/parties/1", headers=accountant, json={}).status_code == 403
    assert client.post("/api/v1/parties/1/sites", headers=accountant, json={}).status_code == 403
    assert client.patch("/api/v1/sites/1", headers=accountant, json={}).status_code == 403
    assert client.get("/api/v1/parties", headers=accountant).status_code == 200
    assert client.get("/api/v1/parties").status_code == 401


def test_counter_cannot_grant_credit_but_owner_can(client):
    counter = login(client, *COUNTER)
    body = {"name": "Ravi Builders", "type": "customer", "state_code": "33"}
    party = client.post("/api/v1/parties", headers=counter, json=body)
    assert party.status_code == 201 and party.json()["credit_allowed"] is False

    denied = client.patch(
        f"/api/v1/parties/{party.json()['id']}", headers=counter, json={"credit_allowed": True}
    )
    assert denied.status_code == 403
    denied = client.post(
        "/api/v1/parties",
        headers=counter,
        json=body | {"name": "Other", "credit_limit": "5000"},
    )
    assert denied.status_code == 403

    owner = login(client, *OWNER)
    granted = client.patch(
        f"/api/v1/parties/{party.json()['id']}",
        headers=owner,
        json={"credit_allowed": True, "credit_limit": "15000.00", "credit_days": 10},
    )
    assert granted.status_code == 200
    assert (granted.json()["credit_limit"], granted.json()["credit_days"]) == ("15000.00", 10)


# ------------------------------------------------------------------ items and units


def test_item_crud_units_and_duplicates(client):
    headers = login(client, *OWNER)
    item = make_item(client, headers)
    assert [u["unit"] for u in item["units"]] == ["ton"]

    dup = client.post("/api/v1/items", headers=headers, json=TMT | {"name": TMT["name"].upper()})
    assert dup.status_code == 409 and dup.json()["code"] == "ITEM_NAME_TAKEN"

    bad_hsn = client.post("/api/v1/items", headers=headers, json=TMT | {"name": "x", "hsn": "12"})
    assert bad_hsn.status_code == 422 and bad_hsn.json()["field"] == "hsn"
    listed_base = client.post(
        "/api/v1/items",
        headers=headers,
        json=TMT | {"name": "y", "units": [{"unit": "kg", "factor_to_base": "1"}]},
    )
    assert listed_base.status_code == 422
    twice = client.post(
        "/api/v1/items",
        headers=headers,
        json=TMT | {"name": "z", "units": [TMT["units"][0], TMT["units"][0]]},
    )
    assert twice.status_code == 422

    updated = client.patch(
        f"/api/v1/items/{item['id']}",
        headers=headers,
        json={"gst_rate": "12", "units": [{"unit": "bundle", "factor_to_base": "2500"}]},
    )
    assert updated.status_code == 200
    assert updated.json()["gst_rate"] == "12.00"
    assert [u["unit"] for u in updated.json()["units"]] == ["bundle"]

    clash = client.patch(
        f"/api/v1/items/{item['id']}",
        headers=headers,
        json={"units": [{"unit": "kg", "factor_to_base": "1"}]},
    )
    assert clash.status_code == 409 and clash.json()["code"] == "BASE_UNIT_LISTED"
    other = make_item(client, headers, CEMENT)
    rename = client.patch(
        f"/api/v1/items/{other['id']}", headers=headers, json={"name": TMT["name"]}
    )
    assert rename.status_code == 409
    assert client.get("/api/v1/items/99999", headers=headers).status_code == 404

    off = client.patch(f"/api/v1/items/{other['id']}", headers=headers, json={"is_active": False})
    assert off.status_code == 200
    assert client.get("/api/v1/items", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/items?include_inactive=true", headers=headers).json()["total"] == 2
    found = client.get("/api/v1/items?q=kama&category=tmt", headers=headers).json()
    assert [i["name"] for i in found["items"]] == [TMT["name"]]


def test_bag_ton_and_piece_conversions(client):
    headers = login(client, *COUNTER)
    owner = login(client, *OWNER)
    cement = make_item(client, owner, CEMENT)
    tmt = make_item(client, owner, TMT)

    def convert(item_id, qty, a, b):
        return client.get(
            f"/api/v1/items/{item_id}/convert",
            headers=headers,
            params={"quantity": qty, "from_unit": a, "to_unit": b},
        )

    # Cement: 1 ton = 20 bags. 30 bags = 1.5 ton; 1.5 ton = 30 bags.
    assert convert(cement["id"], "30", "bag", "ton").json()["result"] == "1.500"
    assert convert(cement["id"], "1.5", "ton", "bag").json()["result"] == "30.000"
    # 1.51 ton would be 30.2 bags: bags are whole numbers.
    bad = convert(cement["id"], "1.51", "ton", "bag")
    assert bad.status_code == 409 and bad.json()["code"] == "UNIT_NOT_WHOLE"
    # TMT: 2.5 ton = 2,500 kg; 25 pieces at 10.656 kg = 266.400 kg (G7, automatic "piece").
    assert convert(tmt["id"], "2.5", "ton", "kg").json()["result"] == "2500.000"
    assert convert(tmt["id"], "25", "piece", "kg").json()["result"] == "266.400"
    assert convert(tmt["id"], "266.4", "kg", "piece").json()["result"] == "25.000"
    unknown = convert(tmt["id"], "1", "bag", "kg")
    assert unknown.status_code == 409 and unknown.json()["code"] == "UNKNOWN_UNIT"
    assert convert(tmt["id"], "1", "kg", "yard").json()["field"] == "to_unit"


# ------------------------------------------------------------------ Excel import


def row(name, category="tmt", hsn="72142090", gst="18", unit="kg", **extra):
    """One sheet row in COLUMNS order; `extra` fills optional columns by name."""
    cells = {
        "name": name,
        "category": category,
        "hsn": hsn,
        "gst_rate": gst,
        "base_unit": unit,
        "base_whole_only": "no",
    } | extra
    return [cells.get(column) for column in COLUMNS]


def fifty_rows():
    rows = [
        row(
            f"TMT bar {n} mm Fe500D",
            brand="Kamachi",
            size=f"{n} mm",
            grade="Fe500D",
            min_margin="1.25",
            units="ton:1000",
        )
        for n in range(8, 33)  # 25 TMT sizes
    ]
    rows += [
        row(
            f"MS round pipe {n} mm",
            "pipe",
            "73064000",
            brand="Tata",
            size=f"{n} mm",
            min_margin="1",
            units="ton:1000",
        )
        for n in (15, 20, 25, 32, 40, 50, 65, 80, 100, 125)  # 10 pipes
    ]
    rows += [
        row(
            f"Cement 50 kg {brand}",
            "cement",
            "25232930",
            "28",
            "bag",
            brand=brand,
            base_whole_only="yes",
            units="ton:20",
        )
        for brand in ("Dalmia", "UltraTech", "Ramco", "Chettinad", "ACC")  # 5 cement
    ]
    rows.append(row("Binding wire 20 g", "wire", "72171000", size="20 g"))
    rows += [
        row(f"MS angle {size}", "angle", "72166900", size=size)
        for size in ("25x25x3", "40x40x5", "50x50x6", "65x65x6", "75x75x6", "100x100x8")
    ]
    rows += [
        row(f"MS channel {size}", "channel", "72163100", size=size)
        for size in ("75x40", "100x50", "125x65")
    ]
    return rows


def test_fifty_items_import_from_a_sheet(client):
    headers = login(client, *OWNER)
    rows = fifty_rows()
    assert len(rows) == 50

    preview = upload(client, headers, sheet(rows), dry_run=True).json()
    assert (preview["created"], preview["updated"], preview["errors"]) == (50, 0, [])
    assert client.get("/api/v1/items", headers=headers).json()["total"] == 0  # nothing saved

    saved = upload(client, headers, sheet(rows), dry_run=False).json()
    assert saved["created"] == 50 and saved["dry_run"] is False
    assert client.get("/api/v1/items?limit=200", headers=headers).json()["total"] == 50

    # Importing the same sheet again updates, never duplicates.
    again = upload(client, headers, sheet(rows), dry_run=False).json()
    assert (again["created"], again["updated"]) == (0, 50)

    cement = client.get("/api/v1/items?q=Dalmia", headers=headers).json()["items"][0]
    assert cement["base_whole_only"] is True
    convert = client.get(
        f"/api/v1/items/{cement['id']}/convert",
        headers=headers,
        params={"quantity": "40", "from_unit": "bag", "to_unit": "ton"},
    )
    assert convert.json()["result"] == "2.000"  # 40 bags / 20 per ton


def test_import_reports_every_bad_row_and_saves_nothing(client):
    headers = login(client, *OWNER)
    rows = [
        row("Item A", units="ton:1000"),
        row("Item B", category="steel"),  # row 3: bad category
        row("Item C", hsn="12"),  # row 4: bad hsn
        row("Item D", gst="150"),  # row 5: gst above 100
        row("Item E", units="ton"),  # row 6: bad unit
        row("Item F", units="ton:abc"),  # row 7: bad factor
        row("item a"),  # row 8: same name as row 2
        row("Item G", base_whole_only="maybe"),  # row 9: not yes/no
        [None] * len(COLUMNS),  # blank rows are skipped
    ]
    result = upload(client, headers, sheet(rows), dry_run=False).json()
    assert result["created"] == 0
    by_row = {e["row"]: e for e in result["errors"]}
    assert set(by_row) == {3, 4, 5, 6, 7, 8, 9}
    assert by_row[3]["field"] == "category" and by_row[4]["field"] == "hsn"
    assert by_row[8]["message"] == "Same name as row 2"
    assert client.get("/api/v1/items", headers=headers).json()["total"] == 0


def test_import_cannot_change_a_base_unit(client):
    headers = login(client, *OWNER)
    make_item(client, headers, CEMENT)
    result = upload(
        client, headers, sheet([row(CEMENT["name"], "cement", "25232930", "28", "kg")]), False
    ).json()
    assert result["errors"][0]["field"] == "base_unit"


def test_import_rejects_bad_files(client):
    headers = login(client, *OWNER)
    junk = upload(client, headers, b"not a spreadsheet", True)
    assert junk.status_code == 409 and junk.json()["code"] == "BAD_SPREADSHEET"
    short = upload(client, headers, sheet([], header=["name", "category"]), True)
    assert short.status_code == 409 and short.json()["code"] == "MISSING_COLUMNS"
    huge = upload(client, headers, b"x" * 2_000_001, True)
    assert huge.status_code == 409 and huge.json()["code"] == "FILE_TOO_LARGE"
    template = client.get("/api/v1/items/import/template", headers=headers)
    assert template.status_code == 200 and template.content[:2] == b"PK"
    # The template itself imports cleanly: its example row is valid.
    assert upload(client, headers, template.content, True).json()["created"] == 1


# ------------------------------------------------------------------ parties and sites


def test_party_sites_and_validation(client):
    headers = login(client, *COUNTER)
    party = client.post(
        "/api/v1/parties",
        headers=headers,
        json={
            "name": "Ravi Builders",
            "type": "customer",
            "segment": "contractor",
            "state_code": "33",
            "phone": "9876543210",
            "sites": [{"name": "Anna Nagar villa", "state_code": "33", "address": "12 Main Rd"}],
        },
    ).json()
    assert party["sites"][0]["gstin"] is None  # prints as URP on e-way bills (G13)

    site = client.post(
        f"/api/v1/parties/{party['id']}/sites",
        headers=headers,
        json={"name": "Hosur plot", "state_code": "29", "gstin": "29AAPFU0939F1ZW"},
    )
    # The GSTIN has a bad check digit, so it is refused.
    assert site.status_code == 422
    site = client.post(
        f"/api/v1/parties/{party['id']}/sites",
        headers=headers,
        json={"name": "Hosur plot", "state_code": "29"},
    )
    assert site.status_code == 201
    dup = client.post(
        f"/api/v1/parties/{party['id']}/sites",
        headers=headers,
        json={"name": "hosur PLOT", "state_code": "29"},
    )
    assert dup.status_code == 409 and dup.json()["code"] == "SITE_NAME_TAKEN"

    off = client.patch(
        f"/api/v1/sites/{site.json()['id']}", headers=headers, json={"is_active": False}
    )
    assert off.json()["is_active"] is False
    mismatch = client.patch(
        f"/api/v1/sites/{site.json()['id']}", headers=headers, json={"gstin": "27AAPFU0939F1ZV"}
    )
    assert mismatch.status_code == 409 and mismatch.json()["code"] == "GSTIN_STATE_MISMATCH"
    assert client.patch("/api/v1/sites/99999", headers=headers, json={}).status_code == 404

    fetched = client.get(f"/api/v1/parties/{party['id']}", headers=headers).json()
    assert [s["name"] for s in fetched["sites"]] == ["Anna Nagar villa", "Hosur plot"]
    assert client.get("/api/v1/parties/99999", headers=headers).status_code == 404


def test_party_rules_and_filters(client):
    headers = login(client, *OWNER)
    supplier = client.post(
        "/api/v1/parties",
        headers=headers,
        json={
            "name": "Steel Mills Ltd",
            "type": "supplier",
            "state_code": "33",
            "gstin": "33AAPFU0939F1Z2",
        },
    )
    assert supplier.status_code == 201, supplier.text
    assert (
        client.post(
            f"/api/v1/parties/{supplier.json()['id']}/sites",
            headers=headers,
            json={"name": "x", "state_code": "33"},
        ).json()["code"]
        == "SUPPLIER_HAS_NO_SITES"
    )

    bad = client.post(
        "/api/v1/parties",
        headers=headers,
        json={"name": "S", "type": "supplier", "segment": "retail", "state_code": "33"},
    )
    assert bad.status_code == 422
    mismatch = client.post(
        "/api/v1/parties",
        headers=headers,
        json={"name": "M", "type": "customer", "state_code": "29", "gstin": "33AAPFU0939F1Z2"},
    )
    assert mismatch.status_code == 422
    dup = client.post(
        "/api/v1/parties",
        headers=headers,
        json={"name": "steel mills ltd", "type": "both", "state_code": "33"},
    )
    assert dup.status_code == 409 and dup.json()["code"] == "PARTY_NAME_TAKEN"

    both = client.post(
        "/api/v1/parties",
        headers=headers,
        json={"name": "Both Co", "type": "both", "segment": "bulk", "state_code": "33"},
    ).json()
    customers = client.get("/api/v1/parties?kind=customer", headers=headers).json()
    suppliers = client.get("/api/v1/parties?kind=supplier", headers=headers).json()
    assert {p["name"] for p in customers["items"]} == {"Both Co", "Walk-in customer"}
    assert {p["name"] for p in suppliers["items"]} == {"Both Co", "Steel Mills Ltd"}
    assert client.get("/api/v1/parties?q=steel", headers=headers).json()["total"] == 1

    # Turning a customer into a supplier clears segment and credit.
    client.patch(f"/api/v1/parties/{both['id']}", headers=headers, json={"credit_allowed": True})
    changed = client.patch(
        f"/api/v1/parties/{both['id']}", headers=headers, json={"type": "supplier"}
    )
    assert changed.json()["segment"] is None and changed.json()["credit_allowed"] is False
    clash = client.patch(
        f"/api/v1/parties/{both['id']}", headers=headers, json={"name": "Steel Mills Ltd"}
    )
    assert clash.status_code == 409
    mism = client.patch(
        f"/api/v1/parties/{both['id']}", headers=headers, json={"gstin": "27AAPFU0939F1ZV"}
    )
    assert mism.status_code == 409 and mism.json()["code"] == "GSTIN_STATE_MISMATCH"
    off = client.patch(f"/api/v1/parties/{both['id']}", headers=headers, json={"is_active": False})
    assert off.status_code == 200
    assert (
        client.get("/api/v1/parties", headers=headers).json()["total"] == 2
    )  # Steel Mills Ltd and the seeded Walk-in customer
