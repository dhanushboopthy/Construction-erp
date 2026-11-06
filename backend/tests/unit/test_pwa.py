"""The installable app: the manifest a company's address serves (Milestone 29)."""

import struct

from app.domain.pwa import (
    MARK_ICONS,
    PRODUCT,
    SHORT_NAME_MAX,
    THEME_COLOR,
    Icon,
    logo_icon,
    manifest,
    png_side,
    short_name,
)

LOGO = "/api/v1/tenant/logo?v=abc123def456"


def _png(width: int, height: int) -> bytes:
    """The first bytes of a PNG: the signature, then the IHDR chunk with its size."""
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    )


def test_a_short_name_fits_under_an_icon():
    assert short_name("Sri Balaji") == "Sri Balaji"
    assert short_name("  Sri   Balaji  ") == "Sri Balaji"  # spaces tidied
    assert short_name("Sri Balaji Steels and Cements") == "Sri"  # the first word
    assert short_name("Venkateswaraperumal Traders") == "Venkateswara"  # cut to the limit
    assert len(short_name("Venkateswaraperumal Traders")) == SHORT_NAME_MAX
    assert short_name("   ") == "ERP"  # never empty


def test_the_side_of_a_square_png():
    assert png_side(_png(512, 512)) == 512
    assert png_side(_png(512, 256)) is None  # not square
    assert png_side(_png(0, 0)) is None
    assert png_side(b"\x89PNG") is None  # too short
    assert png_side(b"GIF89a" + bytes(30)) is None  # not a PNG
    assert png_side(b"\x89PNG\r\n\x1a\n" + bytes(4) + b"IDAT" + bytes(8)) is None  # no IHDR


def test_the_logo_as_an_icon():
    assert logo_icon(LOGO, "image/svg+xml", b"<svg") == Icon(LOGO, "image/svg+xml", "any")
    assert logo_icon(LOGO, "image/png", _png(192, 192)) == Icon(LOGO, "image/png", "192x192")
    assert logo_icon(LOGO, "image/png", b"broken") is None  # the Duolink mark stands in
    assert logo_icon(LOGO, "image/gif", b"GIF89a") is None


def test_the_manifest_names_the_company_and_installs_as_an_app():
    found = manifest("Sri Balaji Steels")
    assert found["name"] == "Sri Balaji Steels"
    assert found["short_name"] == "Sri"
    assert found["description"] == f"{PRODUCT} for Sri Balaji Steels"
    assert found["start_url"] == "/"
    assert found["scope"] == "/"
    assert found["id"] == "/"
    assert found["display"] == "standalone"
    assert found["theme_color"] == THEME_COLOR
    assert found["background_color"] == THEME_COLOR


def test_without_a_logo_the_duolink_mark_is_the_icon():
    icons = manifest("Acme")["icons"]
    assert icons == [
        {"src": i.src, "type": i.type, "sizes": i.sizes, "purpose": i.purpose} for i in MARK_ICONS
    ]
    # An installable icon: any size (SVG), for "any" use, and a maskable one for phones.
    assert {"sizes": "any", "purpose": "any"}.items() <= icons[0].items()
    assert icons[1]["purpose"] == "maskable"


def test_the_logo_comes_first_and_the_mark_stays_as_a_fallback():
    logo = Icon(LOGO, "image/png", "512x512")
    icons = manifest("Acme", logo)["icons"]
    assert icons[0] == {"src": LOGO, "type": "image/png", "sizes": "512x512", "purpose": "any"}
    assert [i["src"] for i in icons[1:]] == [i.src for i in MARK_ICONS]


def test_a_company_without_a_name_yet_installs_as_the_product():
    found = manifest("  ")
    assert found["name"] == PRODUCT
    assert found["description"] == PRODUCT
