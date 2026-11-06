"""Bill templates (Milestone 28): the HTML is cleaned with an allow-list, filled without ever being
evaluated, and analysed for the diagnostics. Hostile input throughout."""

from xml.etree.ElementTree import Comment, ProcessingInstruction

import pytest

from app.domain.bill_html import (
    MAX_DEPTH,
    MAX_ELEMENTS,
    _sanitize,
    analyse,
    clean,
    fill,
    parse,
    serialize,
)
from app.domain.bill_template import IMAGE_URIS, BillData, TemplateRuleError

ASSETS = frozenset({"stamp.png", "sign.jpg"})


def _body(html: str) -> str:
    out = clean(html, ASSETS).html
    return out.split("<body>", 1)[1].rsplit("</body>", 1)[0]


# ------------------------------------------------------------------ what a browser would run


def test_scripts_and_event_handlers_are_removed_not_refused():
    cleaned = clean(
        '<body onload="steal()"><script>alert(1)</script><p onclick="x()" class="a">Hi</p>'
        "<SCRIPT src=//evil.example/x.js></SCRIPT></body>",
        ASSETS,
    )
    assert "script" not in cleaned.html.lower() and "onload" not in cleaned.html
    assert "onclick" not in cleaned.html
    assert '<p class="a">Hi</p>' in cleaned.html
    assert cleaned.removed == (
        "<script> element (2)",
        "onload attribute on <body>",
        "onclick attribute on <p>",
    )


@pytest.mark.parametrize(
    "markup",
    [
        '<iframe src="https://evil.example"></iframe>',
        '<object data="file:///etc/passwd"></object>',
        '<embed src="x.swf">',
        '<base href="https://evil.example/">',
        '<link rel="stylesheet" href="https://evil.example/x.css">',
        '<link rel="attachment" href="file:///etc/passwd">',
        '<meta http-equiv="refresh" content="0;url=https://evil.example">',
        '<svg><script>alert(1)</script><image href="file:///etc/passwd"/></svg>',
        '<math><mi xlink:href="javascript:alert(1)">x</mi></math>',
        "<noscript><p>x</p></noscript>",
        '<input value="x"><button>b</button><textarea>t</textarea><select></select>',
        "<template><p>x</p></template>",
        '<video src="x.mp4"></video><audio src="x.mp3"></audio>',
    ],
)
def test_elements_that_run_or_fetch_are_dropped_with_their_content(markup):
    assert _body(f"<p>a</p>{markup}<p>b</p>") == "<p>a</p><p>b</p>"


def test_a_form_goes_but_what_it_held_stays():
    assert _body('<form action="https://evil.example"><p>Total</p></form>') == "<p>Total</p>"


def test_unknown_elements_are_unwrapped():
    assert _body("<blink>Hot <b>deal</b></blink><my-box>x</my-box>") == "Hot <b>deal</b>x"


def test_attributes_are_an_allow_list():
    out = _body(
        '<div align="right" style="width: 10mm" data-col="qty" srcdoc="<script>" rel="x" '
        'formaction="javascript:x" xmlns:foo="bar" bogus="1">x</div>'
    )
    assert out == '<div align="right" style="width: 10mm" data-col="qty">x</div>'
    assert _body('<p a"b="1" id="k">x</p>') == '<p id="k">x</p>'


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        " JaVaScRiPt:alert(1)",
        "java&#x09;script:alert(1)",
        "vbscript:msgbox",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "{{customer.name}}",
        "relative/page.html",
    ],
)
def test_a_link_keeps_only_a_safe_address(href):
    assert _body(f'<a href="{href}">x</a>') == "<a>x</a>"


@pytest.mark.parametrize(
    "href", ["https://duolink.app", "http://example.com", "mailto:a@b.in", "tel:+914412345", "#top"]
)
def test_safe_links_stay(href):
    assert _body(f'<a href="{href}">x</a>') == f'<a href="{href}">x</a>'


# ------------------------------------------------------------------ images


def test_images_come_only_from_the_companys_own_files():
    out = _body(
        '<img src="stamp.png" alt="Stamp"><img src="images/sign.jpg">'
        '<img src="asset:stamp.png"><img src="{{company.logo}}">'
        '<img src=" {{ company.secondaryLogo }} "><img src="{{einvoice.qr}}">'
    )
    assert out == (
        '<img src="asset:stamp.png" alt="Stamp"><img src="asset:sign.jpg">'
        '<img src="asset:stamp.png"><img src="{{company.logo}}">'
        '<img src="{{company.secondaryLogo}}"><img src="{{einvoice.qr}}">'
    )


@pytest.mark.parametrize(
    "src",
    [
        "https://evil.example/pixel.png",
        "//evil.example/pixel.png",
        "file:///etc/passwd",
        "/etc/passwd",
        "data:image/png;base64,AAAA",
        "missing.png",
        "../stamp.png",
        "asset:@logo",
        "{{customer.name}}",
        "",
    ],
)
def test_an_unsafe_image_loses_only_itself(src):
    cleaned = clean(f'<p>a<img src="{src}" srcset="x 2x">b</p>', ASSETS)
    assert "<p>ab</p>" in cleaned.html
    assert cleaned.removed[0].startswith("image")


# ------------------------------------------------------------------ styles


def test_a_clean_style_sheet_is_kept_exactly_as_written():
    css = (
        "@page { size: A4; margin: 5mm; @top-right { content: counter(page) } }\n"
        "  .items td { border: 1px solid #000; }  @media print { .x { color: red } }\n"
        "@font-face { font-family: X; src: local('Arial') }"
    )
    assert f"<style>{css}</style>" in clean(f"<style>{css}</style>", ASSETS).html


def test_style_sheets_lose_imports_outside_addresses_and_old_script_hooks():
    cleaned = clean(
        "<style>@import url(https://evil.example/x.css);"
        ".a { background: url(https://evil.example/p.png); color: red }"
        ".b { width: expression(alert(1)); behavior: url(x.htc); -moz-binding: url(x.xml) }"
        '.c { background-image: url("stamp.png") } .d { content: u\\72l(file:///etc/passwd) }'
        ".e { background: image-set('https://evil.example/a.png' 1x) }"
        "@document url(https://x) { .f { color: red } } .g { color: blue }</style>",
        ASSETS,
    )
    style = cleaned.html.split("<style>")[1].split("</style>")[0]
    assert "evil" not in style and "@import" not in style and "expression" not in style
    assert "behavior" not in style and "binding" not in style and "file:" not in style
    assert "@document" not in style
    assert "color:red" in style.replace(" ", "") and "color:blue" in style.replace(" ", "")
    assert 'url("asset:stamp.png")' in style
    assert cleaned.removed == (
        "@import rule in a style",
        "outside address in a style (3)",
        "script hook in a style (3)",
        "@document rule in a style",
    )


def test_nested_values_statements_and_broken_declarations():
    cleaned = clean(
        '<style>@charset "utf-8"; .a { background: linear-gradient(url(http://evil.example/x)) }'
        " .b { color } .c { margin: calc(1mm + 2mm) } @media print { .d { color: red } }</style>",
        ASSETS,
    )
    style = cleaned.html.split("<style>")[1].split("</style>")[0]
    assert '@charset "utf-8";' in style and "evil" not in style and "calc(1mm + 2mm)" in style
    assert "@media print" in style and ".d" in style
    assert cleaned.removed == ("outside address in a style",)


def test_a_processing_instruction_in_a_tree_is_removed_by_cleaning():
    root = parse("<p>a</p>")
    body = root.find("body")
    assert body is not None
    body.append(ProcessingInstruction("php", "echo 1"))
    assert _sanitize(root, ASSETS) == []
    assert len(list(body)) == 1


def test_style_attributes_are_cleaned_too():
    out = _body(
        '<div style="color: red; background: url(http://evil.example/x.png)">a</div>'
        "<div style=\"background: url('sign.jpg')\">b</div>"
        '<div style="width: 5mm">c</div>'
    )
    assert out == (
        '<div style="color: red">a</div>'
        '<div style="background: url(&quot;asset:sign.jpg&quot;)">b</div>'
        '<div style="width: 5mm">c</div>'
    )


def test_a_style_cannot_close_itself_early():
    out = clean('<style>.a::after { content: "x" }</style><p>ok</p>', ASSETS).html
    assert '<style>.a::after { content: "x" }</style>' in out
    root = parse("<style></style>")
    style = root.find(".//style")
    assert style is not None
    style.text = 'p { content: "</style><script>x</script>" }'
    assert "</style><script>" not in serialize(root)
    assert [e.tag for e in parse(serialize(root)).iter() if e.tag == "script"] == []


# ------------------------------------------------------------------ the document as a whole


def test_markup_is_kept_and_cleaning_settles_after_one_pass():
    html = (
        "<!DOCTYPE html><html lang=en><head><meta charset=utf-8><title>Bill {{invoice.number}}"
        "</title><style>td{padding:1mm}</style></head><body><!-- items:start -->"
        "<table class=items><tr><td class=d nowrap>{{item.description}}</td><td>&amp; &lt;"
        "</td></tr></table><!-- items:end --><br><hr><img src=stamp.png></body></html>"
    )
    once = clean(html, ASSETS)
    assert once.removed == ()
    assert once.html == (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Bill '
        "{{invoice.number}}</title><style>td{padding:1mm}</style></head><body>"
        '<!-- items:start --><table class="items"><tbody><tr><td class="d" nowrap="">'
        "{{item.description}}</td><td>&amp; &lt;</td></tr></tbody></table><!-- items:end -->"
        '<br><hr><img src="asset:stamp.png"></body></html>'
    )
    twice = clean(once.html, ASSETS)
    assert twice.html == once.html and twice.removed == ()
    hostile = clean("<p onclick=x><script>y</script><img src=http://e/x>z", ASSETS)
    assert clean(hostile.html, ASSETS).html == hostile.html


@pytest.mark.parametrize(
    "text", [" x --> <script>y</script> ", "a --!><script>y</script>", "><script>y</script>"]
)
def test_odd_comments_cannot_break_out(text):
    root = parse("<p>a</p>")
    body = root.find("body")
    assert body is not None
    body.append(Comment(text))
    again = parse(serialize(root))
    assert [e.tag for e in again.iter() if e.tag == "script"] == []


def test_a_processing_instruction_is_dropped():
    root = parse("<p>a</p>")
    body = root.find("body")
    assert body is not None
    body.append(ProcessingInstruction("php", "echo 1"))
    assert "php" not in serialize(root)


def test_too_deep_or_too_big_is_refused():
    with pytest.raises(TemplateRuleError) as err:
        parse("<div>" * (MAX_DEPTH + 5))
    assert err.value.code == "TEMPLATE_TOO_DEEP"
    with pytest.raises(TemplateRuleError) as err:
        parse("<br>" * (MAX_ELEMENTS + 1))
    assert err.value.code == "TEMPLATE_TOO_BIG"


# ------------------------------------------------------------------ filling

LINES = [
    {"item.lineNo": "1", "item.description": "TMT <script>alert(1)</script>", "item.qty": "2"},
    {"item.lineNo": "2", "item.description": "Wire & nails", "item.qty": "5"},
]
HSN_ROWS = [
    {"hsn.hsn": "7214", "hsn.taxable": "100.00"},
    {"hsn.hsn": "7217", "hsn.taxable": "5.00"},
]
FIELDS = {
    "invoice.number": "MS/1",
    "customer.name": "{{company.gstin}} <b>Kumar</b>",
    "company.gstin": "33ABCDE1234F1Z5",
    "company.logo": IMAGE_URIS["company.logo"],
    "company.secondaryLogo": "",
    "totals.grandTotal": "1,05,000.00",
}
DATA = BillData(fields=FIELDS, items=LINES, hsn=HSN_ROWS)


def _filled(html: str, **kw: object) -> str:
    out = fill(html, DATA, ASSETS, **kw)  # type: ignore[arg-type]
    return out.split("<body>", 1)[1].rsplit("</body>", 1)[0]


def test_the_item_row_is_the_templates_own_row_repeated():
    out = _filled(
        '<table><tr class="head"><th>No</th></tr>'
        '<tr class="item-row" style="height: 5mm"><td class="c">{{item.lineNo}}</td>'
        '<td title="{{item.description}}">{{item.description}} x {{item.qty}}</td></tr>'
        "<tr><td>{{totals.grandTotal|symbol}}</td></tr></table>"
    )
    assert out == (
        '<table><tbody><tr class="head"><th>No</th></tr>'
        '<tr class="item-row" style="height: 5mm"><td class="c">1</td>'
        '<td title="TMT &lt;script&gt;alert(1)&lt;/script&gt;">TMT &lt;script&gt;alert(1)'
        "&lt;/script&gt; x 2</td></tr>"
        '<tr class="item-row" style="height: 5mm"><td class="c">2</td>'
        '<td title="Wire &amp; nails">Wire &amp; nails x 5</td></tr>'
        "<tr><td>₹ 1,05,000.00</td></tr></tbody></table>"
    )


def test_hsn_rows_repeat_and_markers_repeat_a_section():
    out = _filled(
        "<table><tr><td>{{hsn.hsn}}</td><td>{{hsn.taxable}}</td></tr></table>"
        "<div><!-- items:start -->L{{item.lineNo}}:<span>{{item.qty}}</span>;<!-- items:end -->"
        "</div><div><!-- hsn:start --><i>{{hsn.hsn}}</i><!-- hsn:end --></div>"
    )
    assert out == (
        "<table><tbody><tr><td>7214</td><td>100.00</td></tr><tr><td>7217</td><td>5.00</td></tr>"
        "</tbody></table><div><!-- items:start -->L1:<span>2</span>;L2:<span>5</span>;"
        "<!-- items:end --></div><div><!-- hsn:start --><i>7214</i><i>7217</i>"
        "<!-- hsn:end --></div>"
    )


def test_text_between_elements_is_filled_and_a_row_inside_a_row_repeats_with_it():
    out = _filled(
        "<p>a</p>Bill {{invoice.number}} for {{customer.name|upper}}<br>"
        "<table><tr><td>{{item.lineNo}}<table><tr><td>{{item.qty}}</td></tr></table></td></tr>"
        "</table>"
    )
    assert out.startswith("<p>a</p>Bill MS/1 for {{COMPANY.GSTIN}} &lt;B&gt;KUMAR&lt;/B&gt;<br>")
    assert out.count("<tr>") == 4 and "<td>5</td>" in out


def test_a_marker_section_with_no_lines_prints_nothing():
    empty = BillData(fields={}, items=[], hsn=[])
    out = fill(
        "<div><!-- items:start -->L{{item.lineNo}}<b>x</b><!-- items:end --></div>", empty, ASSETS
    )
    assert "<div><!-- items:start --><!-- items:end --></div>" in out
    out = fill("<table><tr><td>{{item.qty}}</td></tr></table>", empty, ASSETS)
    assert "<tbody></tbody>" in out


def test_a_marker_without_its_end_is_ignored():
    out = _filled("<div><!-- items:start --><b>{{item.qty}}</b></div>")
    assert out == "<div><!-- items:start --><b></b></div>"


def test_values_are_escaped_and_never_read_again():
    out = _filled("<p>{{customer.name}}</p><p>{{invoice.number|upper}}</p>")
    assert out == "<p>{{company.gstin}} &lt;b&gt;Kumar&lt;/b&gt;</p><p>MS/1</p>"


@pytest.mark.parametrize(
    "hostile",
    [
        "{{config.__class__}}",
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{7*7}}",
        "{{ cycler.__init__.__globals__.os.popen('id').read() }}",
        "{% for i in range(99999999) %}x{% endfor %}",
        "{# hidden #}",
        "{{invoice.number|attr('__class__')}}",
        "{{item.qty}}",  # outside any repeating row
    ],
)
def test_no_template_can_execute_code(hostile):
    out = _filled(f"<p>[{hostile}]</p>")
    # Only the literal text between the statements is left; nothing ran or looped.
    assert out == ("<p>[x]</p>" if "for i" in hostile else "<p>[]</p>")


def test_styles_are_never_filled():
    out = fill(
        '<style>.x::after { content: "{{customer.name}}" }</style><p style="x:{{a}}">a</p>',
        DATA,
        ASSETS,
    )
    assert '"{{customer.name}}"' in out and 'style="x:{{a}}"' in out


def test_image_placeholders_become_the_companys_own_addresses():
    out = _filled(
        '<img src="{{company.logo}}" alt="Logo"><img src="{{company.secondaryLogo}}">'
        "<p>{{company.logo}}</p>"
    )
    assert out == '<img src="asset:@logo" alt="Logo"><p></p>'


def test_a_mark_can_be_laid_over_the_page():
    out = _filled("<p>x</p>", mark="SAMPLE")
    assert out.startswith('<div style="position: fixed;') and ">SAMPLE</div><p>x</p>" in out


def test_fill_cleans_again_so_a_tampered_file_is_still_safe():
    out = fill('<p onclick="x()">a</p><script>y</script><img src="http://e/p.png">', DATA, ASSETS)
    assert "onclick" not in out and "script" not in out and "http" not in out


# ------------------------------------------------------------------ diagnostics


INVOICE = (
    "<html><head><title>{{invoice.unknownInHead}}</title>"
    "<style>@page { size: A4 landscape } p::after { content: '{{customer.name}}' }</style>"
    '</head><body><h1>{{invoice.title}} {{invoice.number}}</h1><img src="{{company.logo}}">'
    '<img src="stamp.png"><p style="color: {{invoice.date}}">{{company.name}} '
    "{{config.__class__}} {{item.qty}} {{note.against}}</p>"
    "<table><tr><td>{{item.description}}</td><td>{{hsn.hsn}}</td></tr>"
    "<tr><td>{{hsn.taxable}}</td></tr></table>"
    "<div><!-- items:start --><b>{{item.hsn}}</b><!-- items:end --></div>"
    "<p>Tax Invoice</p></body></html>"
)


def test_the_diagnostics_list_what_will_not_print():
    report = analyse(clean(INVOICE, ASSETS).html, "tax_invoice")
    assert report.unknown == ("{{config.__class__}}",)
    assert report.other_slot == ("{{note.against}}",)
    assert report.outside_rows == ("{{item.qty}}", "{{hsn.hsn}}")
    assert report.in_styles == ("{{customer.name}}", "{{invoice.date}}")
    assert report.item_rows == 2 and report.hsn_rows == 1
    assert report.images == ("company.logo", "stamp.png")
    assert report.page_size == "A4 landscape"
    assert report.present == frozenset(
        {
            "invoice.title",
            "invoice.number",
            "company.logo",
            "company.name",
            "item.description",
            "item.hsn",
            "hsn.taxable",
        }
    )
    assert "Seller's GSTIN" in report.missing and "Document name" not in report.missing
    assert report.wording is False
    assert analyse(clean(INVOICE, ASSETS).html, "proforma").wording is True


def test_no_page_size_means_the_default():
    report = analyse("<p>{{invoice.number}}</p>", "quotation")
    assert report.page_size is None and report.item_rows == 0
    assert report.images == () and report.present == frozenset({"invoice.number"})
