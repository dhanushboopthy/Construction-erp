"""Online renewal through Razorpay: amounts in paise, what may be sold online, the two signatures
and reading a webhook event (Milestone 30).

The signatures are checked against values worked out by hand with Python's `hmac` module, so a
change to the message format would fail here.
"""

import hashlib
import hmac
import json
from decimal import Decimal

import pytest

from app.domain.online_renewal import (
    CAPTURED_EVENT,
    CapturedPayment,
    captured_payment,
    check_payable,
    checkout_signature,
    checkout_signature_ok,
    is_offered,
    matches_order,
    to_paise,
    webhook_signature,
    webhook_signature_ok,
)
from app.domain.subscriptions import SubscriptionRuleError

SECRET = "test-key-secret"  # a made-up test value


# ---------------------------------------------------------------- rupees to paise


@pytest.mark.parametrize(
    ("rupees", "paise"),
    [
        (Decimal("1.00"), 100),
        (Decimal("999.90"), 99990),
        (Decimal("11800"), 1180000),
        (Decimal("9999999999.99"), 999999999999),
    ],
)
def test_an_amount_in_rupees_becomes_whole_paise(rupees, paise):
    assert to_paise(rupees) == paise


@pytest.mark.parametrize(
    "bad",
    [
        Decimal("0.99"),  # Razorpay's smallest order is one rupee
        Decimal("0"),
        Decimal("-5.00"),
        Decimal("10.005"),  # part of a paisa
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("10000000000.00"),  # more than NUMERIC(12,2) holds
        10,  # not a Decimal
    ],
)
def test_an_amount_that_cannot_be_charged_is_refused(bad):
    with pytest.raises(SubscriptionRuleError) as caught:
        to_paise(bad)
    assert caught.value.code == "ORDER_AMOUNT"


# ---------------------------------------------------------------- what is offered online


def test_an_active_price_of_an_active_paid_plan_is_offered():
    terms = {"plan_active": True, "price_active": True, "trial_plan": False}
    assert is_offered(price=Decimal("999.00"), **terms)
    check_payable(price=Decimal("999.00"), **terms)  # does not raise


@pytest.mark.parametrize(
    "terms",
    [
        {"plan_active": False, "price_active": True, "trial_plan": False, "price": "999"},
        {"plan_active": True, "price_active": False, "trial_plan": False, "price": "999"},
        {"plan_active": True, "price_active": True, "trial_plan": True, "price": "999"},
        {"plan_active": True, "price_active": True, "trial_plan": False, "price": "0"},
        {"plan_active": True, "price_active": True, "trial_plan": False, "price": "0.50"},
    ],
)
def test_archived_trial_and_free_prices_are_not_sold_online(terms):
    price = Decimal(terms.pop("price"))
    assert not is_offered(price=price, **terms)
    with pytest.raises(SubscriptionRuleError) as caught:
        check_payable(price=price, **terms)
    assert caught.value.code == "PRICE_NOT_OFFERED"


# ---------------------------------------------------------------- the Checkout signature


def test_the_checkout_signature_is_hmac_sha256_of_order_bar_payment():
    expected = hmac.new(SECRET.encode(), b"order_ABC123|pay_XYZ789", hashlib.sha256).hexdigest()
    assert checkout_signature("order_ABC123", "pay_XYZ789", SECRET) == expected
    assert checkout_signature_ok("order_ABC123", "pay_XYZ789", expected, SECRET)


GENUINE = checkout_signature("order_ABC123", "pay_XYZ789", SECRET)


@pytest.mark.parametrize(
    ("order_id", "payment_id", "signature", "secret"),
    [
        ("order_ABC123", "pay_OTHER", GENUINE, SECRET),  # signed for another payment
        ("order_OTHER", "pay_XYZ789", GENUINE, SECRET),  # signed for another order
        ("order_ABC123", "pay_XYZ789", GENUINE, "another-secret"),  # checked with another key
        ("order_ABC123", "pay_XYZ789", "0" * 64, SECRET),  # made up
        ("order_ABC123", "pay_XYZ789", "", SECRET),  # missing
        ("order_ABC123", "pay_XYZ789", None, SECRET),  # missing
        ("order_ABC123", "pay_XYZ789", "zzénot-hex", SECRET),  # not even ASCII
    ],
)
def test_a_forged_checkout_signature_fails(order_id, payment_id, signature, secret):
    assert not checkout_signature_ok(order_id, payment_id, signature, secret)


def test_an_empty_secret_never_verifies_even_its_own_signature():
    made_with_nothing = checkout_signature("order_A", "pay_B", "")
    assert not checkout_signature_ok("order_A", "pay_B", made_with_nothing, "")


# ---------------------------------------------------------------- the webhook signature


def test_the_webhook_signature_is_hmac_sha256_of_the_raw_body():
    body = b'{"event":"payment.captured"}'
    expected = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    assert webhook_signature(body, "hook-secret") == expected
    assert webhook_signature_ok(body, expected, "hook-secret")


def test_a_changed_body_or_a_wrong_secret_fails_the_webhook_signature():
    body = b'{"event":"payment.captured"}'
    signature = webhook_signature(body, "hook-secret")
    assert not webhook_signature_ok(body + b" ", signature, "hook-secret")
    assert not webhook_signature_ok(body, signature, "other-secret")
    assert not webhook_signature_ok(body, "", "hook-secret")
    assert not webhook_signature_ok(body, None, "hook-secret")
    assert not webhook_signature_ok(body, webhook_signature(body, ""), "")
    assert not webhook_signature_ok(body, "é", "hook-secret")


# ---------------------------------------------------------------- reading a webhook event


def event(**entity_changes: object) -> dict[str, object]:
    entity: dict[str, object] = {
        "id": "pay_XYZ789",
        "order_id": "order_ABC123",
        "amount": 99990,
        "currency": "INR",
        "status": "captured",
    } | entity_changes
    return {"event": CAPTURED_EVENT, "payload": {"payment": {"entity": entity}}}


def test_a_captured_payment_is_read_from_its_event():
    assert captured_payment(event()) == CapturedPayment(
        payment_id="pay_XYZ789", order_id="order_ABC123", amount_paise=99990, currency="INR"
    )
    assert captured_payment(json.loads(json.dumps(event()))) is not None


@pytest.mark.parametrize(
    "other",
    [
        {"event": "payment.failed", "payload": event()["payload"]},
        {"event": "order.paid"},
        {"payload": {}},
        [],
        "payment.captured",
        None,
        {"event": CAPTURED_EVENT},
        {"event": CAPTURED_EVENT, "payload": []},
        {"event": CAPTURED_EVENT, "payload": {"payment": "x"}},
        {"event": CAPTURED_EVENT, "payload": {"payment": {"entity": None}}},
        event(id=None),
        event(id=""),
        event(order_id=None),  # a payment made outside an order (a payment link)
        event(amount="99990"),
        event(amount=True),
        event(amount=-1),
        event(currency=5),
    ],
)
def test_any_other_or_malformed_event_is_not_a_captured_payment(other):
    assert captured_payment(other) is None


def test_a_payment_matches_its_order_only_for_the_same_amount_and_currency():
    paid = CapturedPayment("pay_X", "order_Y", 99990, "INR")
    assert matches_order(paid, amount_paise=99990, currency="INR")
    assert not matches_order(paid, amount_paise=100, currency="INR")
    assert not matches_order(paid, amount_paise=99990, currency="USD")
