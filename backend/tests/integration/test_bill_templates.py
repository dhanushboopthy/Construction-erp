"""M28: bill templates per company (ADR 0013).

Admin calls run at admin.localhost as the app's database role. The default company "main" issues
the bills; "acme" is the other company. Uploaded HTML is data: the tests feed it hostile input and
inspect the HTML the renderer is given, because that is what a browser-like engine would run.
"""

import re

import pytest
from sqlalchemy import text
from weasyprint import HTML

from app.core.tenancy import set_tenant
from app.domain.bill_template import MAX_HTML_BYTES, REGISTRY, SLOTS
from app.services import bill_render
from app.services import invoice_pdf as invoice_pdf_service
from tests.bill_samples import design
from tests.integration.test_company_profile import (  # noqa: F401 - the fixtures
    acme,
    boss,
    helper,
    onboard,
    owner_of,
)
from tests.integration.test_returns import buy
from tests.integration.test_sales import body, line, post, world  # noqa: F401 - the fixture
from tests.integration.test_tenant import png

pytestmark = pytest.mark.integration

SLOT = "tax_invoice"


@pytest.fixture
def seen(monkeypatch):
    """The HTML every renderer is handed, with the real renderer still drawing the PDF."""
    html: list[str] = []

    class Capture:
        def __init__(self, string: str, **kwargs):
            html.append(string)
            self._real = HTML(string=string, **kwargs)

        def write_pdf(self) -> bytes:
            return self._real.write_pdf()

    monkeypatch.setattr(bill_render, "HTML", Capture)
    monkeypatch.setattr(invoice_pdf_service, "HTML", Capture)
    return html


@pytest.fixture
def main_id(client, boss):
    items = client.get("/api/v1/admin/tenants", headers=boss).json()["items"]
    return next(t["id"] for t in items if t["slug"] == "main")


def url(tenant, tail=""):
    return f"/api/v1/admin/tenants/{tenant}/bill-templates{tail}"


def upload(client, who, tenant, html, slot=SLOT, name="Our bill", images=()):
    files = [("html", ("bill.html", html.encode(), "text/html"))]
    files += [("images", (n, data, "image/png")) for n, data in images]
    return client.post(url(tenant), headers=who, data={"slot": slot, "name": name}, files=files)


def stored(client, who, tenant, html, slot=SLOT, **kw):
    made = upload(client, who, tenant, html, slot=slot, **kw)
    assert made.status_code == 201, made.text
    return made.json()


def activate(client, who, tenant, template):
    done = client.post(url(tenant, f"/{template['id']}/activate"), headers=who)
    assert done.status_code == 200, done.text
    return done.json()


def flat(html: str) -> str:
    return re.sub(r"\s+", " ", html)


def pin_of(seeded, table, row_id, tenant=1):
    set_tenant(seeded, tenant)
    return seeded.execute(
        text(f"SELECT bill_template_id FROM {table} WHERE id = :i"),  # noqa: S608 - a test table name
        {"i": row_id},
    ).scalar_one()


def issue(client, world):
    made = post(
        client, world, body(world, [line(world, "tmt", "2.5", "ton"), line(world, "cement", "7")])
    )
    assert made.status_code == 201, made.text
    return made.json()


def bill_html(client, world, bill, seen):
    before = len(seen)
    pdf = client.get(f"/api/v1/invoices/{bill['id']}/pdf", headers=world["owner"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert len(seen) == before + 1
    return flat(seen[-1])


# ------------------------------------------------------------------ the registry


def test_the_field_registry_lists_every_placeholder_and_what_each_document_requires(
    client, boss, main_id
):
    got = client.get(url(main_id, "/field-registry"), headers=boss)
    assert got.status_code == 200, got.text
    registry = got.json()
    assert {f["key"] for f in registry["fields"]} == set(REGISTRY)
    one = next(f for f in registry["fields"] if f["key"] == "invoice.number")
    assert one["description"] and one["sample"] and one["slots"] == list(SLOTS)
    assert registry["slots"] == list(SLOTS)
    assert "Seller's GSTIN" in registry["required"]["tax_invoice"]
    assert registry["limits"]["html_bytes"] == 500 * 1024
    assert client.get(url(99999, "/field-registry"), headers=boss).status_code == 404


# ------------------------------------------------------------------ cleaning and hostile input


def test_scripts_and_event_handlers_are_cleaned_and_the_preview_runs_none(
    client, boss, main_id, seen
):
    html = design(
        SLOT,
        head='<script>alert("head")</script><meta http-equiv="refresh" content="0;url=http://e.in">'
        '<link rel="stylesheet" href="https://evil.example/x.css">'
        "<style>@import url(https://evil.example/y.css); p { background: url(http://e.in/p.png) }"
        "</style>",
        body='<p onclick="steal()">hi</p><iframe src="http://e.in"></iframe><object data="x">'
        '</object><form action="http://e.in"><b>kept</b></form>'
        '<a href="javascript:alert(1)">x</a><img src="http://e.in/pixel.png">',
    ).replace("<body>", '<body onload="steal()">')
    made = stored(client, boss, main_id, html)
    assert made["version"] == 1 and made["is_active"] is False
    removed = " | ".join(made["removed"])
    for gone in ("<script>", "onload", "onclick", "<iframe>", "<object>", "<link>", "@import"):
        assert gone in removed, (gone, removed)

    preview = client.post(url(main_id, f"/{made['id']}/preview"), headers=boss)
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF")
    drawn = seen[-1].lower()
    for bad in (
        "<script",
        "onload",
        "onclick",
        "<iframe",
        "<object",
        "<form",
        "javascript:",
        "http",
    ):
        assert bad not in drawn, bad
    assert "<b>kept</b>" in drawn and "sample" in drawn  # the content stays, marked as a sample


def test_a_placeholder_is_never_evaluated(client, boss, main_id, seen):
    hostile = (
        "<p>[{{config.__class__}}][{{7*7}}][{{ ''.__class__.__mro__ }}][{% for i in x %}]"
        "[{{invoice.number|attr('x')}}][{{cycler.__init__.__globals__}}]</p>"
    )
    made = stored(client, boss, main_id, design(SLOT, body=hostile))
    report = client.get(url(main_id, f"/{made['id']}/diagnostics"), headers=boss).json()
    assert "{{config.__class__}}" in report["unknown"] and "{{7*7}}" in report["unknown"]
    assert "{% for i in x %}" in report["unknown"]
    client.post(url(main_id, f"/{made['id']}/preview"), headers=boss)
    printed = flat(seen[-1])
    assert "<p>[][][][][][]</p>" in printed  # six placeholders, nothing printed for any


def test_the_renderer_serves_only_the_designs_own_images(client, boss, main_id):
    fetcher = bill_render.AssetFetcher({"stamp.png": (png(8), "image/png")})
    assert fetcher.fetch("asset:stamp.png").read() == png(8)
    for bad in (
        "file:///etc/passwd",
        "http://127.0.0.1:8000/api/v1/health",
        "https://evil.example/p.png",
        "asset:other.png",
        "asset:@logo",
        "data:text/plain,x",
    ):
        with pytest.raises(ValueError, match=r"Not one of the design's images|disallowed"):
            fetcher.fetch(bad)
    html = design(
        SLOT,
        body='<img src="file:///etc/hostname"><img src="stamp.png"><img src="nope.png">'
        '<div style="background: url(file:///etc/hostname)">x</div>',
    )
    made = stored(client, boss, main_id, html, images=[("stamp.png", png(8))])
    assert any("nope.png" in r for r in made["removed"])
    assert any("file:///etc/hostname" in r for r in made["removed"])
    diag = client.get(url(main_id, f"/{made['id']}/diagnostics"), headers=boss).json()
    assert diag["missing_images"] == ["nope.png"] and diag["images"].count("stamp.png") == 1
    assert client.post(url(main_id, f"/{made['id']}/preview"), headers=boss).status_code == 200


# ------------------------------------------------------------------ the GST fields stay


@pytest.mark.parametrize(
    ("slot", "dropped", "label"),
    [
        ("tax_invoice", ("company.gstin",), "Seller's GSTIN"),
        ("tax_invoice", ("customer.gstin",), "Buyer's GSTIN"),
        ("tax_invoice", ("item.hsn",), "HSN code of each item"),
        ("tax_invoice", ("invoice.placeOfSupply",), "Place of supply"),
        ("tax_invoice", ("totals.grandTotal",), "Invoice total"),
        ("tax_invoice", ("einvoice.irn", "einvoice.qr"), "e-Invoice IRN and QR code"),
        ("tax_invoice", ("invoice.number",), "Document number"),
        ("credit_note", ("note.against",), "Original document number and date"),
        ("debit_note", ("company.gstin",), "Seller's GSTIN"),
        ("proforma", ("invoice.declaration",), "Not-a-tax-invoice wording"),
    ],
)
def test_a_design_that_drops_a_required_field_is_refused(
    client, boss, main_id, slot, dropped, label
):
    refused = upload(client, boss, main_id, design(slot, drop=dropped), slot=slot)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "TEMPLATE_MISSING_FIELDS"
    assert label in refused.json()["message"]
    assert client.get(url(main_id), headers=boss).json()["templates"] == []  # nothing stored


def test_tax_may_be_shown_per_item_or_in_the_totals_but_not_left_out(client, boss, main_id):
    per_line = tuple(
        k for k in REGISTRY if k.startswith(("item.cgst", "item.sgst", "item.igst", "hsn.cgst"))
    ) + tuple(k for k in REGISTRY if k.startswith(("hsn.sgst", "hsn.igst")))
    totals = ("totals.cgst", "totals.sgst", "totals.igst")
    # Tax shown only in the totals (with the rate on each item) is a full tax invoice.
    ok = upload(client, boss, main_id, design(SLOT, drop=per_line))
    assert ok.status_code == 201, ok.text
    # No amount of CGST, SGST or IGST anywhere is not.
    refused = upload(client, boss, main_id, design(SLOT, drop=per_line + totals))
    assert refused.status_code == 409
    assert refused.json()["missing_fields"] == ["Amount of CGST, SGST and IGST"]


def test_a_proforma_or_quotation_may_not_call_itself_a_tax_invoice(client, boss, main_id):
    for slot in ("proforma", "quotation"):
        refused = upload(
            client, boss, main_id, design(slot, body="<h1>TAX  INVOICE</h1>"), slot=slot
        )
        assert refused.status_code == 409 and refused.json()["code"] == "TEMPLATE_WORDING"
        fine = upload(
            client, boss, main_id, design(slot, body="<p>This is not a tax invoice.</p>"), slot=slot
        )
        assert fine.status_code == 201, fine.text


def test_unreadable_oversized_or_unknown_uploads_are_refused(client, boss, main_id):
    def code(html: bytes, slot=SLOT, images=()):
        files = [("html", ("b.html", html, "text/html"))]
        files += [("images", (n, d, "image/png")) for n, d in images]
        r = client.post(url(main_id), headers=boss, data={"slot": slot, "name": "x"}, files=files)
        assert r.status_code == 409, r.text
        return r.json()["code"]

    assert code(b"") == "TEMPLATE_EMPTY"
    assert code(b"\xff\xfe<\x00p\x00>") == "TEMPLATE_NOT_UTF8"
    assert code(b"x" * (MAX_HTML_BYTES + 1)) == "TEMPLATE_TOO_LARGE"
    assert code(design(SLOT).encode(), slot="invoice") == "SLOT_UNKNOWN"
    assert code(design(SLOT).encode(), images=[("a.png", b"not an image")]) == "ASSET_TYPE"
    assert code(design(SLOT).encode(), images=[("a.png", png(8)), ("A.png", png(8))]) == (
        "ASSET_DUPLICATE"
    )
    assert code(design(SLOT).encode(), images=[("../a.png", png(8))]) == "ASSET_NAME"
    assert code(("<div>" * 400).encode()) == "TEMPLATE_TOO_DEEP"
    blank = client.post(
        url(main_id),
        headers=boss,
        data={"slot": SLOT, "name": "  "},
        files=[("html", ("b.html", design(SLOT).encode(), "text/html"))],
    )
    assert blank.status_code == 409 and blank.json()["code"] == "TEMPLATE_NAME"


# ------------------------------------------------------------------ versions and pinning


def test_a_bill_reprints_on_the_design_it_was_issued_with(
    client, boss, world, main_id, seen, seeded
):
    first = stored(client, boss, main_id, design(SLOT, marker="DESIGN-ONE"), name="Plain")
    assert activate(client, boss, main_id, first)["is_active"] is True
    bill_one = issue(client, world)
    one_before = bill_html(client, world, bill_one, seen)
    assert "DESIGN-ONE" in one_before
    # The same figures the built-in layout prints, in the design's own HTML.
    assert bill_one["number"] in one_before and "1,68,609.00" in one_before
    assert pin_of(seeded, "sales_invoice", bill_one["id"]) == first["id"]

    second = stored(client, boss, main_id, design(SLOT, marker="DESIGN-TWO"), name="Fancy")
    assert second["version"] == 2
    activate(client, boss, main_id, second)
    listed = {t["version"]: t for t in client.get(url(main_id), headers=boss).json()["templates"]}
    assert listed[1]["is_active"] is False and listed[2]["is_active"] is True
    assert listed[1]["used"] is True and listed[2]["used"] is False

    one_after = bill_html(client, world, bill_one, seen)
    assert one_after == one_before  # identical after v2 is active
    bill_two = issue(client, world)
    two = bill_html(client, world, bill_two, seen)
    assert "DESIGN-TWO" in two and "DESIGN-ONE" not in two
    assert pin_of(seeded, "sales_invoice", bill_two["id"]) == second["id"]


def test_deleting_a_used_design_is_refused_and_deactivating_falls_back_to_the_built_in_layout(
    client, boss, world, main_id, seen, seeded
):
    made = stored(client, boss, main_id, design(SLOT, marker="DESIGN-ONE"))
    activate(client, boss, main_id, made)
    old = issue(client, world)

    # Used: never deleted, active or not.
    used = client.delete(url(main_id, f"/{made['id']}"), headers=boss)
    assert used.status_code == 409 and used.json()["code"] == "TEMPLATE_IN_USE"
    off = client.post(url(main_id, f"/{made['id']}/deactivate"), headers=boss)
    assert off.status_code == 200 and off.json()["is_active"] is False
    refused = client.delete(url(main_id, f"/{made['id']}"), headers=boss)
    assert refused.status_code == 409 and refused.json()["code"] == "TEMPLATE_IN_USE"

    fresh = issue(client, world)
    assert pin_of(seeded, "sales_invoice", fresh["id"]) is None
    built_in = bill_html(client, world, fresh, seen)
    assert 'class="page"' in built_in and "DESIGN-ONE" not in built_in
    assert "DESIGN-ONE" in bill_html(client, world, old, seen)  # the old bill keeps its design


def test_an_unused_design_can_be_deleted_with_its_images(client, boss, main_id, seeded):
    made = stored(client, boss, main_id, design(SLOT), images=[("stamp.png", png(8))])
    assert made["images"] == ["stamp.png"] and made["used"] is False
    activate(client, boss, main_id, made)
    active = client.delete(url(main_id, f"/{made['id']}"), headers=boss)
    assert active.status_code == 409 and active.json()["code"] == "TEMPLATE_ACTIVE"
    client.post(url(main_id, f"/{made['id']}/deactivate"), headers=boss)
    assert client.delete(url(main_id, f"/{made['id']}"), headers=boss).status_code == 204
    assert client.get(url(main_id), headers=boss).json()["templates"] == []
    assert client.get(url(main_id, f"/{made['id']}"), headers=boss).status_code == 404
    set_tenant(seeded, 1)
    assert seeded.execute(text("SELECT count(*) FROM bill_template_asset")).scalar_one() == 0


def test_activating_stands_down_only_the_slots_previous_design(client, boss, main_id):
    tax = stored(client, boss, main_id, design(SLOT))
    other = stored(client, boss, main_id, design("credit_note"), slot="credit_note")
    again = stored(client, boss, main_id, design(SLOT))
    for made in (tax, other, again):
        activate(client, boss, main_id, made)
    listed = client.get(url(main_id), headers=boss).json()["templates"]
    assert {t["id"]: t["is_active"] for t in listed} == {
        tax["id"]: False,
        other["id"]: True,
        again["id"]: True,
    }
    # Versions run per slot: the second tax invoice design is version 2, the credit note's is 1.
    assert {t["id"]: t["version"] for t in listed} == {
        tax["id"]: 1,
        other["id"]: 1,
        again["id"]: 2,
    }


def test_credit_notes_debit_notes_and_quotations_pin_their_own_slot(
    client, boss, world, main_id, seen, seeded
):
    owner = world["owner"]
    designs = {
        slot: activate(
            client,
            boss,
            main_id,
            stored(client, boss, main_id, design(slot, marker=f"M-{slot}"), slot=slot),
        )
        for slot in ("credit_note", "debit_note", "proforma", "quotation")
    }
    quote = client.post(
        "/api/v1/quotes",
        headers=owner,
        json=body(world, [line(world, "tmt", "1", "ton")]) | {"kind": "proforma"},
    ).json()
    assert pin_of(seeded, "sales_quote", quote["id"]) == designs["proforma"]["id"]
    assert client.get(f"/api/v1/quotes/{quote['id']}/pdf", headers=owner).status_code == 200
    assert "M-proforma" in seen[-1]
    quotation = client.post(
        "/api/v1/quotes",
        headers=owner,
        json=body(world, [line(world, "tmt", "1", "ton")]) | {"kind": "quotation"},
    ).json()
    assert pin_of(seeded, "sales_quote", quotation["id"]) == designs["quotation"]["id"]

    bill = issue(client, world)
    cancelled = client.post(
        f"/api/v1/invoices/{bill['id']}/cancel", headers=owner, json={"reason": "Wrong party"}
    )
    assert cancelled.status_code == 201, cancelled.text
    note = cancelled.json()
    assert pin_of(seeded, "credit_note", note["id"]) == designs["credit_note"]["id"]
    assert client.get(f"/api/v1/credit-notes/{note['id']}/pdf", headers=owner).status_code == 200
    printed = flat(seen[-1])
    assert "M-credit_note" in printed and note["number"] in printed and bill["number"] in printed

    purchase = buy(client, world)
    debit = client.post(
        "/api/v1/debit-notes",
        headers=owner,
        json={
            "purchase_id": purchase["id"],
            "reason": "Rusted bars",
            "lines": [{"line_id": purchase["lines"][0]["id"], "quantity": "2"}],
        },
    ).json()
    assert pin_of(seeded, "debit_note", debit["id"]) == designs["debit_note"]["id"]
    assert client.get(f"/api/v1/debit-notes/{debit['id']}/pdf", headers=owner).status_code == 200
    assert "M-debit_note" in seen[-1] and "1,29,800.00" in seen[-1]


# ------------------------------------------------------------------ one company's design


def test_company_a_design_is_never_used_for_company_b(
    client, boss, world, main_id, acme, seen, seeded
):
    theirs = stored(client, boss, acme["id"], design(SLOT, marker="ACME-ONLY"))
    activate(client, boss, acme["id"], theirs)
    listed = client.get(url(main_id), headers=boss).json()
    assert listed["templates"] == []  # main's own list does not show acme's design

    bill = issue(client, world)  # a bill of company main
    assert pin_of(seeded, "sales_invoice", bill["id"]) is None
    assert "ACME-ONLY" not in bill_html(client, world, bill, seen)

    # Row-level security: main's session cannot even see the row, and the loader refuses it.
    set_tenant(seeded, 1)
    assert seeded.execute(text("SELECT count(*) FROM bill_template")).scalar_one() == 0
    assert bill_render.load(seeded, theirs["id"]) is None
    # A design of main used by main still works while acme's stays acme's.
    own = stored(client, boss, main_id, design(SLOT, marker="MAIN-ONLY"))
    activate(client, boss, main_id, own)
    mine = issue(client, world)
    assert "MAIN-ONLY" in bill_html(client, world, mine, seen)
    other = client.get(url(acme["id"]), headers=boss).json()["templates"]
    assert [t["id"] for t in other] == [theirs["id"]] and other[0]["is_active"] is True


def test_the_database_allows_one_active_design_per_slot(client, boss, main_id, seeded):
    first = stored(client, boss, main_id, design(SLOT))
    second = stored(client, boss, main_id, design(SLOT))
    activate(client, boss, main_id, first)
    set_tenant(seeded, 1)
    with pytest.raises(Exception, match="uq_bill_template_active_slot"):
        seeded.execute(
            text("UPDATE bill_template SET is_active = true WHERE id = :i"), {"i": second["id"]}
        )
    seeded.rollback()


# ------------------------------------------------------------------ the second logo


def test_the_second_logo_follows_unused_designs_and_never_changes_a_used_one(
    client, boss, world, main_id, seen, seeded
):
    assert client.get(url(main_id), headers=boss).json()["secondary_logo"] is None
    bad = client.put(
        url(main_id, "/secondary-logo"),
        headers=boss,
        files={"file": ("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")},
    )
    assert bad.status_code == 409 and bad.json()["code"] == "ASSET_TYPE"

    def put(data):
        done = client.put(
            url(main_id, "/secondary-logo"),
            headers=boss,
            files={"file": ("logo.png", data, "image/png")},
        )
        assert done.status_code == 200, done.text
        return done.json()["secondary_logo"]["sha256"]

    logo_a = put(png(16))
    one = stored(client, boss, main_id, design(SLOT, marker="ONE"))
    activate(client, boss, main_id, one)
    bill = issue(client, world)
    before = bill_html(client, world, bill, seen)
    assert 'src="asset:@secondary-logo"' in before

    two = stored(client, boss, main_id, design(SLOT, marker="TWO"))
    logo_b = put(png(24, 12))
    assert logo_a != logo_b

    def sha(template):
        set_tenant(seeded, 1)
        return seeded.execute(
            text("SELECT secondary_logo_sha256 FROM bill_template WHERE id = :i"),
            {"i": template["id"]},
        ).scalar_one()

    assert sha(one) == logo_a  # used by a bill: keeps the logo it was issued with
    assert sha(two) == logo_b  # not used yet: follows the company's logo
    assert bill_html(client, world, bill, seen) == before

    removed = client.delete(url(main_id, "/secondary-logo"), headers=boss)
    assert removed.status_code == 200 and removed.json()["secondary_logo"] is None
    assert sha(one) == logo_a and sha(two) is None
    reprint = client.get(f"/api/v1/invoices/{bill['id']}/pdf", headers=world["owner"])
    assert reprint.status_code == 200


def test_a_logo_placeholder_with_no_logo_prints_no_image(client, boss, main_id, seen):
    made = stored(client, boss, main_id, design(SLOT))
    client.post(url(main_id, f"/{made['id']}/preview"), headers=boss)
    assert 'src="asset:@secondary-logo"' in seen[-1]  # a sample shows where it will sit
    activate(client, boss, main_id, made)


# ------------------------------------------------------------------ diagnostics


def test_diagnostics_list_what_will_not_print(client, boss, main_id):
    html = design(
        SLOT,
        head='<style>p::after { content: "{{customer.name}}" }</style>',
        body="<p>{{invoice.nope}} {{item.qty}} {{note.against}}</p>",
    ).replace("<style>@page { size: A4; margin: 8mm }", "<style>")
    made = stored(client, boss, main_id, html, images=[("unused.png", png(8))])
    report = client.get(url(main_id, f"/{made['id']}/diagnostics"), headers=boss).json()
    assert report["unknown"] == ["{{invoice.nope}}"]
    assert report["other_slot"] == ["{{note.against}}"]
    assert report["outside_rows"] == ["{{item.qty}}"]
    assert report["in_styles"] == ["{{customer.name}}"]
    assert report["item_rows"] == 1 and report["hsn_rows"] == 1
    assert report["unused_images"] == ["unused.png"] and report["page_size"] is None
    assert report["missing_fields"] == []
    assert any("page size" in w for w in report["warnings"])


# ------------------------------------------------------------------ roles and audit


def test_support_reads_and_previews_but_cannot_change_a_design(client, boss, helper, main_id):
    made = stored(client, boss, main_id, design(SLOT))
    base = url(main_id)
    assert client.get(base, headers=helper).status_code == 200
    assert client.get(url(main_id, "/field-registry"), headers=helper).status_code == 200
    assert client.get(f"{base}/{made['id']}", headers=helper).status_code == 200
    assert client.get(f"{base}/{made['id']}/diagnostics", headers=helper).status_code == 200
    assert client.post(f"{base}/{made['id']}/preview", headers=helper).status_code == 200
    html = ("html", ("b.html", design(SLOT).encode(), "text/html"))
    for call in (
        lambda: client.post(base, headers=helper, data={"slot": SLOT, "name": "x"}, files=[html]),
        lambda: client.post(f"{base}/{made['id']}/activate", headers=helper),
        lambda: client.post(f"{base}/{made['id']}/deactivate", headers=helper),
        lambda: client.delete(f"{base}/{made['id']}", headers=helper),
        lambda: client.put(
            f"{base}/secondary-logo", headers=helper, files={"file": ("a.png", png(8))}
        ),
        lambda: client.delete(f"{base}/secondary-logo", headers=helper),
    ):
        refused = call()
        assert refused.status_code == 403 and refused.json()["code"] == "PERMISSION_DENIED"


def test_every_change_is_audited_without_the_design_itself(client, boss, main_id, seeded):
    made = stored(client, boss, main_id, design(SLOT, marker="SECRET-LAYOUT"))
    activate(client, boss, main_id, made)
    client.post(url(main_id, f"/{made['id']}/deactivate"), headers=boss)
    client.put(
        url(main_id, "/secondary-logo"),
        headers=boss,
        files={"file": ("l.png", png(8), "image/png")},
    )
    client.delete(url(main_id, "/secondary-logo"), headers=boss)
    gone = stored(client, boss, main_id, design(SLOT))
    client.delete(url(main_id, f"/{gone['id']}"), headers=boss)
    rows = seeded.execute(
        text(
            "SELECT action, details::text FROM platform_audit_log "
            "WHERE action LIKE 'bill_template_%' OR action LIKE 'secondary_logo_%' ORDER BY id"
        )
    ).all()
    assert [r[0] for r in rows] == [
        "bill_template_upload",
        "bill_template_activate",
        "bill_template_deactivate",
        "secondary_logo_set",
        "secondary_logo_remove",
        "bill_template_upload",
        "bill_template_delete",
    ]
    assert "SECRET-LAYOUT" not in " ".join(r[1] for r in rows)
