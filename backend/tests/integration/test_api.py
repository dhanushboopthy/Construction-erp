"""API tests against PostgreSQL. Run with `make test` (uses the compose database)."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.enums import DocType
from app.models.setup import Location
from app.services.numbering import allocate_number
from tests.conftest import login

pytestmark = pytest.mark.integration


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/health/ready").status_code == 200


def test_login_me_and_wrong_password(client):
    headers = login(client, "owner", "owner-pass-123")
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["role"] == "owner"

    bad = client.post("/api/v1/auth/login", json={"username": "owner", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["code"] == "NOT_AUTHENTICATED"


def test_refresh_rotates_and_detects_reuse(client):
    login(client, "owner", "owner-pass-123")
    old_cookie = client.cookies.get("erp_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    client.cookies.set("erp_refresh", old_cookie, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_counter_cannot_use_owner_routes(client):
    headers = login(client, "counter1", "counter-pass-123")
    response = client.get("/api/v1/users", headers=headers)
    assert response.status_code == 403 and response.json()["code"] == "PERMISSION_DENIED"


def test_owner_creates_user_and_it_is_audited(client, seeded):
    headers = login(client, "owner", "owner-pass-123")
    s1 = seeded.execute(select(Location).where(Location.code == "S1")).scalar_one()
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "counter3",
            "full_name": "New Counter",
            "role": "counter",
            "password": "long-enough-pass",
            "location_ids": [s1.id],
        },
    )
    assert response.status_code == 201, response.text
    row = seeded.execute(
        select(AuditLog).where(
            AuditLog.entity == "app_user", AuditLog.entity_id == str(response.json()["id"])
        )
    ).scalar_one()
    assert row.user_id is not None and row.changes["password_hash"] == "***"


def test_last_owner_cannot_be_demoted(client):
    headers = login(client, "owner", "owner-pass-123")
    me = client.get("/api/v1/auth/me", headers=headers).json()
    response = client.patch(f"/api/v1/users/{me['id']}", headers=headers, json={"role": "counter"})
    assert response.status_code == 409 and response.json()["code"] == "LAST_OWNER"


def test_numbering_is_sequential_per_series(seeded):
    s1 = seeded.execute(select(Location).where(Location.code == "S1")).scalar_one()
    first = allocate_number(
        seeded, location_id=s1.id, doc_type=DocType.SALES_INVOICE, on=date(2026, 10, 9)
    )
    second = allocate_number(
        seeded, location_id=s1.id, doc_type=DocType.SALES_INVOICE, on=date(2026, 10, 9)
    )
    note = allocate_number(
        seeded, location_id=s1.id, doc_type=DocType.CREDIT_NOTE, on=date(2026, 10, 9)
    )
    assert (first, second, note) == ("S1/26-27/00001", "S1/26-27/00002", "S1C/26-27/00001")
