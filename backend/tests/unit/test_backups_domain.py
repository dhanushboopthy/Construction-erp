"""Backup and recovery rules (Milestone 25), written before the module."""
# fmt: off

from datetime import UTC, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from app.domain import backups as b

IST = timezone(timedelta(hours=5, minutes=30))
GOOD_MANIFEST = {
    "format": 1,
    "tenant_id": 7,
    "tenant_slug": "acme",
    "schema_revision": "0038",
    "created_at": "2026-11-06T02:30:00+00:00",
    "tables": {"item": {"rows": 2, "sha256": "a" * 64}},
    "files": {"attachments/1/x.pdf": {"size": 3, "sha256": "b" * 64}},
}


# ------------------------------------------------------------------ confirmations


def test_confirmations_are_exact_and_case_sensitive():
    assert b.confirmation_ok("RESTORE", b.CONFIRM_RESTORE)
    assert b.confirmation_ok("DELETE", b.CONFIRM_DELETE)
    for typed in ("restore", "Restore", " RESTORE", "RESTORE ", "", None, "DELETE"):
        assert not b.confirmation_ok(typed, b.CONFIRM_RESTORE)
    assert not b.confirmation_ok("delete", b.CONFIRM_DELETE)


# ------------------------------------------------------------------ names


def test_platform_backups_keep_the_nightly_loop_file_names():
    now = datetime(2026, 11, 6, 2, 30, 59, tzinfo=UTC)
    assert b.platform_names(now) == ("erp-20261106-0230.dump", "erp-files-20261106-0230.tar.gz")
    assert b.stamp_of_platform_name("erp-20261106-0230.dump") == "20261106-0230"
    assert b.stamp_of_platform_name("erp-files-20261106-0230.tar.gz") is None
    assert b.stamp_of_platform_name("../erp-20261106-0230.dump") is None
    assert b.stamp_of_platform_name("notes.dump") is None


def test_a_company_archive_is_named_after_the_company_and_the_second():
    now = datetime(2026, 11, 6, 2, 30, 59, tzinfo=UTC)
    assert b.company_name("acme", now) == "company-acme-20261106-023059.tar.gz"
    assert b.is_stored_name("company-acme-20261106-023059.tar.gz")
    assert b.is_stored_name("erp-20261106-0230.dump")
    assert b.is_stored_name("erp-files-20261106-0230.tar.gz")
    for bad in ("../x.tar.gz", "a/b.dump", "x.tar.gz", "erp-1.dump;rm", ""):
        assert not b.is_stored_name(bad)


def test_the_restore_command_is_shown_not_run():
    assert (
        b.restore_command("erp-20261106-0230.dump")
        == "./scripts/restore.sh backups/erp-20261106-0230.dump"
    )
    with pytest.raises(ValueError, match="dump name"):
        b.restore_command("erp-1.dump; rm -rf /")


# ------------------------------------------------------------------ the manifest


def test_a_matching_manifest_is_accepted():
    assert b.check_manifest(GOOD_MANIFEST, tenant_id=7, tenant_slug="acme", revision="0038") is None


def test_a_manifest_for_another_company_is_refused_before_the_schema_is_looked_at():
    assert (
        b.check_manifest(GOOD_MANIFEST, tenant_id=8, tenant_slug="beta", revision="0099")
        is b.ArchiveProblem.WRONG_COMPANY
    )
    # same id, different slug (an id re-used after a rebuild) is also another company
    assert (
        b.check_manifest(GOOD_MANIFEST, tenant_id=7, tenant_slug="beta", revision="0038")
        is b.ArchiveProblem.WRONG_COMPANY
    )


def test_a_manifest_from_another_schema_revision_is_refused():
    assert (
        b.check_manifest(GOOD_MANIFEST, tenant_id=7, tenant_slug="acme", revision="0039")
        is b.ArchiveProblem.SCHEMA_MISMATCH
    )


@pytest.mark.parametrize(
    "change",
    [
        {"format": 2},
        {"format": None},
        {"tenant_id": "7"},
        {"tenant_slug": None},
        {"schema_revision": 38},
        {"tables": []},
        {"tables": {"item": {"rows": -1, "sha256": "a" * 64}}},
        {"tables": {"item": {"rows": 1, "sha256": "short"}}},
        {"tables": {"item; drop": {"rows": 1, "sha256": "a" * 64}}},
        {"tables": {"item": "x"}},
        {"files": []},
        {"files": {"../escape": {"size": 1, "sha256": "b" * 64}}},
        {"files": {"ok": {"size": "1", "sha256": "b" * 64}}},
        {"files": {"ok": {"size": 1, "sha256": "zz"}}},
        {"files": {"ok": 5}},
    ],
)
def test_a_manifest_that_is_not_one_of_ours_is_invalid(change):
    manifest = GOOD_MANIFEST | change
    assert (
        b.check_manifest(manifest, tenant_id=7, tenant_slug="acme", revision="0038")
        is b.ArchiveProblem.INVALID
    )


def test_a_manifest_that_is_not_an_object_is_invalid():
    for value in (None, [], "x", 3):
        assert (
            b.check_manifest(value, tenant_id=7, tenant_slug="acme", revision="0038")  # type: ignore[arg-type]
            is b.ArchiveProblem.INVALID
        )
    missing = {k: v for k, v in GOOD_MANIFEST.items() if k != "tables"}
    assert (
        b.check_manifest(missing, tenant_id=7, tenant_slug="acme", revision="0038")
        is b.ArchiveProblem.INVALID
    )


# ------------------------------------------------------------------ archive members


def test_only_known_safe_member_names_are_read_from_an_archive():
    for ok in ("manifest.json", "tables/item.csv", "files/attachments/1/x.pdf", "files/logo/1/a.png"):
        assert b.is_safe_member(ok), ok
    for bad in (
        "/etc/passwd",
        "../manifest.json",
        "tables/../../x.csv",
        "tables/item.txt",
        "tables/it em.csv",
        "files/../x",
        "files//x",
        "other/x",
        "files/",
        "",
        "files/a\\b",
        "files/a\x00b",
    ):
        assert not b.is_safe_member(bad), bad


def test_table_names_are_plain():
    assert b.is_table_name("sales_invoice") and not b.is_table_name("Sales") and not b.is_table_name("a;b")


# ------------------------------------------------------------------ foreign-key order


def test_tables_come_out_parents_first_and_the_same_way_every_time():
    deps = {"line": {"invoice", "item"}, "invoice": {"party"}, "item": set(), "party": set()}
    order = b.dependency_order(deps)
    assert order == ["item", "party", "invoice", "line"]
    assert b.reverse_order(deps) == ["line", "invoice", "party", "item"]
    # a table pointing at itself (a parent column) is not a cycle
    assert b.dependency_order({"a": {"a"}}) == ["a"]
    # a parent outside the set (the company row itself) is ignored
    assert b.dependency_order({"a": {"tenant"}}) == ["a"]


def test_a_foreign_key_cycle_is_an_error():
    with pytest.raises(ValueError, match="cycle"):
        b.dependency_order({"a": {"b"}, "b": {"a"}})


# ------------------------------------------------------------------ uploads


def test_an_upload_must_be_a_company_tar_gz_within_the_limit():
    assert b.upload_problem("company-acme-1.tar.gz", 1000) is None
    assert b.upload_problem("anything.tar.gz", b.MAX_UPLOAD_BYTES) is None
    assert b.upload_problem("anything.zip", 10) == "NOT_TAR_GZ"
    assert b.upload_problem("anything.TAR.GZ", 10) == "NOT_TAR_GZ"
    assert b.upload_problem("", 10) == "NOT_TAR_GZ"
    assert b.upload_problem(None, 10) == "NOT_TAR_GZ"
    assert b.upload_problem("a.tar.gz", 0) == "EMPTY"
    assert b.upload_problem("a.tar.gz", b.MAX_UPLOAD_BYTES + 1) == "TOO_LARGE"


# ------------------------------------------------------------------ schedule


def test_the_daily_time_is_hours_and_minutes():
    assert b.parse_daily_time("02:30") == time(2, 30)
    assert b.parse_daily_time("23:59") == time(23, 59)
    assert b.format_daily_time(time(2, 5)) == "02:05"
    for bad in ("2:30", "24:00", "12:60", "0230", "", "ab:cd", None):
        with pytest.raises(ValueError, match="HH:MM"):
            b.parse_daily_time(bad)  # type: ignore[arg-type]


def test_retention_counts_are_whole_numbers_in_range():
    for n in (0, 1, 30, 365):
        assert b.retention_ok(n)
    for n in (-1, 366):
        assert not b.retention_ok(n)
    assert not b.retention_ok(True)  # a bool is not a count
    assert not b.retention_ok("3")  # type: ignore[arg-type]


def test_next_scheduled_is_today_if_it_has_not_passed_else_tomorrow():
    at = time(2, 30)
    before = datetime(2026, 11, 6, 1, 0, tzinfo=IST)
    after = datetime(2026, 11, 6, 3, 0, tzinfo=IST)
    assert b.next_scheduled(before, at, IST) == datetime(2026, 11, 6, 2, 30, tzinfo=IST)
    assert b.next_scheduled(after, at, IST) == datetime(2026, 11, 7, 2, 30, tzinfo=IST)
    exactly = datetime(2026, 11, 6, 2, 30, tzinfo=IST)
    assert b.next_scheduled(exactly, at, IST) == datetime(2026, 11, 7, 2, 30, tzinfo=IST)
    # given in UTC, answered in UTC, the same instant
    assert b.next_scheduled(before.astimezone(UTC), at, IST).utcoffset() == timedelta(0)


# ------------------------------------------------------------------ retention


def _fact(i, day, *, protected=False, source="scheduled", kind="platform", status="verified"):
    return b.BackupFacts(
        id=i,
        created_at=datetime(2026, 11, day, 2, 30, tzinfo=IST),
        protected=protected,
        source=source,
        kind=kind,
        status=status,
    )


def test_retention_keeps_the_newest_per_day_week_and_month_and_prunes_the_rest():
    today = datetime(2026, 11, 20, 9, 0, tzinfo=IST).date()
    facts = [_fact(i, i) for i in range(1, 21)]  # one scheduled backup per day, 1..20 November
    pruned = b.backups_to_prune(
        facts, keep_daily=3, keep_weekly=0, keep_monthly=0, today=today, tz=IST
    )
    assert sorted(pruned) == list(range(1, 18))  # only the last three days survive
    kept_all = b.backups_to_prune(
        facts, keep_daily=30, keep_weekly=0, keep_monthly=0, today=today, tz=IST
    )
    assert kept_all == []


def test_weekly_and_monthly_copies_survive_the_daily_window():
    today = datetime(2026, 11, 20, 9, 0, tzinfo=IST).date()
    facts = [_fact(i, i) for i in range(1, 21)]
    pruned = set(
        b.backups_to_prune(facts, keep_daily=2, keep_weekly=2, keep_monthly=1, today=today, tz=IST)
    )
    kept = {f.id for f in facts} - pruned
    # the two newest days, the newest of each of the two latest weeks (19th is in the daily
    # window), and the newest of the month
    assert {19, 20} <= kept
    assert 16 in kept or 15 in kept or 17 in kept  # the previous week's newest, 15 (Sunday)
    assert 20 in kept and 1 not in kept


def test_two_backups_on_one_day_keep_only_the_newest():
    today = datetime(2026, 11, 20, 9, 0, tzinfo=IST).date()
    early = b.BackupFacts(1, datetime(2026, 11, 20, 1, 0, tzinfo=IST), False, "scheduled", "platform", "verified")
    late = b.BackupFacts(2, datetime(2026, 11, 20, 8, 0, tzinfo=IST), False, "scheduled", "platform", "verified")
    pruned = b.backups_to_prune(
        [early, late], keep_daily=5, keep_weekly=0, keep_monthly=0, today=today, tz=IST
    )
    assert pruned == [1]


def test_pruning_never_touches_protected_manual_company_uploaded_or_running_backups():
    today = datetime(2026, 11, 20, 9, 0, tzinfo=IST).date()
    old = [
        _fact(1, 1, protected=True),
        _fact(2, 2, source="manual"),
        _fact(3, 3, source="safety"),
        _fact(4, 4, kind="company"),
        _fact(5, 5, source="uploaded", kind="company"),
        _fact(6, 6, status="running"),
        _fact(7, 7),
        _fact(8, 8),
    ]
    pruned = b.backups_to_prune(
        old, keep_daily=1, keep_weekly=0, keep_monthly=0, today=today, tz=IST
    )
    assert pruned == [7]


def test_a_failed_scheduled_backup_is_pruned_and_never_counts_as_a_copy():
    today = datetime(2026, 11, 20, 9, 0, tzinfo=IST).date()
    good = _fact(1, 19)
    bad = _fact(2, 20, status="failed")
    pruned = b.backups_to_prune(
        [good, bad], keep_daily=1, keep_weekly=0, keep_monthly=0, today=today, tz=IST
    )
    # the failed one takes no daily slot, so the good one is the single kept copy
    assert pruned == [2]


# ------------------------------------------------------------------ jobs


def test_a_job_that_started_long_ago_is_stale():
    now = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
    assert not b.job_is_stale(now - timedelta(minutes=5), now)
    assert b.job_is_stale(now - b.STALE_JOB_AFTER - timedelta(seconds=1), now)
    assert b.job_is_stale(None, now)


# ------------------------------------------------------------------ processes


URL = "postgresql+psycopg://erp:s3cr3t%40pw@db.internal:5433/erpdb"


def test_a_database_url_is_taken_apart_and_the_password_kept_apart():
    c = b.pg_connection(URL)
    assert (c.host, c.port, c.user, c.dbname, c.password) == (
        "db.internal",
        5433,
        "erp",
        "erpdb",
        "s3cr3t@pw",
    )
    d = b.pg_connection("postgresql://u@h/d")
    assert (d.host, d.port, d.user, d.dbname, d.password) == ("h", 5432, "u", "d", "")
    with pytest.raises(ValueError, match="PostgreSQL"):
        b.pg_connection("mysql://u@h/d")
    with pytest.raises(ValueError, match="PostgreSQL"):
        b.pg_connection("postgresql://u@h")


def test_no_password_ever_appears_in_a_command_line():
    c = b.pg_connection(URL)
    dump = b.pg_dump_argv(Path("/usr/bin/pg_dump"), c, Path("/backups/x.dump.partial"))
    check = b.pg_restore_list_argv(Path("/usr/bin/pg_restore"), Path("/backups/x.dump"))
    tar = b.tar_create_argv(Path("/usr/bin/tar"), Path("/b/f.tar.gz"), Path("/files"))
    for argv in (dump, check, tar):
        assert all(isinstance(a, str) for a in argv)
        b.assert_no_secret(argv, c.password)
        assert "s3cr3t" not in " ".join(argv) and "%40" not in " ".join(argv)
        assert argv[0].startswith("/")  # an absolute path, never a name looked up on PATH
    assert "--format=custom" in dump and "--file=/backups/x.dump.partial" in dump
    assert "--host=db.internal" in dump and "--username=erp" in dump and "--dbname=erpdb" in dump
    assert not any(a.startswith("--password") or a == "-W" for a in dump)
    assert b.pg_env(c) == {"PGPASSWORD": "s3cr3t@pw"}
    assert b.pg_env(b.pg_connection("postgresql://u@h/d")) == {}


def test_a_command_line_carrying_the_password_is_refused():
    with pytest.raises(ValueError, match="password"):
        b.assert_no_secret(["pg_dump", "--dbname=postgresql://u:hunter2@h/d"], "hunter2")
    b.assert_no_secret(["pg_dump"], "")  # nothing to leak
    for leak in (["x", "hunter2"], ["x", "--password=abc"]):
        with pytest.raises(ValueError, match="password"):
            b.assert_no_secret(leak, "hunter2" if "hunter2" in leak else "abc")
    b.assert_no_secret(["--username=erp"], "erp")  # a short password is not a substring hunt


def test_a_tar_listing_command_is_argv_only():
    assert b.tar_list_argv(Path("/usr/bin/tar"), Path("/b/f.tar.gz")) == [
        "/usr/bin/tar",
        "-tzf",
        "/b/f.tar.gz",
    ]


def test_a_backup_dated_after_today_is_left_alone():
    today = datetime(2026, 11, 20, 9, 0, tzinfo=IST).date()
    future = b.BackupFacts(9, datetime(2026, 11, 25, 2, 0, tzinfo=IST), False, "scheduled", "platform", "verified")
    assert (
        b.backups_to_prune([future], keep_daily=0, keep_weekly=0, keep_monthly=0, today=today, tz=IST)
        == []
    )


def test_only_allow_listed_tools_have_a_command():
    assert frozenset({"pg_dump", "pg_restore", "tar"}) == b.TOOLS
    assert b.tool_dirs("/opt/pg/bin")[0] == "/opt/pg/bin"
    assert "/usr/bin" in b.tool_dirs("")
    assert b.tool_dirs("")[0] != ""
