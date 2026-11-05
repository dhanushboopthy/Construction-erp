"""The GSP adapters: request shaping, retries, failure handling, and the production guard."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from app.core.config import GspProvider, Settings
from app.services import gsp
from app.services.gsp.base import (
    DocItem,
    DocTotals,
    EwayRequest,
    GspError,
    IrnRequest,
    Party,
)
from app.services.gsp.fake import FakeGsp
from app.services.gsp.sandbox import SandboxGsp

SELLER = Party("Shop", "33AAPFU0939F1Z2", "Chennai", "33", "600001")
BUYER = Party("Ravi", "URP", "Hosur", "29", "635109")
ITEM = DocItem(
    "72142090",
    "TMT",
    Decimal("1000"),
    "kg",
    Decimal("56000"),
    Decimal("18"),
    Decimal("0"),
    Decimal("0"),
    Decimal("10080"),
)
TOTALS = DocTotals(
    Decimal("56000"), Decimal("0"), Decimal("0"), Decimal("10080"), Decimal("0"), Decimal("66080")
)
EWAY = EwayRequest(
    "S1/26-27/00001",
    date(2026, 10, 9),
    SELLER,
    BUYER,
    None,
    TOTALS,
    [ITEM],
    300,
    "TN09AB1234",
    True,
)
IRN = IrnRequest("S1/26-27/00001", date(2026, 10, 9), SELLER, BUYER, None, TOTALS, [ITEM])


def settings(**kw):
    return Settings(
        gsp_provider=GspProvider.SANDBOX,
        gsp_base_url="https://gsp.test/api",
        gsp_client_id="id",
        gsp_client_secret="secret",
        gsp_username="user",
        gsp_password="pass",
        **kw,
    )


def adapter(handler):
    return SandboxGsp(gsp.env_config(settings()), transport=httpx.MockTransport(handler))


def test_sandbox_logs_in_once_and_sends_the_bill():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("authorization")))
        if request.url.path == "/api/auth":
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(
            200,
            json={
                "ewb_no": "391012345678",
                "generated_at": "2026-10-09T10:00:00+05:30",
                "valid_until": "2026-10-11",
            },
        )

    client = adapter(handler)
    result = client.generate_eway(EWAY)
    client.generate_eway(EWAY)
    assert result.number == "391012345678" and result.valid_until == date(2026, 10, 11)
    # One login, then both calls carry the token.
    assert [p for p, _ in seen].count("/api/auth") == 1
    assert all(auth == "Bearer tok" for p, auth in seen if p != "/api/auth")


def test_sandbox_logs_in_again_when_the_token_expires():
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth":
            return httpx.Response(200, json={"access_token": f"tok{state['calls']}"})
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(401, json={})
        return httpx.Response(200, json={"ok": True})

    assert adapter(handler).cancel_eway("391012345678", "wrong vehicle") == {"ok": True}


@pytest.mark.parametrize(
    ("status", "body", "code", "retryable"),
    [
        (500, {}, "GSP_DOWN", True),
        (400, {"message": "Invalid HSN"}, "GSP_REFUSED", False),
        (200, {"status": "error", "message": "Duplicate IRN"}, "GSP_REFUSED", False),
        (200, {}, "GSP_BAD_RESPONSE", False),
    ],
)
def test_sandbox_failures_become_gsp_errors(status, body, code, retryable):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth":
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(status, json=body)

    with pytest.raises(GspError) as caught:
        adapter(handler).generate_eway(EWAY)
    assert caught.value.code == code and caught.value.retryable is retryable


def test_sandbox_timeouts_and_login_failures():
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(GspError) as caught:
        adapter(slow).generate_irn(IRN)
    assert caught.value.code == "GSP_TIMEOUT" and caught.value.retryable

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(GspError) as caught:
        adapter(offline).cancel_irn("a" * 64, "duplicate")
    assert caught.value.code == "GSP_UNREACHABLE"

    def no_token(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    with pytest.raises(GspError) as caught:
        adapter(no_token).generate_eway(EWAY)
    assert caught.value.code == "GSP_AUTH_FAILED"


def test_sandbox_reads_the_irn_answer_and_needs_a_base_url():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth":
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(
            200,
            json={
                "irn": "a" * 64,
                "ack_no": "112",
                "signed_qr": "QR",
                "ack_date": "2026-10-09T10:00:00",
            },
        )

    out = adapter(handler).generate_irn(IRN)
    assert (out.irn, out.ack_no, out.signed_qr) == ("a" * 64, "112", "QR")
    assert out.ack_date.tzinfo is not None
    with pytest.raises(GspError, match="base URL"):
        SandboxGsp(gsp.env_config(Settings(gsp_provider=GspProvider.SANDBOX)))


def test_fake_gsp_is_repeatable_and_can_be_told_to_fail():
    fake = FakeGsp()
    first = fake.generate_eway(EWAY)
    second = fake.generate_eway(EWAY)
    assert len(first.number) == 12 and first.number != second.number
    assert fake.generate_irn(IRN).irn == fake.generate_irn(IRN).irn
    fake.failures.append(GspError("down", code="GSP_DOWN", retryable=True))
    with pytest.raises(GspError):
        fake.cancel_eway(first.number, "x")
    assert fake.cancel_eway(first.number, "x")["cancelled"] is True
    assert (
        fake.update_vehicle(first.number, "TN09AB1234", "breakdown", "Hosur")["vehicle"]
        == "TN09AB1234"
    )
    assert fake.cancel_irn("a" * 64, "dup")["cancelled"] is True


def test_the_pretend_gsp_is_never_used_in_production():
    prod = Settings(
        app_env="production",
        jwt_secret="x" * 40,
        cookie_secure=True,
        gsp_provider=GspProvider.FAKE,
    )
    gsp.reset_client()
    try:
        with patch("app.services.gsp.get_settings", return_value=prod):
            with pytest.raises(GspError) as caught:
                gsp.get_client()
            assert caught.value.code == "GSP_NOT_CONFIGURED"
    finally:
        gsp.reset_client()


# ------------------------------------------------------------------ Milestone 27


GSTIN = "33AAPFU0939F1Z2"


def test_the_fake_looks_up_the_same_sample_for_the_same_gstin():
    fake = FakeGsp(source="database")
    first = fake.lookup_gstin(GSTIN)
    assert first == fake.lookup_gstin(GSTIN)
    assert first.gstin == GSTIN and first.state_code == "33" and first.status == "Active"
    assert first.legal_name.endswith("Private Limited") and "Tamil Nadu" in first.address
    assert fake.lookup_gstin("99AAPFU0939F1Z2").address.endswith("India")  # unknown state
    fake.check_connection()
    assert fake.generate_eway(EWAY).raw["source"] == "database"
    fake.failures.append(GspError("down", code="GSP_DOWN"))
    with pytest.raises(GspError):
        fake.lookup_gstin(GSTIN)


def test_the_config_never_prints_its_secrets():
    config = gsp.env_config(settings())
    assert config.source == "environment" and config.provider == "sandbox"
    assert "secret" not in repr(config) and "pass" not in repr(config)
    assert set(config.secrets()) == {"id", "secret", "user", "pass"}


def key_adapter(handler):
    config = gsp.GspConfig(
        provider="live", source="database", base_url="https://lookup.test/v1", api_key="k" * 12
    )
    return SandboxGsp(config, transport=httpx.MockTransport(handler))


def test_a_lookup_service_is_signed_in_by_key_without_a_login():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("x-api-key")))
        if request.url.path == "/v1/ping":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(
            200,
            json={
                "gstin": GSTIN.lower(),
                "legal_name": "Kaveri Cement Agencies LLP",
                "trade_name": "Kaveri Cement",
                "address": "Salem",
                "state_code": "33",
                "status": "Active",
            },
        )

    client = key_adapter(handler)
    client.check_connection()
    found = client.lookup_gstin(GSTIN)
    assert found.gstin == GSTIN and found.legal_name == "Kaveri Cement Agencies LLP"
    assert seen == [
        ("GET", "/v1/ping", "k" * 12),
        ("GET", f"/v1/taxpayer/{GSTIN}", "k" * 12),
    ]


def test_a_refused_key_and_an_empty_answer():
    with pytest.raises(GspError) as caught:
        key_adapter(lambda r: httpx.Response(401, json={})).check_connection()
    assert caught.value.code == "GSP_AUTH_FAILED"
    with pytest.raises(GspError) as caught:
        key_adapter(lambda r: httpx.Response(200, json=["not", "an", "object"])).lookup_gstin(GSTIN)
    assert caught.value.code == "GSP_BAD_RESPONSE"
    sparse = key_adapter(lambda r: httpx.Response(200, json={"legal_name": "X Traders"}))
    found = sparse.lookup_gstin(GSTIN)
    assert (found.trade_name, found.state_code, found.status) == ("", "33", "Unknown")


def test_a_gsp_account_test_is_a_login():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"access_token": "tok"})

    adapter(handler).check_connection()
    assert paths == ["/api/auth"]
