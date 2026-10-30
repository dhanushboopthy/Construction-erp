"""GET /tenant: the name, tagline and logo the app shell shows; the owner-only logo upload."""

import struct
import zlib

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.setup import ShopSettings
from app.services.shop_settings import DEFAULT_TAGLINE
from tests.conftest import login

pytestmark = pytest.mark.integration

COUNTER = ("counter1", "counter-pass-123")
OWNER = ("owner", "owner-pass-123")


def test_everyone_gets_only_the_name_the_tagline_and_the_logo_address(client):
    for headers in ({}, login(client, *OWNER), login(client, *COUNTER)):
        body = client.get("/api/v1/tenant", headers=headers).json()
        assert set(body) == {"name", "tagline", "logo_url"}
        assert body["tagline"] == DEFAULT_TAGLINE
        assert body["logo_url"] is None


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


# ---------------------------------------------------------------- logo upload (UI refresh T10)

ACCOUNTANT = ("accounts", "accounts-pass-123")


def png(width: int, height: int | None = None) -> bytes:
    """A real, small PNG: one flat colour."""
    height = width if height is None else height

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body)
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    row = b"\x00" + b"\xc2\x41\x0c" * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


SVG_OK = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    b'<defs><linearGradient id="g"><stop offset="0" stop-color="#c2410c"/></linearGradient></defs>'
    b'<rect width="64" height="64" fill="url(#g)"/><path d="M8 8h48v48H8z" fill="#fff"/></svg>'
)


def put_logo(client, headers, data: bytes, name: str = "logo.png", type_: str = "image/png"):
    return client.put("/api/v1/tenant/logo", headers=headers, files={"file": (name, data, type_)})


def test_the_owner_uploads_a_png_and_everyone_can_load_it(client):
    owner = login(client, *OWNER)
    data = png(64)
    response = put_logo(client, owner, data)
    assert response.status_code == 200, response.text
    url = response.json()["logo_url"]
    assert url.startswith("/api/v1/tenant/logo?v=")
    assert (
        client.get("/api/v1/tenant").json()["logo_url"] == url
    )  # signed out, for the sign-in page

    image = client.get("/api/v1/tenant/logo")  # no sign-in
    assert image.status_code == 200 and image.content == data
    assert image.headers["content-type"] == "image/png"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in image.headers["content-security-policy"]
    assert "default-src 'none'" in image.headers["content-security-policy"]


def test_an_svg_logo_is_served_as_an_svg(client):
    owner = login(client, *OWNER)
    assert put_logo(client, owner, SVG_OK, "logo.svg", "image/svg+xml").status_code == 200
    image = client.get("/api/v1/tenant/logo")
    assert image.headers["content-type"].startswith("image/svg+xml") and image.content == SVG_OK


def test_only_the_owner_can_change_the_logo(client):
    put_logo(client, login(client, *OWNER), png(64))
    for creds in (COUNTER, ACCOUNTANT):
        headers = login(client, *creds)
        assert put_logo(client, headers, png(96)).status_code == 403
        assert client.delete("/api/v1/tenant/logo", headers=headers).status_code == 403
    assert put_logo(client, {}, png(96)).status_code == 401
    assert client.delete("/api/v1/tenant/logo").status_code == 401
    # nothing changed
    assert client.get("/api/v1/tenant/logo").content == png(64)


def test_replacing_changes_the_address_and_removing_goes_back_to_the_initials(client):
    owner = login(client, *OWNER)
    first = put_logo(client, owner, png(64)).json()["logo_url"]
    second = put_logo(client, owner, png(96)).json()["logo_url"]
    assert first != second

    removed = client.delete("/api/v1/tenant/logo", headers=owner)
    assert removed.status_code == 200 and removed.json()["logo_url"] is None
    assert client.get("/api/v1/tenant/logo").status_code == 404


def test_no_logo_means_404(client):
    assert client.get("/api/v1/tenant/logo").status_code == 404


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (png(64, 96), 409, "LOGO_NOT_SQUARE"),
        (png(16), 409, "LOGO_SIZE"),
        (b"", 409, "FILE_EMPTY"),
        (b"\xff\xd8\xff\xe0" + b"0" * 100, 400, "FILE_TYPE_NOT_ALLOWED"),  # a JPEG
        (b"GIF89a" + b"0" * 100, 400, "FILE_TYPE_NOT_ALLOWED"),
        (b"just some text", 400, "FILE_TYPE_NOT_ALLOWED"),
        (png(64) + b"0" * (200 * 1024), 413, None),  # over 200 KB
    ],
)
def test_size_and_type_limits(client, data, status, code):
    owner = login(client, *OWNER)
    response = put_logo(client, owner, data)
    assert response.status_code == status, response.text
    if code:
        assert response.json()["code"] == code
    assert client.get("/api/v1/tenant").json()["logo_url"] is None  # nothing was stored


def test_the_type_comes_from_the_bytes_not_the_name(client):
    owner = login(client, *OWNER)
    response = put_logo(client, owner, b"<script>alert(1)</script>", "logo.png", "image/png")
    assert response.status_code == 400
    ok = put_logo(client, owner, png(64), "logo.svg", "image/svg+xml")  # a PNG called .svg
    assert ok.status_code == 200
    assert client.get("/api/v1/tenant/logo").headers["content-type"] == "image/png"


@pytest.mark.parametrize(
    "svg",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" onload="alert(1)"></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect onclick="x()"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><foreignObject/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><style>*{}</style></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><image href="x.png"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'viewBox="0 0 8 8"><path xlink:href="http://evil.test/a.svg#x"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8">'
        b'<rect fill="url(http://evil.test/x)"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8">'
        b'<path d="M0 0" fill="javascript:alert(1)"/></svg>',
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><title>&a;</title></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><title>',  # broken XML
    ],
)
def test_an_svg_that_could_run_code_or_fetch_something_is_refused(client, svg):
    owner = login(client, *OWNER)
    response = put_logo(client, owner, svg, "logo.svg", "image/svg+xml")
    assert response.status_code == 400, response.text
    assert client.get("/api/v1/tenant").json()["logo_url"] is None


def test_an_svg_must_be_square_and_sized(client):
    owner = login(client, *OWNER)
    wide = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 32"><rect/></svg>'
    refused = put_logo(client, owner, wide, "l.svg")
    assert refused.status_code == 409 and refused.json()["code"] == "LOGO_NOT_SQUARE"
    bare = b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
    assert put_logo(client, owner, bare, "l.svg").status_code == 409
    sized = b'<svg xmlns="http://www.w3.org/2000/svg" width="48px" height="48"><rect/></svg>'
    assert put_logo(client, owner, sized, "l.svg").status_code == 200


def test_the_logo_change_is_in_the_audit_log(client, db):
    owner = login(client, *OWNER)
    put_logo(client, owner, png(64))
    rows = db.execute(select(AuditLog).where(AuditLog.entity == "shop_settings")).scalars().all()
    assert any("logo_sha256" in (r.changes or {}) for r in rows)
