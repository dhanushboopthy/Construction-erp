"""M21: subscriptions, manual renewals, payments, Duolink's revenue and read-only on expiry.

Admin calls run at admin.localhost; a company's own calls at acme.localhost, as the app's
database role. A company becomes read-only by moving its trial end into the past.
"""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.core.tenancy import set_platform
from tests.conftest import TEST_DATABASE_URL
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    helper,
    onboard,
    owner_of,
)

pytestmark = pytest.mark.integration

BILLING = "/api/v1/admin/billing"
PARTY = {"name": "Big Contractor", "type": "customer", "state_code": "33"}


def subscription_of(client, headers, company):
    found = client.get(
        f"{BILLING}/subscriptions", headers=headers, params={"tenant_id": company["id"]}
    )
    assert found.status_code == 200, found.text
    return found.json()["items"][0]


def plan_by_code(client, headers, code):
    listed = client.get(f"{BILLING}/plans", headers=headers).json()
    return next(p for p in listed if p["code"] == code)


def move_trial_end(client, boss, company, when):
    moved = client.patch(
        f"/api/v1/admin/tenants/{company['id']}",
        headers=boss,
        json={"trial_ends_at": when.isoformat()},
    )
    assert moved.status_code == 200, moved.text


def lapse(client, boss, company):
    move_trial_end(client, boss, company, datetime.now(UTC) - timedelta(days=2))


def renew(client, boss, sub, plan, **changes):
    body = {
        "plan_id": plan["id"],
        "custom_days": 30,
        "amount": "999.90",
        "method": "upi",
        "reference": "UPI-1",
    } | changes
    return client.post(f"{BILLING}/subscriptions/{sub['id']}/renew", headers=boss, json=body)


def parse(stamp):
    return datetime.fromisoformat(stamp)


# ------------------------------------------------------------------ every company has one


def test_a_new_trial_company_gets_a_subscription_that_ends_with_its_trial(client, boss, acme):
    sub = subscription_of(client, boss, acme)
    assert sub["status"] == "trial" and sub["plan_code"] == "TRIAL"
    assert sub["expires_at"] == acme["trial_ends_at"]
    assert 13 <= sub["days_left"] <= 14
    assert sub["needs_review"] is False


def test_a_company_started_active_has_no_end_date_and_is_flagged(client, boss):
    company = onboard(client, boss, slug="steady", start_active=True)
    sub = subscription_of(client, boss, company)
    assert sub["status"] == "active" and sub["expires_at"] is None and sub["days_left"] is None
    assert sub["needs_review"] is True


def test_moving_the_trial_end_moves_the_subscription(client, boss, acme):
    new_end = datetime.now(UTC) + timedelta(days=40)
    move_trial_end(client, boss, acme, new_end)
    assert abs(parse(subscription_of(client, boss, acme)["expires_at"]) - new_end) < timedelta(
        seconds=1
    )


# ------------------------------------------------------------------ read-only on expiry


def test_an_expired_company_reads_but_cannot_write_and_can_still_sign_in(client, boss, acme):
    owner = owner_of(client)
    assert client.post("/api/v1/parties", headers=owner, json=PARTY).status_code == 201

    lapse(client, boss, acme)
    assert subscription_of(client, boss, acme)["status"] == "expired"

    assert client.get("/api/v1/parties", headers=owner).status_code == 200  # reads work
    blocked = client.post("/api/v1/parties", headers=owner, json=PARTY | {"name": "Another"})
    assert blocked.status_code == 403 and blocked.json()["code"] == "SUBSCRIPTION_EXPIRED"
    assert owner_of(client)  # sign-in still works
    shown = client.get("/api/v1/tenant", headers={"host": "acme.localhost"}).json()
    assert shown["access_state"] == "read_only" and shown["subscription_status"] == "expired"
    assert shown["days_left"] < 0


def test_the_exceptions_to_read_only_are_listed_in_one_place_and_work(client, boss, acme):
    from app.services.subscription_access import READ_ONLY_EXCEPTIONS, is_excepted

    assert {(m, p.pattern) for m, p in READ_ONLY_EXCEPTIONS} == {
        ("POST", r"^/api/v1/auth/login$"),
        ("POST", r"^/api/v1/auth/refresh$"),
        ("POST", r"^/api/v1/auth/logout$"),
        ("POST", r"^/api/v1/auth/change-password$"),
        ("POST", r"^/api/v1/support/tickets$"),
        ("POST", r"^/api/v1/support/tickets/\d+/(reply|close)$"),
    }
    assert is_excepted("GET", "/api/v1/anything")
    assert not is_excepted("POST", "/api/v1/parties")
    assert not is_excepted("PATCH", "/api/v1/auth/login")

    lapse(client, boss, acme)
    owner = owner_of(client)
    wrong = client.post(
        "/api/v1/auth/change-password",
        headers=owner,
        json={"current_password": "not-it-at-all", "new_password": "A-new-pass-123"},
    )
    assert wrong.json().get("code") != "SUBSCRIPTION_EXPIRED"  # reached the password check
    out = client.post("/api/v1/auth/logout", headers=owner)
    assert out.json().get("code") != "SUBSCRIPTION_EXPIRED" if out.content else True


def test_exports_and_pdfs_keep_working_when_expired(client, boss, acme):
    lapse(client, boss, acme)
    owner = owner_of(client)
    assert (
        client.get("/api/v1/gst/gstr1", headers=owner, params={"period": "2026-10"}).status_code
        != 403
    )
    assert client.get("/api/v1/tally/ledgers", headers=owner).status_code != 403


def test_a_suspended_company_is_still_blocked_not_read_only(client, boss, acme):
    owner = owner_of(client)
    client.post(
        f"/api/v1/admin/tenants/{acme['id']}/suspend", headers=boss, json={"reason": "unpaid bill"}
    )
    blocked = client.get("/api/v1/parties", headers=owner)
    assert blocked.status_code == 403 and blocked.json()["code"] == "TENANT_SUSPENDED"


# ------------------------------------------------------------------ renewing


def test_renewing_lets_the_same_session_save_at_once(client, boss, acme):
    owner = owner_of(client)
    lapse(client, boss, acme)
    assert client.post("/api/v1/parties", headers=owner, json=PARTY).status_code == 403

    sub = subscription_of(client, boss, acme)
    done = renew(client, boss, sub, plan_by_code(client, boss, "BASIC"))
    assert done.status_code == 200, done.text
    assert (
        client.post("/api/v1/parties", headers=owner, json=PARTY).status_code == 201
    )  # no sign-out

    after = done.json()
    assert after["status"] == "active" and after["plan_code"] == "BASIC"
    assert 29 <= after["days_left"] <= 30
    company = client.get(f"/api/v1/admin/tenants/{acme['id']}", headers=boss).json()
    assert company["status"] == "active" and company["plan"] == "BASIC"
    assert company["trial_ends_at"] is None


def test_paying_during_a_trial_starts_the_paid_period_today(client, boss, acme):
    sub = subscription_of(client, boss, acme)
    done = renew(client, boss, sub, plan_by_code(client, boss, "BASIC"), custom_days=30).json()
    assert abs(parse(done["starts_at"]) - datetime.now(UTC)) < timedelta(minutes=1)
    assert abs(parse(done["expires_at"]) - (datetime.now(UTC) + timedelta(days=30))) < timedelta(
        minutes=1
    )


def test_renewing_early_adds_to_the_current_end_date(client, boss, acme):
    basic = plan_by_code(client, boss, "BASIC")
    first = renew(client, boss, subscription_of(client, boss, acme), basic, custom_days=30).json()
    second = renew(client, boss, first, basic, custom_days=30, reference="UPI-2").json()
    assert parse(second["starts_at"]) == parse(first["expires_at"])
    assert parse(second["expires_at"]) == parse(first["expires_at"]) + timedelta(days=30)


def test_renewing_with_one_of_the_plans_prices(client, boss, acme):
    pro = plan_by_code(client, boss, "PRO")
    option = pro["prices"][0]
    done = renew(
        client,
        boss,
        subscription_of(client, boss, acme),
        pro,
        price_id=option["id"],
        custom_days=None,
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["duration_value"], body["duration_unit"]) == (1, "month")
    assert body["price"] == option["price"]


def test_the_price_must_belong_to_the_plan_and_one_choice_is_needed(client, boss, acme):
    sub = subscription_of(client, boss, acme)
    pro, basic = plan_by_code(client, boss, "PRO"), plan_by_code(client, boss, "BASIC")
    stranger = renew(client, boss, sub, basic, price_id=pro["prices"][0]["id"], custom_days=None)
    assert stranger.status_code == 404 and stranger.json()["code"] == "PRICE_NOT_FOUND"
    both = renew(client, boss, sub, basic, price_id=basic["prices"][0]["id"])
    neither = renew(client, boss, sub, basic, custom_days=None)
    assert both.status_code == neither.status_code == 409
    assert both.json()["code"] == neither.json()["code"] == "RENEWAL_CHOICE"


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"amount": "-5.00"}, 409, "PAYMENT_AMOUNT"),
        ({"amount": "10.005"}, 422, None),
        ({"amount": 99.5}, 422, None),
        ({"method": "bitcoin"}, 422, None),
        ({"custom_days": 0}, 422, None),
        ({"custom_days": 4000}, 422, None),
    ],
)
def test_a_bad_renewal_is_refused_and_records_nothing(client, boss, acme, changes, status, code):
    sub = subscription_of(client, boss, acme)
    refused = renew(client, boss, sub, plan_by_code(client, boss, "BASIC"), **changes)
    assert refused.status_code == status
    if code:
        assert refused.json()["code"] == code
    assert client.get(f"{BILLING}/payments", headers=boss).json()["total"] == 0


def test_an_archived_plan_cannot_be_moved_to_but_the_current_one_can_be_renewed(client, boss, acme):
    basic = plan_by_code(client, boss, "BASIC")
    sub = renew(client, boss, subscription_of(client, boss, acme), basic).json()
    archived = client.post(
        f"{BILLING}/plans/{basic['id']}/archive", headers=boss, json={"reason": "Retired"}
    )
    assert archived.status_code == 200
    assert renew(client, boss, sub, basic).status_code == 200  # same plan: allowed
    moved = renew(client, boss, sub, plan_by_code(client, boss, "PRO"))
    assert moved.status_code == 200
    back = renew(client, boss, moved.json(), basic)
    assert back.status_code == 409 and back.json()["code"] == "PLAN_INACTIVE"


# ------------------------------------------------------------------ cancelling


def test_cancelling_makes_the_company_read_only_and_a_renewal_brings_it_back(client, boss, acme):
    owner = owner_of(client)
    sub = subscription_of(client, boss, acme)
    cancelled = client.post(
        f"{BILLING}/subscriptions/{sub['id']}/cancel", headers=boss, json={"reason": "Left us"}
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.post("/api/v1/parties", headers=owner, json=PARTY).status_code == 403
    assert client.get("/api/v1/parties", headers=owner).status_code == 200

    again = client.post(
        f"{BILLING}/subscriptions/{sub['id']}/cancel", headers=boss, json={"reason": "Twice"}
    )
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_CANCELLED"

    back = renew(client, boss, cancelled.json(), plan_by_code(client, boss, "PRO"))
    assert back.json()["status"] == "active" and back.json()["cancelled_at"] is None
    assert client.post("/api/v1/parties", headers=owner, json=PARTY).status_code == 201


# ------------------------------------------------------------------ payments and reversals


def test_payments_are_listed_with_totals_and_a_reversal_nets_them_out(client, boss, acme):
    basic = plan_by_code(client, boss, "BASIC")
    sub = renew(client, boss, subscription_of(client, boss, acme), basic, amount="1000.00").json()
    renew(client, boss, sub, basic, amount="250.50", method="cash", reference="CASH-9")

    page = client.get(f"{BILLING}/payments", headers=boss).json()
    assert page["total"] == 2
    assert page["totals"] == {"received": "1250.50", "reversed": "0.00", "net": "1250.50"}
    newest = page["items"][0]
    assert newest["amount"] == "250.50" and newest["method"] == "cash"
    assert newest["recorded_by"] == "Duolink Ops" and newest["reversed"] is False

    reversed_ = client.post(
        f"{BILLING}/payments/{newest['id']}/reverse", headers=boss, json={"reason": "Typed twice"}
    )
    assert reversed_.status_code == 201, reversed_.text
    assert (
        reversed_.json()["amount"] == "-250.50" and reversed_.json()["reverses_id"] == newest["id"]
    )

    page = client.get(f"{BILLING}/payments", headers=boss).json()
    assert page["total"] == 3
    assert page["totals"] == {"received": "1250.50", "reversed": "250.50", "net": "1000.00"}
    assert next(p for p in page["items"] if p["id"] == newest["id"])["reversed"] is True

    cash = client.get(f"{BILLING}/payments", headers=boss, params={"method": "cash"}).json()
    assert cash["total"] == 2 and cash["totals"]["net"] == "0.00"
    one = client.get(f"{BILLING}/payments", headers=boss, params={"tenant_id": acme["id"]}).json()
    assert one["total"] == 3
    today = datetime.now(UTC).date().isoformat()
    day = client.get(
        f"{BILLING}/payments", headers=boss, params={"from": today, "to": today}
    ).json()
    assert day["total"] == 3
    gone = client.get(f"{BILLING}/payments", headers=boss, params={"to": "2020-01-01"}).json()
    assert gone["total"] == 0 and gone["totals"]["net"] == "0.00"


def test_a_payment_is_reversed_once_and_a_reversal_cannot_be_reversed(client, boss, acme):
    sub = renew(
        client, boss, subscription_of(client, boss, acme), plan_by_code(client, boss, "BASIC")
    )
    assert sub.status_code == 200
    original = client.get(f"{BILLING}/payments", headers=boss).json()["items"][0]
    url = f"{BILLING}/payments/{original['id']}/reverse"
    first = client.post(url, headers=boss, json={"reason": "Mistake"})
    second = client.post(url, headers=boss, json={"reason": "Again"})
    assert second.status_code == 409 and second.json()["code"] == "PAYMENT_REVERSED"
    undo = client.post(
        f"{BILLING}/payments/{first.json()['id']}/reverse",
        headers=boss,
        json={"reason": "Not again"},
    )
    assert undo.status_code == 409 and undo.json()["code"] == "PAYMENT_IS_REVERSAL"
    missing = client.post(
        f"{BILLING}/payments/99999/reverse", headers=boss, json={"reason": "None"}
    )
    assert missing.status_code == 404


def test_the_database_refuses_to_change_or_delete_a_payment(client, boss, acme, seeded):
    renew(client, boss, subscription_of(client, boss, acme), plan_by_code(client, boss, "BASIC"))
    set_platform(seeded)
    for statement in (
        "UPDATE subscription_payment SET amount = 1",
        "DELETE FROM subscription_payment",
    ):
        with (
            pytest.raises(DBAPIError, match=r"append-only|not allowed|ledger"),
            seeded.begin_nested(),
        ):
            seeded.execute(text(statement))


# ------------------------------------------------------------------ roles, audit, privacy


def test_support_reads_billing_and_changes_nothing(client, boss, helper, acme):
    sub = renew(
        client, boss, subscription_of(client, boss, acme), plan_by_code(client, boss, "BASIC")
    ).json()
    payment = client.get(f"{BILLING}/payments", headers=boss).json()["items"][0]
    for path in ("subscriptions", "payments", "dashboard"):
        assert client.get(f"{BILLING}/{path}", headers=helper).status_code == 200
    body = {"reason": "Not allowed"}
    assert (
        client.post(
            f"{BILLING}/subscriptions/{sub['id']}/cancel", headers=helper, json=body
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{BILLING}/payments/{payment['id']}/reverse", headers=helper, json=body
        ).status_code
        == 403
    )
    assert renew(client, helper, sub, plan_by_code(client, boss, "BASIC")).status_code == 403


def test_every_billing_action_is_audited_with_the_admin(client, boss, acme):
    basic = plan_by_code(client, boss, "BASIC")
    sub = renew(client, boss, subscription_of(client, boss, acme), basic, reference="UPI-77").json()
    payment = client.get(f"{BILLING}/payments", headers=boss).json()["items"][0]
    client.post(
        f"{BILLING}/payments/{payment['id']}/reverse", headers=boss, json={"reason": "Mistake"}
    )
    client.post(
        f"{BILLING}/subscriptions/{sub['id']}/cancel", headers=boss, json={"reason": "Left"}
    )
    events = client.get("/api/v1/admin/audit", headers=boss, params={"limit": 20}).json()["items"]
    rows = [e for e in events if e["action"].startswith(("subscription", "payment"))]
    assert {e["action"] for e in rows} == {
        "subscription_renew",
        "payment_reverse",
        "subscription_cancel",
    }
    renewed = next(e for e in rows if e["action"] == "subscription_renew")
    assert renewed["details"]["reference"] == "UPI-77" and renewed["details"]["plan"] == "BASIC"


def test_revenue_appears_only_under_billing(client, boss, acme):
    renew(client, boss, subscription_of(client, boss, acme), plan_by_code(client, boss, "BASIC"))
    company = client.get(f"/api/v1/admin/tenants/{acme['id']}", headers=boss).text
    assert "999.90" not in company
    assert "999.90" in client.get(f"{BILLING}/payments", headers=boss).text


# ------------------------------------------------------------------ the dashboard


def test_the_dashboard_counts_revenue_signups_and_expiries(client, boss, acme):
    # The test database already holds the default company "main" (active, a year's subscription).
    onboard(
        client,
        boss,
        slug="beta",
        name="Beta Traders",
        owner_username="beta",
        owner_email="b@b.example",
    )
    empty = client.get(f"{BILLING}/dashboard", headers=boss).json()
    assert empty["revenue_month"] == "0.00" and empty["revenue_fy"] == "0.00"
    assert empty["companies_by_status"] == {"trial": 2, "active": 1, "suspended": 0, "cancelled": 0}
    assert empty["active_subscriptions"] == 1 and empty["renewals_month"] == 0
    assert empty["new_companies_month"] == 3
    assert (
        empty["expiring_30"] == 2 and len(empty["expiring_soon"]) == 2
    )  # both trials; main runs a year
    assert [t["month"] for t in empty["trend"]] == sorted(t["month"] for t in empty["trend"])
    assert len(empty["trend"]) == 12

    basic = plan_by_code(client, boss, "BASIC")
    sub = subscription_of(client, boss, acme)
    renew(client, boss, sub, basic, amount="1000.00", custom_days=90)
    payment = client.get(f"{BILLING}/payments", headers=boss).json()["items"][0]
    full = client.get(f"{BILLING}/dashboard", headers=boss).json()
    assert full["revenue_month"] == "1000.00" and full["revenue_fy"] == "1000.00"
    assert full["active_subscriptions"] == 2 and full["renewals_month"] == 1
    assert full["companies_by_status"] == {"trial": 1, "active": 2, "suspended": 0, "cancelled": 0}
    assert full["expiring_30"] == 1  # only Beta's trial ends within 30 days
    assert full["trend"][-1] == {
        "month": datetime.now(UTC).strftime("%Y-%m"),
        "revenue": "1000.00",
        "signups": 3,
    }
    shares = {p["plan_code"]: p["companies"] for p in full["plan_breakdown"]}
    assert shares["TRIAL"] == 1 and shares["BASIC"] == 1

    client.post(
        f"{BILLING}/payments/{payment['id']}/reverse", headers=boss, json={"reason": "Bounced"}
    )
    netted = client.get(f"{BILLING}/dashboard", headers=boss).json()
    assert netted["revenue_month"] == "0.00" and netted["revenue_fy"] == "0.00"


# ------------------------------------------------------------------ filters


def test_subscriptions_filter_by_status_plan_and_expiry(client, boss, acme):
    onboard(
        client,
        boss,
        slug="beta",
        name="Beta Traders",
        owner_username="beta",
        owner_email="b@b.example",
    )
    lapse(client, boss, acme)
    url = f"{BILLING}/subscriptions"

    def names(**params):
        return [
            s["tenant_slug"] for s in client.get(url, headers=boss, params=params).json()["items"]
        ]

    # "main" is the default company the test database starts with: active for a year, on PRO.
    assert names(status="expired") == ["acme"]
    assert names(status="trial") == ["beta"]
    assert names(status="active") == ["main"] and names(status="cancelled") == []
    assert names(plan="trial") == ["acme", "beta"]  # soonest to end first
    assert names(plan="PRO") == ["main"]
    assert names(expiring_within=30) == ["beta"]  # an ended one is not "expiring"
    assert names(search="Beta") == ["beta"]
    assert client.get(url, headers=boss, params={"status": "bogus"}).status_code == 422


# ------------------------------------------------------------------ the migration


def test_the_migration_gives_every_company_a_subscription(engine):
    """A scratch database at 0033 with a trial, an active and a suspended company: after 0034
    the trial ends with its trial and the others get a year, flagged for review."""
    from alembic import command
    from alembic.config import Config

    base = make_url(TEST_DATABASE_URL)
    scratch = base.set(database="erp_m21_migration")
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS erp_m21_migration"))
        conn.execute(text("CREATE DATABASE erp_m21_migration"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", scratch.render_as_string(hide_password=False))
    scratch_engine = create_engine(scratch)
    try:
        command.upgrade(cfg, "0033")
        with scratch_engine.begin() as conn:
            plan = {
                code: pid for pid, code in conn.execute(text("SELECT id, code FROM platform_plan"))
            }
            for slug, status, plan_code, ends in (
                ("trialco", "trial", "TRIAL", "2026-12-25 10:00+00"),
                ("liveco", "active", "PRO", None),
                ("heldco", "suspended", "BASIC", None),
            ):
                conn.execute(
                    text(
                        "INSERT INTO tenant (slug, name, status, plan_id, trial_ends_at) "
                        "VALUES (:s, :s, :st, :p, :e)"
                    ),
                    {"s": slug, "st": status, "p": plan[plan_code], "e": ends},
                )
        command.upgrade(cfg, "0034")
        with scratch_engine.connect() as conn:
            rows = {
                r[0]: r[1:]
                for r in conn.execute(
                    text(
                        "SELECT t.slug, s.status, s.plan_id = t.plan_id, s.expires_at, s.needs_review, "
                        "s.expires_at > now() + interval '364 days' "
                        "FROM subscription s JOIN tenant t ON t.id = s.tenant_id"
                    )
                )
            }
        assert rows["trialco"][0] == "trial" and rows["trialco"][3] is False
        assert rows["trialco"][2].strftime("%Y-%m-%d") == "2026-12-25"
        assert rows["liveco"][0] == "active" and rows["liveco"][3] is True and rows["liveco"][4]
        assert rows["heldco"][0] == "active" and rows["heldco"][3] is True
        assert all(r[1] for r in rows.values())  # the plan carried over
        assert rows["main"][0] == "active"  # the default company migration 0024 made

        command.downgrade(cfg, "0033")
        with scratch_engine.connect() as conn:
            gone = conn.execute(text("SELECT to_regclass('subscription')")).scalar()
        assert gone is None
    finally:
        scratch_engine.dispose()
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS erp_m21_migration WITH (FORCE)"))
        admin.dispose()
