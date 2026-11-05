"""M29: the installable app (the manifest a company's address serves) and force update.

Company calls run at acme.localhost or the default company, admin calls at admin.localhost, as
the app's database role.
"""

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.audit import AuditLog
from app.models.platform import PlatformAppUpdate
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    gstin,
    helper,
    onboard,
    owner_of,
)
from tests.integration.test_tenant import png, put_logo

pytestmark = pytest.mark.integration

STATUS = "/api/v1/admin/system/app-update"
FORCE = "/api/v1/admin/system/force-update"
MANIFEST = "/api/v1/tenant/manifest.webmanifest"
ACME = {"host": "acme.localhost"}
MARK = "/icons/duolink-mark.svg"


def generation_at(client, headers=None):
    response = client.get("/api/v1/tenant", headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()["app_generation"]


# ------------------------------------------------------------------ force update


def test_the_generation_starts_at_zero_with_the_backend_build(client, boss, acme):
    assert generation_at(client) == 0
    assert generation_at(client, ACME) == 0
    status = client.get(STATUS, headers=boss)
    assert status.status_code == 200, status.text
    assert status.json() == {
        "generation": 0,
        "forced_at": None,
        "forced_by": None,
        "backend_version": get_settings().app_version,
        "backend_build": "dev",  # APP_BUILD is not set in the tests
    }


def test_the_backend_build_is_what_app_build_says(client, boss, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_build", "4f2c9a1")
    assert client.get(STATUS, headers=boss).json()["backend_build"] == "4f2c9a1"


def test_a_super_admin_forces_an_update_and_every_company_sees_the_new_generation(
    client, boss, acme
):
    forced = client.post(FORCE, headers=boss, json={"reason": "Release 1.29"})
    assert forced.status_code == 200, forced.text
    body = forced.json()
    assert body["generation"] == 1
    assert body["forced_by"] == "Duolink Ops"
    assert body["forced_at"] is not None
    # Every company reads it from GET /tenant, signed in or not.
    assert generation_at(client) == 1
    assert generation_at(client, ACME) == 1
    assert generation_at(client, owner_of(client)) == 1

    again = client.post(FORCE, headers=boss, json={})
    assert again.json()["generation"] == 2
    assert generation_at(client, ACME) == 2
    assert client.get(STATUS, headers=boss).json()["generation"] == 2


def test_forcing_is_audited_with_the_generation_and_the_reason(client, boss):
    client.post(FORCE, headers=boss, json={"reason": "  Release 1.29  "})
    client.post(FORCE, headers=boss, json={"reason": "   "})
    rows = client.get(
        "/api/v1/admin/audit", headers=boss, params={"action": "app_update_force"}
    ).json()["items"]
    assert [r["details"] for r in rows] == [
        {"generation": 2, "reason": None},  # newest first; a blank reason is no reason
        {"generation": 1, "reason": "Release 1.29"},
    ]
    assert {r["admin_email"] for r in rows} == {"ops@duolink.app"}
    assert {r["tenant_slug"] for r in rows} == {None}  # the platform's act, not a company's


def test_support_cannot_force_an_update_but_can_read_where_it_stands(client, boss, helper):
    refused = client.post(FORCE, headers=helper, json={})
    assert refused.status_code == 403, refused.text
    assert client.get(STATUS, headers=helper).json()["generation"] == 0
    assert generation_at(client) == 0


def test_a_company_user_cannot_reach_force_update(client, acme):
    owner = owner_of(client)
    # The admin API does not exist at a company's address, and a company token is no good there.
    assert client.post(FORCE, headers=owner, json={}).status_code == 404
    assert (
        client.post(FORCE, headers={**owner, "host": "admin.localhost"}, json={}).status_code == 401
    )


def test_a_long_reason_is_refused(client, boss):
    assert client.post(FORCE, headers=boss, json={"reason": "x" * 201}).status_code == 422
    assert generation_at(client) == 0


def test_forcing_touches_no_company_data(client, boss, acme, seeded):
    before = seeded.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    client.post(FORCE, headers=boss, json={})
    after = seeded.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert after == before
    # The one platform row moved, and nothing else in it but who and when.
    row = seeded.get(PlatformAppUpdate, 1)
    assert row is not None and row.generation == 1 and row.forced_by is not None


# ------------------------------------------------------------------ the manifest


def test_the_manifest_names_the_company_and_uses_the_duolink_mark(client, acme):
    response = client.get(MANIFEST, headers=ACME)  # no sign-in: the browser fetches it
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/manifest+json")
    assert response.headers["cache-control"] == "no-cache"
    body = response.json()
    name = client.get("/api/v1/tenant", headers=ACME).json()["name"]
    assert body["name"] == name
    assert body["display"] == "standalone"
    assert body["start_url"] == "/"
    assert [i["src"] for i in body["icons"]] == [MARK, "/icons/duolink-maskable.svg"]


def test_the_manifest_uses_the_companys_logo_first(client):
    owner = owner_of(client, slug="main", user="owner", password="owner-pass-123")
    assert put_logo(client, owner, png(192)).status_code == 200
    logo_url = client.get("/api/v1/tenant").json()["logo_url"]
    icons = client.get(MANIFEST).json()["icons"]
    assert icons[0] == {"src": logo_url, "type": "image/png", "sizes": "192x192", "purpose": "any"}
    assert icons[1]["src"] == MARK  # always there as well


def test_another_companys_manifest_is_its_own(client, boss, acme):
    onboard(
        client,
        boss,
        name="Beta Cements",
        slug="beta",
        legal_name="Beta Cements Private Limited",
        registration_no=gstin(pan="AAPFB0939F"),
        owner_username="bala",
        owner_email="bala@beta.example",
    )
    beta = {"host": "beta.localhost"}
    named = client.get("/api/v1/tenant", headers=beta).json()["name"]
    assert client.get(MANIFEST, headers=beta).json()["name"] == named
    assert client.get(MANIFEST, headers=ACME).json()["name"] != named


def test_an_unknown_address_has_no_manifest(client):
    assert client.get(MANIFEST, headers={"host": "nobody.localhost"}).status_code == 404
