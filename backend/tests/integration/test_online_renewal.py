"""M30: a company owner renews Duolink online with Razorpay.

There is no network here: the pretend gateway (`services/razorpay/fake.py`) makes the orders,
and the tests sign Checkout answers and webhook bodies with the configured secrets, exactly as
Razorpay does. A company's calls run at acme.localhost as the app's database role; the webhook
runs at no company's address, as Razorpay would call it.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import config
from app.core.config import RazorpayProvider
from app.core.tenancy import set_platform
from app.domain.online_renewal import checkout_signature, webhook_signature
from app.services import razorpay
from app.services.razorpay import FakeRazorpay, RazorpayError
from tests.conftest import as_db_owner, login
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    helper,
    onboard,
    owner_of,
)
from tests.integration.test_subscriptions import lapse, plan_by_code, subscription_of

pytestmark = pytest.mark.integration

ACME = {"host": "acme.localhost"}
PAGE = "/api/v1/subscription"
WEBHOOK = "/api/v1/subscription/webhook"
PAYMENTS = "/api/v1/admin/billing/payments"
PARTY = {"name": "Big Contractor", "type": "customer", "state_code": "33"}

# Made-up values, distinctive so a leak would be found by the test that looks for them.
KEY_ID = "rzp_test_PublicKeyId01"
KEY_SECRET = "KEYSECRET-must-never-leak-7f3a"
HOOK_SECRET = "HOOKSECRET-must-never-leak-91c2"


@pytest.fixture
def online(monkeypatch):
    """Online renewal configured, on the pretend gateway."""
    live = config.get_settings()
    monkeypatch.setattr(live, "razorpay_provider", RazorpayProvider.FAKE)
    monkeypatch.setattr(live, "razorpay_key_id", SecretStr(KEY_ID))
    monkeypatch.setattr(live, "razorpay_key_secret", SecretStr(KEY_SECRET))
    monkeypatch.setattr(live, "razorpay_webhook_secret", SecretStr(HOOK_SECRET))
    razorpay.reset_gateway()
    gateway = razorpay.get_gateway()
    assert isinstance(gateway, FakeRazorpay)
    yield gateway
    razorpay.reset_gateway()


@pytest.fixture
def business(client, boss):
    """A paid plan on sale: a month and a year."""
    made = client.post(
        "/api/v1/admin/billing/plans",
        headers=boss,
        json={
            "code": "BUSINESS",
            "name": "Business",
            "short_description": "Two shops and a godown",
            "max_users": 15,
            "max_locations": 3,
            "features": [],
            "prices": [
                {"duration_value": 1, "duration_unit": "month", "price": "1180.00"},
                {"duration_value": 1, "duration_unit": "year", "price": "11800.00"},
            ],
        },
    )
    assert made.status_code == 201, made.text
    plan = made.json()
    return {p["duration_unit"]: p for p in plan["prices"]} | {"plan": plan}


def order(client, owner, price_id, **extra):
    made = client.post(f"{PAGE}/orders", headers=owner, json={"price_id": price_id} | extra)
    assert made.status_code == 201, made.text
    return made.json()


def checkout_answer(order_id, payment_id="pay_Test0000000001", signature=None):
    return {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature or checkout_signature(order_id, payment_id, KEY_SECRET),
    }


def captured(order_id, amount_paise, payment_id="pay_Test0000000001", currency="INR"):
    return {
        "entity": "event",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "order_id": order_id,
                    "amount": amount_paise,
                    "currency": currency,
                    "status": "captured",
                }
            }
        },
    }


def send_webhook(client, event, secret=HOOK_SECRET, signature=None):
    body = json.dumps(event).encode()
    return client.post(
        WEBHOOK,
        content=body,
        headers={
            "content-type": "application/json",
            "x-razorpay-signature": signature or webhook_signature(body, secret),
        },
    )


def online_payments(seeded):
    set_platform(seeded)
    return seeded.execute(
        text(
            "SELECT reference, amount, recorded_by_admin_id FROM subscription_payment "
            "WHERE method = 'razorpay' ORDER BY id"
        )
    ).all()


def parse(stamp):
    return datetime.fromisoformat(stamp)


# ------------------------------------------------------------------ off unless configured


def test_without_keys_the_owner_is_told_to_contact_duolink(client, acme, business):
    owner = owner_of(client)
    page = client.get(PAGE, headers=owner)
    assert page.status_code == 200, page.text
    assert page.json()["online_renewal"] is False and page.json()["options"] == []
    assert page.json()["plan_code"] == "TRIAL" and page.json()["status"] == "trial"
    refused = client.post(
        f"{PAGE}/orders", headers=owner, json={"price_id": business["year"]["id"]}
    )
    assert refused.status_code == 409 and refused.json()["code"] == "ONLINE_RENEWAL_OFF"
    refused = client.post(f"{PAGE}/verify", headers=owner, json=checkout_answer("order_X"))
    assert refused.status_code == 409 and refused.json()["code"] == "ONLINE_RENEWAL_OFF"
    assert client.get("/api/v1/tenant", headers=ACME).json()["online_renewal"] is False


def test_without_a_webhook_secret_the_webhook_does_not_exist(client, online, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "razorpay_webhook_secret", SecretStr(""))
    assert send_webhook(client, captured("order_X", 100), secret="").status_code == 404


# ------------------------------------------------------------------ the page and the order


def test_the_page_offers_every_active_paid_price_with_the_date_it_buys(
    client, boss, acme, online, business
):
    owner = owner_of(client)
    page = client.get(PAGE, headers=owner).json()
    assert page["online_renewal"] is True
    assert client.get("/api/v1/tenant", headers=ACME).json()["online_renewal"] is True
    codes = {(o["plan_code"], o["duration_unit"], o["price"]) for o in page["options"]}
    # The seeded plans are free (0.00), and a trial is never sold: only Business is on sale.
    assert codes == {("BUSINESS", "month", "1180.00"), ("BUSINESS", "year", "11800.00")}
    year = next(o for o in page["options"] if o["duration_unit"] == "year")
    # Paying during a trial starts the paid period now.
    expected = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    assert abs(parse(year["would_run_until"]) - expected) < timedelta(minutes=1)
    assert year["is_current_plan"] is False

    archived = client.post(
        f"/api/v1/admin/billing/plans/{business['plan']['id']}/archive",
        headers=boss,
        json={"reason": "No longer sold"},
    )
    assert archived.status_code == 200, archived.text
    assert client.get(PAGE, headers=owner).json()["options"] == []
    refused = client.post(
        f"{PAGE}/orders", headers=owner, json={"price_id": business["year"]["id"]}
    )
    assert refused.status_code == 409 and refused.json()["code"] == "PRICE_NOT_OFFERED"


def test_a_free_or_unknown_price_cannot_be_ordered(client, boss, acme, online):
    owner = owner_of(client)
    free = plan_by_code(client, boss, "BASIC")["prices"][0]
    refused = client.post(f"{PAGE}/orders", headers=owner, json={"price_id": free["id"]})
    assert refused.status_code == 409 and refused.json()["code"] == "PRICE_NOT_OFFERED"
    missing = client.post(f"{PAGE}/orders", headers=owner, json={"price_id": 999999})
    assert missing.status_code == 404 and missing.json()["code"] == "PRICE_NOT_FOUND"


def test_the_amount_comes_from_the_plan_price_never_the_browser(
    client, acme, online, business, seeded
):
    owner = owner_of(client)
    made = order(client, owner, business["year"]["id"], amount="1.00", amount_paise=100)
    assert made["amount"] == "11800.00" and made["amount_paise"] == 1180000
    assert made["currency"] == "INR" and made["key_id"] == KEY_ID
    assert made["description"] == "Business, 1 year" and made["name"] == "Duolink"
    assert online.calls[-1][1]["amount"] == 1180000  # what Razorpay was asked for
    stored = seeded.execute(
        text("SELECT amount, status, duration_unit FROM subscription_order WHERE id = :id"),
        {"id": made["id"]},
    ).one()
    assert stored == (Decimal("11800.00"), "created", "year")


def test_only_the_owner_uses_plan_and_billing(client, acme, online, business):
    owner = owner_of(client)
    made = client.post(
        "/api/v1/users",
        headers=owner,
        json={
            "username": "asha",
            "full_name": "Asha",
            "role": "accountant",
            "password": "asha-pass-12345",
        },
    )
    assert made.status_code == 201, made.text
    accountant = login(client, "asha", "asha-pass-12345", host="acme.localhost")
    assert client.get(PAGE, headers=accountant).status_code == 403
    assert (
        client.post(
            f"{PAGE}/orders", headers=accountant, json={"price_id": business["year"]["id"]}
        ).status_code
        == 403
    )
    assert client.get(PAGE, headers=ACME).status_code == 401


def test_a_gateway_failure_answers_502_and_saves_no_order(client, acme, online, business, seeded):
    online.failures.append(RazorpayError("Razorpay could not be reached. Try again in a minute."))
    owner = owner_of(client)
    failed = client.post(f"{PAGE}/orders", headers=owner, json={"price_id": business["year"]["id"]})
    assert failed.status_code == 502 and failed.json()["code"] == "RAZORPAY_ERROR"
    assert seeded.execute(text("SELECT count(*) FROM subscription_order")).scalar_one() == 0


# ------------------------------------------------------------------ verifying and applying


def test_a_forged_signature_answers_400_and_records_nothing(
    client, boss, acme, online, business, seeded
):
    owner = owner_of(client)
    made = order(client, owner, business["year"]["id"])
    before = subscription_of(client, boss, acme)
    forged = checkout_answer(made["razorpay_order_id"], signature="0" * 64)
    refused = client.post(f"{PAGE}/verify", headers=owner, json=forged)
    assert refused.status_code == 400 and refused.json()["code"] == "SIGNATURE_INVALID"
    # Signed with the wrong key, or for another payment: refused too.
    for wrong in (
        checkout_signature(made["razorpay_order_id"], "pay_Test0000000001", "guessed-key"),
        checkout_signature(made["razorpay_order_id"], "pay_Other000000001", KEY_SECRET),
    ):
        answer = checkout_answer(made["razorpay_order_id"], signature=wrong)
        assert client.post(f"{PAGE}/verify", headers=owner, json=answer).status_code == 400
    assert online_payments(seeded) == []
    assert subscription_of(client, boss, acme) == before
    status = seeded.execute(text("SELECT status FROM subscription_order")).scalar_one()
    assert status == "created"


def test_a_forged_webhook_answers_400_and_records_nothing(client, acme, online, business, seeded):
    owner = owner_of(client)
    made = order(client, owner, business["year"]["id"])
    event = captured(made["razorpay_order_id"], made["amount_paise"])
    assert send_webhook(client, event, signature="0" * 64).status_code == 400
    assert send_webhook(client, event, secret=KEY_SECRET).status_code == 400  # the wrong secret
    no_header = client.post(WEBHOOK, content=json.dumps(event).encode())
    assert no_header.status_code == 400 and no_header.json()["code"] == "SIGNATURE_INVALID"
    assert online_payments(seeded) == []


@pytest.mark.parametrize("first", ["checkout", "webhook"])
def test_checkout_and_the_webhook_in_either_order_give_one_payment_and_one_renewal(
    client, boss, acme, online, business, seeded, first
):
    owner = owner_of(client)
    made = order(client, owner, business["year"]["id"])
    answer = checkout_answer(made["razorpay_order_id"])
    event = captured(made["razorpay_order_id"], made["amount_paise"])

    def by_checkout():
        done = client.post(f"{PAGE}/verify", headers=owner, json=answer)
        assert done.status_code == 200, done.text
        return done.json()["applied"]

    def by_webhook():
        done = send_webhook(client, event)
        assert done.status_code == 200, done.text
        return done.json()["status"] == "applied"

    steps = [by_checkout, by_webhook] if first == "checkout" else [by_webhook, by_checkout]
    assert [step() for step in steps] == [True, False]
    assert [step() for step in steps] == [False, False]  # and again: still nothing new

    assert online_payments(seeded) == [("pay_Test0000000001", Decimal("11800.00"), None)]
    sub = subscription_of(client, boss, acme)
    assert sub["status"] == "active" and sub["plan_code"] == "BUSINESS"
    assert sub["duration_unit"] == "year" and sub["price"] == "11800.00"
    expected = datetime.now(UTC).replace(year=datetime.now(UTC).year + 1)
    assert abs(parse(sub["expires_at"]) - expected) < timedelta(minutes=1)  # one year, not two
    row = seeded.execute(text("SELECT status, paid_via FROM subscription_order")).one()
    assert row == ("paid", first)
    audit = seeded.execute(
        text(
            "SELECT admin_id, tenant_id, details FROM platform_audit_log "
            "WHERE action = 'subscription_pay_online'"
        )
    ).all()
    assert len(audit) == 1 and audit[0][0] is None and audit[0][1] == acme["id"]
    assert audit[0][2]["razorpay_payment_id"] == "pay_Test0000000001"
    assert audit[0][2]["via"] == first


def test_renewing_online_early_adds_to_the_current_end(client, boss, acme, online, business):
    owner = owner_of(client)
    first = order(client, owner, business["month"]["id"])
    client.post(f"{PAGE}/verify", headers=owner, json=checkout_answer(first["razorpay_order_id"]))
    month_end = parse(subscription_of(client, boss, acme)["expires_at"])
    second = order(client, owner, business["month"]["id"])
    done = client.post(
        f"{PAGE}/verify",
        headers=owner,
        json=checkout_answer(second["razorpay_order_id"], payment_id="pay_Test0000000002"),
    )
    assert done.json()["applied"] is True
    after = subscription_of(client, boss, acme)
    assert parse(after["starts_at"]) == month_end
    assert parse(after["expires_at"]) > month_end + timedelta(days=27)


def test_a_read_only_company_can_open_the_page_pay_and_save_at_once(
    client, boss, acme, online, business
):
    owner = owner_of(client)
    lapse(client, boss, acme)
    blocked = client.post("/api/v1/parties", headers=owner, json=PARTY)
    assert blocked.status_code == 403 and blocked.json()["code"] == "SUBSCRIPTION_EXPIRED"

    page = client.get(PAGE, headers=owner).json()
    assert page["access_state"] == "read_only" and page["status"] == "expired"
    made = order(client, owner, business["month"]["id"])
    done = client.post(
        f"{PAGE}/verify", headers=owner, json=checkout_answer(made["razorpay_order_id"])
    )
    assert done.status_code == 200, done.text
    assert done.json()["access_state"] == "full" and done.json()["status"] == "active"
    assert client.post("/api/v1/parties", headers=owner, json=PARTY).status_code == 201


def test_a_read_only_company_is_writable_again_after_the_webhook_alone(
    client, boss, acme, online, business
):
    owner = owner_of(client)
    made = order(client, owner, business["month"]["id"])
    lapse(client, boss, acme)
    assert client.post("/api/v1/parties", headers=owner, json=PARTY).status_code == 403
    landed = send_webhook(client, captured(made["razorpay_order_id"], made["amount_paise"]))
    assert landed.json() == {"status": "applied"}
    assert client.post("/api/v1/parties", headers=owner, json=PARTY).status_code == 201


def test_another_companys_order_cannot_be_verified_here(client, boss, acme, online, business):
    order_id = order(client, owner_of(client), business["year"]["id"])["razorpay_order_id"]
    onboard(
        client,
        boss,
        slug="beta",
        name="Beta Traders",
        owner_username="bela",
        owner_email="b@b.example",
    )
    other = login(client, "bela", "ravi-pass-123", host="beta.localhost")
    found = client.post(f"{PAGE}/verify", headers=other, json=checkout_answer(order_id))
    assert found.status_code == 404 and found.json()["code"] == "ORDER_NOT_FOUND"


# ------------------------------------------------------------------ webhook edge cases


def test_other_events_and_unknown_orders_answer_200_and_change_nothing(
    client, acme, online, business, seeded
):
    made = order(client, owner_of(client), business["year"]["id"])
    other = {"event": "payment.failed", "payload": {}}
    assert send_webhook(client, other).json() == {"status": "ignored"}
    unknown = captured("order_NotOurs0000001", 100)
    assert send_webhook(client, unknown).json() == {"status": "ignored"}
    short = captured(made["razorpay_order_id"], 100)  # paid less than the order
    assert send_webhook(client, short).json() == {"status": "ignored"}
    dollars = captured(made["razorpay_order_id"], made["amount_paise"], currency="USD")
    assert send_webhook(client, dollars).json() == {"status": "ignored"}
    assert online_payments(seeded) == []


def test_a_signed_body_that_is_not_json_is_refused(client, online):
    body = b"not json"
    sent = client.post(
        WEBHOOK,
        content=body,
        headers={"x-razorpay-signature": webhook_signature(body, HOOK_SECRET)},
    )
    assert sent.status_code == 400 and sent.json()["code"] == "BAD_PAYLOAD"


def test_a_second_payment_on_a_paid_order_is_not_applied(client, acme, online, business, seeded):
    owner = owner_of(client)
    made = order(client, owner, business["year"]["id"])
    client.post(f"{PAGE}/verify", headers=owner, json=checkout_answer(made["razorpay_order_id"]))
    again = captured(
        made["razorpay_order_id"], made["amount_paise"], payment_id="pay_Second0000001"
    )
    assert send_webhook(client, again).json() == {"status": "duplicate"}
    assert [r[0] for r in online_payments(seeded)] == ["pay_Test0000000001"]


# ------------------------------------------------------------------ Duolink's side


def test_online_payments_show_in_admin_payments_and_can_be_reversed(
    client, boss, helper, acme, online, business
):
    owner = owner_of(client)
    made = order(client, owner, business["year"]["id"])
    client.post(f"{PAGE}/verify", headers=owner, json=checkout_answer(made["razorpay_order_id"]))

    page = client.get(PAYMENTS, headers=helper, params={"method": "razorpay"}).json()
    assert page["total"] == 1
    paid = page["items"][0]
    assert (paid["method"], paid["amount"], paid["reference"]) == (
        "razorpay",
        "11800.00",
        "pay_Test0000000001",
    )
    assert paid["recorded_by"] == "Online (Razorpay)" and paid["plan_code"] == "BUSINESS"
    assert paid["period_ends_at"] is not None

    reversed_ = client.post(
        f"{PAYMENTS}/{paid['id']}/reverse", headers=boss, json={"reason": "Refunded"}
    )
    assert reversed_.status_code == 201, reversed_.text
    assert reversed_.json()["amount"] == "-11800.00" and reversed_.json()["recorded_by"]
    totals = client.get(PAYMENTS, headers=boss).json()["totals"]
    assert totals["net"] == "0.00"


def test_a_razorpay_payment_recorded_by_hand_first_is_not_recorded_again(
    client, boss, acme, online, business, seeded
):
    owner = owner_of(client)
    made = order(client, owner, business["year"]["id"])
    sub = subscription_of(client, boss, acme)
    by_hand = {
        "plan_id": business["plan"]["id"],
        "price_id": business["year"]["id"],
        "amount": "11800.00",
        "method": "razorpay",
        "reference": "pay_Test0000000001",
    }
    renew = f"/api/v1/admin/billing/subscriptions/{sub['id']}/renew"
    assert client.post(renew, headers=boss, json=by_hand).status_code == 200
    taken = client.post(renew, headers=boss, json=by_hand)
    assert taken.status_code == 409 and taken.json()["code"] == "PAYMENT_REFERENCE_TAKEN"

    done = client.post(
        f"{PAGE}/verify", headers=owner, json=checkout_answer(made["razorpay_order_id"])
    )
    assert done.status_code == 200 and done.json()["applied"] is False
    assert len(online_payments(seeded)) == 1


def test_only_an_online_payment_may_be_recorded_without_an_admin(seeded, client, boss, acme):
    sub = subscription_of(client, boss, acme)
    with as_db_owner(seeded), pytest.raises(IntegrityError), seeded.begin_nested():
        seeded.execute(
            text(
                "INSERT INTO subscription_payment (tenant_id, subscription_id, plan_id, "
                "amount, method, paid_at) VALUES (:t, :s, :p, 10, 'upi', now())"
            ),
            {"t": acme["id"], "s": sub["id"], "p": sub["plan_id"]},
        )


# ------------------------------------------------------------------ no secret leaks


def test_no_secret_appears_in_any_response_or_log_line(
    client, boss, acme, online, business, seeded, caplog
):
    caplog.set_level(logging.DEBUG)
    owner = owner_of(client)
    answers = [client.get(PAGE, headers=owner), client.get("/api/v1/tenant", headers=ACME)]
    made = client.post(f"{PAGE}/orders", headers=owner, json={"price_id": business["year"]["id"]})
    answers.append(made)
    order_id = made.json()["razorpay_order_id"]
    answers.append(
        client.post(
            f"{PAGE}/verify", headers=owner, json=checkout_answer(order_id, signature="f" * 64)
        )
    )
    answers.append(client.post(f"{PAGE}/verify", headers=owner, json=checkout_answer(order_id)))
    event = captured(order_id, made.json()["amount_paise"])
    answers.append(send_webhook(client, event, signature="0" * 64))
    answers.append(send_webhook(client, event))
    answers.append(client.get(PAYMENTS, headers=boss))
    answers.append(client.get("/api/v1/admin/billing/subscriptions", headers=boss))
    assert [a.status_code for a in answers] == [200, 200, 201, 400, 200, 400, 200, 200, 200]

    logged = caplog.text + "\n".join(str(r.__dict__) for r in caplog.records)
    stored = (
        seeded.execute(
            text(
                "SELECT coalesce(string_agg(details::text, ' '), '') FROM platform_audit_log "
                "UNION ALL SELECT coalesce(string_agg(changes::text, ' '), '') FROM audit_log"
            )
        )
        .scalars()
        .all()
    )
    for secret in (KEY_SECRET, HOOK_SECRET):
        for answer in answers:
            assert secret not in answer.text
            assert all(secret not in v for v in answer.headers.values())
        assert secret not in logged
        assert all(secret not in s for s in stored)
    assert repr(config.get_settings()).count(KEY_SECRET) == 0
