"""M25: backup and recovery from the admin, including one company.

Company A is the default company ("main", with a bill); company B is "acme". Jobs run inline on
the test session. The test that breaks a rule on purpose (deleting a bill) uses the owner
connection with triggers off.
"""
# fmt: off

import csv
import hashlib
import io
import json
import subprocess
import tarfile
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.tenancy import set_platform, set_tenant
from app.domain import backups as rules
from app.main import app
from app.models.enums import (
    BackupJobStatus,
    BackupKind,
    BackupSource,
    BackupStatus,
    PlatformAction,
)
from app.models.platform import PlatformAuditLog, PlatformBackup, PlatformBackupJob
from app.models.tenancy import Tenant
from app.services import process_runner
from app.services.platform import backups as service
from app.services.platform import company_archive as archive
from app.services.platform.purge import data_purge
from tests.conftest import as_db_owner, login
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
BACKUPS = f"{ADMIN}/backups"
SKIP = {"audit_log", "auth_session"}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "backup_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def inline(client, seeded):
    app.state.backup_launcher = service.inline_launcher(seeded, app.state.maintenance)


def _tenant_id(db, slug):
    return db.execute(select(Tenant.id).where(Tenant.slug == slug)).scalar_one()


def _make(client, boss, company_id=None, kind="company"):
    response = client.post(
        BACKUPS, headers=boss, json={"kind": kind, "company_id": company_id, "note": "test"}
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "succeeded", (job["error_code"], job["error_message"])
    return job["backup_id"]


def _snapshot(db, tenant_id):
    """Row count and a checksum of every restorable table of one company, read as the owner."""
    out = {}
    with as_db_owner(db):
        for name in archive.restored_tables():
            out[name] = db.execute(
                text(
                    f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) "  # noqa: S608
                    f'FROM "{name}" t WHERE tenant_id = :id'
                ),
                {"id": tenant_id},
            ).one()
            out[name] = tuple(out[name])
    return out


def _restore(client, boss, backup_id, company_id, confirm="RESTORE"):
    return client.post(
        f"{BACKUPS}/{backup_id}/restore",
        headers=boss,
        json={"company_id": company_id, "confirm": confirm},
    )


def _rewrite(path: Path, replace: dict[str, bytes], fix_manifest=False):
    with tarfile.open(path) as src:
        members = {m.name: src.extractfile(m).read() for m in src if m.isfile()}
    members.update(replace)
    if fix_manifest:
        manifest = json.loads(members["manifest.json"])
        for name, data in replace.items():
            manifest["tables"][name[len("tables/") : -len(".csv")]]["sha256"] = hashlib.sha256(
                data
            ).hexdigest()
        members["manifest.json"] = json.dumps(manifest).encode()
    with tarfile.open(path, "w:gz") as out:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            out.addfile(info, io.BytesIO(data))


def _retarget(db, backup_id, path):
    row = db.get(PlatformBackup, backup_id)
    row.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    db.commit()


def _bill(client, world):
    response = post(client, world, body(world, [line(world, "cement", "2")]))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _delete_bill_as_superuser(db, invoice_id):
    with as_db_owner(db):
        db.execute(text("SET LOCAL session_replication_role = replica"))
        for sql_text in (
            "DELETE FROM sales_line WHERE invoice_id = :i",
            "DELETE FROM stock_ledger WHERE ref_type = 'sale' AND ref_id = :i",
            "DELETE FROM party_ledger WHERE ref_type = 'sale' AND ref_id = :i",
            "DELETE FROM sales_invoice WHERE id = :i",
        ):
            db.execute(text(sql_text), {"i": invoice_id})
        db.execute(text("SET LOCAL session_replication_role = origin"))


# ------------------------------------------------------------------ the main promise


def test_restoring_a_company_brings_back_a_deleted_bill_and_leaves_another_company_alone(
    client, boss, world, acme, folder, inline, seeded
):
    a, b = _tenant_id(seeded, "main"), _tenant_id(seeded, "acme")
    invoice_id = _bill(client, world)
    backup_id = _make(client, boss, a)
    before_a, before_b = _snapshot(seeded, a), _snapshot(seeded, b)

    _delete_bill_as_superuser(seeded, invoice_id)
    assert _snapshot(seeded, a) != before_a
    owner = login(client, "owner", "owner-pass-123")
    assert client.get(f"/api/v1/invoices/{invoice_id}", headers=owner).status_code == 404

    done = _restore(client, boss, backup_id, a)
    assert done.status_code == 202 and done.json()["status"] == "succeeded", done.text
    assert _snapshot(seeded, a) == before_a
    assert _snapshot(seeded, b) == before_b
    owner = login(client, "owner", "owner-pass-123")  # sessions were ended by the restore
    assert client.get(f"/api/v1/invoices/{invoice_id}", headers=owner).status_code == 200

    job = done.json()
    safety = seeded.get(PlatformBackup, job["safety_backup_id"])
    assert safety.protected and safety.source is BackupSource.SAFETY
    assert safety.status is BackupStatus.VERIFIED
    actions = {r.action for r in seeded.scalars(select(PlatformAuditLog))}
    assert PlatformAction.BACKUP_RESTORE in actions and PlatformAction.BACKUP_CREATE in actions
    assert not app.state.maintenance.tenant_restoring(seeded, a)


def test_an_archive_holds_only_its_own_company_and_a_manifest(client, boss, acme, folder, inline, seeded):
    a, b = _tenant_id(seeded, "main"), _tenant_id(seeded, "acme")
    backup_id = _make(client, boss, a)
    path = folder / seeded.get(PlatformBackup, backup_id).file_name
    with tarfile.open(path) as tar:
        names = {m.name for m in tar}
        manifest = json.load(tar.extractfile("manifest.json"))
        assert "manifest.json" in names and "tables/audit_log.csv" in names
        assert all(rules.is_safe_member(n) for n in names)
        seen = 0
        for member in tar:
            if member.name.startswith("tables/"):
                rows = list(csv.DictReader(io.TextIOWrapper(tar.extractfile(member), "utf-8")))
                assert {r["tenant_id"] for r in rows} <= {str(a)}, member.name
                seen += len(rows)
    assert seen > 10 and b not in {manifest["tenant_id"]}
    assert (manifest["tenant_id"], manifest["tenant_slug"]) == (a, "main")
    assert manifest["schema_revision"] == archive.schema_revision(seeded)
    assert "subscription_payment" not in manifest["tables"]
    assert "auth_session" not in manifest["tables"]


def test_an_archive_cannot_be_restored_onto_another_company(client, boss, acme, folder, inline, seeded):
    a, b = _tenant_id(seeded, "main"), _tenant_id(seeded, "acme")
    backup_id = _make(client, boss, a)
    jobs = seeded.scalar(text("SELECT count(*) FROM platform_backup_job"))
    wrong = _restore(client, boss, backup_id, b)
    assert wrong.status_code == 409 and wrong.json()["code"] == "BACKUP_WRONG_COMPANY"
    assert seeded.scalar(text("SELECT count(*) FROM platform_backup_job")) == jobs


def test_a_schema_revision_mismatch_is_refused(client, boss, folder, inline, seeded):
    a = _tenant_id(seeded, "main")
    backup_id = _make(client, boss, a)
    path = folder / seeded.get(PlatformBackup, backup_id).file_name
    with tarfile.open(path) as tar:
        manifest = json.load(tar.extractfile("manifest.json"))
    manifest["schema_revision"] = "0001"
    _rewrite(path, {"manifest.json": json.dumps(manifest).encode()})
    _retarget(seeded, backup_id, path)
    refused = _restore(client, boss, backup_id, a)
    assert refused.status_code == 409 and refused.json()["code"] == "BACKUP_SCHEMA_MISMATCH"


def test_the_restore_needs_the_word_restore_typed_exactly(client, boss, folder, inline, seeded):
    a = _tenant_id(seeded, "main")
    backup_id = _make(client, boss, a)
    for typed in ("restore", "RESTORE ", "", "DELETE"):
        r = _restore(client, boss, backup_id, a, typed)
        assert r.status_code == 409 and r.json()["code"] == "CONFIRMATION_MISMATCH"


@pytest.mark.parametrize("how", ["file_sum", "member_sum", "bad_csv"])
def test_a_failed_restore_leaves_the_company_exactly_as_it_was(
    client, boss, world, folder, inline, seeded, how
):
    a = _tenant_id(seeded, "main")
    _bill(client, world)
    backup_id = _make(client, boss, a)
    path = folder / seeded.get(PlatformBackup, backup_id).file_name
    with tarfile.open(path) as tar:
        party = tar.extractfile("tables/party.csv").read()
    if how == "file_sum":
        _rewrite(path, {"tables/party.csv": party + b"junk"})  # row checksum no longer matches
    elif how == "member_sum":
        _rewrite(path, {"tables/party.csv": party + b"junk"})
        _retarget(seeded, backup_id, path)
    else:
        lines = party.decode().splitlines()
        cells = lines[1].split(",")
        cells[0] = "not-a-number"  # the id column
        lines[1] = ",".join(cells)
        _rewrite(path, {"tables/party.csv": ("\n".join(lines) + "\n").encode()}, fix_manifest=True)
        _retarget(seeded, backup_id, path)
    before = _snapshot(seeded, a)

    failed = _restore(client, boss, backup_id, a)
    job = failed.json()
    assert failed.status_code == 202 and job["status"] == "failed", job
    assert job["error_code"] in {"BACKUP_CORRUPT", "BACKUP_FAILED"}
    assert "not-a-number" not in json.dumps(job)  # a failure never echoes a row
    assert _snapshot(seeded, a) == before
    safety = seeded.get(PlatformBackup, job["safety_backup_id"])
    assert safety.protected and safety.status is BackupStatus.VERIFIED
    assert (folder / safety.file_name).is_file()
    audited = seeded.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == PlatformAction.BACKUP_RESTORE_FAILED)
    ).all()
    assert len(audited) == 1 and audited[0].tenant_id == a
    assert not app.state.maintenance.tenant_restoring(seeded, a)


# ------------------------------------------------------------------ the company while it restores


def test_a_company_being_restored_answers_403_and_the_others_carry_on(
    client, boss, acme, seeded
):
    a = _tenant_id(seeded, "main")
    switch = app.state.maintenance
    switch.begin_tenant_restore(a)
    try:
        refused = client.get("/api/v1/auth/me")
        assert refused.status_code == 403 and refused.json()["code"] == "TENANT_RESTORING"
        assert client.get("/api/v1/tenant").status_code == 200
        assert client.get("/api/v1/tenant", headers={"host": "acme.localhost"}).status_code == 200
        assert client.get(f"{ADMIN}/overview", headers=boss).status_code == 200
    finally:
        switch.end_tenant_restore(a)
    assert client.get("/api/v1/auth/me").status_code != 403


def test_another_process_s_running_restore_is_seen_through_the_job_row(client, seeded):
    a = _tenant_id(seeded, "main")
    job = PlatformBackupJob(
        kind="restore_company", status=BackupJobStatus.RUNNING, company_id=a
    )
    job.started_at = service._now()
    seeded.add(job)
    seeded.flush()
    app.state.maintenance.forget()
    assert client.get("/api/v1/auth/me").json()["code"] == "TENANT_RESTORING"
    job.started_at = service._now() - rules.STALE_JOB_AFTER * 2  # a dead process: ignored
    seeded.flush()
    app.state.maintenance.forget()
    assert client.get("/api/v1/auth/me").status_code != 403


# ------------------------------------------------------------------ the purge switch


def test_only_a_platform_session_with_the_purge_switch_may_remove_ledger_rows(client, world, seeded):
    _bill(client, world)
    a = _tenant_id(seeded, "main")
    delete = text("DELETE FROM stock_ledger WHERE tenant_id = :t")
    set_tenant(seeded, a)
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(delete, {"t": a})
    set_platform(seeded)
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(delete, {"t": a})
    with seeded.begin_nested() as sp:
        with data_purge(seeded):
            assert seeded.execute(delete, {"t": a}).rowcount > 0
        sp.rollback()
    seeded.info.pop("platform", None)
    with pytest.raises(RuntimeError), data_purge(seeded):
        pass


# ------------------------------------------------------------------ platform backups and tools


def test_a_platform_backup_is_dumped_verified_listed_and_streamed(client, boss, folder, inline, seeded):
    backup_id = _make(client, boss, kind="platform")
    row = seeded.get(PlatformBackup, backup_id)
    assert row.kind is BackupKind.PLATFORM and row.status is BackupStatus.VERIFIED
    dump = folder / row.file_name
    assert dump.is_file() and rules.stamp_of_platform_name(row.file_name)
    assert row.sha256 == hashlib.sha256(dump.read_bytes()).hexdigest()
    assert row.files_name and (folder / row.files_name).is_file()
    listed = client.get(BACKUPS, headers=boss).json()["items"][0]
    assert listed["restore_command"] == f"./scripts/restore.sh backups/{row.file_name}"

    streamed = client.get(f"{BACKUPS}/{backup_id}/download", headers=boss)
    assert streamed.status_code == 200 and streamed.content == dump.read_bytes()
    files = client.get(f"{BACKUPS}/{backup_id}/download?part=files", headers=boss)
    assert files.status_code == 200
    audit = seeded.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == PlatformAction.BACKUP_DOWNLOAD)
    ).all()
    assert len(audit) == 2
    # a platform backup is never restored from the web
    r = _restore(client, boss, backup_id, _tenant_id(seeded, "main"))
    assert r.status_code == 409 and r.json()["code"] == "BACKUP_PLATFORM_RESTORE_CLI"


def test_a_missing_tool_is_said_plainly(client, boss, folder, monkeypatch):
    def missing(name):
        raise process_runner.ToolMissingError(name)

    monkeypatch.setattr(process_runner, "find_tool", missing)
    tiles = client.get(f"{BACKUPS}/summary", headers=boss).json()
    assert {t["name"]: t["found"] for t in tiles["tools"]} == {
        "pg_dump": False,
        "pg_restore": False,
        "tar": False,
    }
    r = client.post(BACKUPS, headers=boss, json={"kind": "platform"})
    assert r.status_code == 409 and r.json()["code"] == "BACKUP_TOOLS_MISSING"


def test_no_folder_is_said_plainly(client, boss, monkeypatch):
    monkeypatch.setattr(get_settings(), "backup_dir", "")
    s = client.get(f"{BACKUPS}/summary", headers=boss).json()
    assert s["folder_ready"] is False and "BACKUP_DIR" in s["folder_problem"]
    r = client.post(BACKUPS, headers=boss, json={"kind": "company", "company_id": 1})
    assert r.status_code == 409 and r.json()["code"] == "BACKUP_FOLDER_UNAVAILABLE"


def test_the_password_goes_in_the_environment_never_on_the_command_line(monkeypatch, folder, seeded):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"], seen["env"] = argv, kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(process_runner.subprocess, "run", fake_run)
    conn = rules.pg_connection("postgresql+psycopg://erp:hunter2@db:5432/erp")
    exe = process_runner.find_tool("pg_dump")
    process_runner.run(
        rules.pg_dump_argv(exe, conn, folder / "x.partial"),
        password=conn.password,
        env=rules.pg_env(conn),
    )
    assert "hunter2" not in " ".join(seen["argv"]) and seen["env"]["PGPASSWORD"] == "hunter2"
    assert seen["argv"][0].startswith("/")


def test_the_runner_refuses_other_programs_and_kills_a_slow_one(monkeypatch):
    with pytest.raises(process_runner.ToolFailedError):
        process_runner.run(["/bin/ls"])
    with pytest.raises(process_runner.ToolFailedError):
        process_runner.run(["pg_dump"])  # not an absolute path
    with pytest.raises(process_runner.ToolFailedError, match="password"):
        process_runner.run(["/usr/bin/pg_dump", "--dbname=x", "--password=hunter2"], password="hunter2")

    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(process_runner.subprocess, "run", slow)
    with pytest.raises(process_runner.ToolFailedError, match="longer than"):
        process_runner.run(["/usr/bin/tar", "--version"], timeout=1)
    assert [t.name for t in process_runner.tool_status()] == ["pg_dump", "pg_restore", "tar"]
    with pytest.raises(process_runner.ToolMissingError):
        process_runner.find_tool("rm")


def test_a_real_failing_tool_reports_its_own_message():
    with pytest.raises(process_runner.ToolFailedError):
        process_runner.run([str(process_runner.find_tool("tar")), "-tzf", "/nonexistent.tar.gz"])


# ------------------------------------------------------------------ delete, upload


def test_delete_needs_the_word_delete_and_never_touches_a_protected_copy(client, boss, folder, inline, seeded):
    a = _tenant_id(seeded, "main")
    backup_id = _make(client, boss, a)
    path = folder / seeded.get(PlatformBackup, backup_id).file_name
    url = f"{BACKUPS}/{backup_id}"
    assert client.request("DELETE", url, headers=boss, json={"confirm": "delete"}).status_code == 409
    assert path.is_file()
    protected = _restore(client, boss, backup_id, a).json()["safety_backup_id"]
    refused = client.request(
        "DELETE", f"{BACKUPS}/{protected}", headers=boss, json={"confirm": "DELETE"}
    )
    assert refused.status_code == 409 and refused.json()["code"] == "BACKUP_PROTECTED"
    gone = client.request("DELETE", url, headers=boss, json={"confirm": "DELETE"})
    assert gone.status_code == 204 and not path.exists()
    assert seeded.get(PlatformBackup, backup_id) is None
    assert client.request("DELETE", url, headers=boss, json={"confirm": "DELETE"}).status_code == 404


def _upload(client, boss, name, data):
    return client.post(
        f"{BACKUPS}/upload", headers=boss, files={"file": (name, data, "application/gzip")}
    )


def test_an_uploaded_archive_is_checked_and_can_be_restored(client, boss, world, folder, inline, seeded):
    a = _tenant_id(seeded, "main")
    backup_id = _make(client, boss, a)
    path = folder / seeded.get(PlatformBackup, backup_id).file_name
    data = path.read_bytes()
    up = _upload(client, boss, "whatever-name.tar.gz", data)
    assert up.status_code == 201, up.text
    item = up.json()
    assert item["source"] == "uploaded" and item["company"]["slug"] == "main"
    assert item["file_name"] != "whatever-name.tar.gz" and (folder / item["file_name"]).is_file()
    r = _restore(client, boss, item["id"], a)
    assert r.json()["status"] == "succeeded"


def test_an_upload_must_be_a_matching_company_archive(client, boss, folder, inline, seeded, monkeypatch):
    a = _tenant_id(seeded, "main")
    backup_id = _make(client, boss, a)
    path = folder / seeded.get(PlatformBackup, backup_id).file_name
    with tarfile.open(path) as tar:
        manifest = json.load(tar.extractfile("manifest.json"))

    def with_manifest(**change):
        _rewrite(path, {"manifest.json": json.dumps(manifest | change).encode()})
        return path.read_bytes()

    assert _upload(client, boss, "x.zip", b"abc").json()["code"] == "UPLOAD_NOT_TAR_GZ"
    assert _upload(client, boss, "x.tar.gz", b"").json()["code"] == "UPLOAD_EMPTY"
    assert _upload(client, boss, "x.tar.gz", b"not a tar").json()["code"] == "BACKUP_INVALID"
    wrong = _upload(client, boss, "x.tar.gz", with_manifest(tenant_id=9999))
    assert wrong.status_code == 409 and wrong.json()["code"] == "BACKUP_WRONG_COMPANY"
    other = _upload(client, boss, "x.tar.gz", with_manifest(tenant_slug="nope"))
    assert other.json()["code"] == "BACKUP_WRONG_COMPANY"
    old = _upload(client, boss, "x.tar.gz", with_manifest(schema_revision="0001"))
    assert old.json()["code"] == "BACKUP_SCHEMA_MISMATCH"
    assert _upload(client, boss, "x.tar.gz", with_manifest(format=7)).json()["code"] == "BACKUP_INVALID"
    monkeypatch.setattr(rules, "MAX_UPLOAD_BYTES", 10)
    big = _upload(client, boss, "x.tar.gz", b"x" * 50)
    assert big.status_code == 409 and big.json()["code"] == "FILE_TOO_LARGE"
    assert not list(folder.glob("*.partial"))


def test_an_archive_with_a_path_that_escapes_is_refused(client, boss, folder, seeded):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("../evil")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    r = _upload(client, boss, "x.tar.gz", buffer.getvalue())
    assert r.status_code == 409 and r.json()["code"] == "BACKUP_INVALID"


# ------------------------------------------------------------------ schedule, retention, the loop's CLI


def test_the_schedule_is_validated_audited_and_pruning_follows_it(client, boss, folder, seeded):
    s = client.get(f"{BACKUPS}/schedule", headers=boss).json()
    assert (s["daily_time"], s["keep_daily"], s["keep_weekly"], s["keep_monthly"]) == (
        "02:30",
        30,
        8,
        12,
    )
    bad = client.put(
        f"{BACKUPS}/schedule",
        headers=boss,
        json={"daily_time": "25:00", "keep_daily": 1, "keep_weekly": 1, "keep_monthly": 1},
    )
    assert bad.status_code == 409 and bad.json()["code"] == "BAD_TIME"
    ok = client.put(
        f"{BACKUPS}/schedule",
        headers=boss,
        json={"daily_time": "01:15", "keep_daily": 2, "keep_weekly": 0, "keep_monthly": 0},
    )
    assert ok.status_code == 200 and ok.json()["daily_time"] == "01:15"
    audit = seeded.scalars(
        select(PlatformAuditLog).where(PlatformAuditLog.action == PlatformAction.BACKUP_SCHEDULE_UPDATE)
    ).one()
    assert audit.details["before"]["daily_time"] == "02:30"

    now = service._now()
    for i in range(4):  # four nightly copies, a manual one and a protected one
        row = PlatformBackup(
            kind=BackupKind.PLATFORM,
            source=BackupSource.SCHEDULED,
            file_name=f"erp-2026010{i + 1}-0230.dump",
            status=BackupStatus.VERIFIED,
            started_at=now - timedelta(days=i),
        )
        seeded.add(row)
        (folder / row.file_name).write_bytes(b"x")
    for name, source, protected in (
        ("erp-20260201-0230.dump", BackupSource.MANUAL, False),
        ("erp-20260202-0230.dump", BackupSource.SAFETY, True),
    ):
        seeded.add(
            PlatformBackup(
                kind=BackupKind.PLATFORM,
                source=source,
                file_name=name,
                status=BackupStatus.VERIFIED,
                started_at=now - timedelta(days=40),
                protected=protected,
            )
        )
    seeded.flush()
    assert service.prune(seeded, now) == 2
    left = {r.file_name for r in seeded.scalars(select(PlatformBackup))}
    assert {"erp-20260201-0230.dump", "erp-20260202-0230.dump"} <= left and len(left) == 4
    assert len(list(folder.glob("erp-2026010*.dump"))) == 2


def test_the_nightly_loop_records_its_runs_in_the_same_list(client, boss, folder, seeded):
    from app.scripts import backup_schedule

    backup_id, dump, files = service.record_scheduled_start(seeded, service._now())
    assert rules.stamp_of_platform_name(dump) and files.startswith("erp-files-")
    listed = client.get(BACKUPS, headers=boss).json()["items"]
    assert listed[0]["status"] == "running" and listed[0]["source"] == "scheduled"
    (folder / dump).write_bytes(b"dump")
    service.record_scheduled_finish(seeded, backup_id, True, None)
    row = seeded.get(PlatformBackup, backup_id)
    assert row.status is BackupStatus.VERIFIED and row.size_bytes == 4 and row.files_name is None
    _, other, _ = service.record_scheduled_start(seeded, service._now())
    assert other != dump  # two runs in one minute do not collide
    failed_id = seeded.scalars(select(PlatformBackup.id).where(PlatformBackup.file_name == other)).one()
    service.record_scheduled_finish(seeded, failed_id, False, "pg_dump broke")
    assert seeded.get(PlatformBackup, failed_id).error == "pg_dump broke"
    assert backup_schedule.main([]) == 1
    assert len(backup_schedule._time_text("02:30")) == 4


# ------------------------------------------------------------------ roles, jobs, secrets


def test_support_may_list_backups_but_not_create_download_restore_or_delete(
    client, boss, helper, folder, inline, seeded
):
    a = _tenant_id(seeded, "main")
    backup_id = _make(client, boss, a)
    assert client.get(BACKUPS, headers=helper).status_code == 200
    assert client.get(f"{BACKUPS}/summary", headers=helper).status_code == 200
    assert client.get(f"{BACKUPS}/schedule", headers=helper).status_code == 200
    job = seeded.scalars(select(PlatformBackupJob.id)).first()
    assert client.get(f"{BACKUPS}/jobs/{job}", headers=helper).status_code == 200
    assert client.get(f"{BACKUPS}/jobs/99999", headers=helper).status_code == 404
    calls = [
        client.post(BACKUPS, headers=helper, json={"kind": "platform"}),
        client.get(f"{BACKUPS}/{backup_id}/download", headers=helper),
        _restore(client, helper, backup_id, a),
        client.request("DELETE", f"{BACKUPS}/{backup_id}", headers=helper, json={"confirm": "DELETE"}),
        _upload(client, helper, "x.tar.gz", b"x"),
        client.put(
            f"{BACKUPS}/schedule",
            headers=helper,
            json={"daily_time": "02:30", "keep_daily": 1, "keep_weekly": 1, "keep_monthly": 1},
        ),
    ]
    assert [c.status_code for c in calls] == [403] * 6


def test_one_job_at_a_time_per_company_and_a_stale_one_blocks_nothing(client, boss, folder, seeded):
    a = _tenant_id(seeded, "main")
    first = client.post(BACKUPS, headers=boss, json={"kind": "company", "company_id": a})
    assert first.status_code == 202 and first.json()["status"] == "queued"
    again = client.post(BACKUPS, headers=boss, json={"kind": "company", "company_id": a})
    assert again.status_code == 409 and again.json()["code"] == "BACKUP_JOB_RUNNING"
    polled = client.get(f"{BACKUPS}/jobs/{first.json()['id']}", headers=boss).json()
    assert polled["company"]["slug"] == "main" and polled["status"] == "queued"
    job = seeded.get(PlatformBackupJob, first.json()["id"])
    job.created_at = service._now() - rules.STALE_JOB_AFTER * 2
    seeded.flush()
    assert client.post(BACKUPS, headers=boss, json={"kind": "company", "company_id": a}).status_code == 202
    assert client.post(BACKUPS, headers=boss, json={"kind": "company"}).json()["code"] == "COMPANY_REQUIRED"
    assert client.post(BACKUPS, headers=boss, json={"kind": "company", "company_id": 9999}).status_code == 404


def test_a_company_session_cannot_reach_the_backup_tables_through_the_api(client, world):
    assert client.get(BACKUPS, headers=world["owner"]).status_code in {401, 403, 404}


def test_nothing_secret_is_written_to_the_audit_log(client, boss, folder, inline, seeded):
    a = _tenant_id(seeded, "main")
    backup_id = _make(client, boss, a)
    _restore(client, boss, backup_id, a)
    client.get(f"{BACKUPS}/{backup_id}/download", headers=boss)
    rows = [
        r
        for r in seeded.scalars(select(PlatformAuditLog))
        if r.action.value.startswith("backup_")
    ]
    assert len(rows) >= 3
    text_blob = json.dumps([r.details for r in rows]).lower()
    for word in ("password", "pgpassword", "secret", "token", "postgresql://"):
        assert word not in text_blob
    summary = client.get(f"{BACKUPS}/summary", headers=boss).json()
    assert summary["verified_count"] >= 2 and summary["storage_bytes"] > 0
    assert summary["next_scheduled_at"] and summary["last_backup_at"]


def test_a_failing_unexpected_error_shows_no_internals(client, boss, folder, inline, seeded, monkeypatch):
    a = _tenant_id(seeded, "main")

    def boom(*args, **kwargs):
        raise RuntimeError("password=hunter2 row=secret")

    monkeypatch.setattr(archive, "build_archive", boom)
    r = client.post(BACKUPS, headers=boss, json={"kind": "company", "company_id": a})
    job = r.json()
    assert job["status"] == "failed" and job["error_code"] == "BACKUP_FAILED"
    assert "hunter2" not in json.dumps(job)
    failed = seeded.get(PlatformBackup, seeded.scalars(select(PlatformBackup.id)).first())
    assert failed.status is BackupStatus.FAILED and "hunter2" not in (failed.error or "")
    assert not list(folder.glob("*.partial"))


def test_the_migration_gives_a_default_schedule_and_the_new_actions(seeded):
    assert seeded.execute(text("SELECT daily_time FROM platform_backup_schedule")).scalar_one() == "02:30"
    allowed = seeded.execute(
        text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_platform_audit_log_platform_action'")
    ).scalar_one()
    for action in ("backup_create", "backup_download", "backup_upload", "backup_delete",
                   "backup_restore", "backup_restore_failed", "backup_schedule_update"):
        assert action in allowed
