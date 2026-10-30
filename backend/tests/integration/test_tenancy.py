"""M15 (ADR 0011): many companies in one database, each kept apart.

The default company ("main", tenant 1) answers on any host outside BASE_DOMAIN, such as the test
client's "testserver"; a second company "beta" answers on beta.localhost. Both are seeded with
the same usernames and passwords, so a mix-up would show.
"""

import re

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.tenancy import set_tenant
from app.main import app
from app.models.enums import PartyType, TenantStatus
from app.models.masters import Party
from app.models.tenancy import Tenant
from app.scripts.seed import seed
from app.services.shop_settings import DEFAULT_TAGLINE
from app.services.tenancy import CrossTenantWriteError
from tests.conftest import login

pytestmark = pytest.mark.integration

BETA = "beta.localhost"
OWNER = ("owner", "owner-pass-123")
MARKER = "Only-in-main Builders"


def _sign_in(client, host: str | None = None):
    headers = {"host": host} if host else {}
    body = {"username": OWNER[0], "password": OWNER[1]}
    return client.post("/api/v1/auth/login", json=body, headers=headers)


@pytest.fixture
def beta(seeded):
    seed(seeded, tenant_slug="beta")
    tenant = seeded.execute(select(Tenant).where(Tenant.slug == "beta")).scalar_one()
    set_tenant(seeded, 1)
    return tenant


@pytest.fixture
def marked(client, beta):
    """A customer only main has."""
    main_owner = login(client, *OWNER)
    made = client.post(
        "/api/v1/parties",
        headers=main_owner,
        json={"name": MARKER, "type": "customer", "state_code": "33"},
    )
    assert made.status_code == 201, made.text
    return made.json()


# ------------------------------------------------------------------ the address picks the company


def test_each_address_names_its_company(client, beta):
    assert client.get("/api/v1/tenant").json()["slug"] == "main"
    named = client.get("/api/v1/tenant", headers={"host": BETA}).json()
    assert named == {
        "slug": "beta",
        "status": "active",
        "name": "Demo Construction Materials",
        "tagline": DEFAULT_TAGLINE,
        "logo_url": None,
    }


@pytest.mark.parametrize("host", ["nobody.localhost", "admin.localhost"])
def test_unknown_and_admin_addresses_name_no_company(client, host):
    response = client.get("/api/v1/tenant", headers={"host": host})
    assert response.status_code == 404
    assert response.json()["code"] == "TENANT_NOT_FOUND"
    assert _sign_in(client, host).status_code == 404


def test_the_proxy_forwarded_host_wins(client, beta):
    response = client.get("/api/v1/tenant", headers={"x-forwarded-host": BETA, "host": "backend"})
    assert response.json()["slug"] == "beta"


# ------------------------------------------------------------------ signing in


def test_a_user_belongs_to_one_company(client, beta):
    beta_owner = login(client, *OWNER, host=BETA)
    made = client.post(
        "/api/v1/users",
        headers=beta_owner,
        json={"username": "ravi", "full_name": "Ravi", "role": "accountant", "password": "x" * 12},
    )
    assert made.status_code == 201, made.text
    assert login(client, "ravi", "x" * 12, host=BETA)
    wrong = client.post("/api/v1/auth/login", json={"username": "ravi", "password": "x" * 12})
    assert wrong.status_code == 401


def test_a_token_from_one_company_is_refused_at_another(client, beta):
    beta_owner = login(client, *OWNER, host=BETA)
    assert client.get("/api/v1/auth/me", headers=beta_owner).status_code == 200
    elsewhere = {"Authorization": beta_owner["Authorization"]}  # same token, main's address
    response = client.get("/api/v1/auth/me", headers=elsewhere)
    assert response.status_code == 401


def test_a_refresh_cookie_from_one_company_is_refused_at_another(client, beta):
    cookie = _sign_in(client, BETA).cookies.get("erp_refresh")
    assert cookie
    client.cookies.clear()
    at_main = client.post("/api/v1/auth/refresh", headers={"cookie": f"erp_refresh={cookie}"})
    assert at_main.status_code == 401
    at_beta = client.post(
        "/api/v1/auth/refresh", headers={"cookie": f"erp_refresh={cookie}", "host": BETA}
    )
    assert at_beta.status_code == 200


def test_a_suspended_company_cannot_sign_in_or_carry_on(client, beta, seeded):
    beta_owner = login(client, *OWNER, host=BETA)
    beta.status = TenantStatus.SUSPENDED
    seeded.commit()
    for response in (
        _sign_in(client, BETA),
        client.get("/api/v1/auth/me", headers=beta_owner),
        client.get("/api/v1/tenant", headers={"host": BETA}),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "TENANT_SUSPENDED"
    assert client.get("/api/v1/tenant").status_code == 200  # other companies carry on


# ------------------------------------------------------------------ data stays apart


def test_lists_show_only_the_companys_own_rows(client, marked):
    beta_owner = login(client, *OWNER, host=BETA)
    names = [p["name"] for p in client.get("/api/v1/parties", headers=beta_owner).json()["items"]]
    assert MARKER not in names
    assert client.get(f"/api/v1/parties/{marked['id']}", headers=beta_owner).status_code == 404


def _get_routes_without_ids():
    for path, methods in app.openapi()["paths"].items():
        if "get" in methods and not re.search(r"\{[^}]+\}", path):
            yield path


def test_no_screen_of_another_company_shows_main_s_customer(client, marked):
    beta_owner = login(client, *OWNER, host=BETA)
    checked = 0
    for path in _get_routes_without_ids():
        response = client.get(path, headers=beta_owner)
        assert response.status_code < 500, f"{path} answered {response.status_code}"
        assert MARKER not in response.text, f"{path} showed another company's customer"
        checked += 1
    assert checked > 50


def test_the_database_hides_other_companies_rows(seeded, marked, beta):
    count = text("SELECT count(*) FROM party WHERE name = :n")
    assert seeded.execute(count, {"n": MARKER}).scalar_one() == 1
    set_tenant(seeded, beta.id)
    assert seeded.execute(count, {"n": MARKER}).scalar_one() == 0
    # No company at all: nothing is visible.
    seeded.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    assert seeded.execute(text("SELECT count(*) FROM party")).scalar_one() == 0


def test_the_database_refuses_a_row_for_another_company(seeded, beta):
    set_tenant(seeded, beta.id)
    with pytest.raises(DBAPIError, match="row-level security"), seeded.begin_nested():
        seeded.execute(
            text(
                "INSERT INTO party (tenant_id, name, type, state_code, address) "
                "VALUES (1, 'Sneaky', 'customer', '33', '')"
            )
        )


def test_the_session_refuses_a_row_for_another_company(seeded, beta):
    set_tenant(seeded, beta.id)
    seeded.add(
        Party(tenant_id=1, name="Sneaky", type=PartyType.CUSTOMER, state_code="33", address="")
    )
    with pytest.raises(CrossTenantWriteError):
        seeded.flush()
    seeded.rollback()


def test_new_rows_get_the_session_s_company(seeded, beta):
    set_tenant(seeded, beta.id)
    party = Party(name="Beta Builders", type=PartyType.CUSTOMER, state_code="33", address="")
    seeded.add(party)
    seeded.flush()
    assert party.tenant_id == beta.id


def test_every_company_table_has_row_level_security(seeded):
    rows = seeded.execute(
        text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
            "(SELECT array_agg(p.polname::text ORDER BY p.polname) FROM pg_policy p "
            "WHERE p.polrelid = c.oid) "
            "FROM pg_class c JOIN information_schema.columns col "
            "ON col.table_name = c.relname AND col.column_name = 'tenant_id' "
            "WHERE col.table_schema = 'public' AND c.relkind = 'r' "
            "AND c.relname <> 'platform_audit_log'"  # Duolink's own log, not a company's row
        )
    ).all()
    assert len(rows) > 50
    expected = ["platform_admin", "tenant_isolation"]
    unprotected = [name for name, rls, forced, _ in rows if not (rls and forced)]
    wrong_policies = [name for name, _, _, pols in rows if pols != expected]
    assert unprotected == [] and wrong_policies == []


def test_every_table_belongs_to_a_company(seeded):
    """New tables must carry tenant_id (TenantMixin); only these are shared by all companies."""
    shared = {"tenant", "alembic_version", "platform_admin", "platform_session"}
    missing = seeded.execute(
        text(
            "SELECT t.table_name FROM information_schema.tables t "
            "WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE' "
            "AND NOT EXISTS (SELECT FROM information_schema.columns c "
            "WHERE c.table_name = t.table_name AND c.column_name = 'tenant_id')"
        )
    ).scalars()
    assert set(missing) == shared
