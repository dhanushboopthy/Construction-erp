"""FM3: an owner-typed price is labelled, needs a reason and shows up in the leakage report.

Hand-worked numbers: TMT lists at ₹62 a kg (₹62,000 a ton). The owner bills 1,000 kg at ₹60:
  rupees given away = (62 - 60) x 1,000 = ₹2,000; taxable 60,000; GST 18% = 10,800.
A counter user, with the owner's PIN, bills 500 kg at ₹61: (62 - 61) x 500 = ₹500.
Realisation = (60,000 + 30,500) ÷ (62,000 + 31,000) = 97.31 %.
"""

import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.clock import today_ist
from tests.conftest import login
from tests.integration.test_credit import PIN, set_pin
from tests.integration.test_sales import (  # noqa: F401 - the world fixture is shared
    COUNTER,
    body,
    day,
    line,
    post,
    world,
)

PERIOD = today_ist().strftime("%Y-%m")


@pytest.fixture
def listed(client, world):
    """TMT lists at ₹62 a kg from today."""
    client.put(
        "/api/v1/rates/market",
        headers=world["owner"],
        json={
            "effective_date": day(0),
            "rates": [{"item_id": world["tmt"]["id"], "rate": "62000", "unit": "ton"}],
        },
    )
    return world


def override_bill(world, rate="60000", reason="matching a competitor", qty="1", **extra):
    return body(
        world,
        [line(world, "tmt", qty, "ton", rate_override=rate, rate_override_reason=reason)],
        **extra,
    )


def test_an_override_is_labelled_with_its_reason_and_the_list_rate(client, listed, seeded):
    saved = post(client, listed, override_bill(listed))
    assert saved.status_code == 201, saved.text
    out = saved.json()["lines"][0]
    assert out["rate_source"] == "override"
    assert out["rate_override_reason"] == "matching a competitor"
    assert (out["rate"], saved.json()["taxable_value"], saved.json()["grand_total"]) == (
        "60.000000",
        "60000.00",
        "70800.00",
    )
    row = seeded.execute(
        text("select rate_source, list_rate, rate_override_reason from sales_line")
    ).one()
    assert (row[0], row[1], row[2]) == ("override", 62, "matching a competitor")


def test_an_override_without_a_reason_is_refused(client, listed):
    for reason in (None, "", "   "):
        payload = override_bill(listed, reason=reason)
        denied = post(client, listed, payload)
        assert denied.status_code == 409, denied.text
        assert denied.json()["code"] == "OVERRIDE_REASON"
        assert denied.json()["field"] == "rate_override_reason"
    preview = client.post(
        "/api/v1/invoices/preview", headers=listed["owner"], json=override_bill(listed, reason=None)
    )
    assert preview.json()["can_save"] is False


def test_the_database_refuses_an_override_without_a_reason(client, listed, seeded):
    assert post(client, listed, override_bill(listed)).status_code == 201
    with pytest.raises(DBAPIError), seeded.begin_nested():
        seeded.execute(text("update sales_line set rate_override_reason = null"))


def test_normal_lines_stay_market_or_customer_and_keep_the_list_rate(client, listed, seeded):
    ok = post(client, listed, body(listed, [line(listed, "tmt", "1", "ton")]))
    assert ok.json()["lines"][0]["rate_source"] == "market"
    assert ok.json()["lines"][0]["rate_override_reason"] is None
    row = seeded.execute(text("select list_rate, rate_override_reason from sales_line")).one()
    assert row[0] == 62 and row[1] is None


def test_the_bill_pdf_looks_the_same_as_any_other_bill(client, listed, monkeypatch):
    """The printed bill shows the rate, never how it was chosen. A bill whose price was typed
    and a bill whose price came from the rate board render the same HTML."""
    from app.services import invoice_pdf

    seen: list[str] = []

    class Capture:
        def __init__(self, string: str) -> None:
            seen.append(string)

        def write_pdf(self) -> bytes:
            return b"%PDF"

    monkeypatch.setattr(invoice_pdf, "HTML", Capture)
    typed = post(client, listed, override_bill(listed)).json()
    client.put(
        "/api/v1/rates/market",
        headers=listed["owner"],
        json={
            "effective_date": day(0),
            "rates": [{"item_id": listed["tmt"]["id"], "rate": "60000", "unit": "ton"}],
        },
    )
    plain = post(client, listed, body(listed, [line(listed, "tmt", "1", "ton")])).json()
    assert plain["lines"][0]["rate_source"] == "market"
    for invoice in (typed, plain):
        assert (
            client.get(f"/api/v1/invoices/{invoice['id']}/pdf", headers=listed["owner"]).status_code
            == 200
        )

    def clean(html: str, number: str) -> str:
        html = html.replace(number.replace("/", "-"), "N").replace(number, "N")
        html = re.sub(r"stock left: [\d,.]+ kg", "stock left", html, flags=re.I)
        html = re.sub(
            r'<div style="margin-top: 2mm"><strong>Pending balance[^<]*</strong>[^<]*</div>',
            "",
            html,
        )
        return re.sub(r"\s+", " ", html)

    assert clean(seen[0], typed["number"]) == clean(seen[1], plain["number"])
    assert "override" not in seen[0].lower() and "matching a competitor" not in seen[0]


def test_the_report_shows_overrides_by_user_with_their_rupee_effect(client, listed):
    set_pin(client, listed)
    counter = login(client, *COUNTER)
    owner_bill = post(client, listed, override_bill(listed))
    assert owner_bill.status_code == 201
    # A counter user needs the owner's PIN approval to use a price of their own.
    approval = client.post(
        "/api/v1/approvals",
        headers=counter,
        json={"pin": PIN, "action": "discount", "reason": "owner agreed on the phone"},
    ).json()["id"]
    staff_bill = post(
        client,
        listed,
        override_bill(
            listed, rate="61000", reason="owner agreed", qty="0.5", approval_ids=[approval]
        ),
        headers=counter,
    )
    assert staff_bill.status_code == 201, staff_bill.text

    report = client.get(f"/api/v1/reports/rate-overrides?period={PERIOD}", headers=listed["owner"])
    assert report.status_code == 200, report.text
    r = report.json()
    assert (r["lines"], r["unpriced"], r["cut"], r["raised"], r["net"]) == (
        2,
        0,
        "2500.00",
        "0.00",
        "2500.00",
    )
    assert (r["discounts"], r["leakage"], r["realisation_pct"]) == ("0.00", "2500.00", "97.31")
    by_name = {u["user_name"]: u for u in r["by_user"]}
    assert len(by_name) == 2
    cut_by = sorted((u["cut"] for u in r["by_user"]), key=float, reverse=True)
    assert cut_by == ["2000.00", "500.00"]
    top = r["rows"][0]
    assert (top["list_rate"], top["billed_rate"], top["effect"], top["reason"]) == (
        "62.000000",
        "60.000000",
        "2000.00",
        "matching a competitor",
    )
    # Only that month, and only that shop.
    other_shop = client.get(
        f"/api/v1/reports/rate-overrides?period={PERIOD}&location_id={listed['loc']['G1']}",
        headers=listed["owner"],
    ).json()
    assert other_shop["lines"] == 0 and other_shop["leakage"] == "0.00"
    assert other_shop["realisation_pct"] is None


def test_bill_discounts_count_towards_leakage(client, listed):
    ok = post(
        client,
        listed,
        body(listed, [line(listed, "tmt", "1", "ton", discount="500", discount_reason="bulk")]),
    )
    assert ok.status_code == 201
    r = client.get(
        f"/api/v1/reports/rate-overrides?period={PERIOD}", headers=listed["owner"]
    ).json()
    assert (r["lines"], r["cut"], r["discounts"], r["leakage"]) == (0, "0.00", "500.00", "500.00")
    assert r["by_user"][0]["discounts"] == "500.00"


def test_the_report_is_for_the_owner_only_and_checks_the_month(client, listed):
    url = f"/api/v1/reports/rate-overrides?period={PERIOD}"
    for creds in (COUNTER, ("accounts", "accounts-pass-123")):
        assert client.get(url, headers=login(client, *creds)).status_code == 403
    assert (
        client.get("/api/v1/reports/rate-overrides?period=nope", headers=listed["owner"]).json()[
            "code"
        ]
        == "BAD_PERIOD"
    )
    assert (
        client.get("/api/v1/reports/rate-overrides?period=2099-01", headers=listed["owner"]).json()[
            "code"
        ]
        == "FUTURE_PERIOD"
    )
    kpis = {
        k["code"]
        for k in client.get("/api/v1/kpis/definitions", headers=login(client, *COUNTER)).json()
    }
    assert "discount_leakage" not in kpis
