"""Go-live safety net: no route answers without a sign-in, and responses are never cached."""

import re

import pytest

from app.main import app
from tests.conftest import login

pytestmark = pytest.mark.integration

PUBLIC = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/ready"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
}


def routes():
    """Every method and path the API declares, read from its own OpenAPI description."""
    for path, methods in app.openapi()["paths"].items():
        for method in sorted(methods):
            verb = method.upper()
            if verb in {"GET", "POST", "PUT", "PATCH", "DELETE"} and (verb, path) not in PUBLIC:
                yield verb, path


def test_there_are_many_routes_to_check():
    assert len(list(routes())) > 100


@pytest.mark.parametrize(("method", "path"), list(routes()))
def test_every_route_needs_a_sign_in(client, method, path):
    url = re.sub(r"\{[^}]+\}", "1", path)
    response = client.request(method, url, json={} if method != "GET" else None)
    assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
    assert response.json()["code"] == "NOT_AUTHENTICATED"


def test_api_answers_are_never_cached_and_carry_security_headers(client):
    headers = login(client, "owner", "owner-pass-123")
    for response in (
        client.get("/api/v1/settings", headers=headers),
        client.get("/api/v1/health"),
        client.get("/api/v1/settings"),
    ):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "same-origin"
    assert "x-request-id" in client.get("/api/v1/health").headers
