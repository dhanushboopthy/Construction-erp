"""M26: a Super Admin counts and deletes a company's business data.

Company A is the default company ("main") with bills, a quotation, a purchase with a stored slip,
a receipt and a credit note; company B is "acme" with a customer and an item. After every
deletion B is compared, table by table, with how it was.
"""
# fmt: off

import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.models.enums import BackupSource, PlatformAction
from app.models.platform import PlatformAuditLog, PlatformBackup
from app.models.tenancy import Tenant
from app.services import verify
from app.services.platform import backups as backup_service
from app.services.platform import company_archive as archive
from app.services.platform import data_management as service
from app.services.platform.data_catalogue import ORDER, PRESERVED, TABLES
from app.services.storage import get_storage
from tests.conftest import as_db_owner, login
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    helper,
    onboard,
    owner_of,
)
from tests.integration.test_sales import (  # noqa: F401 - the fixture
    OWNER,
    body,
    day,
    line,
    post,
    world,
)
from tests.integration.test_weight_schemes import purchase, upload

pytestmark = pytest.mark.integration

ADMIN = "/api/v1/admin"
CONFIRM = "DELETE"


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "backup_dir", str(tmp_path))
    return tmp_path


def _tenant(db, slug="main"):
    return db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one()


def _snapshot(db, tenant_id, tables=None):
    """Row count and checksum of the company's rows in every table, read as the table owner."""
    out = {}
    with as_db_owner(db):
        for name in tables or sorted(TABLES | PRESERVED):
            out[name] = tuple(
                db.execute(
                    text(
                        "SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) "  # noqa: S608
                        f'FROM "{name}" t WHERE tenant_id = :id'
                    ),
                    {"id": tenant_id},
                ).one()
            )
    return out


def _counts(db, tenant_id, tables):
    return {t: n for t, (n, _) in _snapshot(db, tenant_id, tables).items()}


@pytest.fixture
def loaded(client, boss, world, acme, seeded, folder):
    """Company A with one of most things; company B with a customer and an item."""
    owner = world["owner"]
    first = post(client, world, body(world, [line(world, "cement", "2")])).json()
    second = post(client, world, body(world, [line(world, "cement", "1")])).json()
    cancelled = client.post(
        f"/api/v1/invoices/{second['id']}/cancel", headers=owner, json={"reason": "Wrong customer"}
    )
    assert cancelled.status_code == 201, cancelled.text
    quote = client.post(
        "/api/v1/quotes", headers=owner, json=body(world, [line(world, "cement", "3")]) | {"kind": "quotation"}
    )
    assert quote.status_code == 201, quote.text
    bought = purchase(client, world).json()
    slip = upload(client, owner, "purchase", bought["id"])
    assert slip.status_code == 201, slip.text
    paid = client.post(
        "/api/v1/payments",
        headers=owner,
        json={
            "direction": "received",
            "party_id": world["ravi"]["id"],
            "location_id": world["loc"]["S1"],
            "amount": "100",
            "mode": "cash",
            "payment_date": day(0),
        },
    )
    assert paid.status_code == 201, paid.text
    other = owner_of(client)
    made = client.post(
        "/api/v1/parties", headers=other,
        json={"name": "Acme Customer", "type": "customer", "state_code": "33"},
    )
    assert made.status_code == 201, made.text
    return {"first": first, "slip": slip.json(), "owner": owner, "acme_owner": other}


def _url(tenant_id, tail=""):
    return f"{ADMIN}/tenants/{tenant_id}/data{tail}"


def _delete(client, boss, tenant_id, keys, confirm=CONFIRM):
    return client.post(_url(tenant_id, "/delete"), headers=boss, json={"keys": keys, "confirm": confirm})


def _delete_all(client, boss, tenant_id, name, confirm=CONFIRM, acknowledged=True):
    return client.post(
        _url(tenant_id, "/delete-all"),
        headers=boss,
        json={"confirm": confirm, "company_name": name, "acknowledged": acknowledged},
    )


def _kinds(client, boss, tenant_id):
    return {k["key"]: k for k in client.get(_url(tenant_id), headers=boss).json()["items"]}


# ------------------------------------------------------------------ the inventory


def test_the_inventory_counts_each_kind_and_names_what_blocks_it(client, boss, loaded, seeded):
    a = _tenant(seeded).id
    kinds = _kinds(client, boss, a)
    assert list(kinds) == list(ORDER)
    assert kinds["sales"]["count"] == 2 and kinds["quotes"]["count"] == 1
    assert kinds["purchases"]["count"] == 1 and kinds["attachments"]["count"] == 1
    assert kinds["notes"]["count"] == 1  # the credit note of the cancelled bill
    parties = kinds["parties"]
    assert parties["can_delete"] is False
    blockers = {b["key"]: b["count"] for b in parties["blocked_by"]}
    assert blockers["sales"] >= 2 and "payments" in blockers and "quotes" in blockers
    assert kinds["quotes"]["can_delete"] is True and kinds["quotes"]["blocked_by"] == []
    # The company's own name is the check that the right company is on screen.
    assert client.get(_url(a), headers=boss).json()["company_name"] == _tenant(seeded).name


def test_view_shows_the_latest_rows_as_four_identifying_columns_only(client, boss, loaded, seeded):
    a = _tenant(seeded).id
    for key in ORDER:  # every view runs, whatever the company holds
        shown = client.get(_url(a, f"/{key}"), headers=boss)
        assert shown.status_code == 200, f"{key}: {shown.text}"
        out = shown.json()
        assert len(out["columns"]) == 4 and all(len(r) == 4 for r in out["rows"]), key
        assert len(out["rows"]) <= 25
    sales = client.get(_url(a, "/sales"), headers=boss).json()
    assert sales["total"] == 2 and len(sales["rows"]) == 2
    assert sales["columns"] == ["Number", "Date", "Status", "Customer"]
    assert sales["rows"][0][0].startswith("S1/")


def test_an_unknown_kind_is_refused_never_ignored(client, boss, loaded, seeded):
    a = _tenant(seeded).id
    before = _snapshot(seeded, a)
    shown = client.get(_url(a, "/saels"), headers=boss)
    assert shown.status_code == 422 and shown.json()["code"] == "UNKNOWN_DATA_KIND"
    assert client.get(_url(a, "/preview?keys=quotes&keys=saels"), headers=boss).status_code == 422
    refused = _delete(client, boss, a, ["quotes", "saels"])
    assert refused.status_code == 422 and refused.json()["code"] == "UNKNOWN_DATA_KIND"
    assert _snapshot(seeded, a) == before


def test_the_preview_counts_a_selection_and_names_what_would_block_it(client, boss, loaded, seeded):
    a = _tenant(seeded).id
    one = client.get(_url(a, "/preview?keys=quotes"), headers=boss).json()
    assert one["everything"] is False and one["blocked"] == []
    assert {t["table"]: t["count"] for t in one["tables"]} == {"sales_quote_line": 1, "sales_quote": 1}
    assert one["total"] == 2
    blocked = client.get(_url(a, "/preview?keys=parties"), headers=boss).json()
    assert blocked["blocked"][0]["key"] == "parties" and blocked["message"].startswith("Parties and sites is blocked by")
    everything = client.get(_url(a, "/preview"), headers=boss).json()
    assert everything["everything"] is True and everything["blocked"] == []
    assert everything["files"] >= 1
    stock_rows = {t["table"]: t["count"] for t in everything["tables"]}["stock_ledger"]
    assert stock_rows == _counts(seeded, a, ["stock_ledger"])["stock_ledger"]


# ------------------------------------------------------------------ deleting selected kinds


def test_deleting_quotations_leaves_the_bills_and_the_other_company_untouched(client, boss, loaded, acme, seeded):
    a, b = _tenant(seeded).id, acme["id"]
    other = _snapshot(seeded, b)
    mine = _snapshot(seeded, a)
    done = _delete(client, boss, a, ["quotes"])
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["operation"] == "selected" and out["kinds"] == ["quotes"] and out["total"] == 2
    after = _snapshot(seeded, a)
    assert after["sales_quote"][0] == 0 and after["sales_quote_line"][0] == 0
    for table in sorted(TABLES | PRESERVED) :
        if table in ("sales_quote", "sales_quote_line"):
            continue
        if table in ("audit_log", "document_sequence_event", "platform_audit_log"):
            continue
        if table == "document_sequence":  # only the emptied quotation series moved
            continue
        assert after[table] == mine[table], table  # bills and everything else untouched
    assert _snapshot(seeded, b) == other
    assert out["backup_id"] and seeded.get(PlatformBackup, out["backup_id"]).protected is True


def test_deleting_parties_while_bills_exist_answers_409_and_names_the_bills(client, boss, loaded, seeded):
    a = _tenant(seeded).id
    before = _snapshot(seeded, a)
    refused = _delete(client, boss, a, ["parties"])
    assert refused.status_code == 409 and refused.json()["code"] == "DATA_BLOCKED"
    assert "Parties and sites is blocked by" in refused.json()["message"]
    assert "2 Sales bills" in refused.json()["message"]
    named = {b["key"] for b in refused.json()["blocked"][0]["blocked_by"]}
    assert {"sales", "payments", "quotes"} <= named
    assert _snapshot(seeded, a) == before


def test_a_blocker_chosen_together_with_what_it_blocks_goes_first(client, boss, loaded, seeded):
    a = _tenant(seeded).id
    refused = _delete(client, boss, a, ["sales", "quotes"])  # the credit note still points at a bill
    assert refused.status_code == 409 and "Credit and debit notes" in refused.json()["message"]
    done = _delete(client, boss, a, ["sales", "notes", "quotes"])
    assert done.status_code == 200, done.text
    counts = _counts(seeded, a, ["sales_invoice", "sales_line", "credit_note", "sales_quote", "item", "party", "purchase"])
    assert counts["sales_invoice"] == counts["sales_line"] == counts["credit_note"] == counts["sales_quote"] == 0
    assert counts["item"] > 0 and counts["party"] > 0 and counts["purchase"] == 1
    # The bills' ledger rows went with them; the purchase's stayed.
    refs = seeded_refs(seeded, a)
    assert "sale" not in refs and "purchase" in refs


def seeded_refs(db, tenant_id):
    with as_db_owner(db):
        return set(db.execute(text("SELECT DISTINCT ref_type FROM stock_ledger WHERE tenant_id = :t"), {"t": tenant_id}).scalars())


def test_the_ledgers_alone_cannot_be_emptied_while_documents_still_post_to_them(client, boss, loaded, seeded):
    a = _tenant(seeded).id
    refused = _delete(client, boss, a, ["ledgers"])
    assert refused.status_code == 409 and refused.json()["code"] == "DATA_BLOCKED"
    assert "Stock and party ledgers is blocked by" in refused.json()["message"]


# ------------------------------------------------------------------ confirmations


@pytest.mark.parametrize("typed", ["delete", "Delete", " DELETE", "DELETE ", "", "REMOVE"])
def test_a_wrong_word_deletes_nothing(client, boss, loaded, seeded, typed):
    a = _tenant(seeded).id
    before = _snapshot(seeded, a)
    refused = _delete(client, boss, a, ["quotes"], confirm=typed)
    assert refused.status_code == 422 and refused.json()["code"] in ("CONFIRMATION_MISMATCH", "VALIDATION_ERROR")
    assert _snapshot(seeded, a) == before


def test_delete_everything_needs_the_word_the_exact_name_and_the_tick(client, boss, loaded, seeded):
    tenant = _tenant(seeded)
    before = _snapshot(seeded, tenant.id)
    name = tenant.name
    cases = [
        ({"confirm": "delete"}, "CONFIRMATION_MISMATCH"),
        ({"name": name.upper()}, "COMPANY_NAME_MISMATCH"),
        ({"name": name + " "}, "COMPANY_NAME_MISMATCH"),
        ({"name": name.lower()}, "COMPANY_NAME_MISMATCH"),
        ({"name": ""}, "COMPANY_NAME_MISMATCH"),
        ({"acknowledged": False}, "ACKNOWLEDGEMENT_REQUIRED"),
    ]
    for change, code in cases:
        args = {"name": name, "confirm": CONFIRM, "acknowledged": True} | change
        refused = _delete_all(client, boss, tenant.id, args["name"], args["confirm"], args["acknowledged"])
        assert refused.status_code == 422, (change, refused.text)
        assert refused.json()["code"] == code, change
    assert _snapshot(seeded, tenant.id) == before
    assert seeded.scalars(select(PlatformBackup).where(PlatformBackup.source == BackupSource.SAFETY)).all() == []


# ------------------------------------------------------------------ delete everything


def _rebuild_and_bill(client, owner):
    loc = {x["code"]: x["id"] for x in client.get("/api/v1/locations", headers=owner).json()}
    item = client.post(
        "/api/v1/items", headers=owner,
        json={"name": "Cement PPC", "category": "cement", "hsn": "25232930", "gst_rate": "28",
              "base_unit": "bag", "base_whole_only": True},
    ).json()
    client.post("/api/v1/opening", headers=owner, json={
        "kind": "stock", "as_of": day(30), "item_id": item["id"], "location_id": loc["S1"],
        "quantity": "100", "unit_cost": "350"})
    assert client.post("/api/v1/opening/post", headers=owner, json={"kinds": ["stock"]}).status_code == 200
    client.put("/api/v1/rates/market", headers=owner, json={
        "effective_date": day(1), "rates": [{"item_id": item["id"], "rate": "380.45"}]})
    party = client.post("/api/v1/parties", headers=owner,
                        json={"name": "Ravi Builders", "type": "customer", "state_code": "33"}).json()
    client.patch(f"/api/v1/parties/{party['id']}", headers=owner,
                 json={"credit_allowed": True, "credit_limit": "10000000", "credit_days": 30})
    return client.post("/api/v1/invoices", headers=owner, json={
        "location_id": loc["S1"], "party_id": party["id"], "site_id": None,
        "lines": [{"item_id": item["id"], "quantity": "1", "unit": None}]})


def test_delete_everything_empties_the_catalogue_and_keeps_the_company(client, boss, loaded, acme, seeded):
    tenant = _tenant(seeded)
    a, b = tenant.id, acme["id"]
    other = _snapshot(seeded, b)
    before = _snapshot(seeded, a)
    key = loaded["slip"]["id"]
    with as_db_owner(seeded):
        stored = seeded.execute(text("SELECT storage_key FROM attachment WHERE id = :i"), {"i": key}).scalar_one()
    assert get_storage().exists(stored)

    done = _delete_all(client, boss, a, tenant.name)
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["operation"] == "all" and out["kinds"] == list(ORDER) and out["total"] > 10
    assert out["files_removed"] >= 1 and not get_storage().exists(stored)
    assert out["series_reset"] and all(s["to_number"] == 1 for s in out["series_reset"])
    assert any(s["series"].startswith("S1/") for s in out["series_reset"])

    after = _snapshot(seeded, a)
    for table in sorted(TABLES):
        assert after[table][0] == 0, table
    for table in ("app_user", "location", "shop_settings", "subscription", "document_sequence",
                  "cost_component", "expense_category"):
        assert after[table][0] > 0, table
    for table in ("app_user", "location", "shop_settings", "subscription", "audit_log"):
        assert after[table][0] >= before[table][0] or table == "audit_log", table
    assert after["app_user"] == before["app_user"] and after["location"] == before["location"]
    assert after["shop_settings"] == before["shop_settings"] and after["subscription"] == before["subscription"]
    assert _snapshot(seeded, b) == other  # the bystander, table by table

    # The owner still signs in, and the next bill is number 1 again.
    owner = login(client, *OWNER)
    billed = _rebuild_and_bill(client, owner)
    assert billed.status_code == 201, billed.text
    assert billed.json()["number"].endswith("/00001")
    from app.core.tenancy import set_tenant
    set_tenant(seeded, a)
    seeded.info.pop("platform", None)
    assert verify.run_checks(seeded).ok


def test_the_audit_names_counts_the_backup_and_the_series_and_no_secret(client, boss, loaded, seeded):
    tenant = _tenant(seeded)
    done = _delete_all(client, boss, tenant.id, tenant.name).json()
    entry = seeded.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == PlatformAction.COMPANY_DATA_DELETED_ALL)
    ).one()
    assert entry.tenant_id == tenant.id and entry.admin_id
    d = entry.details
    assert d["operation"] == "all" and d["backup_id"] == done["backup_id"] and d["total"] == done["total"]
    assert d["tables"]["sales_invoice"] == 2 and d["kinds"] == list(ORDER)
    assert d["series_reset"] and d["series_reset"][0]["to_number"] == 1
    flat = str(d).lower()
    assert not any(w in flat for w in ("password", "token", "secret", "authorization"))
    one = _delete(client, boss, tenant.id, ["quotes"])
    assert one.status_code == 200
    assert seeded.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == PlatformAction.COMPANY_DATA_DELETED)
    ).one().details["kinds"] == ["quotes"]


def test_the_safety_backup_is_protected_and_still_holds_what_was_deleted(client, boss, loaded, seeded, folder):
    tenant = _tenant(seeded)
    done = _delete_all(client, boss, tenant.id, tenant.name).json()
    row = seeded.get(PlatformBackup, done["backup_id"])
    assert row.protected is True and row.source is BackupSource.SAFETY and row.company_id == tenant.id
    assert (folder / row.file_name).is_file()
    manifest = archive.read_manifest(folder / row.file_name)
    assert manifest["tables"]["sales_invoice"]["rows"] == 2
    gone = client.request("DELETE", f"{ADMIN}/backups/{row.id}", headers=boss, json={"confirm": "DELETE"})
    assert gone.status_code == 409 and gone.json()["code"] == "BACKUP_PROTECTED"


# ------------------------------------------------------------------ guards


def test_if_the_safety_backup_fails_nothing_is_removed(client, boss, loaded, seeded, monkeypatch):
    tenant = _tenant(seeded)
    before = _snapshot(seeded, tenant.id, sorted(TABLES))

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(backup_service, "make_company_backup", broken)
    refused = _delete_all(client, boss, tenant.id, tenant.name)
    assert refused.status_code == 409 and refused.json()["code"] == "SAFETY_BACKUP_FAILED"
    assert _snapshot(seeded, tenant.id, sorted(TABLES)) == before
    failed = seeded.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == PlatformAction.COMPANY_DATA_DELETE_FAILED)
    ).all()
    assert len(failed) == 1


def test_a_failure_halfway_rolls_everything_back_and_is_audited(client, boss, loaded, acme, seeded, monkeypatch):
    tenant = _tenant(seeded)
    before = _snapshot(seeded, tenant.id)
    real = service._delete_kind
    calls = []

    def flaky(db, tenant_id, kind):
        calls.append(kind.key)
        if len(calls) == 6:
            raise RuntimeError("the disk went away")
        return real(db, tenant_id, kind)

    monkeypatch.setattr(service, "_delete_kind", flaky)
    refused = _delete_all(client, boss, tenant.id, tenant.name)
    assert refused.status_code == 400 and refused.json()["code"] == "DATA_DELETE_FAILED"
    assert "nothing was removed" in refused.json()["message"].lower()
    assert len(calls) == 6
    after = _snapshot(seeded, tenant.id)
    for table in sorted(TABLES | PRESERVED):
        if table not in ("audit_log", "document_sequence_event", "platform_audit_log"):
            assert after[table] == before[table], table
    failed = seeded.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == PlatformAction.COMPANY_DATA_DELETE_FAILED)
    ).all()
    assert len(failed) == 1 and failed[0].details["operation"] == "all"
    # The safety backup was made before the attempt and is kept.
    assert seeded.scalars(select(PlatformBackup).where(PlatformBackup.source == BackupSource.SAFETY)).all()


def test_nothing_runs_for_a_company_that_does_not_exist(client, boss, seeded):
    assert client.get(_url(999999), headers=boss).status_code == 404
    assert _delete(client, boss, 999999, ["quotes"]).status_code == 404
    assert _delete_all(client, boss, 999999, "x").status_code == 404


def test_support_gets_403_on_every_data_route_reads_included(client, helper, loaded, seeded):
    a = _tenant(seeded).id
    before = _snapshot(seeded, a)
    for method, url, payload in (
        ("GET", _url(a), None),
        ("GET", _url(a, "/sales"), None),
        ("GET", _url(a, "/preview"), None),
        ("POST", _url(a, "/delete"), {"keys": ["quotes"], "confirm": CONFIRM}),
        ("POST", _url(a, "/delete-all"), {"confirm": CONFIRM, "company_name": "x", "acknowledged": True}),
    ):
        response = client.request(method, url, headers=helper, json=payload)
        assert response.status_code == 403, f"{method} {url}"
        assert response.json()["code"] == "PERMISSION_DENIED"
    assert _snapshot(seeded, a) == before


def test_a_company_user_cannot_reach_the_data_routes(client, loaded, seeded):
    a = _tenant(seeded).id
    owner = loaded["owner"]
    assert client.get(_url(a), headers=owner).status_code in (401, 403, 404)
