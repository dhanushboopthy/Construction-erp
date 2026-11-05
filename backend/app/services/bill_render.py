"""Printing a bill on a company's own design (Milestone 28).

The stored HTML is data. It is cleaned again, filled by `app/domain/bill_html.py` (a placeholder
grammar that evaluates nothing) and drawn by WeasyPrint with a fetcher that serves only the
design's own images: no file, no network, nothing else.
"""

import hashlib
import logging
import struct
import zlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_to_bytes

from sqlalchemy import select
from sqlalchemy.orm import Session
from weasyprint import HTML
from weasyprint.urls import URLFetcher, URLFetcherResponse

from app.core.config import get_settings
from app.core.tenancy import current_tenant_id
from app.domain.bill_html import fill
from app.domain.bill_template import BillData
from app.models.bill_templates import BillTemplate, BillTemplateAsset
from app.services import shop_settings, tenant_logo
from app.services.storage import StorageError, get_storage

log = logging.getLogger(__name__)

Asset = tuple[bytes, str]  # the bytes and the content type
LOGO, SECONDARY_LOGO, QR = "@logo", "@secondary-logo", "@einvoice-qr"


class AssetFetcher(URLFetcher):  # type: ignore[misc]
    """Serves `asset:<name>` from the design's own images and refuses every other address."""

    def __init__(self, assets: dict[str, Asset]) -> None:
        super().__init__(allowed_protocols=[])
        self._assets = assets

    def fetch(self, url: str, headers: Any = None) -> URLFetcherResponse:
        name = url.removeprefix("asset:") if url.startswith("asset:") else None
        if name is None or name not in self._assets:
            raise ValueError(f"Not one of the design's images: {url[:60]}")
        data, content_type = self._assets[name]
        return URLFetcherResponse(url, data, {"Content-Type": content_type})


def draw(html: str, assets: dict[str, Asset]) -> bytes:
    return HTML(string=html, url_fetcher=AssetFetcher(assets)).write_pdf()  # type: ignore[no-any-return]


def qr_asset(qr_uri: str) -> Asset:
    """The e-Invoice QR as the design's own image (the printed bill carries it as a data URI)."""
    head, _, body = qr_uri.partition(",")
    return unquote_to_bytes(body), head.removeprefix("data:").split(";")[0]


@dataclass(frozen=True)
class Loaded:
    template: BillTemplate
    html: str
    assets: dict[str, Asset]


def _read(key: str, sha256: str) -> bytes:
    data = get_storage().get(key)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise StorageError("The stored file does not match its record")
    return data


def load(db: Session, template_id: int | None) -> Loaded | None:
    """The company's design with its images, or None when there is none to use (the caller then
    prints the built-in layout)."""
    if template_id is None:
        return None
    template = db.scalar(
        select(BillTemplate).where(
            BillTemplate.tenant_id == current_tenant_id(db), BillTemplate.id == template_id
        )
    )
    if template is None:
        return None
    try:
        html = _read(template.html_key, template.html_sha256).decode("utf-8")
        assets: dict[str, Asset] = {
            row.name: (_read(row.key, row.sha256), row.content_type)
            for row in db.scalars(
                select(BillTemplateAsset).where(
                    BillTemplateAsset.tenant_id == current_tenant_id(db),
                    BillTemplateAsset.template_id == template.id,
                )
            )
        }
        if template.secondary_logo_key and template.secondary_logo_sha256:
            assets[SECONDARY_LOGO] = (
                _read(template.secondary_logo_key, template.secondary_logo_sha256),
                template.secondary_logo_type or "image/png",
            )
        row = shop_settings.get_settings_row(db)
        if row.logo_key:
            data, content_type, _ = tenant_logo.read(db)
            assets[LOGO] = (data, content_type)
    except Exception:  # a file lost from storage must not stop a bill printing
        log.exception("bill design %s could not be read; printing the built-in layout", template_id)
        return None
    return Loaded(template, html, assets)


def render(loaded: Loaded, data: BillData, *, extra: dict[str, Asset] | None = None) -> bytes:
    assets = {**loaded.assets, **(extra or {})}
    mark = None if get_settings().is_production else "TEST"
    return draw(fill(loaded.html, data, assets.keys(), mark=mark), assets)


def preview(loaded: Loaded, data: BillData) -> bytes:
    """The same renderer with sample data, marked as a sample on every page."""
    assets = dict(loaded.assets)
    for name, content_type in [(LOGO, "image/png"), (QR, "image/png")]:
        assets.setdefault(name, (_PLACEHOLDER_PNG, content_type))
    assets.setdefault(SECONDARY_LOGO, (_PLACEHOLDER_PNG, "image/png"))
    return draw(fill(loaded.html, data, assets.keys(), mark="SAMPLE"), assets)


def _grey_png() -> bytes:
    """A small light-grey PNG, so a sample bill shows where each logo and the QR code sit."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    side = 16
    rows = b"".join(b"\x00" + b"\xdd" * side for _ in range(side))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


_PLACEHOLDER_PNG = _grey_png()
