"""M24: system health, the notifications bell, maintenance mode and the audit log.

Admin calls run at admin.localhost, company calls on the default company ("main") or at
acme.localhost, as the app's database role.
"""

import csv
import io
import json
import re
import shutil
from collections import namedtuple
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_db
from app.core.tenancy import set_platform
from app.domain.platform_health import RESTORE_MESSAGE
from app.main import app, create_app
from app.models.enums import PlatformAction
from app.services.platform import audit as platform_audit
from app.services.platform import system as system_service
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    helper,
    onboard,
    owner_of,
)
from tests.integration.test_sales import body, line, post, world  # noqa: F401 - the fixture
from tests.integration.test_subscriptions import move_trial_end, plan_by_code, renew

pytestmark = pytest.mark.integration

ADMIN = "/api/v1/admin"
MAINTENANCE = f"{ADMIN}/system/maintenance"
SECRET_KEYS = re.compile(r"password|secret|token|dsn|_url|key|credential", re.IGNORECASE)


def _bill(client, world):
    return post(client, world, body(world, [line(world, "cement", "2")]))


def _switch(client, headers, enabled, message=None):
    response = client.post(
        MAINTENANCE, headers=headers, json={"enabled": enabled, "message": message}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _bell(client, headers):
    response = client.get(f"{ADMIN}/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return {n["id"]: n for n in response.json()["items"]}


def _keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


# ------------------------------------------------------------------ maintenance mode


def test_maintenance_closes_company_writes_but_not_the_admin_or_the_health_checks(
    client, boss, world
):
    assert client.get("/api/v1/maintenance").json() == {"enabled": False, "message": None}
    shown = _switch(client, boss, True, "  Back at 9 pm  ")
    assert (shown["enabled"], shown["message"], shown["cause"]) == (
        True,
        "Back at 9 pm",
        "operator",
    )
    assert shown["changed_by"] == "Duolink Ops" and shown["enabled_at"]

    saved = _bill(client, world)
    assert saved.status_code == 503
    assert saved.json()["code"] == "MAINTENANCE" and saved.json()["message"] == "Back at 9 pm"
    assert saved.json()["maintenance_message"] == "Back at 9 pm"
    signed_in = client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "owner-pass-123"}
    )
    assert signed_in.status_code == 503

    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health/ready").status_code == 200
    assert client.get("/api/v1/tenant").status_code == 200  # the "Back soon" screen's name
    assert client.get(f"{ADMIN}/overview", headers=boss).status_code == 200
    assert client.get("/api/v1/maintenance").json() == {"enabled": True, "message": "Back at 9 pm"}

    off = _switch(client, boss, False)
    assert (off["enabled"], off["cause"]) == (False, None)
    assert _bill(client, world).status_code == 201  # no restart needed


def test_every_company_route_answers_503_while_maintenance_is_on(client, boss):
    _switch(client, boss, True)
    open_routes = {("GET", "/api/v1/tenant"), ("GET", "/api/v1/tenant/logo")}
    checked = 0
    for path, methods in app.openapi()["paths"].items():
        if path.startswith(("/api/v1/admin", "/api/v1/health", "/api/v1/maintenance")):
            continue
        url = re.sub(r"\{\w+\}", "1", path)
        for method in methods:
            if (method.upper(), path) in open_routes:
                continue
            response = client.request(method.upper(), url, json={})
            assert response.status_code == 503, f"{method} {path}: {response.status_code}"
            assert response.json()["code"] == "MAINTENANCE"
            checked += 1
    assert checked > 100


def test_maintenance_survives_a_restart(client, boss, seeded):
    _switch(client, boss, True, "Moving servers")
    restarted = create_app()  # a new process: an empty switch, which must read the row
    restarted.dependency_overrides[get_db] = lambda: seeded
    fresh = TestClient(restarted)
    refused = fresh.get("/api/v1/auth/me")
    assert refused.status_code == 503 and refused.json()["message"] == "Moving servers"
    assert fresh.get("/api/v1/health/live").status_code == 200


def test_another_process_switching_is_seen_within_five_seconds(client, world, seeded, monkeypatch):
    from app.services import maintenance as switch_module

    assert _bill(client, world).status_code == 201  # the switch is now read and cached as off
    seeded.execute(text("UPDATE platform_maintenance SET enabled = true, message = 'Elsewhere'"))
    assert client.get("/api/v1/locations", headers=world["owner"]).status_code == 200  # cached
    later = switch_module.time.monotonic() + 5
    monkeypatch.setattr(switch_module.time, "monotonic", lambda: later)
    refused = client.get("/api/v1/locations", headers=world["owner"])
    assert refused.status_code == 503 and refused.json()["message"] == "Elsewhere"


def test_the_restore_flag_is_separate_and_in_memory_only(client, boss, world, seeded):
    app.state.maintenance.set_restoring(True)
    refused = _bill(client, world)
    assert refused.status_code == 503 and refused.json()["message"] == RESTORE_MESSAGE
    shown = client.get(MAINTENANCE, headers=boss).json()
    assert (shown["enabled"], shown["cause"], shown["restoring"]) == (True, "restore", True)
    assert shown["operator_enabled"] is False  # nothing was persisted
    restarted = create_app()
    restarted.dependency_overrides[get_db] = lambda: seeded
    assert TestClient(restarted).get("/api/v1/locations", headers=world["owner"]).status_code == 200
    app.state.maintenance.set_restoring(False)
    assert _bill(client, world).status_code == 201


def test_switching_maintenance_is_for_a_super_admin_and_is_audited(client, boss, helper):
    refused = client.post(MAINTENANCE, headers=helper, json={"enabled": True})
    assert refused.status_code == 403
    assert client.get(MAINTENANCE, headers=helper).status_code == 200  # Support may look
    too_long = client.post(MAINTENANCE, headers=boss, json={"enabled": True, "message": "x" * 301})
    assert too_long.status_code == 409 and too_long.json()["code"] == "MESSAGE_TOO_LONG"

    _switch(client, boss, True, "Back at 9 pm")
    _switch(client, boss, False)
    entries = client.get(f"{ADMIN}/audit", headers=boss).json()["items"]
    assert [e["action"] for e in entries[:2]] == ["maintenance_off", "maintenance_on"]
    assert entries[1]["details"] == {"message": "Back at 9 pm", "was_on": False}
    assert entries[1]["admin_email"] == "ops@duolink.app"


# ------------------------------------------------------------------ health


def test_health_answers_every_admin_and_never_a_secret(client, helper, acme, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path))
    made = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=3)
    (tmp_path / ".last-success").write_text(f"{int(made.timestamp())}\n")
    (tmp_path / ".offsite-success").write_text(f"{int(made.timestamp()) + 600}\n")
    owner = owner_of(client)
    client.post(
        "/api/v1/support/tickets",
        headers=owner,
        json={"subject": "A question", "category": "other", "body": "Hello"},
    )

    response = client.get(f"{ADMIN}/system/health", headers=helper)
    assert response.status_code == 200, response.text
    found = response.json()
    assert [k for k in _keys(found) if SECRET_KEYS.search(k)] == []
    raw = response.text
    for secret in (settings.database_url, settings.jwt_secret, "erp:erp@"):
        assert secret not in raw

    assert found["api"]["uptime_seconds"] >= 0 and found["api"]["python_version"].startswith("3.")
    assert found["api"]["version"] == settings.app_version
    assert found["api"]["changelog_version"]  # read from CHANGELOG.md in a checkout
    database = found["database"]
    assert database["up"] is True and database["size_bytes"] > 0
    assert database["connections_in_use"] >= 1 and database["migrations"]["state"] == "ok"
    assert re.fullmatch(r"\d+\.\d{2}", database["round_trip_ms"])
    backup = found["backup"]
    assert datetime.fromisoformat(backup["last_success_at"]) == made
    assert backup["age_hours"] == 3 and backup["stale"] is False
    assert datetime.fromisoformat(backup["offsite_synced_at"]) == made + timedelta(minutes=10)
    disks = {d["name"]: d for d in found["disks"]}
    assert disks["backups"]["watched"] is True and disks["backups"]["free_bytes"] > 0
    counters = found["counters"]
    assert counters["companies"] >= 2 and counters["active_users"] >= 1
    assert counters["open_tickets"] == 1 and counters["admin_actions_today"] >= 1
    assert counters["audit_events_today"] >= 1 and counters["open_sessions"] >= 1
    assert found["maintenance"] == {"enabled": False, "message": None}


def test_platform_settings_show_configuration_but_no_secret(client, helper):
    response = client.get(f"{ADMIN}/system/settings", headers=helper)
    assert response.status_code == 200, response.text
    found = response.json()
    lifetimes = {"access_token_minutes", "refresh_token_hours"}  # durations, not tokens
    assert [k for k in _keys(found) if SECRET_KEYS.search(k) and k not in lifetimes] == []
    settings = get_settings()
    for secret in (settings.database_url, settings.jwt_secret):
        assert secret not in response.text
    assert found["security"]["login_max_attempts"] == settings.login_max_attempts
    assert found["lifecycle"] == {
        "trial_days": 14,
        "max_trial_days": 90,
        "banner_days": 7,
        "ending_soon_days": 7,
        "notice_days": 7,
        "backup_stale_hours": 26,
        "disk_low_free_percent": 20,
        "failed_admin_sign_ins_limit": 10,
        "maintenance_cache_seconds": 5,
    }


# ------------------------------------------------------------------ the bell


def test_a_quiet_platform_rings_no_bell(client, helper, monkeypatch):
    monkeypatch.setattr(get_settings(), "backup_dir", "")
    response = client.get(f"{ADMIN}/notifications", headers=helper).json()
    assert response == {"count": 0, "items": []}


def test_the_bell_rings_for_subscriptions_expiring_within_seven_days(client, boss):
    company = onboard(client, boss)
    sub = client.get(
        f"{ADMIN}/billing/subscriptions", headers=boss, params={"tenant_id": company["id"]}
    ).json()["items"][0]
    renew(client, boss, sub, plan_by_code(client, boss, "BASIC"), custom_days=3)
    item = _bell(client, boss)["subscriptions-expiring"]
    assert item["level"] == "warning" and item["title"] == "1 subscription ends within 7 days"
    assert item["link"] == "/admin/subscriptions?status=active&expiring_within=7"


def test_the_bell_rings_for_expired_companies(client, boss, acme):
    move_trial_end(client, boss, acme, datetime.now(UTC) - timedelta(days=2))
    item = _bell(client, boss)["companies-expired"]
    assert item["level"] == "critical" and item["title"] == "1 company has expired"


def test_the_bell_rings_for_trials_ending(client, boss, acme):
    move_trial_end(client, boss, acme, datetime.now(UTC) + timedelta(days=2))
    item = _bell(client, boss)["trials-ending"]
    assert item["level"] == "warning" and item["title"] == "1 trial ends within 7 days"


def test_the_bell_counts_new_and_urgent_tickets_as_the_support_list_does(client, boss, acme):
    owner = owner_of(client)
    for priority in ("normal", "urgent"):
        client.post(
            "/api/v1/support/tickets",
            headers=owner,
            json={"subject": "Help", "category": "other", "priority": priority, "body": "Hi"},
        )
    counts = client.get(f"{ADMIN}/support/tickets", headers=boss).json()["counts"]
    bell = _bell(client, boss)
    assert bell["tickets-new"]["title"] == f"{counts['open']} new tickets are waiting"
    assert bell["tickets-urgent"]["title"] == f"{counts['urgent_open']} urgent ticket is open"
    assert bell["tickets-new"]["level"] == "info" and bell["tickets-urgent"]["level"] == "warning"


def test_the_bell_rings_when_the_last_backup_is_older_than_26_hours(
    client, boss, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "backup_dir", str(tmp_path))
    assert _bell(client, boss)["backup-stale"]["title"] == "No backup has been recorded"
    old = datetime.now(UTC) - timedelta(hours=30)
    (tmp_path / ".last-success").write_text(str(int(old.timestamp())))
    item = _bell(client, boss)["backup-stale"]
    assert item["level"] == "critical" and item["title"] == "The last backup is 30 hours old"
    (tmp_path / ".last-success").write_text(str(int(datetime.now(UTC).timestamp())))
    assert "backup-stale" not in _bell(client, boss)


def test_the_bell_rings_when_a_disk_is_below_20_percent_free(client, boss, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "backup_dir", str(tmp_path))
    (tmp_path / ".last-success").write_text(str(int(datetime.now(UTC).timestamp())))
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(system_service.shutil, "disk_usage", lambda _: usage(1000, 850, 150))
    bell = _bell(client, boss)
    assert bell["disk-low-backups"]["title"] == "The backups disk is 15.0% free"
    assert bell["disk-low-files"]["level"] == "critical"
    disks = client.get(f"{ADMIN}/system/health", headers=boss).json()["disks"]
    assert all(d["low"] for d in disks)
    monkeypatch.setattr(system_service.shutil, "disk_usage", shutil.disk_usage)


def test_the_bell_rings_after_more_than_ten_failed_admin_sign_ins_in_a_day(client, boss, seeded):
    for _ in range(10):
        platform_audit.record(seeded, PlatformAction.LOGIN_FAILED, None, details={"email": "x"})
    seeded.flush()
    assert "admin-sign-ins-failed" not in _bell(client, boss)
    platform_audit.record(seeded, PlatformAction.LOGIN_FAILED, None, details={"email": "x"})
    seeded.flush()
    item = _bell(client, boss)["admin-sign-ins-failed"]
    assert item["title"] == "11 failed admin sign-ins in 24 hours"
    assert item["link"] == "/admin/audit?tab=admin&action=login_failed"


def test_support_sessions_are_not_counted_until_owner_granted_access_is_merged(seeded):
    # Milestone 23 (a parallel branch) adds the support_session table; the merge wires it here.
    assert system_service.open_support_sessions(seeded, datetime.now(UTC)) == 0


# ------------------------------------------------------------------ the audit log


def _audit(client, headers, **params):
    response = client.get(f"{ADMIN}/audit", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_audit_log_filters_by_admin_company_action_and_dates(client, boss, helper, acme):
    other = onboard(client, boss, slug="beta", name="Beta Steels", shop_code="BS")
    client.post(f"{ADMIN}/tenants/{acme['id']}/suspend", headers=boss, json={"reason": "Test"})
    staff = {m["email"]: m["id"] for m in client.get(f"{ADMIN}/staff", headers=boss).json()}
    owner = owner_of(client, "beta")
    ticket = client.post(
        "/api/v1/support/tickets",
        headers=owner,
        json={"subject": "Help", "category": "other", "body": "Hi"},
    ).json()["id"]
    client.post(f"{ADMIN}/support/tickets/{ticket}/reply", headers=helper, json={"body": "Hello"})

    by_helper = _audit(client, boss, admin_id=staff["help@duolink.app"])
    assert [e["action"] for e in by_helper["items"] if e["action"] != "login"] == ["support_reply"]
    at_acme = _audit(client, boss, tenant_id=acme["id"])
    assert {e["action"] for e in at_acme["items"]} == {"tenant_create", "tenant_suspend"}
    created = _audit(client, boss, action="tenant_create")
    assert {e["tenant_slug"] for e in created["items"]} >= {"acme", other["slug"]}
    today = datetime.now(UTC).date()
    assert _audit(client, boss, date_from=today.isoformat())["total"] >= 4
    tomorrow = (today + timedelta(days=2)).isoformat()
    assert _audit(client, boss, date_from=tomorrow)["total"] == 0
    backwards = client.get(
        f"{ADMIN}/audit", headers=boss, params={"date_from": tomorrow, "date_to": today.isoformat()}
    )
    assert backwards.status_code == 409 and backwards.json()["code"] == "DATE_RANGE"


def test_sign_ins_filter_by_dates(client, boss, acme):
    owner_of(client)
    today = datetime.now(UTC).date()
    found = client.get(
        f"{ADMIN}/activity",
        headers=boss,
        params={"tenant_id": acme["id"], "date_from": (today - timedelta(days=1)).isoformat()},
    ).json()
    assert found["total"] >= 1
    later = client.get(
        f"{ADMIN}/activity",
        headers=boss,
        params={"date_from": (today + timedelta(days=2)).isoformat()},
    ).json()
    assert later["total"] == 0


def test_the_audit_csv_has_one_row_per_action_with_the_screens_filters(client, boss, acme):
    client.post(f"{ADMIN}/tenants/{acme['id']}/suspend", headers=boss, json={"reason": "=Test"})
    client.post(f"{ADMIN}/tenants/{acme['id']}/reactivate", headers=boss)
    for params in ({}, {"tenant_id": acme["id"]}, {"action": "tenant_suspend"}):
        screen = _audit(client, boss, limit=200, **params)
        exported = client.get(f"{ADMIN}/audit/export", headers=boss, params=params)
        assert exported.status_code == 200, exported.text
        assert exported.headers["content-type"].startswith("text/csv")
        assert "attachment" in exported.headers["content-disposition"]
        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert [int(r["id"]) for r in rows] == [e["id"] for e in screen["items"]]
        assert len(rows) == screen["total"]
    suspended = next(r for r in rows if r["action"] == "tenant_suspend")
    assert suspended["company"] == "acme" and suspended["admin"] == "ops@duolink.app"
    assert json.loads(suspended["details"])["reason"] == "=Test"  # inside JSON, so still text

    exports = _audit(client, boss, action="audit_export")["items"]
    assert len(exports) == 3
    assert exports[0]["details"] == {"filters": {"action": "tenant_suspend"}, "rows": 1}


def test_only_a_super_admin_exports_the_audit_log(client, helper):
    refused = client.get(f"{ADMIN}/audit/export", headers=helper)
    assert refused.status_code == 403 and refused.json()["code"] == "PERMISSION_DENIED"


def test_the_maintenance_row_is_one_row_only(seeded):
    set_platform(seeded)
    count = seeded.execute(text("SELECT count(*) FROM platform_maintenance")).scalar_one()
    assert count == 1
    with pytest.raises(Exception, match="singleton"), seeded.begin_nested():
        seeded.execute(text("INSERT INTO platform_maintenance (id, enabled) VALUES (2, false)"))


def test_a_company_sees_the_notice_without_signing_in(client, boss):
    _switch(client, boss, True, "Back at 9 pm")
    notice = client.get("/api/v1/maintenance", headers={"host": "acme.localhost"})
    assert notice.status_code == 200 and notice.json()["enabled"] is True
