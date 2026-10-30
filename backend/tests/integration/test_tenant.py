"""GET /tenant: the name and tagline the app shell shows."""

import pytest
from sqlalchemy import select

from app.models.setup import ShopSettings
from app.services.shop_settings import DEFAULT_TAGLINE
from tests.conftest import login

pytestmark = pytest.mark.integration

COUNTER = ("counter1", "counter-pass-123")
OWNER = ("owner", "owner-pass-123")


def test_every_role_gets_only_the_name_and_the_tagline(client):
    for who in (OWNER, COUNTER):
        body = client.get("/api/v1/tenant", headers=login(client, *who)).json()
        assert set(body) == {"name", "tagline"}
        assert body["tagline"] == DEFAULT_TAGLINE


def test_trade_name_wins_over_the_legal_name(client, db):
    row = db.execute(select(ShopSettings)).scalar_one()
    row.legal_name = "Demo Construction Materials Pvt Ltd"
    row.trade_name = None
    db.flush()
    headers = login(client, *COUNTER)
    assert client.get("/api/v1/tenant", headers=headers).json()["name"] == (
        "Demo Construction Materials Pvt Ltd"
    )

    row.trade_name = "Demo Steels"
    db.flush()
    assert client.get("/api/v1/tenant", headers=headers).json()["name"] == "Demo Steels"
