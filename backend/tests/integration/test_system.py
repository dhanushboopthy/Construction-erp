"""Milestone 14: database guards on issued documents, integrity checks and system status."""

import os
import time

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
    line,
    post,
    world,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def busy(client, world, seeded):
    inv = post(client, world, body(world, [line(world, "cement", "7")])).json()
    client.post(
        "/api/v1/credit-notes",
        headers=world["owner"],
        json={
            "invoice_id": inv["id"],
            "reason": "Extra bags",
            "lines": [{"line_id": inv["lines"][0]["id"], "quantity": "2"}],
        },
    )
    client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "SYS-1",
            "bill_date": today_ist().isoformat(),
            "lines": [
                {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": "2", "rate": "55000"}
            ],
        },
    )
    return inv


# ------------------------------------------------------------------ the database refuses edits


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM sales_invoice",
        "DELETE FROM sales_line",
        "DELETE FROM credit_note",
        "DELETE FROM purchase",
        "DELETE FROM purchase_line",
        "UPDATE sales_invoice SET grand_total = grand_total + 1",
        "UPDATE sales_line SET taxable = taxable + 1",
        "UPDATE credit_note SET reason = 'changed'",
        "UPDATE purchase_line SET rate = rate + 1",
        "DELETE FROM stock_ledger",
        "UPDATE party_ledger SET debit = debit + 1",
    ],
)
def test_the_database_refuses_to_change_issued_documents(seeded, busy, statement):
    with pytest.raises(DBAPIError, match=r"issued document|append-only"), seeded.begin_nested():
        seeded.execute(text(statement))


def test_bookkeeping_columns_may_still_change(seeded, busy):
    seeded.execute(text("UPDATE sales_invoice SET updated_at = now(), updated_by = 1"))
    seeded.flush()


# ------------------------------------------------------------------ integrity checks


def test_a_healthy_set_of_books_passes_every_check(seeded, busy):
    result = verify.run_checks(seeded, full=True)
    states = {c.name: c.state for c in result.checks}
    assert result.ok, result
    assert set(states.values()) == {"ok"}
    assert {"Document numbers", "Stock", "Accounts agree with documents"} <= set(states)


def test_the_checks_catch_a_gap_a_wrong_total_and_a_stray_ledger_row(seeded, busy):
    def failed(name):
        return next(c for c in verify.run_checks(seeded).checks if c.name == name).state == "fail"

    seeded.execute(text("ALTER TABLE sales_invoice DISABLE TRIGGER sales_invoice_no_edit"))
    seeded.execute(text("UPDATE sales_invoice SET grand_total = grand_total + 5"))
    assert failed("Document totals")
    seeded.execute(text("UPDATE sales_invoice SET number = 'S1/26-27/00009'"))
    assert failed("Document numbers") is False  # a single number has no gap, only its neighbours do
    seeded.execute(text("ALTER TABLE sales_invoice ENABLE TRIGGER sales_invoice_no_edit"))

    seeded.execute(
        text(
            "INSERT INTO party_ledger (tenant_id, party_id, account, entry_date, ref_type, ref_id, "
            "doc_no, debit, credit) SELECT 1, party_id, 'receivable', CURRENT_DATE, 'sale', 0, 'X', 10, 0 "
            "FROM sales_invoice LIMIT 1"
        )
    )
    assert failed("Accounts agree with documents")
    seeded.execute(text("ALTER TABLE stock_ledger DISABLE TRIGGER stock_ledger_append_only"))
    seeded.execute(text("UPDATE stock_ledger SET qty_out = qty_out + 100000 WHERE qty_out > 0"))
    assert failed("Stock")
    seeded.execute(text("ALTER TABLE stock_ledger ENABLE TRIGGER stock_ledger_append_only"))


def test_missing_guards_and_a_missing_file_are_reported(seeded, busy, client, world):
    seeded.execute(text("DROP TRIGGER sales_invoice_no_delete ON sales_invoice"))
    check = verify.triggers_check(seeded)
    assert check.state == "fail" and "sales_invoice_no_delete" in check.detail

    import io

    bought = client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "SYS-2",
            "bill_date": today_ist().isoformat(),
            "lines": [
                {"item_id": world["tmt"]["id"], "unit": "ton", "quantity": "1", "rate": "55000"}
            ],
        },
    ).json()
    up = client.post(
        "/api/v1/attachments",
        headers=world["owner"],
        data={"ref_type": "purchase", "ref_id": str(bought["id"]), "kind": "weighbridge"},
        files={"file": ("slip.pdf", io.BytesIO(b"%PDF-1.4 slip"), "application/pdf")},
    ).json()
    from sqlalchemy import select

    from app.models.documents import Attachment
    from app.services.storage import LocalStorage, get_storage

    key = seeded.execute(
        select(Attachment.storage_key).where(Attachment.id == up["id"])
    ).scalar_one()
    path = LocalStorage(get_storage().root)._path(key)  # type: ignore[attr-defined]
    path.unlink()
    files = verify.files_check(seeded, full=False)
    assert files.state == "fail" and "slip.pdf" in files.detail


# ------------------------------------------------------------------ status and roles


def test_status_reports_backups_storage_and_unclosed_days(
    client, world, busy, monkeypatch, tmp_path
):
    owner = world["owner"]
    first = client.get("/api/v1/system/status", headers=owner).json()
    assert first["backup"]["state"] == "warn" and first["storage"]["state"] == "ok"
    assert first["test_watermark"] is True and first["migrations"]["state"] == "ok"
    assert first["gsp"]["state"] == "warn"  # the pretend provider outside production

    from app.core import config

    monkeypatch.setattr(config.get_settings(), "backup_dir", str(tmp_path))
    assert client.get("/api/v1/system/status", headers=owner).json()["backup"]["state"] == "fail"
    dump = tmp_path / "erp-20261009-0230.dump"
    dump.write_bytes(b"x")
    ok = client.get("/api/v1/system/status", headers=owner).json()
    assert ok["backup"]["state"] == "ok" and ok["last_backup_at"] is not None
    old = time.time() - 40 * 3600
    os.utime(dump, (old, old))
    stale = client.get("/api/v1/system/status", headers=owner).json()
    assert stale["backup"]["state"] == "fail" and "hours old" in stale["backup"]["detail"]


def test_a_shop_that_sold_yesterday_but_did_not_close_is_listed(client, world, seeded):
    from datetime import timedelta

    day = (today_ist() - timedelta(days=1)).isoformat()
    client.put(
        "/api/v1/rates/market",
        headers=world["owner"],
        json={"effective_date": day, "rates": [{"item_id": world["cement"]["id"], "rate": "380"}]},
    )
    sold = post(client, world, body(world, [line(world, "cement", "1")], invoice_date=day))
    assert sold.status_code == 201, sold.text
    status = client.get("/api/v1/system/status", headers=world["owner"]).json()
    assert status["unclosed"] == ["S1"]
    closed = client.post(
        "/api/v1/closings",
        headers=world["owner"],
        json={
            "location_id": world["loc"]["S1"],
            "closing_date": day,
            "counted_cash": "0",
            "opening_cash": "0",
        },
    )
    assert closed.status_code == 201, closed.text
    assert client.get("/api/v1/system/status", headers=world["owner"]).json()["unclosed"] == []


def test_system_endpoints_are_the_owners(client, world, seeded, busy):
    for who in (login(client, *COUNTER), login(client, *ACCOUNTANT)):
        assert client.get("/api/v1/system/status", headers=who).status_code == 403
        assert client.post("/api/v1/system/verify", headers=who).status_code == 403
    ran = client.post("/api/v1/system/verify?full=true", headers=world["owner"])
    assert ran.status_code == 200 and ran.json()["ok"] is True


def test_the_command_line_check_exits_with_the_result(seeded, busy, monkeypatch, capsys):
    from app.scripts import verify as cli

    class Same:
        def __enter__(self):
            return seeded

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cli, "SessionLocal", lambda: Same())
    assert cli.main([]) == 0
    assert "OK" in capsys.readouterr().out
    seeded.execute(text("DROP TRIGGER sales_invoice_no_delete ON sales_invoice"))
    assert cli.main(["--full"]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_a_forgotten_password_can_be_reset_from_the_server(client, seeded, monkeypatch, capsys):
    from app.scripts import reset_password as cli

    class Same:
        def __enter__(self):
            return seeded

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cli, "SessionLocal", lambda: Same())
    assert cli.main([]) == 2
    assert cli.main(["nobody"]) == 1
    assert cli.main(["owner"]) == 0
    printed = capsys.readouterr().out
    new = next(x for x in printed.splitlines() if x.startswith("New password for owner: ")).split(
        ": "
    )[1]
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "owner-pass-123"}
        ).status_code
        == 401
    )
    assert (
        client.post("/api/v1/auth/login", json={"username": "owner", "password": new}).status_code
        == 200
    )
