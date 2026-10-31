"""M16 (ADR 0012): the Duolink admin at admin.localhost/api/v1/admin.

The default company "main" is seeded with owner, counter1, counter2 and accounts. Admin calls run
as the app's database role, so reading across companies proves the platform_admin policy.
"""

import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.main import app
from app.services.platform import auth as platform_auth
from tests.conftest import login

pytestmark = pytest.mark.integration

ADMIN = "admin.localhost"
ACME = "acme.localhost"
ADMIN_LOGIN = ("ops@duolink.app", "admin-pass-123")
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


@pytest.fixture
def admin(client, seeded):
    platform_auth.create_admin(seeded, ADMIN_LOGIN[0], "Duolink Ops", ADMIN_LOGIN[1])
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": ADMIN_LOGIN[0], "password": ADMIN_LOGIN[1]},
        headers={"host": ADMIN},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}", "host": ADMIN}


@pytest.fixture
def acme(client, admin):
    made = client.post("/api/v1/admin/tenants", headers=admin, json=NEW_COMPANY)
    assert made.status_code == 201, made.text
    return made.json()


def _users(client, admin, **params):
    return client.get("/api/v1/admin/users", headers=admin, params=params).json()["items"]


def _user_id(client, admin, tenant_slug, username):
    return next(
        u["id"]
        for u in _users(client, admin, q=username)
        if u["tenant_slug"] == tenant_slug and u["username"] == username
    )


# ------------------------------------------------------------------ only at the admin address


def test_the_admin_api_exists_only_at_the_admin_address(client, admin):
    assert client.get("/api/v1/admin/overview").status_code == 404
    assert client.get("/api/v1/admin/overview", headers={"host": ACME}).status_code == 404
    assert client.get("/api/v1/admin/overview", headers={"host": ADMIN}).status_code == 401
    assert client.get("/api/v1/admin/overview", headers=admin).status_code == 200


def test_company_and_admin_tokens_never_cross(client, admin):
    owner = login(client, *OWNER)
    as_admin = {"Authorization": owner["Authorization"], "host": ADMIN}
    assert client.get("/api/v1/admin/overview", headers=as_admin).status_code == 401
    as_company = {"Authorization": admin["Authorization"]}
    assert client.get("/api/v1/auth/me", headers=as_company).status_code == 401


def test_admin_sign_in(client, admin):
    me = client.get("/api/v1/admin/auth/me", headers=admin).json()
    assert me["email"] == ADMIN_LOGIN[0] and me["last_login_at"]
    wrong = client.post(
        "/api/v1/admin/auth/login",
        json={"email": ADMIN_LOGIN[0], "password": "nope-nope-nope"},
        headers={"host": ADMIN},
    )
    assert wrong.status_code == 401
    refreshed = client.post("/api/v1/admin/auth/refresh", headers={"host": ADMIN})
    assert refreshed.status_code == 200, refreshed.text
    assert client.post("/api/v1/admin/auth/logout", headers={"host": ADMIN}).status_code == 204


# ------------------------------------------------------------------ companies


def test_a_new_company_starts_on_a_trial_and_its_owner_signs_in_at_its_address(client, acme):
    assert acme["slug"] == "acme" and acme["status"] == "trial" and acme["plan"] == "trial"
    assert acme["trial_state"] == "running" and acme["trial_ends_at"]
    assert (acme["users"], acme["max_users"]) == (1, 5)
    assert (acme["locations"], acme["max_locations"]) == (2, 2)
    owner = login(client, "ravi", "ravi-pass-123", host=ACME)
    parties = client.get("/api/v1/parties", headers=owner).json()["items"]
    assert [p["name"] for p in parties] == ["Walk-in customer"]
    settings = client.get("/api/v1/settings", headers=owner).json()
    assert settings["legal_name"] == "Acme Steels"


@pytest.mark.parametrize(
    ("slug", "code"), [("acme", "SLUG_TAKEN"), ("admin", "SLUG_INVALID"), ("-x-", "SLUG_INVALID")]
)
def test_company_codes_are_unique_and_valid(client, admin, acme, slug, code):
    again = client.post("/api/v1/admin/tenants", headers=admin, json={**NEW_COMPANY, "slug": slug})
    assert again.status_code == 409 and again.json()["code"] == code


def test_the_company_list_shows_usage_and_searches(client, admin, acme):
    rows = client.get("/api/v1/admin/tenants", headers=admin).json()["items"]
    by_slug = {r["slug"]: r for r in rows}
    assert {"main", "acme"} <= set(by_slug)
    assert by_slug["main"]["users"] == 4 and by_slug["main"]["plan"] == "pro"
    found = client.get("/api/v1/admin/tenants", headers=admin, params={"q": "acme"}).json()
    assert [r["slug"] for r in found["items"]] == ["acme"]
    trial = client.get("/api/v1/admin/tenants", headers=admin, params={"status": "trial"}).json()
    assert [r["slug"] for r in trial["items"]] == ["acme"]


def test_suspending_a_company_signs_everyone_out_until_it_is_reactivated(client, admin, acme):
    owner = login(client, "ravi", "ravi-pass-123", host=ACME)
    assert (
        client.get(f"/api/v1/admin/tenants/{acme['id']}", headers=admin).json()["open_sessions"]
        == 1
    )

    short = client.post(
        f"/api/v1/admin/tenants/{acme['id']}/suspend", headers=admin, json={"reason": "x"}
    )
    assert short.status_code == 422  # a reason is required
    done = client.post(
        f"/api/v1/admin/tenants/{acme['id']}/suspend",
        headers=admin,
        json={"reason": "Unpaid invoice"},
    ).json()
    assert done["status"] == "suspended" and done["suspended_reason"] == "Unpaid invoice"
    assert done["open_sessions"] == 0
    assert client.get("/api/v1/auth/me", headers=owner).json()["code"] == "TENANT_SUSPENDED"
    signin = client.post(
        "/api/v1/auth/login",
        json={"username": "ravi", "password": "ravi-pass-123"},
        headers={"host": ACME},
    )
    assert signin.status_code == 403
    assert login(client, *OWNER)  # other companies carry on

    back = client.post(f"/api/v1/admin/tenants/{acme['id']}/reactivate", headers=admin).json()
    assert back["status"] == "trial" and back["suspended_reason"] is None
    assert login(client, "ravi", "ravi-pass-123", host=ACME)


def test_a_paid_plan_ends_the_trial(client, admin, acme):
    changed = client.patch(
        f"/api/v1/admin/tenants/{acme['id']}", headers=admin, json={"plan": "basic"}
    ).json()
    assert changed["status"] == "active" and changed["max_users"] == 10


# ------------------------------------------------------------------ plans and limits


def test_the_plan_limits_users_and_shops(client, admin, acme):
    client.patch(f"/api/v1/admin/tenants/{acme['id']}", headers=admin, json={"max_users": 2})
    owner = login(client, "ravi", "ravi-pass-123", host=ACME)
    user = {"full_name": "Accounts", "role": "accountant", "password": "x" * 12}
    assert (
        client.post("/api/v1/users", headers=owner, json={**user, "username": "acc1"}).status_code
        == 201
    )
    over = client.post("/api/v1/users", headers=owner, json={**user, "username": "acc2"})
    assert over.status_code == 409 and over.json()["code"] == "PLAN_USER_LIMIT"

    plan = client.get("/api/v1/tenant/plan", headers=owner).json()
    assert (plan["users"], plan["max_users"], plan["locations"], plan["max_locations"]) == (
        2,
        2,
        2,
        2,
    )
    shop = {"code": "S2", "name": "Shop 2", "kind": "shop", "state_code": "33"}
    more = client.post("/api/v1/locations", headers=owner, json=shop)
    assert more.status_code == 409 and more.json()["code"] == "PLAN_LOCATION_LIMIT"

    # Back to the plan's limit (5 on a trial): room again.
    client.patch(f"/api/v1/admin/tenants/{acme['id']}", headers=admin, json={"max_users": None})
    again = client.post("/api/v1/users", headers=owner, json={**user, "username": "acc2"})
    assert again.status_code == 201


def test_reactivating_a_user_counts_against_the_plan(client, admin, acme):
    owner = login(client, "ravi", "ravi-pass-123", host=ACME)
    body = {"username": "acc1", "full_name": "A", "role": "accountant", "password": "x" * 12}
    assert client.post("/api/v1/users", headers=owner, json=body).status_code == 201
    acc1 = _user_id(client, admin, "acme", "acc1")
    client.post(f"/api/v1/admin/users/{acc1}/deactivate", headers=admin)
    client.patch(f"/api/v1/admin/tenants/{acme['id']}", headers=admin, json={"max_users": 1})
    back = client.post(f"/api/v1/admin/users/{acc1}/activate", headers=admin)
    assert back.status_code == 409 and back.json()["code"] == "PLAN_USER_LIMIT"


def test_the_last_owner_stays_active_from_the_admin_side_too(client, admin, acme):
    ravi = _user_id(client, admin, "acme", "ravi")
    last = client.post(f"/api/v1/admin/users/{ravi}/deactivate", headers=admin)
    assert last.status_code == 409 and last.json()["code"] == "LAST_OWNER"
    audit = client.get("/api/v1/admin/audit", headers=admin).json()["items"]
    assert audit[0]["action"] != "user_deactivate"  # a refused action leaves no entry


# ------------------------------------------------------------------ users across companies


def test_users_of_every_company_are_listed(client, admin, acme):
    slugs = {u["tenant_slug"] for u in _users(client, admin)}
    assert slugs == {"main", "acme"}
    only_acme = _users(client, admin, tenant_id=acme["id"])
    assert [u["username"] for u in only_acme] == ["ravi"]


def test_support_actions_on_a_user(client, admin):
    counter = _user_id(client, admin, "main", "counter1")

    off = client.post(f"/api/v1/admin/users/{counter}/deactivate", headers=admin).json()
    assert off["is_active"] is False
    failed = client.post(
        "/api/v1/auth/login", json={"username": COUNTER[0], "password": COUNTER[1]}
    )
    assert failed.status_code == 401
    assert client.post(f"/api/v1/admin/users/{counter}/activate", headers=admin).json()["is_active"]

    for _ in range(5):  # lock the account
        client.post("/api/v1/auth/login", json={"username": COUNTER[0], "password": "wrong"})
    assert _users(client, admin, locked="true")[0]["username"] == "counter1"
    assert (
        client.post(f"/api/v1/admin/users/{counter}/unlock", headers=admin).json()["locked"]
        is False
    )

    temp = client.post(f"/api/v1/admin/users/{counter}/reset-password", headers=admin).json()[
        "temporary_password"
    ]
    signed_in = client.post("/api/v1/auth/login", json={"username": COUNTER[0], "password": temp})
    assert signed_in.status_code == 200
    cookie = {"cookie": f"erp_refresh={signed_in.cookies.get('erp_refresh')}"}
    client.cookies.clear()
    client.post(f"/api/v1/admin/users/{counter}/sign-out", headers=admin)
    # The 30-minute access token runs out on its own; the session cannot be renewed.
    assert client.post("/api/v1/auth/refresh", headers=cookie).status_code == 401


# ------------------------------------------------------------------ monitoring and audit


def test_the_overview_counts_companies_users_and_sign_ins(client, admin, acme):
    login(client, *OWNER)
    client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    view = client.get("/api/v1/admin/overview", headers=admin).json()
    assert view["tenants_total"] == 2 and view["tenants_by_status"]["trial"] == 1
    assert view["active_users"] == 5
    assert view["sign_ins_24h"] >= 1 and view["failed_sign_ins_24h"] >= 1
    assert view["new_tenants_this_month"] >= 1
    assert view["trials_ending"] == []  # 14 days left


def test_sign_ins_of_every_company_are_listed(client, admin):
    login(client, *OWNER)
    client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    events = client.get("/api/v1/admin/activity", headers=admin).json()["items"]
    assert {"action": "login", "username": "owner", "tenant_slug": "main"}.items() <= next(
        e for e in events if e["action"] == "login"
    ).items()
    failed = next(e for e in events if e["action"] == "login_failed")
    assert failed["username"] == "nobody"


def test_every_admin_action_is_written_down_and_kept(client, admin, acme, seeded):
    client.post(
        f"/api/v1/admin/tenants/{acme['id']}/suspend", headers=admin, json={"reason": "Test"}
    )
    actions = [
        a["action"] for a in client.get("/api/v1/admin/audit", headers=admin).json()["items"]
    ]
    assert actions[:3] == ["tenant_suspend", "tenant_create", "login"]
    entry = client.get("/api/v1/admin/audit", headers=admin).json()["items"][0]
    assert entry["admin_email"] == ADMIN_LOGIN[0] and entry["tenant_slug"] == "acme"
    with pytest.raises(DBAPIError, match="append-only"), seeded.begin_nested():
        seeded.execute(text("UPDATE platform_audit_log SET action = 'login'"))


# Duolink's own revenue (plan prices, subscription payments) may appear only under this prefix
# (ADR 0013). No such path exists before Milestone 20; every other admin path is checked below.
MONEY_ALLOWED_PREFIX = "/api/v1/admin/billing/"
MONEY_WORDS = re.compile(r"amount|cost|price|rate|profit|margin|balance|taxable|gst|value|paid")


def _keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


def test_no_admin_answer_carries_money(client, admin, acme):
    paths = [p for p in app.openapi()["paths"] if p.startswith("/api/v1/admin/")]
    gets = [
        p
        for p in paths
        if "get" in app.openapi()["paths"][p] and not p.startswith(MONEY_ALLOWED_PREFIX)
    ]
    checked = 0
    ravi = _user_id(client, admin, "acme", "ravi")
    for path in gets:
        url = path.replace("{tenant_id}", str(acme["id"])).replace("{user_id}", str(ravi))
        response = client.get(url, headers=admin)
        assert response.status_code == 200, f"{path}: {response.text}"
        money = [k for k in _keys(response.json()) if MONEY_WORDS.search(k)]
        assert money == [], f"{path} answered {money}"
        checked += 1
    assert checked >= 6
