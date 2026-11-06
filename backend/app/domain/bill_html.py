"""The HTML of a bill template (Milestone 28): parse, clean, analyse and fill.

- **Parse** with tinyhtml5, the HTML5 parser WeasyPrint itself uses, so the tree that is cleaned
  is the tree that is drawn.
- **Clean** with an allow-list. What a browser would run or what would fetch something goes:
  `<script>`, `on*` attributes, `javascript:` and other unsafe links, `<iframe>`, `<object>`,
  `<embed>`, `<base>`, `<link>`, `<form>` (its content stays), meta refresh, inline SVG and
  MathML, CSS `@import`, `expression()`, `behavior` and `-moz-binding`, and any `url()` that is
  not one of the template's own images. An image whose source is not one of the template's own
  images or a company image placeholder loses only that image. Everything else is kept as
  written, and a style sheet with nothing to remove is kept byte for byte. Cleaning settles after
  one pass.
- **Fill**: the `<tr>` holding `{{item.*}}` placeholders (or the section between
  `<!-- items:start -->` and `<!-- items:end -->`) is repeated once per line, the same for
  `{{hsn.*}}`; every placeholder is replaced by its value, which the serializer escapes. Styles
  are never filled. Nothing is evaluated.

Pure. The renderer serves the `asset:` addresses itself and refuses every other address.
"""

import copy
import re
from collections import Counter
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass, field
from typing import Any
from xml.etree.ElementTree import Comment, Element

import tinycss2
import tinyhtml5
from tinycss2 import ast

from app.domain.bill_template import (
    HSN,
    IMAGE_URIS,
    ITEM,
    REGISTRY,
    BillData,
    TemplateRuleError,
    Token,
    format_value,
    has_forbidden_wording,
    missing_requirements,
    parse_token,
    substitute,
    tokens,
)

MAX_DEPTH = 200
MAX_ELEMENTS = 20_000


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


def _tag(node: Element) -> Any:
    """An element's tag: a string, or the `Comment` function for a comment node."""
    return node.tag


# Kept as they are.
ALLOWED = _words(
    """html head body title meta style div span p br hr table thead tbody tfoot tr td th
    colgroup col caption img b i u s strong em small big sub sup h1 h2 h3 h4 h5 h6 ul ol li dl
    dt dd section header footer main article aside nav address pre code blockquote figure
    figcaption del ins mark abbr label center font a wbr time q cite var samp kbd bdi bdo"""
)
# Dropped with everything inside them.
DROPPED = _words(
    """script iframe object embed base frame frameset applet noscript template link audio
    video canvas source track param input button select textarea option optgroup datalist
    output progress meter portal noembed noframes plaintext xmp dialog slot picture map area"""
)
VOID = _words("area base br col embed hr img input link meta param source track wbr")
ATTRIBUTES = _words(
    """id class style title lang dir align valign width height border bgcolor color colspan
    rowspan span cellpadding cellspacing nowrap scope headers face size start type reversed
    alt charset name content datetime abbr frame rules"""
)
_ATTR_NAME = re.compile(r"^[a-zA-Z_][-a-zA-Z0-9_.]*$")
_SAFE_LINK = re.compile(r"^(https?:|mailto:|tel:|#)", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x20]+")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
MARKERS = {"items:start": ("item", "items:end"), "hsn:start": ("hsn", "hsn:end")}

# CSS.
_SCRIPT_PROPERTIES = frozenset({"behavior", "-moz-binding"})
_SCRIPT_FUNCTIONS = frozenset({"expression"})
_FETCH_FUNCTIONS = frozenset({"image-set", "-webkit-image-set", "image", "cross-fade", "element"})
_URL_FUNCTIONS = frozenset({"url", "src"})
_RULE_LIST_AT = frozenset({"media", "supports", "layer"})
_MARGIN_BOXES = frozenset(
    f"{side}-{place}"
    for side, places in [
        ("top", ("left-corner", "left", "center", "right", "right-corner")),
        ("bottom", ("left-corner", "left", "center", "right", "right-corner")),
        ("left", ("top", "middle", "bottom")),
        ("right", ("top", "middle", "bottom")),
    ]
    for place in places
)
_BLOCK_AT = frozenset({"page", "font-face", "counter-style"}) | _MARGIN_BOXES
_STATEMENT_AT = frozenset({"charset", "namespace"})

_MARK_STYLE = (
    "position: fixed; top: 38%; left: 8%; font-size: 90pt; color: rgba(180, 35, 24, 0.13); "
    "transform: rotate(-30deg); letter-spacing: 8mm; z-index: -1"
)


# ------------------------------------------------------------------ parse and serialize


def parse(html: str) -> Element:
    """The document tree, refused when it is too deep or too big to handle safely."""
    root: Element = tinyhtml5.parse(html, namespace_html_elements=False)
    count = 0
    stack: list[tuple[Element, int]] = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH:
            raise TemplateRuleError(
                "TEMPLATE_TOO_DEEP", f"The template nests elements more than {MAX_DEPTH} deep."
            )
        if count > MAX_ELEMENTS:
            raise TemplateRuleError(
                "TEMPLATE_TOO_BIG", f"The template has more than {MAX_ELEMENTS} elements."
            )
        stack.extend((child, depth + 1) for child in node)
    return root


def _text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _attr(value: str) -> str:
    return _text(value).replace('"', "&quot;")


def _comment(value: str) -> str:
    safe = value.replace("--!>", "-- !>").replace("-->", "-- >")
    return " " + safe if safe.startswith((">", "->")) else safe


def serialize(root: Element) -> str:
    out: list[str] = ["<!DOCTYPE html>"]

    def walk(node: Element) -> None:
        if _tag(node) is Comment:
            out.append(f"<!--{_comment(node.text or '')}-->")
        elif isinstance(node.tag, str):
            attrs = "".join(f' {k}="{_attr(v)}"' for k, v in node.attrib.items())
            out.append(f"<{node.tag}{attrs}>")
            if node.tag not in VOID:
                if node.text:
                    # A style sheet is raw text: only a closing tag inside it could end it early.
                    out.append(
                        node.text.replace("</", "<\\/") if node.tag == "style" else _text(node.text)
                    )
                for child in node:
                    walk(child)
                out.append(f"</{node.tag}>")
        if node.tail:
            out.append(_text(node.tail))

    walk(root)
    return "".join(out)


# ------------------------------------------------------------------ tree helpers


def _parents(root: Element) -> dict[int, Element]:
    return {id(child): parent for parent in root.iter() for child in parent}


def _append_text(parent: Element, before: Element | None, text: str | None) -> None:
    """Put `text` at the end of `before` (its tail), or at the start of `parent`."""
    if not text:
        return
    if before is None:
        parent.text = (parent.text or "") + text
    else:
        before.tail = (before.tail or "") + text


def _previous(parent: Element, node: Element) -> Element | None:
    kids = list(parent)
    index = kids.index(node)
    return kids[index - 1] if index else None


def _remove(parent: Element, node: Element) -> None:
    """Take `node` out, keeping the text that followed it."""
    _append_text(parent, _previous(parent, node), node.tail)
    parent.remove(node)


def _unwrap(parent: Element, node: Element) -> None:
    """Replace `node` by its content."""
    index = list(parent).index(node)
    previous = _previous(parent, node)
    _append_text(parent, previous, node.text)
    children = list(node)
    for offset, child in enumerate(children):
        parent.insert(index + offset, child)
    _append_text(parent, children[-1] if children else previous, node.tail)
    parent.remove(node)


# ------------------------------------------------------------------ addresses


def _asset_of(value: str, assets: Collection[str]) -> str | None:
    """The template image an address names: `asset:name`, `name` or `some/folder/name`."""
    target = value.strip()
    if target.startswith("asset:"):
        name = target.removeprefix("asset:")
        return name if name in assets else None
    if not target or _SCHEME.match(target) or target.startswith(("/", "\\")):
        return None
    parts = target.replace("\\", "/").split("/")
    if ".." in parts:
        return None
    return parts[-1] if parts[-1] in assets else None


def _image_key(value: str) -> str | None:
    """The company image placeholder an image's source is, if it is one."""
    token = parse_token(value.strip())
    if token.known and token.key in IMAGE_URIS and token.fmt is None:
        return token.key
    return None


# ------------------------------------------------------------------ CSS


@dataclass
class _Css:
    assets: Collection[str]
    notes: list[str]
    changed: bool = False

    def values(self, nodes: list[Any]) -> tuple[list[Any], str | None]:
        """Cleaned component values, or the reason the declaration holding them must go."""
        cleaned: list[Any] = []
        for node in nodes:
            kind = node.type
            if kind == "url" or (kind == "function" and node.lower_name in _URL_FUNCTIONS):
                target = node.value if kind == "url" else _string_argument(node)
                name = None if target is None else _asset_of(target, self.assets)
                if name is None:
                    return [], "outside address in a style"
                new = f"asset:{name}"
                if target != new or kind != "url":
                    self.changed = True
                    node = ast.URLToken(node.source_line, node.source_column, new, f'url("{new}")')
            elif kind == "function" and node.lower_name in _SCRIPT_FUNCTIONS:
                return [], "script hook in a style"
            elif kind == "function" and node.lower_name in _FETCH_FUNCTIONS:
                return [], "outside address in a style"
            elif kind == "function" or kind in {"() block", "[] block", "{} block"}:
                inner, why = self.values(node.arguments if kind == "function" else node.content)
                if why:
                    return [], why
                if kind == "function":
                    node.arguments = inner
                else:
                    node.content = inner
            cleaned.append(node)
        return cleaned, None

    def declaration(self, node: Any) -> str | None:
        """The declaration as text, or None when it goes."""
        if node.lower_name in _SCRIPT_PROPERTIES:
            self.notes.append("script hook in a style")
            return None
        value, why = self.values(node.value)
        if why:
            self.notes.append(why)
            return None
        important = " !important" if node.important else ""
        return f"{node.name}:{tinycss2.serialize(value)}{important}"

    def blocks(self, content: list[Any]) -> str:
        """The inside of a block holding declarations (and, in nested CSS, rules)."""
        parts = [
            self.rule(node)
            for node in tinycss2.parse_blocks_contents(
                content, skip_comments=True, skip_whitespace=True
            )
        ]
        return "; ".join(p for p in parts if p is not None)

    def rule_list(self, content: list[Any]) -> str:
        parts = [self.rule(n) for n in tinycss2.parse_rule_list(content)]
        return "".join(p for p in parts if p is not None)

    def rule(self, node: Any) -> str | None:
        kind = node.type
        if kind == "declaration":
            return self.declaration(node)
        if kind == "qualified-rule":
            return f"{tinycss2.serialize(node.prelude)}{{{self.blocks(node.content)}}}"
        if kind == "at-rule":
            name = node.lower_at_keyword
            head = f"@{node.at_keyword}{tinycss2.serialize(node.prelude)}"
            if name in _STATEMENT_AT and node.content is None:
                return f"{head};"
            if name in _RULE_LIST_AT and node.content is not None:
                return f"{head}{{{self.rule_list(node.content)}}}"
            if name in _BLOCK_AT and node.content is not None:
                return f"{head}{{{self.blocks(node.content)}}}"
            self.notes.append(f"@{name} rule in a style")
            return None
        if kind == "error":
            return None
        return str(tinycss2.serialize([node]))  # whitespace and comments


def _string_argument(node: Any) -> str | None:
    args = [a for a in node.arguments if a.type != "whitespace"]
    return str(args[0].value) if len(args) == 1 and args[0].type == "string" else None


def _clean_sheet(css: str, assets: Collection[str], notes: list[str]) -> str:
    cleaner = _Css(assets, notes)
    before = len(notes)
    parts = [cleaner.rule(n) for n in tinycss2.parse_stylesheet(css)]
    text = "".join(p for p in parts if p is not None)
    return text if len(notes) > before or cleaner.changed else css


def _clean_inline(css: str, assets: Collection[str], notes: list[str]) -> str:
    cleaner = _Css(assets, notes)
    before = len(notes)
    text = cleaner.blocks(tinycss2.parse_component_value_list(css))
    return text if len(notes) > before or cleaner.changed else css


# ------------------------------------------------------------------ clean


@dataclass(frozen=True)
class Cleaned:
    html: str
    removed: tuple[str, ...]  # what came out, for the person who uploaded it


def _summary(notes: list[str]) -> tuple[str, ...]:
    counts = Counter(notes)
    return tuple(n if counts[n] == 1 else f"{n} ({counts[n]})" for n in counts)


def _keep_image(node: Element, assets: Collection[str]) -> bool:
    src = node.get("src", "")
    key = _image_key(src)
    if key is not None:
        node.set("src", f"{{{{{key}}}}}")
        return True
    name = _asset_of(src, assets)
    if name is None:
        return False
    node.set("src", f"asset:{name}")
    return True


def _clean_elements(root: Element, assets: Collection[str], notes: list[str]) -> None:
    parents = _parents(root)
    gone: set[int] = set()
    for node in list(root.iter()):
        parent = parents.get(id(node))
        if parent is None or id(parent) in gone or _tag(node) is Comment:
            continue  # the root, a comment, or inside something already dropped
        if not isinstance(node.tag, str):
            _remove(parent, node)  # a processing instruction
            continue
        local = node.tag.rsplit("}", 1)[-1].lower()
        if node.tag.startswith("{") or local in DROPPED:
            notes.append(f"<{local}> element")
            gone.update(id(n) for n in node.iter())
            _remove(parent, node)
        elif local == "meta" and "http-equiv" in {k.lower() for k in node.attrib}:
            notes.append("<meta http-equiv> element")
            _remove(parent, node)
        elif local == "img" and not _keep_image(node, assets):
            notes.append(f"image {node.get('src', '')!r} (not one of the template's images)")
            _remove(parent, node)
        elif local not in ALLOWED:
            notes.append(f"<{local}> tag (what it held is kept)")
            for child in node:
                parents[id(child)] = parent
            _unwrap(parent, node)


def _keep_attribute(node: Element, name: str, value: str) -> bool:
    lower = name.lower()
    if lower == "href" and node.tag == "a":
        return bool(_SAFE_LINK.match(_CONTROL.sub("", value)))
    if lower == "src" and node.tag == "img":
        return True  # settled by _keep_image
    return bool(_ATTR_NAME.match(name)) and (lower in ATTRIBUTES or lower.startswith("data-"))


def _clean_attributes(root: Element, assets: Collection[str], notes: list[str]) -> None:
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag == "style" and node.text:
            node.text = _clean_sheet(node.text, assets, notes)
        for name in list(node.attrib):
            value = node.attrib[name]
            if not _keep_attribute(node, name, value):
                notes.append(f"{name.lower()} attribute on <{node.tag}>")
                del node.attrib[name]
            elif name.lower() == "style":
                node.attrib[name] = _clean_inline(value, assets, notes)


def _sanitize(root: Element, assets: Collection[str]) -> list[str]:
    notes: list[str] = []
    _clean_elements(root, assets, notes)
    _clean_attributes(root, assets, notes)
    return notes


def clean(html: str, assets: Collection[str]) -> Cleaned:
    root = parse(html)
    notes = _sanitize(root, assets)
    return Cleaned(html=serialize(root), removed=_summary(notes))


# ------------------------------------------------------------------ where the text is


@dataclass(frozen=True)
class _Loc:
    """One piece of fillable text: an element's text, one of its attributes, or the text that
    follows a node (its tail). `owner` is the element the text sits in."""

    node: Element
    where: str  # "text", "attr" or "tail"
    name: str | None
    value: str
    owner: Element | None


def _locations(node: Element, parent: Element | None = None) -> Iterator[_Loc]:
    """Every piece of text in document order. Style sheets and style attributes are left out:
    they are never filled."""
    if isinstance(node.tag, str):
        if node.tag != "style" and node.text:
            yield _Loc(node, "text", None, node.text, node)
        for name, value in node.attrib.items():
            if name.lower() != "style":
                yield _Loc(node, "attr", name, value, node)
        for child in node:
            yield from _locations(child, node)
    if node.tail:
        yield _Loc(node, "tail", None, node.tail, parent)


def _set(loc: _Loc, value: str) -> None:
    if loc.where == "text":
        loc.node.text = value
    elif loc.where == "attr" and loc.name is not None:
        loc.node.set(loc.name, value)
    else:
        loc.node.tail = value


# ------------------------------------------------------------------ repeating sections


@dataclass(eq=False)
class _Section:
    kind: str  # "item" or "hsn"
    parent: Element
    nodes: list[Element]
    start: Element | None = None  # the start marker, for a marker section
    inside: set[int] = field(default_factory=set)  # every element inside it

    def holds(self, loc: _Loc) -> bool:
        if (
            loc.where == "tail"
            and self.start is not None
            and (loc.node is self.start or any(loc.node is n for n in self.nodes))
        ):
            return True
        return loc.owner is not None and id(loc.owner) in self.inside


def _marker(node: Element) -> str | None:
    return (node.text or "").strip() if _tag(node) is Comment else None


def _kinds(text: str) -> set[str]:
    keys = [t.key for t in tokens(text) if t.key]
    return {"item" for k in keys if k.startswith(ITEM)} | {"hsn" for k in keys if k.startswith(HSN)}


def _sections(root: Element) -> list[_Section]:
    """The repeating sections: marker pairs first, then each `<tr>` holding a line or HSN
    placeholder outside them (a row inside another repeating row is part of that row)."""
    parents = _parents(root)
    found: list[_Section] = []
    for parent in root.iter():
        kids = list(parent)
        for i, kid in enumerate(kids):
            name = _marker(kid)
            if name not in MARKERS:
                continue
            kind, end = MARKERS[name]
            j = next((j for j in range(i + 1, len(kids)) if _marker(kids[j]) == end), None)
            if j is not None:
                section = _Section(kind, parent, kids[i + 1 : j], start=kid)
                section.inside = {id(n) for node in section.nodes for n in node.iter()}
                found.append(section)
    rows: dict[int, _Section] = {}
    for loc in _locations(root):
        kinds = _kinds(loc.value)
        if not kinds or any(s.holds(loc) for s in found):
            continue
        row = loc.owner
        while row is not None and row.tag != "tr":
            row = parents.get(id(row))
        if row is None:
            continue
        section = rows.setdefault(id(row), _Section("hsn", parents[id(row)], [row]))
        if "item" in kinds:
            section.kind = "item"
    for section in rows.values():
        section.inside = {id(n) for n in section.nodes[0].iter()}
    for key, section in list(rows.items()):
        up = parents.get(id(section.nodes[0]))
        while up is not None:
            if id(up) in rows:
                del rows[key]
                break
            up = parents.get(id(up))
    return found + list(rows.values())


def _kind_of(loc: _Loc, sections: list[_Section]) -> str | None:
    return next((s.kind for s in sections if s.holds(loc)), None)


# ------------------------------------------------------------------ analyse


@dataclass(frozen=True)
class Analysis:
    present: frozenset[str]  # registered fields that will print
    unknown: tuple[str, ...]  # not a placeholder: prints blank
    other_slot: tuple[str, ...]  # a real field, but not one this slot fills: prints blank
    outside_rows: tuple[str, ...]  # a line or HSN field outside its repeating row: blank
    in_styles: tuple[str, ...]  # in a style: never filled
    item_rows: int
    hsn_rows: int
    images: tuple[str, ...]  # company image placeholders and template image names
    page_size: str | None
    missing: tuple[str, ...]  # what the GST rules need and the template leaves out
    wording: bool  # a proforma or quotation calling itself a tax invoice


@dataclass
class _Report:
    slot: str
    present: set[str] = field(default_factory=set)
    unknown: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    outside: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)

    def token(self, token: Token, kind: str | None) -> None:
        key = token.key
        if not token.known or key is None:
            self.unknown.append(token.raw)
        elif self.slot not in REGISTRY[key].slots:
            self.other.append(token.raw)
        elif (key.startswith(ITEM) and kind != "item") or (key.startswith(HSN) and kind != "hsn"):
            self.outside.append(token.raw)
        elif not REGISTRY[key].image:  # an image placeholder prints only as a source
            self.present.add(key)


def analyse(html: str, slot: str) -> Analysis:
    root = parse(html)
    sections = _sections(root)
    head = root.find("head")
    in_head = {id(n) for n in head.iter()} if head is not None else set()
    report = _Report(slot)
    for loc in _locations(root):
        if loc.owner is None or id(loc.owner) in in_head:
            continue
        if loc.where == "attr" and loc.name == "src" and loc.node.tag == "img":
            key = _image_key(loc.value)
            report.images.append(key or loc.value.removeprefix("asset:"))
            if key is not None:
                report.present.add(key)
            continue
        report.words.append(substitute(loc.value, lambda _t: " "))
        kind = _kind_of(loc, sections)
        for token in tokens(loc.value):
            report.token(token, kind)
    styles: list[str] = []
    pages: list[str] = []
    for node in root.iter():
        if node.tag == "style":
            styles.extend(t.raw for t in tokens(node.text or ""))
            pages.extend(_page_sizes(node.text or ""))
        if isinstance(node.tag, str):
            styles.extend(t.raw for t in tokens(node.get("style", "")))
    return Analysis(
        present=frozenset(report.present),
        unknown=tuple(dict.fromkeys(report.unknown)),
        other_slot=tuple(dict.fromkeys(report.other)),
        outside_rows=tuple(dict.fromkeys(report.outside)),
        in_styles=tuple(dict.fromkeys(styles)),
        item_rows=sum(1 for s in sections if s.kind == "item"),
        hsn_rows=sum(1 for s in sections if s.kind == "hsn"),
        images=tuple(dict.fromkeys(report.images)),
        page_size=pages[-1] if pages else None,
        missing=tuple(missing_requirements(slot, report.present)),
        wording=has_forbidden_wording(slot, " ".join(report.words)),
    )


def _page_sizes(css: str) -> list[str]:
    sizes: list[str] = []
    for rule in tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True):
        if rule.type == "at-rule" and rule.lower_at_keyword == "page" and rule.content:
            for decl in tinycss2.parse_blocks_contents(
                rule.content, skip_comments=True, skip_whitespace=True
            ):
                if decl.type == "declaration" and decl.lower_name == "size":
                    sizes.append(tinycss2.serialize(decl.value).strip())
    return sizes


# ------------------------------------------------------------------ fill

Lookup = Callable[[Token], str]


def _lookup(data: BillData, kind: str | None, row: dict[str, str] | None) -> Lookup:
    def value(token: Token) -> str:
        key = token.key
        if not token.known or key is None or REGISTRY[key].image:
            return ""
        if key.startswith(ITEM) or key.startswith(HSN):
            wanted = "item" if key.startswith(ITEM) else "hsn"
            text = (row or {}).get(key, "") if kind == wanted else ""
        else:
            text = data.fields.get(key, "")
        return format_value(text, token.fmt)

    return value


def _fill_loc(loc: _Loc, data: BillData, lookup: Lookup, images: list[Element]) -> None:
    if loc.where == "attr" and loc.name == "src" and loc.node.tag == "img":
        key = _image_key(loc.value)
        if key is not None:
            uri = data.fields.get(key, "")
            if uri:
                loc.node.set("src", uri)
            else:
                images.append(loc.node)  # nothing to show: the image goes
        return
    _set(loc, substitute(loc.value, lookup))


@dataclass
class _Filled:
    """What the repeating sections filled already: element texts and attributes (`nodes`) and
    the texts that follow nodes (`tails`)."""

    nodes: set[int] = field(default_factory=set)
    tails: set[int] = field(default_factory=set)


def _repeat(section: _Section, data: BillData, images: list[Element], filled: _Filled) -> None:
    """Put one filled copy of the section per row where the section was."""
    rows = data.items if section.kind == "item" else data.hsn
    parent, start = section.parent, section.start
    if start is not None:
        # A marker section: the text after the start marker, and after each node in the
        # section, belongs to the section.
        lead, start.tail = start.tail, None
        filled.tails.add(id(start))
        index = list(parent).index(start) + 1
    else:
        lead = None
        index = list(parent).index(section.nodes[0])
    last: Element | None = start
    for row in rows:
        lookup = _lookup(data, section.kind, dict(row))
        if lead:
            _append_text(parent, last, substitute(lead, lookup))
        for node in section.nodes:
            clone = copy.deepcopy(node)
            tail, clone.tail = clone.tail, None
            for loc in list(_locations(clone)):
                _fill_loc(loc, data, lookup, images)
            # A row's own tail is outside the row; a marker section's node's tail is inside.
            clone.tail = substitute(tail, lookup) if tail and start is not None else tail
            parent.insert(index, clone)
            index += 1
            last = clone
            ids = {id(n) for n in clone.iter()}
            filled.nodes |= ids
            filled.tails |= ids if start is not None else ids - {id(clone)}
    for node in section.nodes:
        if rows or start is not None:
            parent.remove(node)
        else:
            _remove(parent, node)


def fill(html: str, data: BillData, assets: Collection[str], *, mark: str | None = None) -> str:
    """The template filled with one document's values, cleaned again first so a file changed
    in storage is still safe. `mark` is laid across every page."""
    root = parse(html)
    _sanitize(root, assets)
    images: list[Element] = []
    filled = _Filled()
    for section in _sections(root):
        _repeat(section, data, images, filled)
    lookup = _lookup(data, None, None)
    for loc in list(_locations(root)):
        done = filled.tails if loc.where == "tail" else filled.nodes
        if id(loc.node) not in done:
            _fill_loc(loc, data, lookup, images)
    parents = _parents(root)
    for image in images:
        _remove(parents[id(image)], image)
    body = root.find("body")
    if mark and body is not None:
        overlay = Element("div", {"style": _MARK_STYLE})
        overlay.text = mark
        overlay.tail = body.text
        body.text = None
        body.insert(0, overlay)
    return serialize(root)
