"""M18: company profile, onboarding in one form, seller details, the company list, logo, cancel.

Admin calls run at admin.localhost as the app's database role, so reading across companies
proves the platform_admin policy. The default company "main" has owner, counter1 and accounts.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.domain.gst import gstin_checksum
from app.models.enums import PlatformRole
from app.services.platform import auth as platform_auth
from tests.conftest import login
from tests.integration.test_sales import body, line, post, world  # noqa: F401 - the fixture
from tests.integration.test_tenant import png

pytestmark = pytest.mark.integration

ADMIN = "admin.localhost"
SUPER = ("ops@duolink.app", "admin-pass-123")
SUPPORT = ("help@duolink.app", "support-pass-123")


def gstin(state: str = "33", pan: str = "AAPFU0939F", entity: str = "1") -> str:
    first14 = f"{state}{pan}{entity}Z"
    return first14 + gstin_checksum(first14)


FORM = {
    "name": "Acme Steels",
    "slug": "acme",
    "plan": "trial",
    "state_code": "33",
    "city": "Coimbatore",
    "legal_name": "Acme Steels Private Limited",
    "registration_no": gstin(),
    "shop_name": "Acme Main Shop",
    "shop_code": "AM",
    "owner_username": "ravi",
    "owner_full_name": "Ravi Kumar",
    "owner_email": "ravi@acme.example",
    "owner_mobile": "+91 98765 43210",
    "owner_password": "ravi-pass-123",
}


def _sign_in(client, email, password):
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
    return _sign_in(client, *SUPER)


@pytest.fixture
def helper(client, boss, seeded):
    platform_auth.create_admin(
        seeded, SUPPORT[0], "Help Desk", SUPPORT[1], role=PlatformRole.SUPPORT
    )
    return _sign_in(client, *SUPPORT)


def onboard(client, boss, **changes):
    made = client.post("/api/v1/admin/tenants", headers=boss, json=FORM | changes)
    assert made.status_code == 201, made.text
    return made.json()


@pytest.fixture
def acme(client, boss):
    return onboard(client, boss)


def owner_of(client, slug="acme", user="ravi", password="ravi-pass-123"):  # noqa: S107
    return login(client, user, password, host=f"{slug}.localhost")


# ------------------------------------------------------------------ onboarding


def test_a_super_admin_onboards_a_company_in_one_form_and_its_owner_signs_in(client, acme):
    assert acme["sign_in_url"] == "http://acme.localhost"
    assert (acme["status"], acme["plan"], acme["state_code"], acme["city"]) == (
        "trial",
        "trial",
        "33",
        "Coimbatore",
    )
    assert acme["owner_name"] == "Ravi Kumar" and acme["owner_email"] == "ravi@acme.example"
    assert acme["owner_mobile"] == "+91 98765 43210" and acme["trial_ends_at"]

    owner = owner_of(client)
    settings = client.get("/api/v1/settings", headers=owner).json()
    assert settings["legal_name"] == "Acme Steels Private Limited"
    assert settings["gstin"] == FORM["registration_no"] and settings["state_code"] == "33"
    shops = client.get("/api/v1/locations", headers=owner).json()
    assert {(x["code"], x["name"], x["kind"]) for x in shops} == {
        ("AM", "Acme Main Shop", "shop"),
        ("G1", "Godown", "godown"),
    }
    # The owner onboarded with a working password is not made to change it (WA's default).
    assert client.get("/api/v1/auth/me", headers=owner).json()["must_change_password"] is False


def test_the_form_has_sensible_defaults(client, boss):
    made = client.post(
        "/api/v1/admin/tenants",
        headers=boss,
        json={
            "name": "Beta Traders",
            "slug": "beta",
            "state_code": "33",
            "owner_username": "bala",
            "owner_full_name": "Bala",
            "owner_password": "bala-pass-123",
        },
    )
    assert made.status_code == 201, made.text
    owner = owner_of(client, "beta", "bala", "bala-pass-123")
    settings = client.get("/api/v1/settings", headers=owner).json()
    assert settings["legal_name"] == "Beta Traders" and settings["gstin"] is None
    codes = {x["code"] for x in client.get("/api/v1/locations", headers=owner).json()}
    assert codes == {"S1", "G1"}


def test_a_shop_coded_g1_gets_the_godown_g2(client, boss):
    onboard(client, boss, shop_code="G1", shop_name="Gee")
    owner = owner_of(client)
    codes = {x["code"] for x in client.get("/api/v1/locations", headers=owner).json()}
    assert codes == {"G1", "G2"}


@pytest.mark.parametrize(
    "bad",
    [
        {"registration_no": "33AAPFU0939F1ZA"},  # wrong check character
        {"registration_no": gstin("27")},  # a Maharashtra GSTIN for a Tamil Nadu company
        {"shop_code": "abc"},
        {"owner_email": "not-an-email"},
        {"owner_mobile": "call me"},
    ],
)
def test_bad_onboarding_details_are_refused(client, boss, bad):
    refused = client.post("/api/v1/admin/tenants", headers=boss, json=FORM | bad)
    assert refused.status_code == 422, bad


def test_trial_length_start_active_and_paid_plans(client, boss):
    thirty = onboard(client, boss, slug="thirty", trial_days=30)
    ends = datetime.fromisoformat(thirty["trial_ends_at"])
    assert timedelta(days=29, hours=23) < ends - datetime.now(UTC) <= timedelta(days=30)

    active = onboard(client, boss, slug="active", start_active=True)
    assert (active["status"], active["trial_ends_at"]) == ("active", None)

    paid = onboard(client, boss, slug="paid", plan="basic")
    assert (paid["status"], paid["plan"], paid["trial_ends_at"]) == ("active", "basic", None)

    for changes, code in (
        ({"slug": "xa1", "start_active": True, "trial_days": 10}, "TRIAL_CONFLICT"),
        ({"slug": "xa2", "plan": "pro", "trial_days": 10}, "TRIAL_ON_PAID_PLAN"),
        ({"slug": "xa3", "trial_days": 0}, "TRIAL_DAYS"),
        ({"slug": "xa4", "trial_days": 91}, "TRIAL_DAYS"),
    ):
        refused = client.post("/api/v1/admin/tenants", headers=boss, json=FORM | changes)
        assert refused.status_code == 409, changes
        assert refused.json()["code"] == code


def test_an_owner_onboarded_with_require_password_change_must_change_it_first(client, boss):
    onboard(client, boss, require_owner_password_change=True)
    owner = owner_of(client)
    me = client.get("/api/v1/auth/me", headers=owner)
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    blocked = client.get("/api/v1/parties", headers=owner)
    assert blocked.status_code == 403 and blocked.json()["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.get("/api/v1/settings", headers=owner).status_code == 403

    same = client.post(
        "/api/v1/auth/change-password",
        headers=owner,
        json={"current_password": "ravi-pass-123", "new_password": "ravi-pass-123"},
    )
    assert same.status_code == 409 and same.json()["code"] == "PASSWORD_UNCHANGED"
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=owner,
        json={"current_password": "ravi-pass-123", "new_password": "ravi-new-pass-1"},
    )
    assert changed.status_code == 204
    fresh = owner_of(client, password="ravi-new-pass-1")
    assert client.get("/api/v1/auth/me", headers=fresh).json()["must_change_password"] is False
    assert client.get("/api/v1/parties", headers=fresh).status_code == 200


def test_onboarding_is_audited_without_the_password(client, boss, acme, seeded):
    rows = seeded.execute(
        text("SELECT details FROM platform_audit_log WHERE action = 'tenant_create'")
    ).scalars()
    details = next(iter(rows))
    assert details["slug"] == "acme" and details["owner"] == "ravi" and details["shop"] == "AM"
    assert "ravi-pass-123" not in str(details)


# ------------------------------------------------------------------ seller details


def test_correcting_a_gstin_shows_as_duolinks_act_in_both_audit_logs(client, boss, acme):
    new = gstin("33", "ABCDE1234F", "2")
    url = f"/api/v1/admin/tenants/{acme['id']}/seller-details"
    assert client.get(url, headers=boss).json()["registration_no"] == FORM["registration_no"]

    done = client.patch(
        url, headers=boss, json={"registration_no": new, "reason": "Owner sent the new certificate"}
    )
    assert done.status_code == 200, done.text
    assert done.json()["registration_no"] == new
    assert done.json()["pan"] is None  # blank: taken from the GSTIN
    assert client.get("/api/v1/settings", headers=owner_of(client)).json()["gstin"] == new

    # The company's own audit log: done by Duolink, with old and new values.
    owner = owner_of(client)
    rows = client.get(
        "/api/v1/audit-log", headers=owner, params={"entity": "shop_settings", "action": "update"}
    ).json()["items"]
    mine = next(r for r in rows if "gstin" in r["changes"])
    assert mine["user_id"] is None
    assert mine["changes"]["_actor"] == "Duolink: Duolink Ops"
    assert mine["changes"]["gstin"] == {"from": FORM["registration_no"], "to": new}

    # Duolink's audit log: the admin, the company, old and new values, the reason.
    entries = client.get("/api/v1/admin/audit", headers=boss).json()["items"]
    entry = next(e for e in entries if e["action"] == "tenant_seller_update")
    assert entry["admin_email"] == SUPER[0] and entry["tenant_slug"] == "acme"
    assert entry["details"] == {
        "changes": {"registration_no": {"from": FORM["registration_no"], "to": new}},
        "reason": "Owner sent the new certificate",
    }


def test_seller_details_are_validated_as_the_company_form_is(client, boss, acme):
    url = f"/api/v1/admin/tenants/{acme['id']}/seller-details"
    why = {"reason": "Correction"}
    for bad in (
        {"registration_no": "33AAPFU0939F1ZA"},  # check character
        {"registration_no": gstin("27")},  # state does not match the company's
        {"state_code": "27"},  # the company's GSTIN is a 33 one
        {"pan": "NOTAPAN"},
        {"pan": "ABCDE1234F"},  # does not match the GSTIN's PAN
        {"cin": "X123"},
        {"legal_name": ""},
    ):
        refused = client.patch(url, headers=boss, json=bad | why)
        assert refused.status_code == 422, bad
    assert client.patch(url, headers=boss, json={"cin": "U45200TN2015PTC098765"}).status_code == 422
    # Nothing was written by the refusals.
    assert client.get(url, headers=boss).json()["registration_no"] == FORM["registration_no"]


def test_pan_cin_address_and_clearing_a_value(client, boss, acme):
    url = f"/api/v1/admin/tenants/{acme['id']}/seller-details"
    done = client.patch(
        url,
        headers=boss,
        json={
            "pan": "aapfu0939f",
            "cin": "u45200tn2015ptc098765",
            "address": "12 Race Course Road, Coimbatore",
            "reason": "Added from the incorporation certificate",
        },
    )
    assert done.status_code == 200, done.text
    assert (done.json()["pan"], done.json()["cin"]) == ("AAPFU0939F", "U45200TN2015PTC098765")
    cleared = client.patch(url, headers=boss, json={"cin": None, "reason": "Entered by mistake"})
    assert cleared.json()["cin"] is None and cleared.json()["pan"] == "AAPFU0939F"
    assert cleared.json()["address"] == "12 Race Course Road, Coimbatore"
    # Other settings are untouched: the thresholds are still what onboarding gave.
    settings = client.get("/api/v1/settings", headers=owner_of(client)).json()
    assert settings["return_window_days"] == 2 and settings["cash_receipt_limit"] == "200000.00"


def test_a_change_that_changes_nothing_writes_no_audit_row(client, boss, acme, seeded):
    url = f"/api/v1/admin/tenants/{acme['id']}/seller-details"
    before = seeded.execute(text("SELECT count(*) FROM platform_audit_log")).scalar_one()
    same = client.patch(
        url, headers=boss, json={"legal_name": "Acme Steels Private Limited", "reason": "Check"}
    )
    assert same.status_code == 200
    after = seeded.execute(text("SELECT count(*) FROM platform_audit_log")).scalar_one()
    assert after == before


def test_seller_details_need_a_reason(client, boss, acme):
    url = f"/api/v1/admin/tenants/{acme['id']}/seller-details"
    assert client.patch(url, headers=boss, json={"cin": None}).status_code == 422
    assert client.patch(url, headers=boss, json={"cin": None, "reason": "x"}).status_code == 422


def test_the_company_settings_form_keeps_pan_and_cin(client, world):
    owner = world["owner"]
    settings = client.get("/api/v1/settings", headers=owner).json()
    assert settings["pan"] is None and settings["cin"] is None
    first14 = "33AAPFU0939F1Z"
    gst = first14 + gstin_checksum(first14)
    saved = client.put(
        "/api/v1/settings",
        headers=owner,
        json=settings | {"gstin": gst, "pan": "AAPFU0939F", "cin": "U45200TN2015PTC098765"},
    )
    assert saved.status_code == 200, saved.text
    assert (saved.json()["pan"], saved.json()["cin"]) == ("AAPFU0939F", "U45200TN2015PTC098765")
    mismatch = client.put(
        "/api/v1/settings", headers=owner, json=settings | {"gstin": gst, "pan": "ABCDE1234F"}
    )
    assert mismatch.status_code == 422 and mismatch.json()["field"] == "pan"
    assert (
        client.put("/api/v1/settings", headers=owner, json=settings | {"cin": "bogus"}).status_code
        == 422
    )


def test_the_cin_and_a_stored_pan_print_on_the_bill(client, world, monkeypatch):
    from app.services import invoice_pdf

    seen: list[str] = []

    class Capture:
        def __init__(self, string: str) -> None:
            seen.append(string)

        def write_pdf(self) -> bytes:
            return b"%PDF"

    monkeypatch.setattr(invoice_pdf, "HTML", Capture)
    owner = world["owner"]
    settings = client.get("/api/v1/settings", headers=owner).json()

    def print_bill() -> str:
        inv = post(client, world, body(world, [line(world, "tmt", "1")])).json()
        assert client.get(f"/api/v1/invoices/{inv['id']}/pdf", headers=owner).status_code == 200
        return re.sub(r"\s+", " ", seen[-1])

    assert "Company&#39;s CIN" not in print_bill()  # no CIN, no slot printed
    client.put(
        "/api/v1/settings",
        headers=owner,
        json=settings | {"pan": "ABCDE1234F", "cin": "U45200TN2015PTC098765"},
    )
    html = print_bill()
    assert "Company&#39;s CIN" in html and "U45200TN2015PTC098765" in html
    assert "ABCDE1234F" in html  # the stored PAN, for a company with no GSTIN


# ------------------------------------------------------------------ roles


def test_support_reads_every_tab_but_cannot_change_a_company(client, helper, acme):
    base = f"/api/v1/admin/tenants/{acme['id']}"
    for path in ("", "/usage", "/seller-details"):
        assert client.get(base + path, headers=helper).status_code == 200, path
    assert client.get("/api/v1/admin/users", headers=helper, params={"tenant_id": acme["id"]})
    assert client.get("/api/v1/admin/audit", headers=helper).status_code == 200
    assert client.get("/api/v1/admin/activity", headers=helper).status_code == 200
    # Every write is refused. (test_platform_staff walks every route; these are the new ones.)
    for method, path, payload in (
        ("PATCH", "/seller-details", {"cin": None, "reason": "Trying"}),
        ("PATCH", "", {"notes": "x"}),
        ("POST", "/cancel", {"reason": "Trying"}),
        ("POST", "/reactivate", {}),
        ("POST", "/logo", None),
        ("DELETE", "/logo", None),
    ):
        response = client.request(method, base + path, headers=helper, json=payload)
        assert response.status_code == 403, (method, path)
    assert (
        client.post(
            "/api/v1/admin/tenants", headers=helper, json=FORM | {"slug": "zzz"}
        ).status_code
        == 403
    )


# ------------------------------------------------------------------ usage and activity


def test_usage_counts_users_shops_bills_and_purchases(client, boss, acme, world):
    fresh = client.get(f"/api/v1/admin/tenants/{acme['id']}/usage", headers=boss).json()
    assert fresh == {
        "users": 1,
        "shops": 2,
        "bills_7d": 0,
        "bills_30d": 0,
        "bills_90d": 0,
        "purchases_30d": 0,
        "attachments": 0,
        "attachment_bytes": 0,
    }
    main = next(
        t
        for t in client.get("/api/v1/admin/tenants", headers=boss).json()["items"]
        if t["slug"] == "main"
    )
    before = client.get(f"/api/v1/admin/tenants/{main['id']}/usage", headers=boss).json()
    post(client, world, body(world, [line(world, "tmt", "1")]))
    post(client, world, body(world, [line(world, "cement", "2")]))
    after = client.get(f"/api/v1/admin/tenants/{main['id']}/usage", headers=boss).json()
    for window in ("bills_7d", "bills_30d", "bills_90d"):
        assert after[window] == before[window] + 2, window
    assert after["users"] == before["users"] and after["shops"] == before["shops"]
    assert client.get("/api/v1/admin/tenants/9999/usage", headers=boss).status_code == 404


def test_last_activity_is_written_at_most_once_a_minute(client, boss, acme, seeded):
    def last_activity():
        return client.get(f"/api/v1/admin/tenants/{acme['id']}", headers=boss).json()[
            "last_activity_at"
        ]

    assert last_activity() is None
    owner = owner_of(client)
    client.get("/api/v1/parties", headers=owner)
    first = last_activity()
    assert first is not None
    client.get("/api/v1/parties", headers=owner)
    client.get("/api/v1/items", headers=owner)
    assert last_activity() == first  # inside the minute: no new write
    seeded.execute(
        text("UPDATE tenant SET last_activity_at = now() - interval '2 minutes' WHERE id = :i"),
        {"i": acme["id"]},
    )
    seeded.expire_all()
    client.get("/api/v1/parties", headers=owner)
    assert last_activity() > (datetime.now(UTC) - timedelta(seconds=30)).isoformat()


def test_a_company_request_does_not_move_updated_at(client, boss, acme, seeded):
    before = seeded.execute(
        text("SELECT updated_at FROM tenant WHERE id = :i"), {"i": acme["id"]}
    ).scalar_one()
    client.get("/api/v1/parties", headers=owner_of(client))
    after = seeded.execute(
        text("SELECT updated_at FROM tenant WHERE id = :i"), {"i": acme["id"]}
    ).scalar_one()
    assert after == before


# ------------------------------------------------------------------ the company list


@pytest.fixture
def several(client, boss, acme):
    """acme (trial, 14 days), beta (basic, active), gamma (trial ending in 3 days), delta (trial
    that ended yesterday), and the seeded default company "main"."""
    onboard(
        client, boss, name="Beta Traders", slug="beta", plan="basic", owner_username="bala", owner_email="bala@beta.example",
        owner_full_name="Bala Menon", registration_no=gstin("33", "BBBBB1111B"), city="Salem",
        legal_name="Beta Traders LLP",
    )  # fmt: skip
    gamma = onboard(client, boss, name="Gamma Pipes", slug="gamma", owner_username="gita", owner_email="gita@gamma.example",
                    owner_full_name="Gita Rao", registration_no=None, city="Erode")  # fmt: skip
    delta = onboard(client, boss, name="Delta Wire", slug="delta", owner_username="dev", owner_email="dev@delta.example",
                    owner_full_name="Dev Anand", registration_no=None, city="Madurai")  # fmt: skip
    for tenant, when in ((gamma, "3 days"), (delta, "-1 day")):
        client.patch(
            f"/api/v1/admin/tenants/{tenant['id']}",
            headers=boss,
            json={
                "trial_ends_at": (
                    datetime.now(UTC) + timedelta(days=int(when.split()[0]))
                ).isoformat()
            },
        )


def slugs(client, boss, **params):
    page = client.get("/api/v1/admin/tenants", headers=boss, params=params).json()
    return [t["slug"] for t in page["items"]], page["total"]


def test_search_finds_a_company_by_gstin_name_code_owner_and_email(client, boss, several):
    assert slugs(client, boss, q=FORM["registration_no"]) == (["acme"], 1)
    assert slugs(client, boss, q=FORM["registration_no"].lower())[0] == ["acme"]
    assert slugs(client, boss, q="BBBBB1111B")[0] == ["beta"]  # inside the GSTIN
    assert slugs(client, boss, q="gamma")[0] == ["gamma"]  # name
    assert slugs(client, boss, q="Pipes")[0] == ["gamma"]
    assert slugs(client, boss, q="Gita Rao")[0] == ["gamma"]  # owner
    assert slugs(client, boss, q="ravi@acme.example")[0] == ["acme"]  # owner email
    assert slugs(client, boss, q="nobody-like-this") == ([], 0)


def test_filters_by_status_plan_trial_state_and_expiring(client, boss, several):
    assert set(slugs(client, boss, plan="basic")[0]) == {"beta"}
    assert set(slugs(client, boss, status="trial")[0]) == {"acme", "gamma", "delta"}
    assert set(slugs(client, boss, status="active")[0]) == {"beta", "main"}
    assert slugs(client, boss, trial="ended")[0] == ["delta"]
    assert slugs(client, boss, trial="ending")[0] == ["gamma"]
    assert slugs(client, boss, trial="running")[0] == ["acme"]
    assert set(slugs(client, boss, trial="none")[0]) == {"beta", "main"}
    # Expiring within 30 days: trials still to end soon (not the one that already ended).
    assert set(slugs(client, boss, expiring="true")[0]) == {"acme", "gamma"}
    assert slugs(client, boss, status="trial", plan="basic") == ([], 0)  # filters combine


def test_sorting_by_name_created_last_activity_and_users(client, boss, several):
    asc, _ = slugs(client, boss, sort="name")
    assert asc == sorted(asc, key=str.lower) or asc == ["acme", "beta", "delta", "gamma", "main"]
    assert slugs(client, boss, sort="name", order="desc")[0] == [
        "main",
        "gamma",
        "delta",
        "beta",
        "acme",
    ]
    assert slugs(client, boss, sort="created")[0][0] == "main"  # the seeded company is oldest
    assert slugs(client, boss, sort="created", order="desc")[0][0] == "delta"

    # Last activity: only acme's owner has done anything; companies with none sort last.
    client.get("/api/v1/parties", headers=owner_of(client))
    newest = slugs(client, boss, sort="last_activity", order="desc")[0]
    assert newest[0] == "acme"
    assert slugs(client, boss, sort="last_activity")[0][0] == "acme"  # nulls last either way

    # Users: the seeded company has four, every other one has its owner only.
    assert slugs(client, boss, sort="users", order="desc")[0][0] == "main"
    assert slugs(client, boss, sort="users")[0][-1] == "main"
    assert (
        client.get("/api/v1/admin/tenants", headers=boss, params={"sort": "bogus"}).status_code
        == 422
    )


def test_pagination_reports_the_total_and_pages_do_not_overlap(client, boss, several):
    page1, total = slugs(client, boss, limit=2, offset=0)
    page2, _ = slugs(client, boss, limit=2, offset=2)
    page3, _ = slugs(client, boss, limit=2, offset=4)
    assert total == 5 and len(page1) == len(page2) == 2 and len(page3) == 1
    assert len({*page1, *page2, *page3}) == 5
    assert slugs(client, boss, limit=2, offset=10) == ([], 5)


# ------------------------------------------------------------------ contact record


def test_the_contact_record_is_edited_and_notes_stay_internal(client, boss, acme):
    url = f"/api/v1/admin/tenants/{acme['id']}"
    done = client.patch(
        url,
        headers=boss,
        json={
            "owner_name": "R. Kumar",
            "owner_mobile": "9876543210",
            "city": "Tiruppur",
            "notes": "Pays by cheque. Call before suspending.",
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["notes"] == "Pays by cheque. Call before suspending."
    assert (done.json()["owner_name"], done.json()["city"]) == ("R. Kumar", "Tiruppur")
    cleared = client.patch(url, headers=boss, json={"notes": "  ", "city": None})
    assert cleared.json()["notes"] is None and cleared.json()["city"] is None

    # The company never sees the note, here or on its public address.
    public = client.get("/api/v1/tenant", headers={"host": "acme.localhost"})
    assert "notes" not in public.json() and "owner_email" not in public.json()
    assert "Pays by cheque" not in public.text
    audit = client.get("/api/v1/admin/audit", headers=boss).json()["items"]
    assert next(e for e in audit if e["action"] == "tenant_update")["tenant_slug"] == "acme"


# ------------------------------------------------------------------ logo


def test_an_admin_sets_and_removes_a_logo_with_the_owners_checks(client, boss, acme):
    base = f"/api/v1/admin/tenants/{acme['id']}/logo"
    data = png(64)
    done = client.post(base, headers=boss, files={"file": ("logo.png", data, "image/png")})
    assert done.status_code == 200, done.text
    shown = client.get("/api/v1/tenant/logo", headers={"host": "acme.localhost"})
    assert shown.status_code == 200 and shown.content == data
    assert client.get("/api/v1/tenant", headers={"host": "acme.localhost"}).json()["logo_url"]

    for name, content, code in (
        ("wide.png", png(64, 32), "LOGO_NOT_SQUARE"),
        ("evil.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><script/></svg>', "LOGO_SVG_UNSAFE"),
        ("note.txt", b"hello", "FILE_TYPE_NOT_ALLOWED"),
    ):  # fmt: skip
        refused = client.post(base, headers=boss, files={"file": (name, content, "image/png")})
        assert refused.status_code in (400, 409, 422), name
        assert refused.json()["code"] == code, name
    assert client.get("/api/v1/tenant/logo", headers={"host": "acme.localhost"}).content == data

    assert client.delete(base, headers=boss).status_code == 200
    assert client.get("/api/v1/tenant/logo", headers={"host": "acme.localhost"}).status_code == 404
    actions = [a["action"] for a in client.get("/api/v1/admin/audit", headers=boss).json()["items"]]
    assert actions[:2] == ["tenant_logo_remove", "tenant_logo_set"]


# ------------------------------------------------------------------ status: cancel and reopen


def test_cancel_ends_every_session_keeps_the_data_and_blocks_sign_in(client, boss, acme):
    owner = owner_of(client)
    assert client.get("/api/v1/parties", headers=owner).status_code == 200
    url = f"/api/v1/admin/tenants/{acme['id']}"
    assert client.post(f"{url}/cancel", headers=boss, json={}).status_code == 422
    assert client.post(f"{url}/cancel", headers=boss, json={"reason": "no"}).status_code == 422

    done = client.post(f"{url}/cancel", headers=boss, json={"reason": "Left for another vendor"})
    assert done.status_code == 200, done.text
    body_ = done.json()
    assert body_["status"] == "cancelled" and body_["open_sessions"] == 0
    assert body_["cancelled_reason"] == "Left for another vendor" and body_["cancelled_at"]
    closed = client.post(
        "/api/v1/auth/login",
        json={"username": "ravi", "password": "ravi-pass-123"},
        headers={"host": "acme.localhost"},
    )
    assert closed.status_code == 403 and closed.json()["code"] == "TENANT_CANCELLED"
    # The company's data is kept: its users and settings are still there for an admin to see.
    assert client.get(url, headers=boss).json()["users"] == 1
    assert client.get(f"{url}/seller-details", headers=boss).json()["legal_name"]

    again = client.post(f"{url}/cancel", headers=boss, json={"reason": "Again please"})
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_CANCELLED"
    suspend = client.post(f"{url}/suspend", headers=boss, json={"reason": "Closed already"})
    assert suspend.status_code == 409 and suspend.json()["code"] == "ALREADY_CANCELLED"


def test_a_suspended_company_can_be_cancelled_and_reopening_a_cancelled_one_needs_a_reason(
    client, boss, helper, acme
):
    url = f"/api/v1/admin/tenants/{acme['id']}"
    client.post(f"{url}/suspend", headers=boss, json={"reason": "Invoice unpaid"})
    assert client.post(f"{url}/cancel", headers=boss, json={"reason": "Gave up"}).status_code == 200

    # Support cannot reopen it; a Super Admin must say why.
    assert (
        client.post(f"{url}/reactivate", headers=helper, json={"reason": "Pleased"}).status_code
        == 403
    )
    missing = client.post(f"{url}/reactivate", headers=boss)
    assert missing.status_code == 409 and missing.json()["code"] == "REASON_REQUIRED"
    reopened = client.post(f"{url}/reactivate", headers=boss, json={"reason": "Paid in full"})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "trial"  # a trial-plan company goes back on trial
    assert reopened.json()["cancelled_at"] is None and reopened.json()["suspended_at"] is None
    assert owner_of(client)  # the owner signs in again

    audit = [a for a in client.get("/api/v1/admin/audit", headers=boss).json()["items"]
             if a["action"] in {"tenant_cancel", "tenant_reactivate"}]  # fmt: skip
    reopen = next(a for a in audit if a["action"] == "tenant_reactivate")
    assert reopen["details"] == {"was": "cancelled", "reason": "Paid in full"}
    cancel = next(a for a in audit if a["action"] == "tenant_cancel")
    assert cancel["details"]["was"] == "suspended" and cancel["details"]["reason"] == "Gave up"


def test_reactivating_a_suspended_company_needs_no_reason(client, boss, acme):
    url = f"/api/v1/admin/tenants/{acme['id']}"
    client.post(f"{url}/suspend", headers=boss, json={"reason": "Invoice unpaid"})
    assert client.post(f"{url}/reactivate", headers=boss).status_code == 200
    again = client.post(f"{url}/reactivate", headers=boss)
    assert again.status_code == 409 and again.json()["code"] == "NOT_SUSPENDED"
