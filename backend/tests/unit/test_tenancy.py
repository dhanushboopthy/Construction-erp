"""Company slugs and reading the company from the browser's host name (ADR 0011)."""

import pytest

from app.domain.tenancy import check_slug, slug_from_host


@pytest.mark.parametrize(
    ("host", "slug"),
    [
        ("acme.duolink.app", "acme"),
        ("ACME.Duolink.App", "acme"),
        ("acme.duolink.app:443", "acme"),
        ("acme.duolink.app.", "acme"),
        ("admin.duolink.app", "admin"),
        ("duolink.app", None),  # the bare domain names no company
        ("www.acme.duolink.app", None),  # only one label in front of the base domain
        ("evilduolink.app", None),
        ("192.168.1.20:8080", None),  # a shop LAN by IP address
        ("testserver", None),
        ("", None),
        (None, None),
    ],
)
def test_slug_from_host(host, slug):
    assert slug_from_host(host, "duolink.app") == slug


def test_localhost_subdomains_work_in_development():
    assert slug_from_host("acme.localhost:5173", "localhost") == "acme"
    assert slug_from_host("localhost:5173", "localhost") is None


@pytest.mark.parametrize("slug", ["acme", "abc", "shree-steels", "a1b2", "x" * 30])
def test_valid_slugs(slug):
    assert check_slug(slug) == slug


def test_slug_is_trimmed_and_lowercased():
    assert check_slug("  Shree-Steels ") == "shree-steels"


@pytest.mark.parametrize(
    "slug",
    ["ab", "x" * 31, "-acme", "acme-", "ac me", "acme_co", "acmé", "ac.me", ""],
)
def test_invalid_slugs(slug):
    with pytest.raises(ValueError, match="3 to 30"):
        check_slug(slug)


@pytest.mark.parametrize("slug", ["admin", "www", "api", "app"])
def test_reserved_slugs(slug):
    with pytest.raises(ValueError, match="reserved"):
        check_slug(slug)
