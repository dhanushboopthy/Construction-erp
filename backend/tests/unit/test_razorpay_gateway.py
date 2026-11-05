"""The Razorpay adapters (Milestone 30): which one configuration picks, the pretend one, and the
HTTP one against a mock transport (no network)."""

import base64
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core import config
from app.core.config import Environment, RazorpayProvider, Settings
from app.services import razorpay
from app.services.razorpay import FakeRazorpay, RazorpayError
from app.services.razorpay.http import HttpRazorpay

KEY_ID = "rzp_test_PUBLICKEY"
KEY_SECRET = "very-secret-key-value"  # a made-up test value


@pytest.fixture
def settings(monkeypatch):
    live = config.get_settings()
    monkeypatch.setattr(live, "razorpay_key_id", SecretStr(KEY_ID))
    monkeypatch.setattr(live, "razorpay_key_secret", SecretStr(KEY_SECRET))
    monkeypatch.setattr(live, "razorpay_provider", RazorpayProvider.FAKE)
    razorpay.reset_gateway()
    yield live
    razorpay.reset_gateway()


def test_online_renewal_is_off_until_both_keys_are_set():
    assert not Settings(razorpay_key_id=SecretStr(KEY_ID)).online_renewal_enabled
    assert not Settings(razorpay_key_secret=SecretStr(KEY_SECRET)).online_renewal_enabled
    assert Settings(
        razorpay_key_id=SecretStr(KEY_ID), razorpay_key_secret=SecretStr(KEY_SECRET)
    ).online_renewal_enabled


def test_no_keys_means_no_gateway(monkeypatch):
    live = config.get_settings()
    monkeypatch.setattr(live, "razorpay_key_id", SecretStr(""))
    razorpay.reset_gateway()
    with pytest.raises(RazorpayError) as caught:
        razorpay.get_gateway()
    assert caught.value.code == "ONLINE_RENEWAL_OFF"


def test_the_pretend_gateway_is_used_outside_production_and_refused_in_it(settings, monkeypatch):
    assert isinstance(razorpay.get_gateway(), FakeRazorpay)
    razorpay.reset_gateway()
    monkeypatch.setattr(settings, "app_env", Environment.PRODUCTION)
    with pytest.raises(RazorpayError) as caught:
        razorpay.get_gateway()
    assert caught.value.code == "ONLINE_RENEWAL_OFF"


def test_live_keys_pick_the_http_adapter(settings, monkeypatch):
    monkeypatch.setattr(settings, "razorpay_provider", RazorpayProvider.LIVE)
    assert isinstance(razorpay.get_gateway(), HttpRazorpay)


def test_the_pretend_gateway_makes_unique_orders_and_can_be_made_to_fail():
    fake = FakeRazorpay()
    one = fake.create_order(amount_paise=100, currency="INR", receipt="r1", notes={})
    two = fake.create_order(amount_paise=100, currency="INR", receipt="r1", notes={})
    assert one.id.startswith("order_") and one.id != two.id
    assert (one.amount_paise, one.currency) == (100, "INR")
    fake.failures.append(RazorpayError("down"))
    with pytest.raises(RazorpayError):
        fake.create_order(amount_paise=100, currency="INR", receipt="r2", notes={})
    assert len(fake.calls) == 3


def _adapter(handler) -> HttpRazorpay:
    keys = Settings(
        razorpay_key_id=SecretStr(KEY_ID),
        razorpay_key_secret=SecretStr(KEY_SECRET),
        razorpay_base_url="https://api.razorpay.test/v1/",
    )
    return HttpRazorpay(keys, transport=httpx.MockTransport(handler))


def test_the_http_adapter_posts_the_order_with_basic_auth():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "order_Q1", "amount": 99990, "currency": "INR"})

    made = _adapter(handler).create_order(
        amount_paise=99990, currency="INR", receipt="t1-abc", notes={"company": "acme"}
    )
    assert (made.id, made.amount_paise, made.currency) == ("order_Q1", 99990, "INR")
    request = seen[0]
    assert str(request.url) == "https://api.razorpay.test/v1/orders"
    expected = base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
    assert request.headers["authorization"] == f"Basic {expected}"
    assert json.loads(request.content) == {
        "amount": 99990,
        "currency": "INR",
        "receipt": "t1-abc",
        "notes": {"company": "acme"},
    }


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(401, json={"error": {"description": "Authentication failed"}}),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"id": "order_Q1"}),
        httpx.Response(200, json=["order_Q1"]),
    ],
)
def test_a_refusal_or_an_odd_answer_is_a_razorpay_error_without_the_keys(answer):
    with pytest.raises(RazorpayError) as caught:
        _adapter(lambda _: answer).create_order(
            amount_paise=100, currency="INR", receipt="r", notes={}
        )
    assert KEY_SECRET not in caught.value.message and KEY_ID not in caught.value.message


def test_an_unreachable_razorpay_is_a_razorpay_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(RazorpayError) as caught:
        _adapter(handler).create_order(amount_paise=100, currency="INR", receipt="r", notes={})
    assert "could not be reached" in caught.value.message
