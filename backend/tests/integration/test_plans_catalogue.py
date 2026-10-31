"""M20: the plan catalogue Duolink edits, and companies on plans that are rows, not code.

Admin calls run at admin.localhost as the app's database role. The seeded plans come from the
migration: TRIAL 5/2, BASIC 10/3, PRO 50/10 (the limits companies had when plans were code).
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.main import app
from tests.conftest import TEST_DATABASE_URL, login
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    FORM,
    acme,
    boss,
    helper,
    onboard,
)

pytestmark = pytest.mark.integration

PLANS = "/api/v1/admin/billing/plans"
OLD_LIMITS = {"trial": (5, 2), "basic": (10, 3), "pro": (50, 10)}


def new_plan(**changes):
    body = {
        "code": "GOLD",
        "name": "Gold",
        "short_description": "For growing teams",
        "max_users": 20,
        "max_locations": 4,
        "features": ["EWAY_BILL", "GST_EXPORTS"],
        "prices": [
            {"duration_value": 1, "duration_unit": "month", "price": "999.90"},
            {"duration_value": 1, "duration_unit": "year", "price": "9999.00"},
        ],
    }
    return body | changes


def create(client, boss, **changes):
    made = client.post(PLANS, headers=boss, json=new_plan(**changes))
    assert made.status_code == 201, made.text
    return made.json()


def plans_by_code(client, headers, **params):
    listed = client.get(PLANS, headers=headers, params=params)
    assert listed.status_code == 200, listed.text
    return {p["code"]: p for p in listed.json()}


# ------------------------------------------------------------------ what is seeded


def test_the_three_plans_are_seeded_with_the_limits_companies_had(client, boss):
    plans = plans_by_code(client, boss)
    assert {c: (p["max_users"], p["max_locations"]) for c, p in plans.items()} == {
        c.upper(): limits for c, limits in OLD_LIMITS.items()
    }
    assert [p["code"] for p in client.get(PLANS, headers=boss).json()] == ["TRIAL", "BASIC", "PRO"]
    assert [c for c, p in plans.items() if p["is_popular"]] == ["PRO"]
    assert all(p["is_active"] and 1 <= len(p["prices"]) <= 6 for p in plans.values())
    assert all(p["currency"] == "INR" for plan in plans.values() for p in plan["prices"])


def test_the_feature_catalogue_is_listed_for_every_role(client, boss, helper):
    for who in (boss, helper):
        features = client.get(f"{PLANS}/features", headers=who).json()
        assert [f["code"] for f in features] == [
            "EWAY_BILL",
            "GST_EXPORTS",
            "TALLY_EXPORT",
            "MULTI_SHOP",
            "ATTACHMENTS",
        ]
        assert all(f["name"] and f["description"] for f in features)


def test_companies_are_counted_on_their_plan(client, boss, acme):
    plans = plans_by_code(client, boss)
    assert plans["TRIAL"]["companies"] == 1 and plans["PRO"]["companies"] == 1  # acme and main
    assert plans["BASIC"]["companies"] == 0


# ------------------------------------------------------------------ prices are Decimal, never float


def test_a_price_goes_in_and_comes_back_as_the_same_text(client, boss):
    made = create(client, boss)
    assert [p["price"] for p in made["prices"]] == ["999.90", "9999.00"]
    again = client.get(f"{PLANS}/{made['id']}", headers=boss).json()
    assert [p["price"] for p in again["prices"]] == ["999.90", "9999.00"]
    listed = plans_by_code(client, boss)["GOLD"]
    assert listed["prices"][0]["price"] == "999.90"
    edited = client.patch(
        f"{PLANS}/{made['id']}",
        headers=boss,
        json={"prices": [{"duration_value": 3, "duration_unit": "month", "price": "2500"}]},
    )
    assert [p["price"] for p in edited.json()["prices"]] == ["2500.00"]


@pytest.mark.parametrize("price", [999.9, 0.1, 1000.0])
def test_a_json_number_with_a_fraction_is_refused(client, boss, price):
    prices = [{"duration_value": 1, "duration_unit": "month", "price": price}]
    refused = client.post(PLANS, headers=boss, json=new_plan(prices=prices))
    assert refused.status_code == 422, "a price is sent as text, so no float is ever read"
    assert plans_by_code(client, boss).get("GOLD") is None


@pytest.mark.parametrize("price", ["1.001", "-1", "abc", "99999999999.00", "NaN"])
def test_a_bad_price_is_refused(client, boss, price):
    prices = [{"duration_value": 1, "duration_unit": "month", "price": price}]
    refused = client.post(PLANS, headers=boss, json=new_plan(prices=prices))
    assert refused.status_code in (409, 422), refused.text
    assert plans_by_code(client, boss).get("GOLD") is None


# ------------------------------------------------------------------ rules of a plan


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"code": "gold plan!"}, "PLAN_CODE_INVALID"),
        ({"code": "1gold"}, "PLAN_CODE_INVALID"),
        ({"prices": []}, "PLAN_PRICE_COUNT"),
        (
            {
                "prices": [
                    {"duration_value": n, "duration_unit": "month", "price": "1"}
                    for n in range(1, 8)
                ]
            },
            "PLAN_PRICE_COUNT",
        ),
        (
            {
                "prices": [
                    {"duration_value": 1, "duration_unit": "month", "price": "1"},
                    {"duration_value": 1, "duration_unit": "month", "price": "2"},
                ]
            },
            "PLAN_PRICE_DUPLICATE",
        ),
        ({"features": ["EWAY_BILL", "TELEPORT"]}, "PLAN_FEATURE_UNKNOWN"),
        ({"code": "PRO"}, "PLAN_CODE_TAKEN"),
    ],
)
def test_a_plan_the_rules_refuse_answers_409_with_a_code(client, boss, changes, code):
    refused = client.post(PLANS, headers=boss, json=new_plan(**changes))
    assert refused.status_code == 409 and refused.json()["code"] == code, refused.text


def test_one_to_six_prices_are_accepted(client, boss):
    six = [{"duration_value": n, "duration_unit": "month", "price": "10"} for n in range(1, 7)]
    assert len(create(client, boss, code="SIX", prices=six)["prices"]) == 6


def test_a_code_is_upper_snake_case_whatever_was_typed(client, boss):
    assert create(client, boss, code=" gold-plus ")["code"] == "GOLD_PLUS"


def test_only_one_active_plan_is_popular(client, boss):
    gold = create(client, boss, is_popular=True)
    plans = plans_by_code(client, boss)
    assert gold["is_popular"] and not plans["PRO"]["is_popular"]
    assert [c for c, p in plans.items() if p["is_popular"]] == ["GOLD"]

    client.patch(f"{PLANS}/{plans['PRO']['id']}", headers=boss, json={"is_popular": True})
    popular = [c for c, p in plans_by_code(client, boss).items() if p["is_popular"]]
    assert popular == ["PRO"]


def test_an_archived_plan_is_not_popular_and_cannot_become_so(client, boss):
    pro = plans_by_code(client, boss)["PRO"]
    archived = client.post(f"{PLANS}/{pro['id']}/archive", headers=boss, json={"reason": "Retired"})
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False and archived.json()["is_popular"] is False
    again = client.patch(f"{PLANS}/{pro['id']}", headers=boss, json={"is_popular": True})
    assert again.status_code == 409 and again.json()["code"] == "PLAN_INACTIVE"
    restored = client.patch(
        f"{PLANS}/{pro['id']}", headers=boss, json={"is_active": True, "is_popular": True}
    )
    assert restored.json()["is_active"] and restored.json()["is_popular"]


def test_a_plan_is_edited_in_part(client, boss):
    gold = create(client, boss)
    edited = client.patch(
        f"{PLANS}/{gold['id']}",
        headers=boss,
        json={"name": "Gold 2027", "max_users": 30, "features": ["ATTACHMENTS", "MULTI_SHOP"]},
    ).json()
    assert (edited["name"], edited["max_users"], edited["max_locations"]) == ("Gold 2027", 30, 4)
    assert edited["features"] == ["ATTACHMENTS", "MULTI_SHOP"]
    assert [p["price"] for p in edited["prices"]] == ["999.90", "9999.00"]  # untouched
    missing = client.patch(f"{PLANS}/99999", headers=boss, json={"name": "x"})
    assert missing.status_code == 404 and missing.json()["code"] == "PLAN_NOT_FOUND"


def test_a_copy_gets_the_next_free_code_and_is_never_popular(client, boss):
    pro = plans_by_code(client, boss)["PRO"]
    first = client.post(f"{PLANS}/{pro['id']}/duplicate", headers=boss)
    second = client.post(f"{PLANS}/{pro['id']}/duplicate", headers=boss)
    assert first.status_code == 201 and second.status_code == 201
    assert (first.json()["code"], second.json()["code"]) == ("PRO_COPY", "PRO_COPY_2")
    copy = first.json()
    assert copy["is_popular"] is False and copy["companies"] == 0
    assert (copy["max_users"], copy["max_locations"], copy["features"]) == (
        pro["max_users"],
        pro["max_locations"],
        pro["features"],
    )
    assert [p["price"] for p in copy["prices"]] == [p["price"] for p in pro["prices"]]
    assert copy["id"] != pro["id"]


# ------------------------------------------------------------------ plans in use


def test_deleting_a_plan_in_use_answers_409_and_archiving_hides_it_from_onboarding(
    client, boss, acme
):
    trial = plans_by_code(client, boss)["TRIAL"]
    body = {"confirmation": "DELETE", "reason": "Tidying up"}
    refused = client.post(f"{PLANS}/{trial['id']}/delete", headers=boss, json=body)
    assert refused.status_code == 409 and refused.json()["code"] == "PLAN_IN_USE"

    client.post(f"{PLANS}/{trial['id']}/archive", headers=boss, json={"reason": "Not selling"})
    picker = plans_by_code(client, boss, include_archived="false")
    assert "TRIAL" not in picker and {"BASIC", "PRO"} <= set(picker)
    new = client.post(
        "/api/v1/admin/tenants", headers=boss, json=FORM | {"slug": "beta", "plan": "TRIAL"}
    )
    assert new.status_code == 409 and new.json()["code"] == "PLAN_INACTIVE"

    # Acme keeps the plan and its limits; it can still be edited without moving it.
    row = client.get(f"/api/v1/admin/tenants/{acme['id']}", headers=boss).json()
    assert (row["plan"], row["max_users"], row["max_locations"]) == ("TRIAL", 5, 2)
    same = client.patch(
        f"/api/v1/admin/tenants/{acme['id']}", headers=boss, json={"plan": "TRIAL", "city": "Erode"}
    )
    assert same.status_code == 200 and same.json()["plan"] == "TRIAL"
    # But nobody else can be moved onto it.
    other = client.patch(f"/api/v1/admin/tenants/{acme['id']}", headers=boss, json={"plan": "PRO"})
    assert other.status_code == 200
    back = client.patch(f"/api/v1/admin/tenants/{acme['id']}", headers=boss, json={"plan": "TRIAL"})
    assert back.status_code == 409 and back.json()["code"] == "PLAN_INACTIVE"


def test_a_plan_no_company_uses_can_be_deleted_by_typing_delete(client, boss):
    gold = create(client, boss)
    body = {"confirmation": "delete", "reason": "Never used"}
    wrong = client.post(f"{PLANS}/{gold['id']}/delete", headers=boss, json=body)
    assert wrong.status_code == 409 and wrong.json()["code"] == "CONFIRMATION_MISMATCH"
    assert "GOLD" in plans_by_code(client, boss)
    gone = client.post(
        f"{PLANS}/{gold['id']}/delete", headers=boss, json=body | {"confirmation": "DELETE"}
    )
    assert gone.status_code == 204
    assert "GOLD" not in plans_by_code(client, boss)
    assert client.get(f"{PLANS}/{gold['id']}", headers=boss).status_code == 404


def test_an_unknown_plan_cannot_be_given_to_a_company(client, boss, acme):
    onboarding = client.post(
        "/api/v1/admin/tenants", headers=boss, json=FORM | {"slug": "beta", "plan": "GOLDEN"}
    )
    assert onboarding.status_code == 404 and onboarding.json()["code"] == "PLAN_NOT_FOUND"
    moving = client.patch(
        f"/api/v1/admin/tenants/{acme['id']}", headers=boss, json={"plan": "GOLDEN"}
    )
    assert moving.status_code == 404 and moving.json()["code"] == "PLAN_NOT_FOUND"


def test_lowering_a_plans_limit_deactivates_nobody_and_blocks_the_next_add(client, boss, acme):
    owner = login(client, "ravi", "ravi-pass-123", host="acme.localhost")
    user = {"full_name": "Accounts", "role": "accountant", "password": "x" * 12}
    for name in ("acc1", "acc2"):
        added = client.post("/api/v1/users", headers=owner, json={**user, "username": name})
        assert added.status_code == 201

    trial = plans_by_code(client, boss)["TRIAL"]
    lowered = client.patch(f"{PLANS}/{trial['id']}", headers=boss, json={"max_users": 2})
    assert lowered.status_code == 200 and lowered.json()["max_users"] == 2

    users = client.get("/api/v1/users", headers=owner).json()
    assert sum(1 for u in users if u["is_active"]) == 3  # nobody was switched off
    plan = client.get("/api/v1/tenant/plan", headers=owner).json()
    assert (plan["users"], plan["max_users"]) == (3, 2)
    over = client.post("/api/v1/users", headers=owner, json={**user, "username": "acc3"})
    assert over.status_code == 409 and over.json()["code"] == "PLAN_USER_LIMIT"


def test_a_companys_own_limit_beats_its_plans(client, boss, acme):
    trial = plans_by_code(client, boss)["TRIAL"]
    client.patch(f"{PLANS}/{trial['id']}", headers=boss, json={"max_users": 2})
    client.patch(f"/api/v1/admin/tenants/{acme['id']}", headers=boss, json={"max_users": 9})
    owner = login(client, "ravi", "ravi-pass-123", host="acme.localhost")
    assert client.get("/api/v1/tenant/plan", headers=owner).json()["max_users"] == 9
    client.patch(f"/api/v1/admin/tenants/{acme['id']}", headers=boss, json={"max_users": None})
    assert client.get("/api/v1/tenant/plan", headers=owner).json()["max_users"] == 2


def test_a_company_sees_its_plans_code_and_name(client, boss, acme):
    owner = login(client, "ravi", "ravi-pass-123", host="acme.localhost")
    plan = client.get("/api/v1/tenant/plan", headers=owner).json()
    assert (plan["plan"], plan["plan_name"], plan["status"]) == ("TRIAL", "Trial", "trial")
    row = client.get(f"/api/v1/admin/tenants/{acme['id']}", headers=boss).json()
    assert (row["plan"], row["plan_name"]) == ("TRIAL", "Trial")
    filtered = client.get("/api/v1/admin/tenants", headers=boss, params={"plan": "pro"}).json()
    assert [t["slug"] for t in filtered["items"]] == ["main"]


def test_a_paid_plan_ends_a_trial_through_a_catalogue_plan(client, boss, acme):
    gold = create(client, boss)
    moved = client.patch(
        f"/api/v1/admin/tenants/{acme['id']}", headers=boss, json={"plan": gold["code"]}
    )
    assert moved.status_code == 200
    assert (moved.json()["status"], moved.json()["plan"]) == ("active", "GOLD")
    assert plans_by_code(client, boss)["GOLD"]["companies"] == 1
    refused = client.post(
        f"{PLANS}/{gold['id']}/delete",
        headers=boss,
        json={"confirmation": "DELETE", "reason": "x y"},
    )
    assert refused.status_code == 409 and refused.json()["code"] == "PLAN_IN_USE"


# ------------------------------------------------------------------ roles and audit


def test_support_reads_the_catalogue_and_changes_nothing(client, boss, helper):
    pro = plans_by_code(client, helper)["PRO"]
    assert client.get(f"{PLANS}/{pro['id']}", headers=helper).status_code == 200
    calls = [
        ("post", PLANS, new_plan()),
        ("patch", f"{PLANS}/{pro['id']}", {"name": "x"}),
        ("post", f"{PLANS}/{pro['id']}/duplicate", None),
        ("post", f"{PLANS}/{pro['id']}/archive", {"reason": "nope"}),
        ("post", f"{PLANS}/{pro['id']}/delete", {"confirmation": "DELETE", "reason": "nope"}),
    ]
    for method, url, body in calls:
        denied = getattr(client, method)(url, headers=helper, json=body)
        assert denied.status_code == 403, f"{method} {url}"
    assert plans_by_code(client, boss)["PRO"]["name"] == pro["name"]


def test_every_plan_change_is_audited_with_the_admin_the_reason_and_no_secret(client, boss):
    gold = create(client, boss, reason="New offer")
    client.patch(f"{PLANS}/{gold['id']}", headers=boss, json={"max_users": 25, "reason": "Raise"})
    copy = client.post(f"{PLANS}/{gold['id']}/duplicate", headers=boss).json()
    client.post(f"{PLANS}/{gold['id']}/archive", headers=boss, json={"reason": "Replaced"})
    client.post(
        f"{PLANS}/{copy['id']}/delete",
        headers=boss,
        json={"confirmation": "DELETE", "reason": "Dup"},
    )
    events = client.get("/api/v1/admin/audit", headers=boss, params={"limit": 10}).json()["items"]
    plan_events = [e for e in events if e["action"].startswith("plan_")]
    assert [e["action"] for e in plan_events] == [
        "plan_delete",
        "plan_archive",
        "plan_duplicate",
        "plan_update",
        "plan_create",
    ]
    assert all(e["admin_email"] == "ops@duolink.app" for e in plan_events)
    by_action = {e["action"]: e["details"] for e in plan_events}
    assert by_action["plan_create"]["reason"] == "New offer"
    assert by_action["plan_update"]["max_users"] == {"from": 20, "to": 25}
    assert by_action["plan_archive"]["reason"] == "Replaced"
    assert by_action["plan_duplicate"]["copied_from"] == "GOLD"
    assert by_action["plan_delete"]["plan"] == "GOLD_COPY"
    blob = str(events).lower()
    assert "password" not in blob and "token" not in blob


# ------------------------------------------------------------------ money allow-list


def test_only_the_billing_paths_may_carry_a_price():
    paths = [p for p in app.openapi()["paths"] if p.startswith("/api/v1/admin/")]
    billing = {p for p in paths if p.startswith("/api/v1/admin/billing/")}
    assert {p.removeprefix("/api/v1/admin/billing") for p in billing} == {
        "/plans",
        "/plans/features",
        "/plans/{plan_id}",
        "/plans/{plan_id}/duplicate",
        "/plans/{plan_id}/archive",
        "/plans/{plan_id}/delete",
    }


# ------------------------------------------------------------------ the migration keeps every limit


def test_the_migration_gives_every_company_the_limits_it_had(engine):
    """Build a scratch database at 0032 (plans still code), add companies on each plan with and
    without their own limits, upgrade to 0033, and compare the limits before and after."""
    from alembic import command
    from alembic.config import Config

    base = make_url(TEST_DATABASE_URL)
    scratch = base.set(database="erp_m20_migration")
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS erp_m20_migration"))
        conn.execute(text("CREATE DATABASE erp_m20_migration"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", scratch.render_as_string(hide_password=False))
    scratch_engine = create_engine(scratch)
    try:
        command.upgrade(cfg, "0032")
        companies = [
            ("a", "trial", None, None),
            ("b", "basic", None, None),
            ("c", "pro", None, None),
            ("d", "basic", 25, None),
            ("e", "pro", None, 1),
            ("f", "trial", 3, 7),
        ]
        with scratch_engine.begin() as conn:
            for slug, plan, users, locations in companies:
                conn.execute(
                    text(
                        "INSERT INTO tenant (slug, name, status, plan, max_users, max_locations) "
                        "VALUES (:slug, :slug, 'active', :plan, :users, :locations)"
                    ),
                    {"slug": slug, "plan": plan, "users": users, "locations": locations},
                )
        companies.append(("main", "pro", None, None))  # the default company migration 0024 made
        expected = {
            slug: (
                users if users is not None else OLD_LIMITS[plan][0],
                locations if locations is not None else OLD_LIMITS[plan][1],
            )
            for slug, plan, users, locations in companies
        }

        command.upgrade(cfg, "0033")
        with scratch_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT t.slug, p.code, coalesce(t.max_users, p.max_users), "
                    "coalesce(t.max_locations, p.max_locations) "
                    "FROM tenant t JOIN platform_plan p ON p.id = t.plan_id"
                )
            ).all()
        assert {slug: (u, loc) for slug, _, u, loc in rows} == expected
        assert {slug: code for slug, code, _, _ in rows} == {
            slug: plan.upper() for slug, plan, _, _ in companies
        }

        command.downgrade(cfg, "0032")  # and back: the old names return
        with scratch_engine.connect() as conn:
            back = dict(conn.execute(text("SELECT slug, plan FROM tenant")).all())
        assert back == {slug: plan for slug, plan, _, _ in companies}
    finally:
        scratch_engine.dispose()
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS erp_m20_migration WITH (FORCE)"))
        admin.dispose()
