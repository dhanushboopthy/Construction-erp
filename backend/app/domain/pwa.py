"""The installable app (Milestone 29): the web app manifest a company's address serves.

Pure: the company's name and logo come in, the manifest goes out. The browser reads it to offer
"Install" and to draw the icon on the shop's PC or phone. The colours are the navy of the
sidebar and the sign-in page (index.html's theme-color), the one place they are written as hex:
a manifest cannot read the CSS tokens.
"""

import struct
from dataclasses import asdict, dataclass
from typing import Any

PRODUCT = "Construction ERP"
THEME_COLOR = "#0f1e33"
SHORT_NAME_MAX = 12  # what fits under an icon on a phone's home screen
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class Icon:
    src: str
    type: str
    sizes: str
    purpose: str = "any"


# The Duolink mark, served from the app's own files: an icon the browser can always load, so
# the app installs even when the company has no logo or its logo will not do.
MARK_ICONS = (
    Icon("/icons/duolink-mark.svg", "image/svg+xml", "any"),
    Icon("/icons/duolink-maskable.svg", "image/svg+xml", "any", "maskable"),
)


def _tidy(name: str) -> str:
    return " ".join(name.split())


def short_name(name: str) -> str:
    """The name under the icon: the whole name if it fits, else its first word, cut to fit."""
    clean = _tidy(name)
    if not clean:
        return "ERP"
    if len(clean) <= SHORT_NAME_MAX:
        return clean
    return clean.split(" ")[0][:SHORT_NAME_MAX]


def png_side(header: bytes) -> int | None:
    """The side of a square PNG from its first 24 bytes; None when it is not one."""
    if len(header) < 24 or header[:8] != _PNG_SIGNATURE or header[12:16] != b"IHDR":
        return None
    width: int
    height: int
    width, height = struct.unpack(">II", header[16:24])
    return width if width == height and width > 0 else None


def logo_icon(url: str, content_type: str, header: bytes) -> Icon | None:
    """The company's logo as a manifest icon: an SVG fits any size, a PNG says its own."""
    if content_type == "image/svg+xml":
        return Icon(url, content_type, "any")
    if content_type == "image/png":
        side = png_side(header)
        return Icon(url, content_type, f"{side}x{side}") if side else None
    return None


def manifest(name: str, logo: Icon | None = None) -> dict[str, Any]:
    """The manifest for the company called `name`. Its logo, when given, is the first icon; the
    Duolink mark always follows, so the browser has an icon it can use."""
    shown = _tidy(name) or PRODUCT
    icons = [logo, *MARK_ICONS] if logo else list(MARK_ICONS)
    return {
        "id": "/",
        "name": shown,
        "short_name": short_name(shown),
        "description": PRODUCT if shown == PRODUCT else f"{PRODUCT} for {shown}",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": THEME_COLOR,
        "theme_color": THEME_COLOR,
        "icons": [asdict(icon) for icon in icons],
    }
