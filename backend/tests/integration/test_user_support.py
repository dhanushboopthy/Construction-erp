"""M19: Duolink's user support tools at admin.localhost/api/v1/admin/users.

The default company "main" has owner, counter1, counter2 and accounts; "acme" is onboarded by
the Super Admin and has one owner, ravi. Every change must reach two audit logs: Duolink's own and
the company's (as "Duolink: <admin>").
"""

import pytest
from sqlalchemy import select

from app.models.sales import SalesInvoice
from app.models.setup import AppUser
from app.services.platform import auth as platform_auth
from tests.conftest import login
from tests.integration.test_sales import body, line, post, world  # noqa: F401 - the fixture

pytestmark = pytest.mark.integration

ADMIN = "admin.localhost"
SUPER = ("ops@duolink.app", "admin-pass-123")
SUPPORT = ("help@duolink.app", "support-pass-123")
OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")
NEW_COMPANY = {
    "name": "Acme Steels",
    "slug": "acme",
    "state_code": "33",
    "owner_username": "ravi",
    "owner_full_name": "Ravi Kumar",
    "owner_password": "ravi-pass-123",
}
API = "/api/v1/admin/users"


def _admin_headers(client, email, password):
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": email, "password": password},
        headers={"host": ADMIN},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}", "host": ADMIN}


@pytest.fixture
def boss(client, seeded):
    platform_auth.create_admin(seeded, SUPER[0], "Duolink Ops", SUPER[1])
    return _admin_headers(client, *SUPER)


@pytest.fixture
def helper(client, boss, seeded):
    from app.models.enums import PlatformRole

    platform_auth.create_admin(
        seeded, SUPPORT[0], "Help Desk", SUPPORT[1], role=PlatformRole.SUPPORT
    )
    return _admin_headers(client, *SUPPORT)


@pytest.fixture
def acme(client, boss):
    made = client.post("/api/v1/admin/tenants", headers=boss, json=NEW_COMPANY)
    assert made.status_code == 201, made.text
    return made.json()


def _users(client, headers, **params):
    response = client.get(API, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _uid(client, headers, slug, username, **params):
    return next(
        u["id"]
        for u in _users(client, headers, q=username, include_removed="true", **params)["items"]
        if u["tenant_slug"] == slug and u["username"] == username
    )


def _acme_owner(client):
    return login(client, "ravi", "ravi-pass-123", host="acme.localhost")


def _company_audit(client, owner, user_id):
    rows = client.get("/api/v1/audit-log", headers=owner, params={"entity": "app_user"}).json()
    return [r for r in rows["items"] if r["entity_id"] == str(user_id)]


def _platform_audit(client, boss, action):
    items = client.get("/api/v1/admin/audit", headers=boss, params={"limit": 100}).json()["items"]
    return [e for e in items if e["action"] == action]


# ------------------------------------------------------------------ directory


def test_the_directory_searches_by_name_username_and_company(client, boss, acme):
    names = {u["username"] for u in _users(client, boss, q="Acme")["items"]}
    assert names == {"ravi"}  # by company name
    assert {u["username"] for u in _users(client, boss, q="kumar")["items"]} == {"ravi"}
    assert {u["username"] for u in _users(client, boss, q="counter")["items"]} == {
        "counter1",
        "counter2",
    }
    assert {u["tenant_slug"] for u in _users(client, boss, q="main")["items"]} == {"main"}


def test_the_directory_filters_by_company_role_active_locked_and_never_signed_in(
    client, boss, acme
):
    assert {u["username"] for u in _users(client, boss, tenant_id=acme["id"])["items"]} == {"ravi"}
    owners = _users(client, boss, role="owner")["items"]
    assert {u["username"] for u in owners} == {"owner", "ravi"}

    counter2 = _uid(client, boss, "main", "counter2")
    client.post(f"{API}/{counter2}/deactivate", headers=boss)
    inactive = _users(client, boss, active="false")["items"]
    assert [u["username"] for u in inactive] == ["counter2"]
    assert "counter2" not in {u["username"] for u in _users(client, boss, active="true")["items"]}

    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": "accounts", "password": "wrong"})
    assert [u["username"] for u in _users(client, boss, locked="true")["items"]] == ["accounts"]
    assert "accounts" not in {u["username"] for u in _users(client, boss, locked="false")["items"]}

    login(client, *OWNER)
    never = {u["username"] for u in _users(client, boss, never_signed_in="true")["items"]}
    assert "owner" not in never and {"counter1", "ravi"} <= never
    ever = {u["username"] for u in _users(client, boss, never_signed_in="false")["items"]}
    assert ever == {"owner"}


def test_the_directory_is_paged_and_ordered_by_company_then_username(client, boss, acme):
    first = _users(client, boss, limit=2, offset=0)
    second = _users(client, boss, limit=2, offset=2)
    third = _users(client, boss, limit=2, offset=4)
    assert first["total"] == second["total"] == third["total"] == 5
    assert (len(first["items"]), len(second["items"]), len(third["items"])) == (2, 2, 1)
    seen = [u["username"] for page in (first, second, third) for u in page["items"]]
    assert len(set(seen)) == 5
    assert seen[0] == "ravi"  # "Acme Steels" sorts before the default company
    assert _users(client, boss, limit=2, offset=10)["items"] == []


# ------------------------------------------------------------------ edit


def test_a_super_admin_edits_name_mobile_username_and_role(client, boss, acme):
    ravi = _acme_owner(client)
    client.post(
        "/api/v1/users",
        headers=ravi,
        json={
            "username": "asha",
            "full_name": "Asha",
            "role": "owner",
            "password": "asha-pass-123",
        },
    )
    asha = _uid(client, boss, "acme", "asha")
    done = client.patch(
        f"{API}/{asha}",
        headers=boss,
        json={
            "full_name": "Asha Devi",
            "mobile": "+91 98765 43210",
            "username": "asha.devi",
            "role": "accountant",
            "reason": "Owner asked by phone",
        },
    )
    assert done.status_code == 200, done.text
    row = done.json()
    assert (row["full_name"], row["mobile"], row["username"], row["role"]) == (
        "Asha Devi",
        "+91 98765 43210",
        "asha.devi",
        "accountant",
    )
    assert login(client, "asha.devi", "asha-pass-123", host="acme.localhost")

    cleared = client.patch(f"{API}/{asha}", headers=boss, json={"mobile": None, "reason": "Typo"})
    assert cleared.json()["mobile"] is None and cleared.json()["username"] == "asha.devi"


def test_an_edit_needs_a_reason_and_a_valid_username_and_mobile(client, boss, acme):
    ravi = _uid(client, boss, "acme", "ravi")
    assert client.patch(f"{API}/{ravi}", headers=boss, json={"full_name": "R"}).status_code == 422
    for bad in ({"username": "Ravi K"}, {"username": "ab"}, {"mobile": "call me"}):
        response = client.patch(f"{API}/{ravi}", headers=boss, json={**bad, "reason": "Fix"})
        assert response.status_code == 422, bad


def test_a_username_is_unique_within_its_company_only(client, boss, acme):
    ravi_owner = _acme_owner(client)
    client.post(
        "/api/v1/users",
        headers=ravi_owner,
        json={"username": "asha", "full_name": "A", "role": "owner", "password": "asha-pass-123"},
    )
    asha = _uid(client, boss, "acme", "asha")
    taken = client.patch(f"{API}/{asha}", headers=boss, json={"username": "ravi", "reason": "Test"})
    assert taken.status_code == 409 and taken.json()["code"] == "USERNAME_TAKEN"
    # "owner" is a user of another company: allowed here.
    other = client.patch(
        f"{API}/{asha}", headers=boss, json={"username": "owner", "reason": "Fine"}
    )
    assert other.status_code == 200 and other.json()["username"] == "owner"
    # Unchanged values are not a clash with oneself.
    same = client.patch(f"{API}/{asha}", headers=boss, json={"username": "owner", "reason": "Fine"})
    assert same.status_code == 200


def test_a_role_change_keeps_the_company_rules(client, boss, acme):
    ravi = _uid(client, boss, "acme", "ravi")
    last = client.patch(
        f"{API}/{ravi}", headers=boss, json={"role": "accountant", "reason": "Test"}
    )
    assert last.status_code == 409 and last.json()["code"] == "LAST_OWNER"

    accounts = _uid(client, boss, "main", "accounts")  # no shop assigned
    counter = client.patch(
        f"{API}/{accounts}", headers=boss, json={"role": "counter", "reason": "Needs a shop"}
    )
    assert counter.status_code == 409 and counter.json()["code"] == "COUNTER_NEEDS_LOCATION"
    row = next(u for u in _users(client, boss, q="accounts")["items"] if u["id"] == accounts)
    assert row["role"] == "accountant"  # the refused change left nothing behind


# ------------------------------------------------------------------ reset password


def test_a_reset_password_works_once_forces_a_change_and_ends_old_sessions(client, boss):
    first = client.post("/api/v1/auth/login", json={"username": COUNTER[0], "password": COUNTER[1]})
    old_cookie = {"cookie": f"erp_refresh={first.cookies.get('erp_refresh')}"}
    client.cookies.clear()
    counter = _uid(client, boss, "main", "counter1")

    temp = client.post(f"{API}/{counter}/reset-password", headers=boss).json()["temporary_password"]
    assert (
        client.post("/api/v1/auth/refresh", headers=old_cookie).status_code == 401
    )  # old session gone
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": COUNTER[0], "password": COUNTER[1]}
        ).status_code
        == 401
    )  # the old password too

    session = login(client, COUNTER[0], temp)
    assert client.get("/api/v1/auth/me", headers=session).json()["must_change_password"] is True
    blocked = client.get("/api/v1/locations", headers=session)
    assert blocked.status_code == 403 and blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = client.post(
        "/api/v1/auth/change-password",
        headers=session,
        json={"current_password": temp, "new_password": "counter-new-pass-1"},
    )
    assert changed.status_code == 204
    fresh = login(client, COUNTER[0], "counter-new-pass-1")
    assert client.get("/api/v1/locations", headers=fresh).status_code == 200
    # "Once": the temporary password no longer signs in.
    client.cookies.clear()
    gone = client.post("/api/v1/auth/login", json={"username": COUNTER[0], "password": temp})
    assert gone.status_code == 401


# ------------------------------------------------------------------ sessions

CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
PHONE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Mobile Safari/537.36"
)


def _sign_in_from(client, agent):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": COUNTER[0], "password": COUNTER[1]},
        headers={"user-agent": agent},
    )
    assert response.status_code == 200
    cookie = {"cookie": f"erp_refresh={response.cookies.get('erp_refresh')}"}
    client.cookies.clear()
    return cookie


def test_the_sessions_list_shows_device_address_and_times(client, boss, helper):
    _sign_in_from(client, CHROME)
    _sign_in_from(client, PHONE)
    counter = _uid(client, boss, "main", "counter1")

    for who in (boss, helper):  # Support may read
        listed = client.get(f"{API}/{counter}/sessions", headers=who)
        assert listed.status_code == 200
    rows = listed.json()
    assert [r["device"] for r in rows] == ["Chrome on Android", "Chrome on Windows"]
    assert all(r["ip"] for r in rows) and all(r["signed_in_at"] <= r["last_used_at"] for r in rows)
    assert set(rows[0]) == {
        "id",
        "device",
        "user_agent",
        "ip",
        "signed_in_at",
        "last_used_at",
        "expires_at",
    }


def test_a_refresh_keeps_one_session_and_the_first_sign_in_time(client, boss):
    cookie = _sign_in_from(client, CHROME)
    counter = _uid(client, boss, "main", "counter1")
    before = client.get(f"{API}/{counter}/sessions", headers=boss).json()
    assert client.post("/api/v1/auth/refresh", headers=cookie).status_code == 200
    after = client.get(f"{API}/{counter}/sessions", headers=boss).json()
    assert len(after) == 1 and after[0]["id"] != before[0]["id"]
    assert after[0]["signed_in_at"] == before[0]["signed_in_at"]
    assert after[0]["last_used_at"] >= before[0]["last_used_at"]


def test_one_session_can_be_ended_and_the_rest_stay(client, boss):
    chrome = _sign_in_from(client, CHROME)
    phone = _sign_in_from(client, PHONE)
    counter = _uid(client, boss, "main", "counter1")
    rows = client.get(f"{API}/{counter}/sessions", headers=boss).json()
    on_phone = next(r for r in rows if r["device"] == "Chrome on Android")

    gone = client.delete(f"{API}/{counter}/sessions/{on_phone['id']}", headers=boss)
    assert gone.status_code == 204
    assert client.post("/api/v1/auth/refresh", headers=phone).status_code == 401
    refreshed = client.post("/api/v1/auth/refresh", headers={**chrome, "user-agent": CHROME})
    assert refreshed.status_code == 200
    assert [r["device"] for r in client.get(f"{API}/{counter}/sessions", headers=boss).json()] == [
        "Chrome on Windows"
    ]
    again = client.delete(f"{API}/{counter}/sessions/{on_phone['id']}", headers=boss)
    assert again.status_code == 404


def test_a_session_of_another_user_is_not_found(client, boss):
    _sign_in_from(client, CHROME)
    counter = _uid(client, boss, "main", "counter1")
    other = _uid(client, boss, "main", "counter2")
    mine = client.get(f"{API}/{counter}/sessions", headers=boss).json()[0]
    assert client.delete(f"{API}/{other}/sessions/{mine['id']}", headers=boss).status_code == 404
    assert len(client.get(f"{API}/{counter}/sessions", headers=boss).json()) == 1


# ------------------------------------------------------------------ remove access


def test_removing_access_needs_the_username_typed_exactly(client, boss):
    counter = _uid(client, boss, "main", "counter1")
    for typed in ("Counter1", "", "counter"):
        refused = client.post(
            f"{API}/{counter}/remove",
            headers=boss,
            json={"confirm_username": typed, "reason": "Left the company"},
        )
        assert refused.status_code == 409, typed
        assert refused.json()["code"] == "CONFIRMATION_MISMATCH"
    still = next(u for u in _users(client, boss, q="counter1")["items"] if u["id"] == counter)
    assert still["is_active"] and still["removed_at"] is None


def test_removing_the_last_active_owner_answers_409(client, boss, acme):
    ravi = _uid(client, boss, "acme", "ravi")
    last = client.post(
        f"{API}/{ravi}/remove",
        headers=boss,
        json={"confirm_username": "ravi", "reason": "Closing the account"},
    )
    assert last.status_code == 409 and last.json()["code"] == "LAST_OWNER"
    assert _users(client, boss, q="ravi")["items"][0]["is_active"] is True

    # With a second active owner the first can go.
    client.post(
        "/api/v1/users",
        headers=_acme_owner(client),
        json={"username": "asha", "full_name": "A", "role": "owner", "password": "asha-pass-123"},
    )
    ok = client.post(
        f"{API}/{ravi}/remove",
        headers=boss,
        json={"confirm_username": "ravi", "reason": "Ravi left"},
    )
    assert ok.status_code == 200 and ok.json()["removed_at"] is not None


def test_removing_a_counter_user_keeps_every_bill_with_their_name(
    client,
    boss,
    seeded,
    world,  # noqa: F811
):
    counter_headers = login(client, *COUNTER)
    bill = post(
        client, world, body(world, [line(world, "tmt", "1", "ton")]), headers=counter_headers
    )
    assert bill.status_code == 201, bill.text
    bill_id = bill.json()["id"]
    counter = _uid(client, boss, "main", "counter1")

    removed = client.post(
        f"{API}/{counter}/remove",
        headers=boss,
        json={"confirm_username": "counter1", "reason": "Left the company"},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["is_active"] is False and removed.json()["removed_at"]

    # The bill is still there, and still points at a user row that still has the name.
    assert client.get(f"/api/v1/invoices/{bill_id}", headers=world["owner"]).status_code == 200
    maker = seeded.execute(
        select(AppUser)
        .join(SalesInvoice, SalesInvoice.created_by == AppUser.id)
        .where(SalesInvoice.id == bill_id)
    ).scalar_one()
    assert (maker.id, maker.full_name, maker.removed_at is not None) == (
        counter,
        "Counter, Shop 1",
        True,
    )

    # Hidden from the company's list by default; they cannot sign in; nothing revives them.
    names = {u["username"] for u in client.get("/api/v1/users", headers=world["owner"]).json()}
    assert "counter1" not in names
    shown = client.get(
        "/api/v1/users", headers=world["owner"], params={"include_removed": "true"}
    ).json()
    assert "counter1" in {u["username"] for u in shown}
    client.cookies.clear()
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": COUNTER[0], "password": COUNTER[1]}
        ).status_code
        == 401
    )
    assert "counter1" not in {u["username"] for u in _users(client, boss)["items"]}
    assert "counter1" in {
        u["username"] for u in _users(client, boss, include_removed="true")["items"]
    }

    back = client.post(f"{API}/{counter}/activate", headers=boss)
    assert back.status_code == 409 and back.json()["code"] == "USER_REMOVED"
    by_owner = client.patch(
        f"/api/v1/users/{counter}", headers=world["owner"], json={"is_active": True}
    )
    assert by_owner.status_code == 409 and by_owner.json()["code"] == "USER_REMOVED"
    for path in ("reset-password", "unlock"):
        refused = client.post(f"{API}/{counter}/{path}", headers=boss)
        assert refused.status_code == 409 and refused.json()["code"] == "USER_REMOVED", path


def test_removing_ends_every_session(client, boss):
    cookie = _sign_in_from(client, CHROME)
    counter = _uid(client, boss, "main", "counter1")
    client.post(
        f"{API}/{counter}/remove",
        headers=boss,
        json={"confirm_username": "counter1", "reason": "Left"},
    )
    assert client.post("/api/v1/auth/refresh", headers=cookie).status_code == 401


# ------------------------------------------------------------------ roles


def test_support_reads_the_directory_and_sessions_but_changes_nothing(client, boss, helper):
    counter = _uid(client, boss, "main", "counter1")
    assert client.get(API, headers=helper).status_code == 200
    assert client.get(f"{API}/{counter}/sessions", headers=helper).status_code == 200

    attempts = [
        ("PATCH", f"{API}/{counter}", {"full_name": "X", "reason": "Test"}),
        ("POST", f"{API}/{counter}/deactivate", None),
        ("POST", f"{API}/{counter}/activate", None),
        ("POST", f"{API}/{counter}/unlock", None),
        ("POST", f"{API}/{counter}/reset-password", None),
        ("POST", f"{API}/{counter}/sign-out", None),
        ("POST", f"{API}/{counter}/remove", {"confirm_username": "counter1", "reason": "Test"}),
        ("DELETE", f"{API}/{counter}/sessions/00000000-0000-0000-0000-000000000001", None),
    ]
    for method, url, payload in attempts:
        response = client.request(method, url, headers=helper, json=payload)
        assert response.status_code == 403, f"{method} {url}"
        assert response.json()["code"] == "PERMISSION_DENIED"
    row = next(u for u in _users(client, boss, q="counter1")["items"] if u["id"] == counter)
    assert row["is_active"] and row["full_name"] != "X" and row["removed_at"] is None
    assert _platform_audit(client, boss, "user_update") == []


# ------------------------------------------------------------------ audit


def test_every_action_is_in_duolinks_log_and_the_companys_log(client, boss, acme):
    ravi_headers = _acme_owner(client)
    client.post(
        "/api/v1/users",
        headers=ravi_headers,
        json={
            "username": "asha",
            "full_name": "Asha",
            "role": "accountant",
            "password": "asha-pass-123",
        },
    )
    asha = _uid(client, boss, "acme", "asha")
    _sign_in_acme = login(client, "asha", "asha-pass-123", host="acme.localhost")
    assert _sign_in_acme
    session_id = client.get(f"{API}/{asha}/sessions", headers=boss).json()[0]["id"]

    temp = ""
    steps = [
        (
            "user_update",
            lambda: client.patch(
                f"{API}/{asha}", headers=boss, json={"full_name": "Asha K", "reason": "Marriage"}
            ),
        ),
        (
            "user_session_revoke",
            lambda: client.delete(f"{API}/{asha}/sessions/{session_id}", headers=boss),
        ),
        ("user_deactivate", lambda: client.post(f"{API}/{asha}/deactivate", headers=boss)),
        ("user_activate", lambda: client.post(f"{API}/{asha}/activate", headers=boss)),
        ("user_unlock", lambda: client.post(f"{API}/{asha}/unlock", headers=boss)),
        ("user_sign_out", lambda: client.post(f"{API}/{asha}/sign-out", headers=boss)),
        ("user_reset_password", lambda: client.post(f"{API}/{asha}/reset-password", headers=boss)),
        (
            "user_remove",
            lambda: client.post(
                f"{API}/{asha}/remove",
                headers=boss,
                json={"confirm_username": "asha", "reason": "Left"},
            ),
        ),
    ]
    for action, run in steps:
        response = run()
        assert response.status_code in (200, 204), f"{action}: {response.text}"
        if action == "user_reset_password":
            temp = response.json()["temporary_password"]

    for action, _ in steps:
        entries = _platform_audit(client, boss, action)
        assert len(entries) == 1, action
        entry = entries[0]
        assert entry["admin_email"] == SUPER[0] and entry["tenant_slug"] == "acme", action
        assert entry["details"] is not None
    update = _platform_audit(client, boss, "user_update")[0]["details"]
    assert update == {
        "changes": {"full_name": {"from": "Asha", "to": "Asha K"}},
        "reason": "Marriage",
    }
    removed = _platform_audit(client, boss, "user_remove")[0]["details"]
    assert removed == {"username": "asha", "reason": "Left"}

    # No secret reaches either log.
    everything = client.get("/api/v1/admin/audit", headers=boss, params={"limit": 100}).text
    assert temp and temp not in everything and "asha-pass-123" not in everything

    # The company's own log: every row of this user's changes names Duolink's admin.
    rows = _company_audit(client, ravi_headers, asha)
    assert rows and all(
        r["changes"].get("_actor") == "Duolink: Duolink Ops"
        for r in rows
        if r["action"] != "insert" and r["action"] != "login" and r["action"] != "logout"
    )
    what = {r["changes"].get("support_action") for r in rows}
    assert {"unlock", "sign_out", "revoke_session", "reset_password", "remove"} <= what
    fields = {key for r in rows for key in r["changes"]}
    assert {"full_name", "is_active", "must_change_password", "removed_at"} <= fields
    assert temp not in str(rows)
