"""Milestone 5: market rates, customer rates, margins and price resolution."""

from datetime import timedelta

import pytest

from app.core.clock import today_ist
from tests.conftest import login

pytestmark = pytest.mark.integration

OWNER = ("owner", "owner-pass-123")
COUNTER = ("counter1", "counter-pass-123")
ACCOUNTANT = ("accounts", "accounts-pass-123")


def day(offset: int = 0) -> str:
    return (today_ist() - timedelta(days=offset)).isoformat()


@pytest.fixture
def world(client):
    owner = login(client, *OWNER)
    loc = {x["code"]: x["id"] for x in client.get("/api/v1/locations", headers=owner).json()}
    tmt = client.post(
        "/api/v1/items",
        headers=owner,
        json={
            "name": "TMT 12 mm",
            "category": "tmt",
            "hsn": "72142090",
            "gst_rate": "18",
            "base_unit": "kg",
            "min_margin": "1",
            "units": [{"unit": "ton", "factor_to_base": "1000"}],
        },
    ).json()
    cement = client.post(
        "/api/v1/items",
        headers=owner,
        json={
            "name": "Cement PPC",
            "category": "cement",
            "hsn": "25232930",
            "gst_rate": "28",
            "base_unit": "bag",
            "base_whole_only": True,
        },
    ).json()
    ravi = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Ravi Builders", "type": "customer", "state_code": "33"},
    ).json()
    kumar = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Kumar Co", "type": "customer", "state_code": "33"},
    ).json()
    supplier = client.post(
        "/api/v1/parties",
        headers=owner,
        json={"name": "Steel Mills", "type": "supplier", "state_code": "33"},
    ).json()
    return {
        "owner": owner,
        "loc": loc,
        "tmt": tmt,
        "cement": cement,
        "ravi": ravi,
        "kumar": kumar,
        "supplier": supplier,
    }


def put_rates(client, world, rates, on=None, headers=None):
    return client.put(
        "/api/v1/rates/market",
        headers=headers or world["owner"],
        json={"effective_date": on or day(0), "rates": rates},
    )


def resolve(client, world, item, party=None, on=None, headers=None):
    params = {"item_id": world[item]["id"]}
    if party:
        params["party_id"] = world[party]["id"]
    if on:
        params["on"] = on
    return client.get("/api/v1/rates/resolve", headers=headers or world["owner"], params=params)


# ---------------------------------------------------------------- resolution (B3)


def test_price_resolves_customer_rate_then_latest_market_rate_then_blocks(client, world):
    owner = world["owner"]
    assert resolve(client, world, "tmt").json()["code"] == "PRICE_NOT_SET"

    # Market rates: 55,000 a ton eight days ago, 56,000 two days ago, 57,000 tomorrow (not yet).
    put_rates(
        client, world, [{"item_id": world["tmt"]["id"], "rate": "55000", "unit": "ton"}], day(8)
    )
    put_rates(
        client, world, [{"item_id": world["tmt"]["id"], "rate": "56000", "unit": "ton"}], day(2)
    )
    tomorrow = (today_ist() + timedelta(days=1)).isoformat()
    put_rates(
        client, world, [{"item_id": world["tmt"]["id"], "rate": "57000", "unit": "ton"}], tomorrow
    )

    today = resolve(client, world, "tmt").json()
    assert (today["rate"], today["source"], today["base_unit"]) == ("56.000000", "market", "kg")
    assert (
        resolve(client, world, "tmt", on=day(5)).json()["rate"] == "55.000000"
    )  # latest on or before
    assert (
        resolve(client, world, "tmt", on=day(20)).json()["code"] == "PRICE_NOT_SET"
    )  # before any rate

    # Ravi has an agreed rate of 54,500 a ton from 10 days ago to 3 days ago.
    agreed = client.post(
        "/api/v1/customer-rates",
        headers=owner,
        json={
            "party_id": world["ravi"]["id"],
            "item_id": world["tmt"]["id"],
            "rate": "54500",
            "unit": "ton",
            "valid_from": day(10),
            "valid_to": day(3),
        },
    )
    assert agreed.status_code == 201, agreed.text
    assert agreed.json()["rate"] == "54.500000"
    assert resolve(client, world, "tmt", "ravi", day(5)).json()["source"] == "customer"
    assert resolve(client, world, "tmt", "ravi", day(5)).json()["rate"] == "54.500000"
    # After the agreement ends, Ravi pays the market rate; Kumar never had one.
    after = resolve(client, world, "tmt", "ravi").json()
    assert (after["source"], after["rate"]) == ("market", "56.000000")
    assert resolve(client, world, "tmt", "kumar", day(5)).json()["source"] == "market"


def test_rates_are_stored_per_base_unit_without_gst(client, world, seeded):
    owner = world["owner"]
    # Cement 380 a bag; steel 55,432.55 a ton is 55.43255 a kg.
    saved = put_rates(
        client,
        world,
        [
            {"item_id": world["cement"]["id"], "rate": "380"},
            {"item_id": world["tmt"]["id"], "rate": "55432.55", "unit": "ton"},
        ],
    )
    assert saved.json()["saved"] == 2
    assert resolve(client, world, "tmt").json()["rate"] == "55.432550"
    assert resolve(client, world, "cement").json()["rate"] == "380.000000"

    # With "rates include GST" on, 55,000 a ton incl 18% is 46,610.169492 a ton: 46.610169 a kg.
    current = client.get("/api/v1/settings", headers=owner).json()
    body = {k: v for k, v in current.items() if k != "id"} | {"rates_include_gst": True}
    assert client.put("/api/v1/settings", headers=owner, json=body).status_code == 200
    put_rates(
        client, world, [{"item_id": world["tmt"]["id"], "rate": "55000", "unit": "ton"}], day(0)
    )
    assert resolve(client, world, "tmt").json()["rate"] == "46.610169"
    history = client.get(f"/api/v1/rates/market/{world['tmt']['id']}/history", headers=owner).json()
    # The same day is overwritten, not duplicated, and what was typed is kept for display.
    assert len(history) == 1 and history[0]["entered_rate"] == "55000.0000"


# ---------------------------------------------------------------- owner board, margin, warnings


def stock_in(client, world, cost_per_ton="55000"):
    return client.post(
        "/api/v1/purchases",
        headers=world["owner"],
        json={
            "supplier_id": world["supplier"]["id"],
            "location_id": world["loc"]["S1"],
            "bill_no": "B-1",
            "bill_date": day(1),
            "lines": [
                {
                    "item_id": world["tmt"]["id"],
                    "unit": "ton",
                    "quantity": "10",
                    "rate": cost_per_ton,
                    "charges": [],
                }
            ],
        },
    )


def test_the_owner_board_suggests_cost_plus_margin_and_warns_below_cost(client, world):
    owner = world["owner"]
    assert stock_in(client, world).status_code == 201  # cost 55.0000 per kg
    margins = client.put(
        "/api/v1/margins",
        headers=owner,
        json=[{"item_id": world["tmt"]["id"], "margin": "1250", "unit": "ton"}],
    ).json()
    row = next(m for m in margins if m["item_id"] == world["tmt"]["id"])
    assert row["margin_per_unit"] == "1.250000" and row["min_margin"] == "1.0000"

    board = {r["item_name"]: r for r in client.get("/api/v1/rates/market", headers=owner).json()}
    tmt = board["TMT 12 mm"]
    # Suggested: cost 55.0000 + margin 1.25 per kg = 56.25 per kg (Rs 56,250 a ton).
    assert (tmt["avg_cost"], tmt["suggested_rate"], tmt["rate"]) == ("55.0000", "56.25", None)
    assert board["Cement PPC"]["quote_unit"] == "bag"
    # The board also speaks in the unit steel is quoted in: per ton.
    assert (
        tmt["quote_unit"],
        tmt["avg_cost_quoted"],
        tmt["margin_quoted"],
        tmt["suggested_quoted"],
    ) == ("ton", "55000.0000", "1250.0000", "56250.0000")

    # 54,500 a ton sells below the 55,000 cost, 55,500 clears cost but not the 1.00 minimum margin,
    # and 56,250 is fine.
    for ton_rate, below_cost, below_min in [
        ("54500", True, True),
        ("55500", False, True),
        ("56250", False, False),
    ]:
        result = put_rates(
            client, world, [{"item_id": world["tmt"]["id"], "rate": ton_rate, "unit": "ton"}]
        ).json()
        flags = [(w["below_cost"], w["below_min_margin"]) for w in result["warnings"]]
        assert flags == ([(below_cost, below_min)] if below_cost or below_min else [])
    after = {r["item_name"]: r for r in client.get("/api/v1/rates/market", headers=owner).json()}[
        "TMT 12 mm"
    ]
    assert (after["margin_now"], after["below_cost"], after["below_min_margin"]) == (
        "1.2500",
        False,
        False,
    )
    assert after["previous_rate"] is None


def test_staff_see_selling_rates_but_never_cost_or_margin(client, world):
    stock_in(client, world)
    client.put(
        "/api/v1/margins",
        headers=world["owner"],
        json=[{"item_id": world["tmt"]["id"], "margin": "1250", "unit": "ton"}],
    )
    put_rates(client, world, [{"item_id": world["tmt"]["id"], "rate": "56250", "unit": "ton"}])
    for who in (COUNTER, ACCOUNTANT):
        headers = login(client, *who)
        response = client.get("/api/v1/rates/market", headers=headers)
        assert response.status_code == 200
        row = {r["item_name"]: r for r in response.json()}["TMT 12 mm"]
        assert row["rate"] == "56.250000"
        for hidden in (
            "avg_cost",
            "margin_per_unit",
            "suggested_rate",
            "margin_now",
            "below_cost",
            "below_min_margin",
        ):
            assert hidden not in row, hidden
        text = response.text
        assert "55.0000" not in text and "1.25" not in text
        assert resolve(client, world, "tmt", headers=headers).json()["rate"] == "56.250000"
        history = client.get(f"/api/v1/rates/market/{world['tmt']['id']}/history", headers=headers)
        assert history.status_code == 200
        assert (
            client.put(
                "/api/v1/rates/market",
                headers=headers,
                json={
                    "effective_date": day(0),
                    "rates": [{"item_id": world["tmt"]["id"], "rate": "1"}],
                },
            ).status_code
            == 403
        )
        assert client.get("/api/v1/margins", headers=headers).status_code == 403
        assert client.put("/api/v1/margins", headers=headers, json=[]).status_code == 403
        assert client.get("/api/v1/customer-rates", headers=headers).status_code == 403
        assert client.post("/api/v1/customer-rates", headers=headers, json={}).status_code == 403
        assert client.patch("/api/v1/customer-rates/1", headers=headers, json={}).status_code == 403
    for path in (
        "/api/v1/rates/market",
        "/api/v1/rates/resolve?item_id=1",
        "/api/v1/margins",
        "/api/v1/customer-rates",
    ):
        assert client.get(path).status_code == 401


# ---------------------------------------------------------------- customer rate rules


def test_customer_rate_rules(client, world):
    owner = world["owner"]
    base = {
        "party_id": world["ravi"]["id"],
        "item_id": world["tmt"]["id"],
        "rate": "54500",
        "unit": "ton",
        "valid_from": day(10),
    }
    first = client.post("/api/v1/customer-rates", headers=owner, json=base)
    assert first.status_code == 201
    # An open-ended agreement blocks a second one that overlaps it.
    overlap = client.post(
        "/api/v1/customer-rates", headers=owner, json=base | {"valid_from": day(2)}
    )
    assert overlap.status_code == 409 and overlap.json()["code"] == "RATE_PERIOD_OVERLAP"
    # End the first agreement 5 days ago: then a new one from 4 days ago is fine.
    ended = client.patch(
        f"/api/v1/customer-rates/{first.json()['id']}", headers=owner, json={"valid_to": day(5)}
    )
    assert ended.json()["valid_to"] == day(5)
    second = client.post(
        "/api/v1/customer-rates", headers=owner, json=base | {"valid_from": day(4), "rate": "55000"}
    )
    assert second.status_code == 201
    listed = client.get(
        f"/api/v1/customer-rates?party_id={world['ravi']['id']}", headers=owner
    ).json()
    assert [r["entered_rate"] for r in listed] == ["55000.0000", "54500.0000"]
    assert (
        client.get(f"/api/v1/customer-rates?item_id={world['cement']['id']}", headers=owner).json()
        == []
    )

    bad_dates = client.patch(
        f"/api/v1/customer-rates/{first.json()['id']}", headers=owner, json={"valid_to": day(30)}
    )
    assert bad_dates.status_code == 409 and bad_dates.json()["code"] == "BAD_PERIOD"
    off = client.patch(
        f"/api/v1/customer-rates/{second.json()['id']}", headers=owner, json={"is_active": False}
    )
    assert off.json()["is_active"] is False
    assert client.patch("/api/v1/customer-rates/99999", headers=owner, json={}).status_code == 404

    errors = [
        (base | {"party_id": world["supplier"]["id"]}, 409),
        (base | {"party_id": 99999}, 404),
        (base | {"item_id": 99999}, 404),
        (base | {"unit": "bag"}, 409),
        (base | {"valid_to": day(20)}, 422),
        (base | {"rate": "-1"}, 422),
    ]
    for body, status in errors:
        assert (
            client.post("/api/v1/customer-rates", headers=owner, json=body).status_code == status
        ), body


def test_market_rate_input_rules(client, world):
    tmt = world["tmt"]["id"]
    for body, status in [
        ({"effective_date": day(0), "rates": []}, 422),
        ({"effective_date": day(0), "rates": [{"item_id": 99999, "rate": "1"}]}, 404),
        ({"effective_date": day(0), "rates": [{"item_id": tmt, "rate": "1", "unit": "bag"}]}, 409),
        ({"effective_date": day(0), "rates": [{"item_id": tmt, "rate": "-5"}]}, 422),
        (
            {
                "effective_date": day(0),
                "rates": [{"item_id": tmt, "rate": "1"}, {"item_id": tmt, "rate": "2"}],
            },
            409,
        ),
    ]:
        response = client.put("/api/v1/rates/market", headers=world["owner"], json=body)
        assert response.status_code == status, (body, response.text)
    assert (
        client.get("/api/v1/rates/market/99999/history", headers=world["owner"]).status_code == 404
    )
    assert (
        client.get("/api/v1/rates/resolve?item_id=99999", headers=world["owner"]).status_code == 404
    )
    assert (
        client.put(
            "/api/v1/margins", headers=world["owner"], json=[{"item_id": 99999, "margin": "1"}]
        ).status_code
        == 404
    )
