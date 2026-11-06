"""M27: Duolink's GSP account and GSTIN lookup from the admin.

Admin calls run at admin.localhost, company calls at the company's own address, as the app's
database role. Only the pretend provider is used: there is no network, and real provider calls go
through the same `services/gsp/` interface the unit tests cover with a mock transport.
"""

import json

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select, text

from app.core.config import Environment, get_settings
from app.core.crypto import decrypt_json
from app.main import app
from app.models.compliance import EwayBill
from app.models.enums import IntegrationKind
from app.services import gsp
from app.services.gsp.base import GspError
from app.services.platform import integrations as service
from tests.conftest import login
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    gstin,
    helper,
    onboard,
    owner_of,
)
from tests.integration.test_compliance import (  # noqa: F401 - the fixtures
    clean_fake,
    eway,
    sale,
    shop,
)
from tests.integration.test_sales import world  # noqa: F401 - the fixture

pytestmark = pytest.mark.integration

BASE = "/api/v1/admin/integrations"
KEY = Fernet.generate_key().decode()
OTHER_KEY = Fernet.generate_key().decode()
GSP_SECRETS = {
    "client_id": "duolink-client-id",
    "client_secret": "S3cret-Client-Value-9876",
    "username": "duolink-portal-user",
    "password": "Portal-Pass-Value-4321",
}
LOOKUP_SECRET = {"api_key": "Lookup-Key-Value-abcd-wxyz"}
SANDBOX = {"provider": "sandbox", "base_url": "https://gsp.example/api"}
FAKE = {"provider": "fake"}


class Offline:
    """Stands in for the HTTP adapter: a sandbox or live provider is never reached from a test
    (there is no network). Every call fails the way an unreachable provider does."""

    def __init__(self, config):
        self.config = config

    def check_connection(self):
        raise GspError("Cannot reach the GSP", code="GSP_UNREACHABLE", retryable=True)


@pytest.fixture(autouse=True)
def secret_key(monkeypatch):
    """INTEGRATION_SECRET_KEY, set for the test only; and no real provider can be called."""
    monkeypatch.setattr(gsp, "SandboxGsp", Offline)
    monkeypatch.setattr(get_settings(), "integration_secret_key", SecretStr(KEY))
    gsp.reset_client()
    yield KEY
    gsp.reset_client()


def connect(client, headers, kind="gsp", **body):
    return client.put(f"{BASE}/{kind}", headers=headers, json=body)


def connect_gsp(client, boss, **extra):
    made = connect(client, boss, **(SANDBOX | GSP_SECRETS | extra))
    assert made.status_code == 200, made.text
    return made.json()


def fake_client(db, kind=IntegrationKind.GSP):
    """The pretend provider the saved settings build (to queue a failure or read its calls)."""
    config = gsp.saved_config(db, kind)
    assert config is not None
    return gsp.client_for(config)


def usage(client, headers, kind="gsp"):
    rows = client.get(f"{BASE}/usage", headers=headers).json()
    return next(r for r in rows if r["kind"] == kind)


def leaves(value):
    if isinstance(value, dict):
        for inner in value.values():
            yield from leaves(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from leaves(inner)
    else:
        yield str(value)


# ------------------------------------------------------------------ the key is never returned


def test_a_saved_key_shows_only_its_last_four_characters_and_no_endpoint_returns_more(
    client, boss, helper, acme, seeded
):
    saved = connect_gsp(client, boss)
    assert saved["key_last4"] == "9876" and saved["provider"] == "sandbox"
    assert saved["credential_fields"] == list(GSP_SECRETS)
    assert (
        connect(
            client,
            boss,
            "gstin_lookup",
            provider="live",
            base_url="https://l.example",
            **LOOKUP_SECRET,
        ).json()["key_last4"]
        == "wxyz"
    )
    secrets = [*GSP_SECRETS.values(), *LOOKUP_SECRET.values()]

    responses = [saved]
    for who in (boss, helper):
        responses.append(client.get(BASE, headers=who).json())
    for kind in ("gsp", "gstin_lookup"):
        client.post(f"{BASE}/{kind}/test", headers=boss)
        responses.append(client.get(f"{BASE}/{kind}/companies", headers=boss).json())
        responses.append(client.get(f"{BASE}/{kind}/failures", headers=boss).json())
    responses.append(client.get(f"{BASE}/usage", headers=boss).json())
    # Every admin GET, as a Super Admin, and the audit log.
    ids = {"tenant_id": acme["id"], "user_id": 1, "ticket_id": 1, "plan_id": 1, "kind": "gsp"}
    for path in app.openapi()["paths"]:
        if path.startswith("/api/v1/admin/") and "get" in app.openapi()["paths"][path]:
            url = path
            for name, value in ids.items():
                url = url.replace("{" + name + "}", str(value))
            if "{" not in url:
                answer = client.get(url, headers=boss)
                # The audit CSV export (M24) is text, not JSON: check its text too.
                responses.append(
                    answer.json()
                    if answer.headers["content-type"].startswith("application/json")
                    else answer.text
                )
    audit = client.get("/api/v1/admin/audit", headers=boss).text
    everything = json.dumps(responses) + audit
    for secret in secrets:
        assert secret not in everything
    # The text of every value, not only the whole body: no field holds a full secret either.
    assert not [v for r in responses for v in leaves(r) if v in secrets]


def test_credentials_are_encrypted_at_rest(client, boss, seeded):
    connect_gsp(client, boss)
    stored = seeded.execute(
        text("SELECT credentials FROM platform_integration WHERE kind = 'gsp'")
    ).scalar_one()
    for secret in GSP_SECRETS.values():
        assert secret not in stored
    assert decrypt_json(stored, KEY) == GSP_SECRETS
    # Another key cannot read them.
    with pytest.raises(Exception, match="another INTEGRATION_SECRET_KEY"):
        decrypt_json(stored, OTHER_KEY)


def test_the_audit_log_names_the_change_but_never_a_credential(client, boss, seeded):
    connect_gsp(client, boss)
    client.patch(
        f"{BASE}/gsp/limits",
        headers=boss,
        json={"daily_limit": 10, "monthly_limit": 100, "warn_at_percent": 70, "cache_hours": 12},
    )
    rows = seeded.execute(
        text(
            "SELECT action, details::text FROM platform_audit_log "
            "WHERE action LIKE 'integration_%' ORDER BY id"
        )
    ).all()
    assert [r[0] for r in rows] == ["integration_connect", "integration_limits"]
    connect_details = json.loads(rows[0][1])
    assert connect_details["key_last4"] == "9876" and connect_details["provider"] == "sandbox"
    assert connect_details["fields_changed"] == sorted(GSP_SECRETS)
    assert json.loads(rows[1][1])["old"]["daily_limit"] == 50
    assert not [s for s in GSP_SECRETS.values() if s in rows[0][1] + rows[1][1]]


def test_a_blank_credential_keeps_the_saved_one(client, boss, seeded):
    connect_gsp(client, boss)
    again = connect(client, boss, **(SANDBOX | {"password": "New-Portal-Pass-0001"}))
    assert again.status_code == 200 and again.json()["key_last4"] == "9876"
    stored = decrypt_json(
        seeded.execute(
            text("SELECT credentials FROM platform_integration WHERE kind = 'gsp'")
        ).scalar_one(),
        KEY,
    )
    assert stored == GSP_SECRETS | {"password": "New-Portal-Pass-0001"}


def test_connect_needs_complete_credentials_a_real_key_and_a_secret_key(client, boss, monkeypatch):
    missing = connect(client, boss, **(SANDBOX | {"client_id": "only-this-one"}))
    assert missing.status_code == 409 and missing.json()["code"] == "CREDENTIALS_MISSING"
    short = connect(client, boss, **(SANDBOX | GSP_SECRETS | {"client_secret": "tiny"}))
    assert short.json()["code"] == "KEY_TOO_SHORT"
    plain = connect(client, boss, **(SANDBOX | GSP_SECRETS | {"base_url": "http://x.example"}))
    assert plain.status_code == 200  # a sandbox may be reached over http
    live = connect(
        client,
        boss,
        **(SANDBOX | GSP_SECRETS | {"provider": "live", "base_url": "http://x.example"}),
    )
    assert live.json()["code"] == "BASE_URL_NOT_HTTPS"
    monkeypatch.setattr(get_settings(), "integration_secret_key", SecretStr(""))
    nokey = connect(client, boss, **(SANDBOX | GSP_SECRETS))
    assert nokey.status_code == 409 and nokey.json()["code"] == "INTEGRATION_KEY_MISSING"
    # The pretend provider has no keys to protect, so it needs no secret key.
    assert connect(client, boss, **FAKE).status_code == 200


def test_the_pretend_provider_is_refused_in_production(client, boss, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", Environment.PRODUCTION)
    refused = connect(client, boss, **FAKE)
    assert refused.status_code == 409 and refused.json()["code"] == "FAKE_NOT_IN_PRODUCTION"


def test_the_app_refuses_to_start_with_saved_keys_and_no_secret_key(
    client, boss, seeded, monkeypatch
):
    service.refuse_to_start_without_key(seeded)  # nothing saved yet
    connect_gsp(client, boss)
    service.refuse_to_start_without_key(seeded)  # saved, key present
    monkeypatch.setattr(get_settings(), "integration_secret_key", SecretStr(""))
    with pytest.raises(RuntimeError, match="INTEGRATION_SECRET_KEY"):
        service.refuse_to_start_without_key(seeded)


def test_a_different_secret_key_is_reported_not_guessed(client, boss, seeded, monkeypatch):
    connect_gsp(client, boss)
    monkeypatch.setattr(get_settings(), "integration_secret_key", SecretStr(OTHER_KEY))
    tested = client.post(f"{BASE}/gsp/test", headers=boss).json()
    assert tested["ok"] is False and tested["error_code"] == "INTEGRATION_KEY_MISMATCH"
    assert connect(client, boss, **(SANDBOX | GSP_SECRETS)).json()["code"] == (
        "INTEGRATION_KEY_MISMATCH"
    )


# ------------------------------------------------------------------ status and roles


def test_status_before_and_after_connecting(client, boss, helper):
    first = {r["kind"]: r for r in client.get(BASE, headers=helper).json()}
    assert set(first) == {"gsp", "gstin_lookup"}
    gsp_row = first["gsp"]
    # Nothing saved: the environment (the pretend provider in tests) is in force.
    assert (gsp_row["status"], gsp_row["source"], gsp_row["effective_provider"]) == (
        "not_connected",
        "environment",
        "fake",
    )
    assert gsp_row["key_last4"] is None and gsp_row["secret_key_set"] is True
    assert (gsp_row["daily_limit"], gsp_row["monthly_limit"]) == (50, 500)
    assert (gsp_row["warn_at_percent"], first["gstin_lookup"]["cache_hours"]) == (80, 168)

    connect_gsp(client, boss)
    after = {r["kind"]: r for r in client.get(BASE, headers=helper).json()}
    assert (after["gsp"]["status"], after["gsp"]["source"]) == ("connected", "database")
    # The lookup rides on the GSP account until it has settings of its own.
    assert after["gstin_lookup"]["source"] == "gsp_account"
    assert after["gstin_lookup"]["status"] == "not_connected"


def test_support_reads_the_status_and_nothing_else(client, boss, helper):
    assert client.get(BASE, headers=helper).status_code == 200
    for method, path, body in (
        ("PUT", f"{BASE}/gsp", {"provider": "fake"}),
        ("POST", f"{BASE}/gsp/test", None),
        ("POST", f"{BASE}/gsp/disconnect", None),
        ("PATCH", f"{BASE}/gsp/limits", {}),
        ("GET", f"{BASE}/usage", None),
        ("GET", f"{BASE}/gsp/companies", None),
        ("GET", f"{BASE}/gsp/failures", None),
        ("POST", f"{BASE}/gstin-lookup", {"gstin": gstin()}),
    ):
        response = client.request(method, path, headers=helper, json=body)
        assert response.status_code == 403, f"{method} {path}"
        assert response.json()["code"] == "PERMISSION_DENIED"


def test_limits_are_checked_and_audited(client, boss):
    ok = client.patch(
        f"{BASE}/gstin_lookup/limits",
        headers=boss,
        json={"daily_limit": 5, "monthly_limit": 50, "warn_at_percent": 60, "cache_hours": 0},
    )
    assert ok.status_code == 200 and ok.json()["cache_hours"] == 0
    over = client.patch(
        f"{BASE}/gstin_lookup/limits",
        headers=boss,
        json={"daily_limit": 60, "monthly_limit": 50, "warn_at_percent": 60, "cache_hours": 0},
    )
    assert over.status_code == 409 and over.json()["code"] == "LIMIT_DAILY_OVER_MONTHLY"
    zero = client.patch(
        f"{BASE}/gstin_lookup/limits",
        headers=boss,
        json={"daily_limit": 0, "monthly_limit": 50, "warn_at_percent": 60, "cache_hours": 0},
    )
    assert zero.status_code == 422


def test_disconnect_forgets_the_keys_and_falls_back_to_the_environment(client, boss, seeded):
    connect_gsp(client, boss)
    gone = client.post(f"{BASE}/gsp/disconnect", headers=boss)
    assert gone.status_code == 200
    assert (gone.json()["provider"], gone.json()["key_last4"], gone.json()["source"]) == (
        None,
        None,
        "environment",
    )
    stored = seeded.execute(
        text("SELECT credentials FROM platform_integration WHERE kind = 'gsp'")
    ).scalar_one()
    assert stored is None
    again = client.post(f"{BASE}/gsp/disconnect", headers=boss)
    assert again.status_code == 409 and again.json()["code"] == "NOT_CONNECTED"


# ------------------------------------------------------------------ settings in force


def test_with_saved_settings_the_eway_bill_uses_them_and_without_them_the_environment(
    client, boss, world, shop, seeded
):
    inv = sale(client, world)
    connect(client, boss, **FAKE)
    made = eway(client, world["owner"], inv)
    assert made.status_code == 201, made.text
    bill = seeded.execute(
        select(EwayBill).where(EwayBill.number == made.json()["number"])
    ).scalar_one()
    assert bill.responses[0]["response"]["source"] == "database"

    client.post(f"{BASE}/gsp/disconnect", headers=boss)
    second = sale(client, world, item="tmt")
    made2 = eway(client, world["owner"], second)
    assert made2.status_code == 201, made2.text
    bill2 = seeded.execute(
        select(EwayBill).where(EwayBill.number == made2.json()["number"])
    ).scalar_one()
    assert bill2.responses[0]["response"]["source"] == "environment"


def test_a_call_is_counted_by_outcome_with_no_bodies(client, boss, world, shop, seeded):
    connect(client, boss, **FAKE)
    inv = sale(client, world)
    assert eway(client, world["owner"], inv).status_code == 201
    fake_client(seeded).failures.append(GspError("Portal is down", code="GSP_DOWN", retryable=True))
    again = sale(client, world, item="tmt")
    failed = eway(client, world["owner"], again)
    assert failed.status_code == 502 and failed.json()["code"] == "GSP_DOWN"

    today = usage(client, boss)["today"]
    assert (today["ok"], today["failed"], today["cached"], today["blocked"]) == (1, 1, 0, 0)
    assert today["total"] == 2
    row = (
        seeded.execute(text("SELECT * FROM integration_call WHERE outcome = 'failed'"))
        .mappings()
        .one()
    )
    # The table has no column that could hold a request or a response.
    assert set(row) == {
        "id",
        "tenant_id",
        "kind",
        "operation",
        "outcome",
        "error_code",
        "latency_ms",
        "at",
    }
    assert (row["operation"], row["error_code"], row["tenant_id"]) == (
        "generate_eway",
        "GSP_DOWN",
        1,
    )

    failures = client.get(f"{BASE}/gsp/failures", headers=boss).json()
    assert len(failures) == 1 and failures[0]["operation"] == "generate_eway"
    assert set(failures[0]) == {
        "id",
        "at",
        "tenant_id",
        "tenant_name",
        "operation",
        "error_code",
        "latency_ms",
    }
    status = client.get(BASE, headers=boss).json()[0]
    assert status["status"] == "failing" and "GSP_DOWN" in status["last_failure_message"]
    assert status["last_success_at"] is not None


def test_per_company_usage(client, boss, world, shop, acme, seeded):
    connect(client, boss, **FAKE)
    assert eway(client, world["owner"], sale(client, world)).status_code == 201
    rows = client.get(f"{BASE}/gsp/companies", headers=boss).json()
    main = next(r for r in rows if r["slug"] == "main")
    assert (main["calls_today"], main["calls_month"], main["over_limit"]) == (1, 1, False)
    assert all(r["slug"] != "acme" for r in rows)  # no calls, no row
    assert set(main) == {
        "tenant_id",
        "slug",
        "name",
        "calls_today",
        "calls_month",
        "cached_month",
        "blocked_month",
        "failed_month",
        "near_limit",
        "over_limit",
    }
    client.patch(
        f"{BASE}/gsp/limits",
        headers=boss,
        json={"daily_limit": 1, "monthly_limit": 10, "warn_at_percent": 80, "cache_hours": 1},
    )
    main = client.get(f"{BASE}/gsp/companies", headers=boss).json()[0]
    assert main["near_limit"] is True and main["over_limit"] is True


def test_the_connection_test_is_one_live_call_and_a_failure_is_an_answer(client, boss, seeded):
    connect(client, boss, **FAKE)
    good = client.post(f"{BASE}/gsp/test", headers=boss).json()
    assert good["ok"] is True and good["error_code"] is None
    assert good["integration"]["status"] == "connected"
    assert good["integration"]["last_success_at"] is not None
    fake_client(seeded).failures.append(
        GspError("Login refused for duolink-portal-user", code="GSP_AUTH_FAILED")
    )
    bad = client.post(f"{BASE}/gsp/test", headers=boss).json()
    assert bad["ok"] is False and bad["error_code"] == "GSP_AUTH_FAILED"
    assert bad["integration"]["status"] == "failing"
    calls = usage(client, boss)["today"]
    assert (calls["ok"], calls["failed"]) == (1, 1)  # a test is counted, with no company


def test_a_failure_message_never_holds_a_credential(client, boss, seeded, monkeypatch):
    connect_gsp(client, boss)
    leak = f"Bad login {GSP_SECRETS['username']} with {GSP_SECRETS['password']}"

    class Leaky:
        def check_connection(self):
            raise GspError(leak, code="GSP_AUTH_FAILED")

    monkeypatch.setattr(gsp, "client_for", lambda _config: Leaky())
    bad = client.post(f"{BASE}/gsp/test", headers=boss).json()
    stored = client.get(BASE, headers=boss).json()[0]["last_failure_message"]
    for shown in (json.dumps(bad), stored):
        assert "Portal-Pass-Value-4321" not in shown and "duolink-portal-user" not in shown
    assert "Bad login" in bad["message"] and "****" in stored


# ------------------------------------------------------------------ GSTIN lookup


LOOKUP = "/api/v1/parties/gstin-lookup"


def calls_to_provider(client_obj, name="lookup_gstin"):
    return len([c for c in client_obj.calls if c[0] == name])


def test_a_company_fetches_details_and_a_second_lookup_is_cached(client, world):
    fake = gsp.get_client()
    before = calls_to_provider(fake)
    number = gstin()
    first = client.post(LOOKUP, headers=world["owner"], json={"gstin": number})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["gstin"] == number and body["cached"] is False and body["status"] == "Active"
    assert body["legal_name"] and body["address"] and body["state_code"] == "33"
    assert body["lookups_left_today"] == 49
    second = client.post(LOOKUP, headers=world["owner"], json={"gstin": number.lower()})
    assert second.status_code == 200 and second.json()["cached"] is True
    assert second.json()["legal_name"] == body["legal_name"]
    assert calls_to_provider(fake) == before + 1  # the cached one never reached the provider


def test_a_company_over_its_daily_lookup_limit_gets_429_and_the_call_is_logged_blocked(
    client, boss, world, seeded
):
    client.patch(
        f"{BASE}/gstin_lookup/limits",
        headers=boss,
        json={"daily_limit": 2, "monthly_limit": 10, "warn_at_percent": 50, "cache_hours": 24},
    )
    fake = gsp.get_client()
    owner = world["owner"]
    one, two, three = gstin(entity="1"), gstin(entity="2"), gstin(entity="3")
    first = client.post(LOOKUP, headers=owner, json={"gstin": one})
    assert first.json()["near_limit"] is True and first.json()["lookups_left_today"] == 1
    assert client.post(LOOKUP, headers=owner, json={"gstin": two}).status_code == 200
    before = calls_to_provider(fake)
    blocked = client.post(LOOKUP, headers=owner, json={"gstin": three})
    assert blocked.status_code == 429 and blocked.json()["code"] == "GSTIN_LOOKUP_LIMIT"
    assert calls_to_provider(fake) == before  # refused before the provider
    # What is already cached is still served, and costs nothing.
    again = client.post(LOOKUP, headers=owner, json={"gstin": one})
    assert again.status_code == 200 and again.json()["cached"] is True

    today = usage(client, boss, "gstin_lookup")["today"]
    assert (today["ok"], today["cached"], today["blocked"], today["failed"]) == (2, 1, 1, 0)
    main = client.get(f"{BASE}/gstin_lookup/companies", headers=boss).json()[0]
    assert (main["calls_today"], main["cached_month"], main["blocked_month"]) == (2, 1, 1)
    assert main["over_limit"] is True


def test_the_limit_is_per_company(client, boss, world, acme):
    client.patch(
        f"{BASE}/gstin_lookup/limits",
        headers=boss,
        json={"daily_limit": 1, "monthly_limit": 10, "warn_at_percent": 80, "cache_hours": 24},
    )
    assert (
        client.post(LOOKUP, headers=world["owner"], json={"gstin": gstin(entity="1")}).status_code
        == 200
    )
    assert (
        client.post(LOOKUP, headers=world["owner"], json={"gstin": gstin(entity="2")}).status_code
        == 429
    )
    other = owner_of(client)
    assert client.post(LOOKUP, headers=other, json={"gstin": gstin(entity="2")}).status_code == 200


def test_the_monthly_limit_blocks_too(client, boss, world):
    client.patch(
        f"{BASE}/gstin_lookup/limits",
        headers=boss,
        json={"daily_limit": 5, "monthly_limit": 5, "warn_at_percent": 80, "cache_hours": 0},
    )
    owner = world["owner"]
    for _ in range(5):  # cache_hours 0: every lookup reaches the provider
        assert client.post(LOOKUP, headers=owner, json={"gstin": gstin()}).status_code == 200
    blocked = client.post(LOOKUP, headers=owner, json={"gstin": gstin()})
    assert blocked.status_code == 429


def test_a_failed_lookup_is_a_502_that_counts_against_the_company(client, boss, world, seeded):
    fake = gsp.get_client()
    fake.failures.append(GspError("Registry is slow", code="GSP_TIMEOUT", retryable=True))
    failed = client.post(LOOKUP, headers=world["owner"], json={"gstin": gstin(entity="5")})
    assert failed.status_code == 502 and failed.json()["code"] == "GSP_TIMEOUT"
    assert "Try again in a minute" in failed.json()["message"]
    # Nothing was cached, so the next try reaches the provider and works.
    retry = client.post(LOOKUP, headers=world["owner"], json={"gstin": gstin(entity="5")})
    assert retry.status_code == 200 and retry.json()["cached"] is False
    today = usage(client, boss, "gstin_lookup")["today"]
    assert (today["ok"], today["failed"]) == (1, 1)


def test_the_gstin_must_be_valid_and_only_owner_and_counter_may_look_up(client, world):
    bad = client.post(LOOKUP, headers=world["owner"], json={"gstin": "33AAPFU0939F1Z0"})
    assert bad.status_code == 422
    assert client.post(LOOKUP, headers=world["owner"], json={}).status_code == 422
    assert client.post(LOOKUP, json={"gstin": gstin()}).status_code == 401
    accountant = login(client, "accounts", "accounts-pass-123")
    assert client.post(LOOKUP, headers=accountant, json={"gstin": gstin()}).status_code == 403
    counter = login(client, "counter1", "counter-pass-123")
    assert client.post(LOOKUP, headers=counter, json={"gstin": gstin()}).status_code == 200


def test_the_cache_is_shared_and_holds_only_public_registry_data(client, world, acme):
    number = gstin(entity="7")
    first = client.post(LOOKUP, headers=world["owner"], json={"gstin": number}).json()
    second = client.post(LOOKUP, headers=owner_of(client), json={"gstin": number}).json()
    assert first["cached"] is False and second["cached"] is True


def test_a_super_admin_looks_up_a_gstin_for_onboarding_with_no_company_limit(client, boss, seeded):
    client.patch(
        f"{BASE}/gstin_lookup/limits",
        headers=boss,
        json={"daily_limit": 1, "monthly_limit": 10, "warn_at_percent": 80, "cache_hours": 0},
    )
    for _ in range(3):
        made = client.post(f"{BASE}/gstin-lookup", headers=boss, json={"gstin": gstin()})
        assert made.status_code == 200 and made.json()["lookups_left_today"] is None
    assert (
        seeded.execute(
            text("SELECT count(*) FROM integration_call WHERE tenant_id IS NULL")
        ).scalar_one()
        == 3
    )
    audited = seeded.execute(
        text("SELECT count(*) FROM platform_audit_log WHERE action = 'gstin_lookup'")
    ).scalar_one()
    assert audited == 3


def test_the_integration_call_rows_are_kept_apart_by_company(client, world, acme, seeded):
    client.post(LOOKUP, headers=world["owner"], json={"gstin": gstin(entity="1")})
    client.post(LOOKUP, headers=owner_of(client), json={"gstin": gstin(entity="2")})
    from app.core.tenancy import set_tenant

    set_tenant(seeded, acme["id"])
    rows = seeded.execute(text("SELECT tenant_id FROM integration_call")).scalars().all()
    assert rows == [acme["id"]]
