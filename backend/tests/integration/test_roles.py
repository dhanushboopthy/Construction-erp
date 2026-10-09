"""Every route has a role test: who may call it, and that others get 401/403."""

import pytest
from sqlalchemy import select

from app.models.setup import Location
from tests.conftest import login

pytestmark = pytest.mark.integration

OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")
ACCOUNTANT = ("accounts", "accounts-pass-123")

# (method, path, json body) for routes only the owner may call.
OWNER_ONLY = [
    ("GET", "/api/v1/users", None),
    (
        "POST",
        "/api/v1/users",
        {"username": "x_user", "full_name": "X", "role": "owner", "password": "long-enough-pass"},
    ),
    ("GET", "/api/v1/users/1", None),
    ("PATCH", "/api/v1/users/1", {"full_name": "X"}),
    ("POST", "/api/v1/users/1/reset-password", {"new_password": "long-enough-pass"}),
    ("POST", "/api/v1/locations", {"code": "S9", "name": "X", "kind": "shop", "state_code": "33"}),
    ("PATCH", "/api/v1/locations/1", {"name": "X"}),
    ("PUT", "/api/v1/settings", {"legal_name": "X", "state_code": "33"}),
    ("GET", "/api/v1/audit-log", None),
]

SIGNED_IN = [
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/locations"),
    ("GET", "/api/v1/settings"),
]


@pytest.mark.parametrize(("method", "path", "body"), OWNER_ONLY)
@pytest.mark.parametrize("who", [COUNTER, ACCOUNTANT], ids=["counter", "accountant"])
def test_owner_routes_refuse_staff(client, who, method, path, body):
    headers = login(client, *who)
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize(("method", "path", "body"), OWNER_ONLY)
def test_owner_routes_need_sign_in(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 401 and response.json()["code"] == "NOT_AUTHENTICATED"


@pytest.mark.parametrize(("method", "path"), SIGNED_IN)
@pytest.mark.parametrize(
    "who", [OWNER, COUNTER, ACCOUNTANT], ids=["owner", "counter", "accountant"]
)
def test_signed_in_routes_open_to_every_role(client, who, method, path):
    headers = login(client, *who)
    assert client.request(method, path, headers=headers).status_code == 200
    assert client.request(method, path).status_code == 401


def test_bad_token_is_rejected(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


# ---------------------------------------------------------------- owner can do each thing


def test_owner_manages_locations(client, seeded):
    headers = login(client, *OWNER)
    created = client.post(
        "/api/v1/locations",
        headers=headers,
        json={"code": "S3", "name": "Shop 3", "kind": "shop", "state_code": "33"},
    )
    assert created.status_code == 201, created.text
    location_id = created.json()["id"]

    dup = client.post(
        "/api/v1/locations",
        headers=headers,
        json={"code": "S3", "name": "Again", "kind": "shop", "state_code": "33"},
    )
    assert dup.status_code == 409 and dup.json()["field"] == "code"

    off = client.patch(
        f"/api/v1/locations/{location_id}", headers=headers, json={"is_active": False}
    )
    assert off.status_code == 200 and off.json()["is_active"] is False
    codes = [loc["code"] for loc in client.get("/api/v1/locations", headers=headers).json()]
    assert "S3" not in codes
    all_codes = [
        loc["code"]
        for loc in client.get("/api/v1/locations?include_inactive=true", headers=headers).json()
    ]
    assert "S3" in all_codes
    assert (
        client.patch("/api/v1/locations/99999", headers=headers, json={"name": "X"}).status_code
        == 404
    )


def test_owner_saves_settings_and_amounts_stay_decimal_strings(client):
    headers = login(client, *OWNER)
    current = client.get("/api/v1/settings", headers=headers).json()
    body = {k: v for k, v in current.items() if k != "id"}
    body |= {"default_credit_limit": "15000.50", "gstin": "33aapfu0939f1z2"}
    saved = client.put("/api/v1/settings", headers=headers, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["default_credit_limit"] == "15000.50"
    assert saved.json()["gstin"] == "33AAPFU0939F1Z2"

    bad = client.put("/api/v1/settings", headers=headers, json=body | {"gstin": "33AAPFU0939F1ZA"})
    assert bad.status_code == 422 and bad.json()["field"] == "gstin"

    # A valid Maharashtra GSTIN cannot belong to a Tamil Nadu (33) shop.
    other_state = client.put(
        "/api/v1/settings", headers=headers, json=body | {"gstin": "27AAPFU0939F1ZV"}
    )
    assert other_state.status_code == 422 and other_state.json()["field"] == "gstin"


def test_owner_edits_user_and_resets_password(client, seeded):
    headers = login(client, *OWNER)
    s2 = seeded.execute(select(Location).where(Location.code == "S2")).scalar_one()
    users = {u["username"]: u for u in client.get("/api/v1/users", headers=headers).json()}
    counter = users["counter1"]

    one = client.get(f"/api/v1/users/{counter['id']}", headers=headers)
    assert one.status_code == 200 and one.json()["username"] == "counter1"
    assert client.get("/api/v1/users/99999", headers=headers).status_code == 404

    moved = client.patch(
        f"/api/v1/users/{counter['id']}", headers=headers, json={"location_ids": [s2.id]}
    )
    assert [loc["code"] for loc in moved.json()["locations"]] == ["S2"]

    none = client.patch(
        f"/api/v1/users/{counter['id']}", headers=headers, json={"location_ids": []}
    )
    assert none.status_code == 409 and none.json()["code"] == "COUNTER_NEEDS_LOCATION"

    reset = client.post(
        f"/api/v1/users/{counter['id']}/reset-password",
        headers=headers,
        json={"new_password": "brand-new-pass"},
    )
    assert reset.status_code == 204
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "counter1", "password": "counter-pass-123"}
        ).status_code
        == 401
    )
    login(client, "counter1", "brand-new-pass")


def test_deactivated_user_cannot_sign_in(client):
    headers = login(client, *OWNER)
    users = {u["username"]: u for u in client.get("/api/v1/users", headers=headers).json()}
    off = client.patch(
        f"/api/v1/users/{users['counter2']['id']}", headers=headers, json={"is_active": False}
    )
    assert off.status_code == 200
    response = client.post(
        "/api/v1/auth/login", json={"username": "counter2", "password": "counter-pass-123"}
    )
    assert response.status_code == 401


def test_owner_cannot_deactivate_self_while_another_owner_exists(client):
    headers = login(client, *OWNER)
    client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "owner2",
            "full_name": "Second Owner",
            "role": "owner",
            "password": "long-enough-pass",
        },
    )
    me = client.get("/api/v1/auth/me", headers=headers).json()
    response = client.patch(f"/api/v1/users/{me['id']}", headers=headers, json={"is_active": False})
    assert response.status_code == 409 and response.json()["code"] == "SELF_DEACTIVATION"


def test_duplicate_username_and_unknown_location(client):
    headers = login(client, *OWNER)
    base = {"full_name": "X", "role": "counter", "password": "long-enough-pass"}
    taken = client.post("/api/v1/users", headers=headers, json=base | {"username": "counter1"})
    assert taken.status_code == 409 and taken.json()["code"] == "USERNAME_TAKEN"
    missing = client.post(
        "/api/v1/users",
        headers=headers,
        json=base | {"username": "counter9", "location_ids": [99999]},
    )
    assert missing.status_code == 404 and missing.json()["field"] == "location_ids"


def test_owner_reads_and_filters_audit_log(client):
    headers = login(client, *OWNER)
    client.post(
        "/api/v1/locations",
        headers=headers,
        json={"code": "S4", "name": "Shop 4", "kind": "shop", "state_code": "33"},
    )
    page = client.get(
        "/api/v1/audit-log",
        headers=headers,
        params={
            "entity": "location",
            "action": "insert",
            "since": "2000-01-01T00:00:00Z",
            "until": "2999-01-01T00:00:00Z",
            "limit": 5,
        },
    ).json()
    assert page["total"] >= 1 and page["limit"] == 5
    entry = page["items"][0]
    assert entry["entity"] == "location" and entry["changes"]["code"] == "S4"
    by_id = client.get(
        "/api/v1/audit-log",
        headers=headers,
        params={"entity_id": entry["entity_id"], "user_id": entry["user_id"]},
    ).json()
    assert by_id["total"] >= 1


# ---------------------------------------------------------------- auth flows for every role


def test_logout_ends_the_session(client):
    login(client, *COUNTER)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 204  # idempotent


def test_change_password_signs_out_everywhere(client):
    headers = login(client, *ACCOUNTANT)
    wrong = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "nope", "new_password": "another-long-pass"},
    )
    assert wrong.status_code == 401 and wrong.json()["field"] == "current_password"
    ok = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": ACCOUNTANT[1], "new_password": "another-long-pass"},
    )
    assert ok.status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401
    login(client, "accounts", "another-long-pass")


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": "counter2", "password": "wrong"})
    locked = client.post(
        "/api/v1/auth/login", json={"username": "counter2", "password": "counter-pass-123"}
    )
    assert locked.status_code == 423 and locked.json()["code"] == "ACCOUNT_LOCKED"


def test_unknown_user_and_missing_refresh_cookie(client):
    unknown = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "x"})
    assert unknown.status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401
