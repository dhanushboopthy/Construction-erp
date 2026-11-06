"""M23: owner-granted support access ("Login as Company", with consent).

The owner of a company grants Duolink access for a fixed time; a Super Admin enters with a
"support" token and reads the company as its owner would, but writes nothing. Company calls run
at acme.localhost or main.localhost, admin calls at admin.localhost, as the app's database role.
"""

import re
from datetime import datetime

import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.tenancy import set_tenant
from app.domain.support_access import EXIT_PATH
from app.main import app
from app.models.enums import PlatformRole
from tests.conftest import login
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    _sign_in,
    acme,
    boss,
    helper,
    onboard,
    owner_of,
)
from tests.integration.test_sales import body, line, post, world  # noqa: F401 - the fixture
from tests.integration.test_subscriptions import lapse

pytestmark = pytest.mark.integration

ACCESS = "/api/v1/support-access"
ACME = "acme.localhost"
MAIN = "main.localhost"
GRANT = {"duration_hours": 4, "reason": "The bill print looks wrong"}


def grant(client, owner, **changes):
    made = client.post(f"{ACCESS}/grants", headers=owner, json=GRANT | changes)
    assert made.status_code == 201, made.text
    return made.json()


def enter(client, admin, tenant_id, reason="Checking the bill print"):
    return client.post(
        f"/api/v1/admin/tenants/{tenant_id}/support-session",
        headers=admin,
        json={"reason": reason},
    )


def support(started, host=ACME):
    return {"Authorization": f"Bearer {started['token']}", "host": host}


def inside(client, boss, company, owner, **changes):
    """The owner grants access and the Super Admin enters: the support headers."""
    grant(client, owner, **changes)
    started = enter(client, boss, company["id"])
    assert started.status_code == 201, started.text
    return support(started.json())


@pytest.fixture
def ravi(client, acme):
    return owner_of(client)


@pytest.fixture
def main_id(seeded):
    return seeded.execute(text("SELECT id FROM tenant WHERE slug = 'main'")).scalar_one()


def history(client, owner):
    return client.get(f"{ACCESS}/sessions", headers=owner).json()


def platform_actions(client, boss, tenant_id):
    entries = client.get(
        "/api/v1/admin/audit", headers=boss, params={"tenant_id": tenant_id}
    ).json()["items"]
    return entries


# ------------------------------------------------------------------ consent


def test_with_no_grant_entering_answers_409(client, boss, acme):
    refused = enter(client, boss, acme["id"])
    assert refused.status_code == 409 and refused.json()["code"] == "NO_SUPPORT_GRANT"
    status = client.get(f"/api/v1/admin/tenants/{acme['id']}/support-access", headers=boss)
    assert status.json()["live"] is False and status.json()["seconds_left"] == 0


def test_only_a_super_admin_enters(client, boss, helper, acme, ravi):
    grant(client, ravi)
    refused = enter(client, helper, acme["id"])
    assert refused.status_code == 403 and refused.json()["code"] == "PERMISSION_DENIED"
    # Support may see whether a grant is live (a read), not use it.
    shown = client.get(f"/api/v1/admin/tenants/{acme['id']}/support-access", headers=helper)
    assert shown.status_code == 200 and shown.json()["live"] is True


def test_the_owner_grants_sees_the_countdown_and_the_admin_sees_it_too(client, boss, acme, ravi):
    made = grant(client, ravi, duration_hours=24, include_costs=True)
    assert made["status"] == "live" and made["include_costs"] is True
    assert 24 * 3600 - 60 < made["seconds_left"] <= 24 * 3600
    assert made["granted_by_name"] == "Ravi Kumar"
    shown = client.get(ACCESS, headers=ravi).json()
    assert shown["live"]["id"] == made["id"] and shown["durations"] == [1, 4, 24, 72]

    status = client.get(f"/api/v1/admin/tenants/{acme['id']}/support-access", headers=boss).json()
    assert status["live"] is True and status["grant_id"] == made["id"]
    assert status["owner_only_figures"] is True and status["granted_by_name"] == "Ravi Kumar"
    assert status["reason"] == GRANT["reason"] and status["open_sessions"] == 0


@pytest.mark.parametrize("hours", [0, 2, 48, 100])
def test_only_the_four_durations_are_offered(client, acme, ravi, hours):
    refused = client.post(f"{ACCESS}/grants", headers=ravi, json=GRANT | {"duration_hours": hours})
    assert refused.status_code == 422


def test_a_grant_may_name_a_ticket_of_this_company_only(client, boss, acme, ravi):
    ticket = client.post(
        "/api/v1/support/tickets",
        headers=ravi,
        json={"subject": "Printing", "category": "printing", "body": "Blank PDF"},
    ).json()
    made = grant(client, ravi, ticket_id=ticket["id"])
    assert made["ticket_number"] == ticket["number"]

    onboard(client, boss, name="Beta Traders", slug="beta", owner_username="bala")
    bala = owner_of(client, "beta", "bala")
    other = client.post(f"{ACCESS}/grants", headers=bala, json=GRANT | {"ticket_id": ticket["id"]})
    assert other.status_code == 404 and other.json()["code"] == "TICKET_NOT_FOUND"


def test_only_the_owner_in_person_manages_access(client, boss, acme, ravi):
    shop = client.get("/api/v1/locations", headers=ravi).json()[0]["id"]
    for role in ("counter", "accountant"):
        client.post(
            "/api/v1/users",
            headers=ravi,
            json={
                "username": f"{role}1",
                "full_name": role.title(),
                "role": role,
                "password": "staff-pass-123",
                "location_ids": [shop],
            },
        )
        staff = login(client, f"{role}1", "staff-pass-123", host=ACME)
        assert client.get(ACCESS, headers=staff).status_code == 403
        assert client.post(f"{ACCESS}/grants", headers=staff, json=GRANT).status_code == 403

    headers = inside(client, boss, acme, ravi)
    for method, path in [
        ("GET", ACCESS),
        ("GET", f"{ACCESS}/sessions"),
        ("POST", f"{ACCESS}/grants"),
        ("POST", f"{ACCESS}/revoke"),
    ]:
        refused = client.request(method, path, headers=headers, json=GRANT)
        assert refused.status_code == 403, f"{method} {path}"
        assert refused.json()["code"] == "SUPPORT_READ_ONLY"


# ------------------------------------------------------------------ inside the company


def test_the_token_is_a_support_token_for_two_hours_at_most(client, boss, acme, ravi):
    grant(client, ravi, duration_hours=72)
    started = enter(client, boss, acme["id"]).json()
    assert started["entry_url"] == f"http://acme.localhost/support-entry#token={started['token']}"
    settings = get_settings()
    claims = jwt.decode(started["token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert claims["typ"] == "support" and claims["tid"] == acme["id"]
    assert claims["ssid"] == started["session_id"] and claims["gid"] and claims["sub"]
    assert claims["exp"] - claims["iat"] == 2 * 3600


def test_the_token_never_outlives_a_short_grant(client, boss, acme, ravi):
    made = grant(client, ravi, duration_hours=1)
    started = enter(client, boss, acme["id"]).json()
    assert datetime.fromisoformat(started["expires_at"]) == datetime.fromisoformat(made["ends_at"])


def test_the_admin_opens_today_and_the_bills_list_and_sees_what_the_owner_sees(
    client, boss, world, main_id
):
    owner = world["owner"]
    assert post(client, world, body(world, [line(world, "tmt", "1", "ton")])).status_code == 201
    headers = inside(client, boss, {"id": main_id}, owner | {"host": MAIN}, include_costs=True)
    headers["host"] = MAIN
    for path in ("/api/v1/reports/today", "/api/v1/invoices", "/api/v1/items", "/api/v1/stock"):
        theirs = client.get(path, headers=owner).json()
        ours = client.get(path, headers=headers)
        assert ours.status_code == 200, f"{path}: {ours.text}"
        assert ours.json() == theirs, path

    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert (me["id"], me["role"], me["username"]) == (0, "owner", "duolink-support")
    assert me["full_name"] == "Duolink support: Duolink Ops" and me["locations"] == []


def test_without_include_costs_cost_and_margin_are_absent_as_for_a_counter_user(
    client, boss, world, main_id
):
    owner = world["owner"]
    made = post(client, world, body(world, [line(world, "tmt", "1", "ton")]))
    invoice = made.json()["id"]
    headers = inside(client, boss, {"id": main_id}, owner | {"host": MAIN})
    headers["host"] = MAIN
    # The same checks as test_counter_bills_own_shop_and_never_sees_cost_or_profit.
    shown = client.get(f"/api/v1/invoices/{invoice}", headers=headers)
    assert shown.status_code == 200
    assert "cost_per_unit" not in shown.text and "profit" not in shown.text
    assert "55.0000" not in shown.text
    items = client.get("/api/v1/items", headers=headers).text
    assert "avg_cost" not in items and "cost" not in items.lower()
    assert "avg_cost" not in client.get("/api/v1/transfers", headers=headers).text
    assert client.get(f"/api/v1/invoices/{invoice}/pdf", headers=headers).status_code == 200


# ------------------------------------------------------------------ read-only


def _company_routes():
    return [
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        if path.startswith("/api/v1/") and not path.startswith("/api/v1/admin")
        for method in methods
    ]


COMPANY_WRITES = [
    r for r in _company_routes() if r[0] in {"POST", "PUT", "PATCH", "DELETE"} and r[1] != EXIT_PATH
]
COMPANY_READS = [r for r in _company_routes() if r[0] == "GET"]


def _fill(path):
    return re.sub(r"\{\w+\}", "1", path)


def test_every_company_write_is_walked():
    assert len(COMPANY_WRITES) >= 80 and len(COMPANY_READS) >= 80
    assert ("POST", "/api/v1/auth/change-password") in COMPANY_WRITES
    assert ("POST", "/api/v1/users") in COMPANY_WRITES
    assert ("POST", f"{ACCESS}/revoke") in COMPANY_WRITES


@pytest.mark.parametrize(
    ("method", "path"), COMPANY_WRITES, ids=[f"{m} {p}" for m, p in COMPANY_WRITES]
)
def test_every_write_under_a_support_token_answers_403(client, boss, acme, ravi, method, path):
    headers = inside(client, boss, acme, ravi)
    response = client.request(method, _fill(path), headers=headers, json={})
    assert response.status_code == 403, f"{method} {path}: {response.status_code}"
    assert response.json()["code"] == "SUPPORT_READ_ONLY"


# Reads that are refused on purpose: the access settings themselves (the session cannot see
# the grant that governs it).
REFUSED_READS = {
    ACCESS,
    f"{ACCESS}/sessions",
    f"{ACCESS}/sessions/{{support_session_id}}/events",
}


def _code(response):
    if "json" not in response.headers.get("content-type", ""):
        return None
    answer = response.json()
    return answer.get("code") if isinstance(answer, dict) else None


def test_every_read_under_a_support_token_answers_without_writing(client, boss, acme, ravi):
    headers = inside(client, boss, acme, ravi)
    checked = 0
    for _, path in COMPANY_READS:
        response = client.get(_fill(path), headers=headers)
        assert response.status_code != 500, f"{path}: {response.text}"
        code = _code(response)
        if path in REFUSED_READS:
            assert code == "SUPPORT_READ_ONLY", path
        else:
            assert code != "SUPPORT_READ_ONLY", f"{path} wrote on a read"
            assert response.status_code != 401, path
        checked += 1
    assert checked == len(COMPANY_READS)


def test_a_read_that_would_write_is_stopped_by_the_database_guard(client, boss, acme, ravi):
    headers = inside(client, boss, acme, ravi)
    # The Tally export records an export event: a write, so a support session cannot export.
    exported = client.get(
        "/api/v1/tally/export",
        headers=headers,
        params={"date_from": "2026-04-01", "date_to": "2026-04-30"},
    )
    assert exported.status_code == 403 and exported.json()["code"] == "SUPPORT_READ_ONLY"
    # The owner can, straight after: the guard belongs to the support request only.
    assert (
        client.get(
            "/api/v1/tally/export",
            headers=ravi,
            params={"date_from": "2026-04-01", "date_to": "2026-04-30"},
        ).status_code
        == 200
    )


def test_reading_a_ticket_from_inside_does_not_mark_it_read_for_the_company(
    client, boss, acme, ravi
):
    ticket = client.post(
        "/api/v1/support/tickets",
        headers=ravi,
        json={"subject": "Printing", "category": "printing", "body": "Blank PDF"},
    ).json()
    client.post(
        f"/api/v1/admin/support/tickets/{ticket['id']}/reply", headers=boss, json={"body": "Hi"}
    )
    headers = inside(client, boss, acme, ravi)
    assert client.get(f"/api/v1/support/tickets/{ticket['id']}", headers=headers).status_code == 200
    assert client.get("/api/v1/support/tickets/unread-count", headers=ravi).json()["unread"] == 1


def test_a_refused_write_changes_nothing_and_is_logged(client, boss, acme, ravi, seeded):
    headers = inside(client, boss, acme, ravi)
    refused = client.post(
        "/api/v1/parties", headers=headers, json={"name": "Ghost", "type": "customer"}
    )
    assert refused.status_code == 403
    names = [p["name"] for p in client.get("/api/v1/parties", headers=ravi).json()["items"]]
    assert "Ghost" not in names
    session = history(client, ravi)[0]
    events = client.get(f"{ACCESS}/sessions/{session['id']}/events", headers=ravi).json()
    assert [(e["method"], e["path"], e["refused"]) for e in events] == [
        ("POST", "/api/v1/parties", True)
    ]


# ------------------------------------------------------------------ revoke, end, wrong place


def test_the_owner_revokes_and_the_admins_next_request_answers_401(client, boss, acme, ravi):
    headers = inside(client, boss, acme, ravi)
    assert client.get("/api/v1/parties", headers=headers).status_code == 200
    revoked = client.post(f"{ACCESS}/revoke", headers=ravi)
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    assert revoked.json()["revoked_by_name"] == "Ravi Kumar"

    after = client.get("/api/v1/parties", headers=headers)
    assert after.status_code == 401 and after.json()["code"] == "SUPPORT_SESSION_ENDED"
    session = history(client, ravi)[0]
    assert session["status"] == "ended" and session["end_reason"] == "revoked"
    assert enter(client, boss, acme["id"]).json()["code"] == "NO_SUPPORT_GRANT"
    again = client.post(f"{ACCESS}/revoke", headers=ravi)
    assert again.status_code == 409 and again.json()["code"] == "NO_LIVE_GRANT"


def test_a_new_grant_replaces_the_live_one_and_ends_its_sessions(client, boss, acme, ravi):
    first = grant(client, ravi)
    headers = support(enter(client, boss, acme["id"]).json())
    second = grant(client, ravi, duration_hours=1, include_costs=True)
    recent = client.get(ACCESS, headers=ravi).json()["recent"]
    assert [(g["id"], g["status"]) for g in recent] == [
        (second["id"], "live"),
        (first["id"], "revoked"),
    ]
    assert client.get("/api/v1/parties", headers=headers).status_code == 401


def test_a_grant_that_runs_out_ends_the_session_on_the_next_request(
    client, boss, acme, ravi, seeded
):
    headers = inside(client, boss, acme, ravi)
    set_tenant(seeded, acme["id"])
    seeded.execute(text("UPDATE support_access_grant SET ends_at = now() - interval '1 minute'"))
    after = client.get("/api/v1/parties", headers=headers)
    assert after.status_code == 401
    assert history(client, ravi)[0]["end_reason"] == "grant_ended"


def test_a_demoted_admin_is_out_on_the_next_request(client, boss, acme, ravi, seeded):
    headers = inside(client, boss, acme, ravi)
    seeded.execute(
        text("UPDATE platform_admin SET role = :role WHERE email = 'ops@duolink.app'"),
        {"role": PlatformRole.SUPPORT.value},
    )
    assert client.get("/api/v1/parties", headers=headers).status_code == 401
    assert history(client, ravi)[0]["end_reason"] == "admin_not_allowed"


def test_a_support_token_for_one_company_answers_401_at_another(client, boss, acme, ravi):
    onboard(client, boss, name="Beta Traders", slug="beta", owner_username="bala")
    headers = inside(client, boss, acme, ravi)
    at_beta = client.get("/api/v1/parties", headers=headers | {"host": "beta.localhost"})
    assert at_beta.status_code == 401
    write_at_beta = client.post(
        "/api/v1/parties", headers=headers | {"host": "beta.localhost"}, json={}
    )
    assert write_at_beta.status_code == 401
    assert client.get("/api/v1/parties", headers=headers).status_code == 200  # still fine here


def test_a_support_token_answers_401_on_the_admin_api(client, boss, acme, ravi):
    headers = inside(client, boss, acme, ravi)
    at_admin = headers | {"host": "admin.localhost"}
    for path in ("/api/v1/admin/tenants", "/api/v1/admin/auth/me", "/api/v1/admin/overview"):
        assert client.get(path, headers=at_admin).status_code == 401, path


def test_a_platform_token_answers_401_on_the_company_api(client, boss, acme):
    platform = {"Authorization": boss["Authorization"], "host": ACME}
    assert client.get("/api/v1/parties", headers=platform).status_code == 401
    assert client.get("/api/v1/auth/me", headers=platform).status_code == 401


def test_a_forged_support_token_answers_401(client, boss, acme, ravi):
    headers = inside(client, boss, acme, ravi)
    token = headers["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode(claims | {"ssid": claims["ssid"] + 1}, "wrong-secret", algorithm="HS256")
    bad = {"Authorization": f"Bearer {forged}", "host": ACME}
    assert client.get("/api/v1/parties", headers=bad).status_code == 401
    settings = get_settings()
    other_session = jwt.encode(
        claims | {"ssid": claims["ssid"] + 1000},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    stray = {"Authorization": f"Bearer {other_session}", "host": ACME}
    assert client.get("/api/v1/parties", headers=stray).status_code == 401


# ------------------------------------------------------------------ exit and audit


def test_the_admin_exits_and_the_token_is_dead(client, boss, acme, ravi):
    headers = inside(client, boss, acme, ravi)
    status = client.get("/api/v1/support-session", headers=headers).json()
    assert status["company_name"] == "Acme Steels" and status["admin_name"] == "Duolink Ops"
    assert status["read_only"] is True and status["include_costs"] is False
    assert client.get("/api/v1/support-session", headers=ravi).status_code == 403
    assert client.post(EXIT_PATH, headers=ravi).status_code == 403

    assert client.post(EXIT_PATH, headers=headers).status_code == 204
    assert client.get("/api/v1/parties", headers=headers).status_code == 401
    assert history(client, ravi)[0]["end_reason"] == "exited"


def test_entering_again_replaces_the_admins_open_session(client, boss, acme, ravi):
    first = inside(client, boss, acme, ravi)
    second = support(enter(client, boss, acme["id"]).json())
    assert client.get("/api/v1/parties", headers=first).status_code == 401
    assert client.get("/api/v1/parties", headers=second).status_code == 200
    reasons = [s["end_reason"] for s in history(client, ravi)]
    assert reasons == [None, "replaced"]


def test_the_history_and_the_platform_audit_show_the_same_session(client, boss, acme, ravi):
    headers = inside(client, boss, acme, ravi)
    for path in ("/api/v1/parties", "/api/v1/items", "/api/v1/reports/today"):
        client.get(path, headers=headers)
    client.post(EXIT_PATH, headers=headers)

    [mine] = history(client, ravi)
    assert mine["admin_name"] == "Duolink Ops" and mine["reason"] == "Checking the bill print"
    assert mine["request_count"] == 4  # three reads and the exit
    assert mine["status"] == "ended" and mine["ended_at"]

    page = client.get(
        "/api/v1/admin/audit/support-sessions", headers=boss, params={"tenant_id": acme["id"]}
    ).json()
    [theirs] = page["items"]
    assert (theirs["id"], theirs["request_count"], theirs["end_reason"]) == (
        mine["id"],
        4,
        "exited",
    )
    assert theirs["tenant_slug"] == "acme" and theirs["admin_name"] == "Duolink Ops"
    assert page["open"] == 0 and page["stale"] == 0

    actions = platform_actions(client, boss, acme["id"])
    start = next(a for a in actions if a["action"] == "support_session_start")
    end = next(a for a in actions if a["action"] == "support_session_end")
    assert start["details"]["session_id"] == mine["id"] == end["details"]["session_id"]
    assert end["details"]["reason"] == "exited"
    assert "token" not in str(start["details"]).lower()


def test_entering_and_exiting_are_in_the_companys_audit_log(client, boss, acme, ravi):
    headers = inside(client, boss, acme, ravi)
    started = history(client, ravi)[0]
    client.post(EXIT_PATH, headers=headers)
    answer = client.get("/api/v1/audit-log", headers=ravi, params={"entity": "support_session"})
    assert answer.status_code == 200, answer.text
    entries = answer.json()["items"]
    actions = {e["action"]: e for e in entries if e["entity"] == "support_session"}
    assert {"support_enter", "support_exit"} <= set(actions)
    assert actions["support_enter"]["entity_id"] == str(started["id"])
    assert "token" not in str(actions["support_enter"]).lower()


def test_a_session_never_exited_shows_as_stale_once_its_token_expires(
    client, boss, acme, ravi, seeded
):
    inside(client, boss, acme, ravi)
    set_tenant(seeded, acme["id"])
    seeded.execute(text("UPDATE support_session SET expires_at = now() - interval '1 minute'"))
    page = client.get("/api/v1/admin/audit/support-sessions", headers=boss).json()
    assert page["stale"] == 1 and page["items"][0]["status"] == "stale"
    assert history(client, ravi)[0]["status"] == "stale"


# ------------------------------------------------------------------ edges


def test_a_suspended_company_cannot_be_entered(client, boss, acme, ravi):
    grant(client, ravi)
    done = client.post(
        f"/api/v1/admin/tenants/{acme['id']}/suspend", headers=boss, json={"reason": "Unpaid"}
    )
    assert done.status_code == 200, done.text
    refused = enter(client, boss, acme["id"])
    assert refused.status_code == 409 and refused.json()["code"] == "TENANT_NOT_OPEN"


def test_a_read_only_company_can_still_grant_revoke_and_be_left(client, boss, acme, ravi):
    lapse(client, boss, acme)
    owner = owner_of(client)
    grant(client, owner)
    headers = support(enter(client, boss, acme["id"]).json())
    blocked = client.post("/api/v1/parties", headers=headers, json={})
    assert blocked.json()["code"] == "SUPPORT_READ_ONLY"  # the support refusal comes first
    assert client.post(EXIT_PATH, headers=headers).status_code == 204
    grant(client, owner)
    assert client.post(f"{ACCESS}/revoke", headers=owner).status_code == 200


def test_the_sessions_events_are_append_only(client, boss, acme, ravi, seeded):
    headers = inside(client, boss, acme, ravi)
    client.get("/api/v1/parties", headers=headers)
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text("UPDATE support_session_event SET path = '/x'"))
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text("DELETE FROM support_session_event"))


def test_another_company_never_sees_the_grants_or_sessions(client, boss, acme, ravi, seeded):
    inside(client, boss, acme, ravi)
    beta = onboard(client, boss, name="Beta Traders", slug="beta", owner_username="bala")
    bala = owner_of(client, "beta", "bala")
    assert client.get(ACCESS, headers=bala).json()["live"] is None
    assert history(client, bala) == []
    set_tenant(seeded, beta["id"])
    for table in ("support_access_grant", "support_session", "support_session_event"):
        assert seeded.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0, table  # noqa: S608
    set_tenant(seeded, acme["id"])
    assert seeded.execute(text("SELECT count(*) FROM support_session")).scalar_one() == 1


def test_a_super_admin_signing_in_again_is_not_a_support_principal(client, boss, acme, ravi):
    """The admin's own console keeps working while a session is open elsewhere."""
    inside(client, boss, acme, ravi)
    again = _sign_in(client, "ops@duolink.app", "admin-pass-123")
    assert client.get("/api/v1/admin/tenants", headers=again).status_code == 200
