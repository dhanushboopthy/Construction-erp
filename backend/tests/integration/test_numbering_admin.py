"""M26: a Super Admin sees and sets a company's number series.

Company A is the default company ("main") with bills; company B is "acme".
"""
# fmt: off

import pytest
from sqlalchemy import select, text

from app.core.tenancy import set_tenant
from app.models.enums import PlatformAction
from app.models.platform import PlatformAuditLog
from app.models.tenancy import Tenant
from app.services import verify
from tests.conftest import as_db_owner
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    helper,
    onboard,
    owner_of,
)
from tests.integration.test_sales import body, line, post, world  # noqa: F401 - the fixture

pytestmark = pytest.mark.integration

ADMIN = "/api/v1/admin"


def _tenant_id(db, slug="main"):
    return db.execute(select(Tenant.id).where(Tenant.slug == slug)).scalar_one()


def _bills(client, world, count):
    out = []
    for _ in range(count):
        made = post(client, world, body(world, [line(world, "cement", "1")]))
        assert made.status_code == 201, made.text
        out.append(made.json())
    return out


def _series(client, boss, tenant_id, doc_type="sales_invoice", location_code="S1", fy=None):
    rows = client.get(f"{ADMIN}/tenants/{tenant_id}/numbering", headers=boss).json()["items"]
    found = [
        r
        for r in rows
        if r["doc_type"] == doc_type
        and r["location_code"] == location_code
        and (fy is None or r["financial_year"] == fy)
    ]
    assert found, rows
    return found[0]


def _set(client, boss, tenant_id, row, number, reason="Starting a new book"):
    return client.patch(
        f"{ADMIN}/tenants/{tenant_id}/numbering",
        headers=boss,
        json={
            "location_id": row["location_id"],
            "doc_type": row["doc_type"],
            "financial_year": row["financial_year"],
            "next_number": number,
            "reason": reason,
        },
    )


def _numbers_check(db, tenant_id):
    set_tenant(db, tenant_id)
    db.info.pop("platform", None)
    return next(c for c in verify.run_checks(db).checks if c.name == "Document numbers")


def test_a_series_shows_both_numbers_and_the_next_document_in_full(client, boss, world, seeded):
    bills = _bills(client, world, 3)
    row = _series(client, boss, _tenant_id(seeded))
    assert row["highest_existing"] == 3 and row["highest_number"] == bills[-1]["number"]
    assert row["configured_next"] == 4 and row["minimum_next"] == 4
    assert row["next_document"] == bills[-1]["number"][:-5] + "00004"
    assert row["prefix"] == "S1" and row["ahead_of_documents"] is False
    assert row["suggested_next"] is None and row["doc_label"] == "Bill"


def test_the_next_number_must_clear_the_highest_existing_one(client, boss, world, seeded):
    tenant = _tenant_id(seeded)
    bills = _bills(client, world, 7)
    row = _series(client, boss, tenant)
    refused = _set(client, boss, tenant, row, 5)
    assert refused.status_code == 409 and refused.json()["code"] == "NUMBER_TOO_LOW"
    assert refused.json()["message"] == (
        f"Bill {bills[-1]['number']} already exists. The next number must be 8 or higher."
    )
    assert _set(client, boss, tenant, row, 7).status_code == 409
    ok = _set(client, boss, tenant, row, 8)
    assert ok.status_code == 200 and ok.json()["configured_next"] == 8
    assert _series(client, boss, tenant)["configured_next"] == 8


def test_a_number_above_the_highest_reaches_the_next_bill_and_verify_still_passes(
    client, boss, world, seeded
):
    tenant = _tenant_id(seeded)
    _bills(client, world, 7)
    row = _series(client, boss, tenant)
    done = _set(client, boss, tenant, row, 20)
    assert done.status_code == 200, done.text
    assert done.json()["ahead_of_documents"] is True and done.json()["suggested_next"] == 8
    nxt = _bills(client, world, 1)[0]
    assert nxt["number"].endswith("/00020")
    check = _numbers_check(seeded, tenant)
    assert check.state == "ok", check.detail


def test_a_gap_nobody_recorded_still_fails_verify(client, boss, world, seeded):
    tenant = _tenant_id(seeded)
    _bills(client, world, 2)
    with as_db_owner(seeded):
        seeded.execute(text("UPDATE document_sequence SET next_value = 30 WHERE tenant_id = :t"), {"t": tenant})
    _bills(client, world, 1)
    assert _numbers_check(seeded, tenant).state == "fail"


def test_a_cancelled_bill_still_counts_but_a_missing_number_below_the_highest_does_not_reopen(
    client, boss, world, seeded
):
    tenant = _tenant_id(seeded)
    bills = _bills(client, world, 3)
    cancelled = client.post(
        f"/api/v1/invoices/{bills[2]['id']}/cancel",
        headers=world["owner"],
        json={"reason": "Wrong customer"},
    )
    assert cancelled.status_code == 201, cancelled.text
    row = _series(client, boss, tenant)
    assert row["highest_existing"] == 3  # the cancelled bill is still a row
    assert _set(client, boss, tenant, row, 3).status_code == 409
    assert _set(client, boss, tenant, row, 4).status_code == 200


def test_a_reason_is_required_and_the_change_is_audited_with_old_and_new_values(
    client, boss, world, seeded
):
    tenant = _tenant_id(seeded)
    _bills(client, world, 2)
    row = _series(client, boss, tenant)
    for reason in ("", "   "):
        refused = _set(client, boss, tenant, row, 9, reason=reason)
        assert refused.status_code == 422 and refused.json()["code"] == "REASON_REQUIRED"
    assert _set(client, boss, tenant, row, 9, reason="New printed book starts at 9").status_code == 200
    entry = seeded.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == PlatformAction.NUMBERING_SET)
    ).one()
    assert entry.tenant_id == tenant
    assert entry.details["old_next"] == 3 and entry.details["new_next"] == 9
    assert entry.details["reason"] == "New printed book starts at 9"
    assert entry.details["financial_year"] == row["financial_year"]
    assert entry.details["highest_existing"] == 2 and entry.details["location"] == "S1"


def test_a_series_with_no_counter_yet_can_be_started(client, boss, world, seeded):
    tenant = _tenant_id(seeded)
    _bills(client, world, 1)
    row = _series(client, boss, tenant)
    made = _set(client, boss, tenant, row | {"doc_type": "credit_note", "financial_year": "31-32"}, 5)
    assert made.status_code == 200, made.text
    assert made.json()["next_document"] == "S1C/31-32/00005"
    assert _series(client, boss, tenant, "credit_note", fy="31-32")["configured_next"] == 5


def test_only_this_companys_shops_and_series_are_touched(client, boss, helper, world, acme, seeded):
    main, other = _tenant_id(seeded), acme["id"]
    _bills(client, world, 2)
    row = _series(client, boss, main)
    acme_rows = client.get(f"{ADMIN}/tenants/{other}/numbering", headers=boss).json()["items"]
    # A shop of another company is not a shop of this one.
    foreign_shop = owner_of(client)
    shops = client.get("/api/v1/locations", headers=foreign_shop).json()
    wrong = _set(client, boss, main, row | {"location_id": shops[0]["id"]}, 9)
    assert wrong.status_code == 404 and wrong.json()["code"] == "LOCATION_NOT_FOUND"
    assert _set(client, boss, main, row, 9).status_code == 200
    assert client.get(f"{ADMIN}/tenants/{other}/numbering", headers=boss).json()["items"] == acme_rows
    assert client.get(f"{ADMIN}/tenants/999999/numbering", headers=boss).status_code == 404


def test_support_gets_403_on_every_numbering_route_reads_included(client, boss, helper, world, seeded):
    tenant = _tenant_id(seeded)
    _bills(client, world, 1)
    row = _series(client, boss, tenant)
    assert client.get(f"{ADMIN}/tenants/{tenant}/numbering", headers=helper).status_code == 403
    assert _set(client, helper, tenant, row, 9).status_code == 403
    assert _series(client, boss, tenant)["configured_next"] == 2
