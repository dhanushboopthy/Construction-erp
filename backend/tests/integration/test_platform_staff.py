"""M17 (ADR 0013): two kinds of Duolink staff, the staff API and the forced password change.

A Super Admin changes things; Support reads. Every route under /api/v1/admin is walked, so a
write added later without `SuperAdminOnly` fails here.
"""

import json
import re

import jwt
import pytest
from sqlalchemy import text

from app.core.security import decode_platform_token
from app.main import app
from app.models.enums import PlatformRole
from app.scripts import create_platform_admin as script
from app.services.platform import auth as platform_auth

pytestmark = pytest.mark.integration

ADMIN = "admin.localhost"
SUPER = ("ops@duolink.app", "admin-pass-123")
SUPPORT = ("help@duolink.app", "support-pass-123")
NEW_COMPANY = {
    "name": "Acme Steels",
    "slug": "acme",
    "state_code": "33",
    "owner_username": "ravi",
    "owner_full_name": "Ravi Kumar",
    "owner_password": "ravi-pass-123",
}
STAFF = {
    "full_name": "Meena Iyer",
    "email": "meena@duolink.app",
    "mobile": "+91 98765 43210",
    "password": "temp-pass-123",
}
# The sign-in routes themselves: they cannot need a signed-in Super Admin.
NOT_ADMIN_WRITES = {
    ("POST", "/api/v1/admin/auth/login"),
    ("POST", "/api/v1/admin/auth/refresh"),
    ("POST", "/api/v1/admin/auth/logout"),
    ("POST", "/api/v1/admin/auth/change-password"),
}


def _sign_in(client, email, password):
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": email, "password": password},
        headers={"host": ADMIN},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _headers(client, email, password):
    return {
        "Authorization": f"Bearer {_sign_in(client, email, password)['access_token']}",
        "host": ADMIN,
    }


@pytest.fixture
def boss(client, seeded):
    """The Super Admin (the first admin the command creates)."""
    platform_auth.create_admin(seeded, SUPER[0], "Duolink Ops", SUPER[1])
    return _headers(client, *SUPER)


@pytest.fixture
def helper(client, boss, seeded):
    """A Support admin, added through the API as a Super Admin would, who has changed the
    temporary password already."""
    platform_auth.create_admin(
        seeded, SUPPORT[0], "Help Desk", SUPPORT[1], role=PlatformRole.SUPPORT
    )
    return _headers(client, *SUPPORT)


@pytest.fixture
def acme(client, boss):
    made = client.post("/api/v1/admin/tenants", headers=boss, json=NEW_COMPANY)
    assert made.status_code == 201, made.text
    return made.json()


def _staff(client, headers):
    return client.get("/api/v1/admin/staff", headers=headers).json()


def _member(client, headers, email):
    return next(m for m in _staff(client, headers) if m["email"] == email)


def _admin_routes():
    """(method, path) of every admin route, as the OpenAPI document lists them."""
    return [
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        if path.startswith("/api/v1/admin/")
        for method in methods
    ]


WRITES = [r for r in _admin_routes() if r[0] != "GET" and r not in NOT_ADMIN_WRITES]
READS = [r for r in _admin_routes() if r[0] == "GET"]


def _fill(path, ids):
    def fill(match):
        name = match.group(1)
        assert name in ids, f"{path}: add {name} to the ids this test fills in"
        return str(ids[name])

    return re.sub(r"\{(\w+)\}", fill, path)


# ------------------------------------------------------------------ roles


def test_every_route_is_listed_so_none_can_be_forgotten():
    assert len(WRITES) >= 14 and len(READS) >= 8
    assert ("POST", "/api/v1/admin/staff") in WRITES and ("GET", "/api/v1/admin/staff") in READS


@pytest.mark.parametrize(("method", "path"), WRITES, ids=[f"{m} {p}" for m, p in WRITES])
def test_support_gets_403_on_every_write_route(client, helper, acme, method, path):
    ids = {"tenant_id": acme["id"], "user_id": 1, "staff_id": 1}
    response = client.request(method, _fill(path, ids), headers=helper, json={})
    assert response.status_code == 403, f"{method} {path}: {response.status_code}"
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize(("method", "path"), READS, ids=[f"{m} {p}" for m, p in READS])
def test_support_gets_200_on_every_read_route(client, helper, acme, method, path):
    ids = {"tenant_id": acme["id"], "user_id": 1, "staff_id": 1}
    response = client.get(_fill(path, ids), headers=helper)
    assert response.status_code == 200, f"{path}: {response.text}"


def test_a_super_admin_does_the_writes_support_cannot(client, boss, helper, acme):
    assert (
        client.post(
            f"/api/v1/admin/tenants/{acme['id']}/suspend", headers=boss, json={"reason": "Test"}
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/admin/tenants/{acme['id']}/reactivate", headers=boss).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/admin/tenants/{acme['id']}", headers=boss, json={"name": "Acme Steels Ltd"}
        ).status_code
        == 200
    )


def test_the_token_carries_the_role_but_the_database_decides(client, boss, seeded):
    staff = client.post(
        "/api/v1/admin/staff", headers=boss, json={**STAFF, "role": "super_admin"}
    ).json()
    assert staff["role"] == "super_admin"
    first = _sign_in(client, SUPER[0], SUPER[1])
    assert decode_platform_token(first["access_token"]).role == "super_admin"

    # The second Super Admin demotes the first; the first one's old token loses its power now.
    other = _headers(client, STAFF["email"], STAFF["password"])
    client.post(
        "/api/v1/admin/auth/change-password",
        headers=other,
        json={"current_password": STAFF["password"], "new_password": "meena-new-pass-1"},
    )
    other = _headers(client, STAFF["email"], "meena-new-pass-1")
    demoted = client.patch(
        f"/api/v1/admin/staff/{first['admin']['id']}", headers=other, json={"role": "support"}
    )
    assert demoted.status_code == 200, demoted.text
    old = {"Authorization": f"Bearer {first['access_token']}", "host": ADMIN}
    assert client.get("/api/v1/admin/overview", headers=old).status_code == 200
    assert client.post("/api/v1/admin/staff", headers=old, json=STAFF).status_code == 403


def test_a_token_from_before_roles_reads_as_support(client, boss):
    claims = decode_platform_token(
        jwt.encode(
            {"sub": "1", "sid": "x", "typ": "platform", "iat": 1, "exp": 4_000_000_000},
            __import__("app.core.config", fromlist=["get_settings"]).get_settings().jwt_secret,
            algorithm="HS256",
        )
    )
    assert claims.role == "support"


def test_a_new_staff_row_defaults_to_support_in_the_database(seeded):
    seeded.execute(
        text(
            "INSERT INTO platform_admin (email, full_name, password_hash, is_active, "
            "failed_login_count) VALUES ('raw@duolink.app', 'Raw', 'x', true, 0)"
        )
    )
    role, must_change = seeded.execute(
        text("SELECT role, must_change_password FROM platform_admin WHERE email='raw@duolink.app'")
    ).one()
    assert (role, must_change) == ("support", False)


# ------------------------------------------------------------------ the staff API


def test_a_super_admin_adds_staff_who_default_to_support(client, boss, helper):
    made = client.post("/api/v1/admin/staff", headers=boss, json=STAFF)
    assert made.status_code == 201, made.text
    row = made.json()
    assert row["role"] == "support" and row["must_change_password"] is True
    assert row["mobile"] == STAFF["mobile"] and row["is_active"] is True
    assert STAFF["password"] not in json.dumps(row)
    assert {m["email"] for m in _staff(client, helper)} == {SUPER[0], SUPPORT[0], STAFF["email"]}


@pytest.mark.parametrize(
    "bad",
    [
        {"email": "not-an-email"},
        {"mobile": "call me"},
        {"password": "short"},
        {"role": "root"},
        {"full_name": ""},
    ],
)
def test_bad_staff_details_are_refused(client, boss, bad):
    assert (
        client.post("/api/v1/admin/staff", headers=boss, json={**STAFF, **bad}).status_code == 422
    )


def test_an_email_is_used_once_whatever_its_case(client, boss):
    client.post("/api/v1/admin/staff", headers=boss, json=STAFF)
    again = client.post(
        "/api/v1/admin/staff", headers=boss, json={**STAFF, "email": "MEENA@duolink.app"}
    )
    assert again.status_code == 409 and again.json()["code"] == "EMAIL_TAKEN"


def test_a_super_admin_edits_name_mobile_and_role(client, boss):
    staff = client.post("/api/v1/admin/staff", headers=boss, json=STAFF).json()
    url = f"/api/v1/admin/staff/{staff['id']}"
    edited = client.patch(
        url,
        headers=boss,
        json={"full_name": "Meena Rao", "role": "super_admin", "reason": "Joins the on-call"},
    )
    assert edited.status_code == 200, edited.text
    assert (edited.json()["full_name"], edited.json()["role"]) == ("Meena Rao", "super_admin")
    assert edited.json()["mobile"] == STAFF["mobile"]  # left alone when not sent
    cleared = client.patch(url, headers=boss, json={"mobile": None})
    assert cleared.json()["mobile"] is None
    assert client.patch("/api/v1/admin/staff/9999", headers=boss, json={}).status_code == 404


def test_deactivating_a_member_signs_them_out_and_blocks_sign_in(client, boss):
    staff = client.post("/api/v1/admin/staff", headers=boss, json=STAFF).json()
    _sign_in(client, STAFF["email"], STAFF["password"])
    assert _member(client, boss, STAFF["email"])["open_sessions"] == 1
    off = client.patch(
        f"/api/v1/admin/staff/{staff['id']}", headers=boss, json={"is_active": False}
    )
    assert off.status_code == 200 and off.json()["open_sessions"] == 0
    refused = client.post(
        "/api/v1/admin/auth/login",
        json={"email": STAFF["email"], "password": STAFF["password"]},
        headers={"host": ADMIN},
    )
    assert refused.status_code == 401
    assert client.post("/api/v1/admin/auth/refresh", headers={"host": ADMIN}).status_code == 401


def test_unlock_and_sign_out_everywhere(client, boss, seeded):
    staff = client.post("/api/v1/admin/staff", headers=boss, json=STAFF).json()
    for _ in range(5):
        client.post(
            "/api/v1/admin/auth/login",
            json={"email": STAFF["email"], "password": "wrong-wrong-1"},
            headers={"host": ADMIN},
        )
    assert _member(client, boss, STAFF["email"])["locked"] is True
    unlocked = client.post(f"/api/v1/admin/staff/{staff['id']}/unlock", headers=boss)
    assert unlocked.status_code == 200 and unlocked.json()["locked"] is False
    _sign_in(client, STAFF["email"], STAFF["password"])
    out = client.post(f"/api/v1/admin/staff/{staff['id']}/sign-out", headers=boss)
    assert out.json()["open_sessions"] == 0


# ------------------------------------------------------------------ the guards


def test_demoting_or_deactivating_the_last_super_admin_answers_409(client, boss):
    me = _member(client, boss, SUPER[0])
    for change in ({"role": "support"}, {"is_active": False}):
        refused = client.patch(f"/api/v1/admin/staff/{me['id']}", headers=boss, json=change)
        assert refused.status_code == 409, change
        assert refused.json()["code"] == "LAST_SUPER_ADMIN"
    assert _member(client, boss, SUPER[0])["role"] == "super_admin"


def test_nobody_demotes_or_deactivates_themselves(client, boss):
    second = client.post(
        "/api/v1/admin/staff", headers=boss, json={**STAFF, "role": "super_admin"}
    ).json()
    me = _member(client, boss, SUPER[0])
    assert second["role"] == "super_admin"
    for change in ({"role": "support"}, {"is_active": False}):
        refused = client.patch(f"/api/v1/admin/staff/{me['id']}", headers=boss, json=change)
        assert refused.status_code == 409 and refused.json()["code"] == "SELF_CHANGE"
    # She may still edit her own name, and may demote or deactivate the other one.
    assert (
        client.patch(
            f"/api/v1/admin/staff/{me['id']}", headers=boss, json={"full_name": "Ops Lead"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/admin/staff/{second['id']}", headers=boss, json={"role": "support"}
        ).status_code
        == 200
    )


# ------------------------------------------------------------------ temporary passwords


def test_a_new_member_must_change_the_temporary_password_before_any_other_call(client, boss, acme):
    client.post("/api/v1/admin/staff", headers=boss, json=STAFF)
    tokens = _sign_in(client, STAFF["email"], STAFF["password"])
    assert tokens["admin"]["must_change_password"] is True
    pending = {"Authorization": f"Bearer {tokens['access_token']}", "host": ADMIN}

    # The three calls that stay open until the password is changed.
    me = client.get("/api/v1/admin/auth/me", headers=pending)
    assert me.status_code == 200 and me.json()["must_change_password"] is True

    # Everything else answers 403 PASSWORD_CHANGE_REQUIRED: reads and, were she a Super Admin, writes.
    for method, path in [
        ("GET", "/api/v1/admin/overview"),
        ("GET", "/api/v1/admin/tenants"),
        ("GET", "/api/v1/admin/staff"),
        ("GET", "/api/v1/admin/audit"),
        ("POST", "/api/v1/admin/staff"),
        ("POST", f"/api/v1/admin/tenants/{acme['id']}/reactivate"),
    ]:
        blocked = client.request(method, path, headers=pending, json={})
        assert blocked.status_code == 403, path
        assert blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED", path

    # A new password that is the same as the temporary one is refused.
    same = client.post(
        "/api/v1/admin/auth/change-password",
        headers=pending,
        json={"current_password": STAFF["password"], "new_password": STAFF["password"]},
    )
    assert same.status_code == 409 and same.json()["code"] == "PASSWORD_UNCHANGED"
    wrong = client.post(
        "/api/v1/admin/auth/change-password",
        headers=pending,
        json={"current_password": "not-my-password", "new_password": "meena-new-pass-1"},
    )
    assert wrong.status_code == 401

    changed = client.post(
        "/api/v1/admin/auth/change-password",
        headers=pending,
        json={"current_password": STAFF["password"], "new_password": "meena-new-pass-1"},
    )
    assert changed.status_code == 204

    # Changing it signs the member out everywhere; the next sign-in is a normal one.
    assert client.post("/api/v1/admin/auth/refresh", headers={"host": ADMIN}).status_code == 401
    fresh = _sign_in(client, STAFF["email"], "meena-new-pass-1")
    assert fresh["admin"]["must_change_password"] is False
    headers = {"Authorization": f"Bearer {fresh['access_token']}", "host": ADMIN}
    assert client.get("/api/v1/admin/overview", headers=headers).status_code == 200


def test_a_reset_password_works_once_and_must_be_changed(client, boss):
    staff = client.post("/api/v1/admin/staff", headers=boss, json=STAFF).json()
    _sign_in(client, STAFF["email"], STAFF["password"])
    reset = client.post(f"/api/v1/admin/staff/{staff['id']}/reset-password", headers=boss)
    assert reset.status_code == 200
    temporary = reset.json()["temporary_password"]
    assert len(temporary) >= 12 and temporary != STAFF["password"]

    assert client.post("/api/v1/admin/auth/refresh", headers={"host": ADMIN}).status_code == 401
    old = client.post(
        "/api/v1/admin/auth/login",
        json={"email": STAFF["email"], "password": STAFF["password"]},
        headers={"host": ADMIN},
    )
    assert old.status_code == 401
    assert _sign_in(client, STAFF["email"], temporary)["admin"]["must_change_password"] is True


# ------------------------------------------------------------------ audit


def test_every_staff_change_is_audited_with_the_admin_and_the_target_and_no_password(
    client, boss, seeded
):
    staff = client.post("/api/v1/admin/staff", headers=boss, json=STAFF).json()
    url = f"/api/v1/admin/staff/{staff['id']}"
    client.patch(url, headers=boss, json={"role": "super_admin", "reason": "On-call rota"})
    temporary = client.post(f"{url}/reset-password", headers=boss).json()["temporary_password"]
    client.post(f"{url}/unlock", headers=boss)
    client.post(f"{url}/sign-out", headers=boss)
    pending = _headers(client, STAFF["email"], temporary)
    client.post(
        "/api/v1/admin/auth/change-password",
        headers=pending,
        json={"current_password": temporary, "new_password": "meena-new-pass-1"},
    )

    entries = client.get("/api/v1/admin/audit", headers=boss, params={"limit": 200}).json()["items"]
    mine = [e for e in entries if e["action"].startswith("staff_")]
    assert [e["action"] for e in reversed(mine)] == [
        "staff_create",
        "staff_update",
        "staff_reset_password",
        "staff_unlock",
        "staff_sign_out",
    ]
    for entry in mine:
        assert entry["admin_email"] == SUPER[0]
        assert entry["target_admin_email"] == STAFF["email"]
    update = next(e for e in mine if e["action"] == "staff_update")
    assert update["details"] == {
        "changes": {"role": {"old": "support", "new": "super_admin"}},
        "reason": "On-call rota",
    }
    changed = next(e for e in entries if e["action"] == "password_change")
    assert changed["admin_email"] == STAFF["email"]

    everything = json.dumps(
        list(seeded.execute(text("SELECT details FROM platform_audit_log")).scalars())
    )
    for secret in (STAFF["password"], temporary, "meena-new-pass-1", SUPER[1]):
        assert secret not in everything


# ------------------------------------------------------------------ the command


def test_the_command_creates_a_super_admin_unless_asked_for_support(client, seeded):
    first = script.create(
        seeded, "first@duolink.app", "First Admin", "first-pass-123", PlatformRole.SUPER_ADMIN
    )
    assert "super_admin" in first
    script.create(seeded, "Desk@Duolink.app", "Desk", "desk-pass-123", PlatformRole.SUPPORT)
    roles = dict(seeded.execute(text("SELECT email, role FROM platform_admin")).all())
    assert roles == {"first@duolink.app": "super_admin", "desk@duolink.app": "support"}
    with pytest.raises(FileExistsError):
        script.create(seeded, "first@duolink.app", "Again", "first-pass-123", PlatformRole.SUPPORT)
    with pytest.raises(ValueError, match="characters"):
        script.create(seeded, "x@duolink.app", "X", "short", PlatformRole.SUPPORT)
    with pytest.raises(ValueError, match="email"):
        script.create(seeded, "nope", "X", "long-enough-1", PlatformRole.SUPPORT)
    assert _headers(client, "first@duolink.app", "first-pass-123")


def test_the_command_line_default_role_and_exit_codes(monkeypatch, seeded, capsys):
    from contextlib import contextmanager

    @contextmanager
    def session():
        yield seeded

    monkeypatch.setattr(script, "SessionLocal", session)
    monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", "cli-pass-12345")
    assert script.main(["cli@duolink.app", "Cli Admin"]) == 0
    assert script.main(["desk@duolink.app", "Desk", "--role", "support"]) == 0
    assert script.main(["cli@duolink.app", "Cli Admin"]) == 1
    assert script.main(["bad", "Bad"]) == 2
    assert script.main(["x@duolink.app", "X", "--role", "root"]) == 2
    roles = dict(seeded.execute(text("SELECT email, role FROM platform_admin")).all())
    assert roles == {"cli@duolink.app": "super_admin", "desk@duolink.app": "support"}
    monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", "short")
    assert script.main(["late@duolink.app", "Late"]) == 2
    assert "shown once" not in capsys.readouterr().out
