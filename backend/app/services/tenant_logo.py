"""The shop's logo (UI refresh T10): a square PNG or a plain SVG, up to 200 KB.

The type is decided from the bytes, never from the file name or the browser's claim. An SVG is
the risky one (it can carry script), so only a short list of drawing elements is accepted and
anything that could run code or fetch something is refused; it is also served with headers that
stop a browser running anything even if a file slipped through."""

import hashlib
import re
import struct
from xml.etree import ElementTree

from sqlalchemy.orm import Session

from app.core.errors import AppError, BusinessRuleError, NotFoundError, PayloadTooLargeError
from app.core.tenancy import current_tenant_id
from app.services import shop_settings
from app.services.storage import StorageError, get_storage

MAX_BYTES = 200 * 1024
MIN_SIDE, MAX_SIDE = 32, 2048  # PNG pixels

PNG, SVG = "image/png", "image/svg+xml"
EXTENSION = {PNG: "png", SVG: "svg"}

_SVG_NS = "{http://www.w3.org/2000/svg}"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
# Drawing only: no script, style sheets, images, foreignObject, animation or <use>.
_ALLOWED = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "defs", "linearGradient", "radialGradient", "stop", "clipPath", "title", "desc",
}  # fmt: skip
_BAD_VALUE = re.compile(
    r"javascript:|data:|https?:|@import|expression\(|url\(\s*(?![\"']?#)", re.IGNORECASE
)
_LENGTH = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$")
_NOT_SQUARE = "The logo must be square (the same width and height)"


def _png_side(data: bytes) -> int:
    if len(data) < 33 or data[12:16] != b"IHDR":
        raise AppError("The PNG file is damaged", code="LOGO_INVALID")
    width: int
    height: int
    width, height = struct.unpack(">II", data[16:24])
    if width != height:
        raise BusinessRuleError(_NOT_SQUARE, code="LOGO_NOT_SQUARE", field="file")
    if not MIN_SIDE <= width <= MAX_SIDE:
        raise BusinessRuleError(
            f"The logo must be between {MIN_SIDE} and {MAX_SIDE} pixels a side",
            code="LOGO_SIZE",
            field="file",
        )
    return width


def _local(tag: str) -> str:
    return tag.removeprefix(_SVG_NS) if tag.startswith(_SVG_NS) else f"?{tag}"


def _refuse_svg(why: str) -> AppError:
    return AppError(
        f"This SVG cannot be used ({why}). Save it as a plain SVG with drawing shapes only.",
        code="LOGO_SVG_UNSAFE",
    )


def _svg_side(data: bytes) -> None:
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise _refuse_svg("it declares entities")
    try:
        # No DOCTYPE got this far, so there is nothing for an entity attack to expand.
        root = ElementTree.fromstring(data)  # noqa: S314
    except ElementTree.ParseError as exc:
        raise AppError("The SVG file is damaged", code="LOGO_INVALID") from exc
    for el in root.iter():
        if not isinstance(el.tag, str):  # comments and processing instructions
            raise _refuse_svg("it has processing instructions")
        name = _local(el.tag)
        if name not in _ALLOWED:
            raise _refuse_svg(f"it uses <{name.lstrip('?').rsplit('}', 1)[-1]}>")
        for attr, value in el.attrib.items():
            if attr.startswith("on") or _BAD_VALUE.search(value):
                raise _refuse_svg("it has a script or an outside link")
            if attr in {"href", _XLINK_HREF} and not value.startswith("#"):
                raise _refuse_svg("it links outside itself")
            if attr.startswith("{") and attr not in {_XLINK_HREF, _XML_SPACE}:
                raise _refuse_svg("it uses a foreign attribute")
    if _local(root.tag) != "svg":
        raise AppError("The SVG file is damaged", code="LOGO_INVALID")
    box = root.attrib.get("viewBox")
    if box is not None:
        parts = box.replace(",", " ").split()
        if len(parts) != 4:
            raise AppError("The SVG viewBox is not valid", code="LOGO_INVALID")
        try:
            width, height = float(parts[2]), float(parts[3])
        except ValueError as exc:
            raise AppError("The SVG viewBox is not valid", code="LOGO_INVALID") from exc
    else:
        w, h = (
            _LENGTH.match(root.attrib.get("width", "")),
            _LENGTH.match(root.attrib.get("height", "")),
        )
        if not (w and h):
            raise BusinessRuleError(
                "The SVG needs a viewBox, or a width and height in pixels",
                code="LOGO_INVALID",
                field="file",
            )
        width, height = float(w.group(1)), float(h.group(1))
    if width <= 0 or abs(width - height) > 1e-6 * max(width, height):
        raise BusinessRuleError(_NOT_SQUARE, code="LOGO_NOT_SQUARE", field="file")


def check(data: bytes) -> str:
    """The logo's content type if the file is acceptable; otherwise the reason it is not."""
    if not data:
        raise BusinessRuleError("The file is empty", code="FILE_EMPTY", field="file")
    if len(data) > MAX_BYTES:
        raise PayloadTooLargeError("The logo is larger than 200 KB. Use a smaller file.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        _png_side(data)
        return PNG
    if re.match(rb"^\s*(<\?xml[^>]*\?>\s*)?(<!--.*?-->\s*)*<svg[\s>]", data[:2048], re.S):
        _svg_side(data)
        return SVG
    raise AppError("The logo must be a PNG or an SVG file", code="FILE_TYPE_NOT_ALLOWED")


def save(db: Session, data: bytes) -> None:
    content_type = check(data)
    digest = hashlib.sha256(data).hexdigest()
    key = f"logo/{current_tenant_id(db)}/{digest[:32]}.{EXTENSION[content_type]}"
    try:
        get_storage().put(key, data)
    except (StorageError, OSError) as exc:
        raise AppError("The logo could not be stored. Try again.", code="STORAGE_FAILED") from exc
    row = shop_settings.get_settings_row(db)
    row.logo_key, row.logo_type, row.logo_sha256 = key, content_type, digest
    db.commit()


def remove(db: Session) -> None:
    """Back to the initials tile. The stored file stays; the name is its hash, so it is harmless."""
    row = shop_settings.get_settings_row(db)
    row.logo_key = row.logo_type = row.logo_sha256 = None
    db.commit()


def read(db: Session) -> tuple[bytes, str, str]:
    """The logo's bytes, its type and its hash."""
    row = shop_settings.get_settings_row(db)
    if row.logo_key is None or row.logo_type is None or row.logo_sha256 is None:
        raise NotFoundError("No logo has been uploaded")
    try:
        data = get_storage().get(row.logo_key)
    except StorageError as exc:
        raise NotFoundError("The stored logo is missing") from exc
    if hashlib.sha256(data).hexdigest() != row.logo_sha256:
        raise AppError("The stored logo does not match its record", code="FILE_CORRUPT")
    return data, row.logo_type, row.logo_sha256
