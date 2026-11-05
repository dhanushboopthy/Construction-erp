"""Bill templates (Milestone 28): the placeholder grammar, the field registry and the fields a
GST document may not drop. Uploaded HTML is data, never a Jinja template."""

import pytest

from app.domain.bill_template import (
    FIELDS,
    IMAGE_URIS,
    MAX_ASSET_BYTES,
    MAX_ASSETS,
    MAX_HTML_BYTES,
    REGISTRY,
    SLOTS,
    TAX_DOCUMENT_SLOTS,
    BillData,
    TemplateRuleError,
    check_asset,
    check_assets,
    check_slot,
    decode_html,
    fields_for,
    format_value,
    has_forbidden_wording,
    missing_requirements,
    parse_token,
    requirements,
    sample_data,
    substitute,
    tokens,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 32


def test_the_slots():
    assert SLOTS == ("tax_invoice", "proforma", "quotation", "credit_note", "debit_note")
    assert TAX_DOCUMENT_SLOTS == ("tax_invoice", "credit_note", "debit_note")
    check_slot("proforma")
    with pytest.raises(TemplateRuleError) as err:
        check_slot("estimate")
    assert err.value.code == "SLOT_UNKNOWN"


def test_the_limits():
    assert MAX_HTML_BYTES == 500 * 1024
    assert MAX_ASSET_BYTES == 2 * 1024 * 1024
    assert MAX_ASSETS == 20


# ------------------------------------------------------------------ the registry


def test_every_field_is_described_with_a_sample_and_a_slot():
    keys = [f.key for f in FIELDS]
    assert len(keys) == len(set(keys))
    assert set(REGISTRY) == set(keys)
    for field in FIELDS:
        assert field.description and field.sample, field.key
        assert field.slots and set(field.slots) <= set(SLOTS), field.key
        assert field.group == field.key.split(".")[0]
    assert {f.group for f in FIELDS} == {
        "invoice",
        "note",
        "einvoice",
        "company",
        "customer",
        "consignee",
        "item",
        "hsn",
        "totals",
    }


def test_the_task_names_are_in_the_registry():
    for key in ("invoice.number", "company.logo", "company.secondaryLogo", "totals.amountInWords"):
        assert key in REGISTRY
    assert REGISTRY["company.logo"].image and not REGISTRY["invoice.number"].image
    assert set(IMAGE_URIS) == {f.key for f in FIELDS if f.image}


def test_fields_for_a_slot():
    invoice = {f.key for f in fields_for("tax_invoice")}
    note = {f.key for f in fields_for("credit_note")}
    assert "invoice.copyLabel" in invoice and "invoice.copyLabel" not in note
    assert "note.against" in note and "note.against" not in invoice
    assert "einvoice.irn" in invoice and "einvoice.irn" not in {
        f.key for f in fields_for("quotation")
    }


def test_every_requirement_names_fields_its_slot_fills():
    for slot in SLOTS:
        offered = {f.key for f in fields_for(slot)}
        assert requirements(slot), slot
        for req in requirements(slot):
            assert req.label
            for option in req.any_of:
                assert option <= offered, (slot, req.label, option - offered)


# ------------------------------------------------------------------ mandatory GST fields


def _all_keys(slot):
    return {f.key for f in fields_for(slot)}


@pytest.mark.parametrize("slot", SLOTS)
def test_a_template_with_every_field_misses_nothing(slot):
    assert missing_requirements(slot, _all_keys(slot)) == []


def test_a_tax_invoice_may_not_drop_a_gst_field():
    every = _all_keys("tax_invoice")
    for dropped, label in [
        ("company.gstin", "Seller's GSTIN"),
        ("customer.gstin", "Buyer's GSTIN"),
        ("invoice.placeOfSupply", "Place of supply"),
        ("item.hsn", "HSN code of each item"),
        ("totals.grandTotal", "Invoice total"),
        ("einvoice.qr", "e-Invoice IRN and QR code"),
        ("invoice.copyLabel", "Copy marking (original, duplicate, triplicate)"),
    ]:
        assert missing_requirements("tax_invoice", every - {dropped}) == [label], dropped


def test_tax_may_be_shown_per_line_per_hsn_or_in_the_totals():
    every = _all_keys("tax_invoice")
    tax_keys = {
        k
        for k in every
        if k.endswith(("Rate", "Amount")) or k in {"totals.cgst", "totals.sgst", "totals.igst"}
    } | {"item.gstRate", "hsn.rate"}
    base = every - tax_keys
    assert missing_requirements("tax_invoice", base) == [
        "Rate of tax",
        "Amount of CGST, SGST and IGST",
    ]
    per_hsn = base | {"hsn.rate", "hsn.cgstAmount", "hsn.sgstAmount", "hsn.igstAmount"}
    assert missing_requirements("tax_invoice", per_hsn) == []
    per_line = base | {"item.gstRate", "item.cgstAmount", "item.sgstAmount", "item.igstAmount"}
    assert missing_requirements("tax_invoice", per_line) == []
    # Half the taxes is not enough: an inter-state bill would print no IGST.
    assert missing_requirements(
        "tax_invoice", base | {"item.gstRate", "totals.cgst", "totals.sgst"}
    ) == ["Amount of CGST, SGST and IGST"]


def test_a_credit_note_names_the_invoice_it_corrects():
    every = _all_keys("credit_note")
    assert missing_requirements("credit_note", every - {"note.against"}) == [
        "Original document number and date"
    ]
    assert missing_requirements("debit_note", set()) != []


def test_a_quotation_must_say_what_it_is():
    every = _all_keys("quotation")
    assert missing_requirements("proforma", _all_keys("proforma") - {"invoice.title"}) == [
        "Document name"
    ]
    assert missing_requirements("quotation", every - {"invoice.declaration"}) == [
        "Not-a-tax-invoice wording"
    ]


def test_a_proforma_or_quotation_cannot_call_itself_a_tax_invoice():
    assert has_forbidden_wording("proforma", "TAX INVOICE")
    assert has_forbidden_wording("quotation", "This is our Tax  Invoice")
    assert not has_forbidden_wording("quotation", "This is not a tax invoice.")
    assert not has_forbidden_wording("tax_invoice", "Tax Invoice")
    assert not has_forbidden_wording("credit_note", "against tax invoice")


# ------------------------------------------------------------------ the grammar


def test_a_placeholder_is_a_key_with_an_optional_format():
    assert parse_token("{{invoice.number}}").key == "invoice.number"
    spaced = parse_token("{{  totals.grandTotal | symbol }}")
    assert (spaced.key, spaced.fmt, spaced.known) == ("totals.grandTotal", "symbol", True)
    assert parse_token("{{customer.name|upper}}").fmt == "upper"


@pytest.mark.parametrize(
    "raw",
    [
        "{{config.__class__}}",
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{7*7}}",
        "{{ lipsum.__globals__.os.popen('id').read() }}",
        "{{invoice.number|e|safe}}",
        "{{invoice.number|attr('x')}}",
        "{{invoice.nope}}",
        "{{ }}",
        "{% for x in range(10) %}",
        "{# a comment #}",
    ],
)
def test_anything_else_is_unknown(raw):
    token = parse_token(raw)
    assert not token.known
    assert token.raw == raw


def test_an_unknown_format_is_unknown():
    token = parse_token("{{invoice.number|lower}}")
    assert token.key == "invoice.number" and not token.known


def test_tokens_are_found_in_text():
    found = tokens("No. {{invoice.number}} dated {{ invoice.date }} {% if x %}{{x}}")
    assert [t.raw for t in found] == [
        "{{invoice.number}}",
        "{{ invoice.date }}",
        "{% if x %}",
        "{{x}}",
    ]
    assert tokens("a { b } {{ c") == []


def test_substitution_is_one_pass_and_never_evaluates():
    values = {"customer.name": "{{company.gstin}} & <b>", "company.gstin": "33ABCDE1234F1Z5"}

    def lookup(token):
        return values.get(token.key or "", "") if token.known else ""

    text = "{{customer.name}} / {{7*7}} / {{config.__class__}} / {% raw %}"
    assert substitute(text, lookup) == "{{company.gstin}} & <b> /  /  / "


def test_formats():
    assert format_value("1,18,000.00", None) == "1,18,000.00"
    assert format_value("1,18,000.00", "symbol") == "₹ 1,18,000.00"
    assert format_value("", "symbol") == ""
    assert format_value("Ravi Kumar", "upper") == "RAVI KUMAR"


# ------------------------------------------------------------------ the uploaded files


def test_the_html_must_be_utf8_and_not_too_large():
    assert decode_html(b"\xef\xbb\xbf<p>hi</p>") == "<p>hi</p>"
    for data, code in [
        (b"", "TEMPLATE_EMPTY"),
        (b"   \n", "TEMPLATE_EMPTY"),
        (b"\xff\xfe<\x00p\x00", "TEMPLATE_NOT_UTF8"),
        (b"x" * (MAX_HTML_BYTES + 1), "TEMPLATE_TOO_LARGE"),
    ]:
        with pytest.raises(TemplateRuleError) as err:
            decode_html(data)
        assert err.value.code == code
    assert decode_html(b"x" * MAX_HTML_BYTES)


def test_an_asset_is_a_png_or_jpeg_with_a_plain_name():
    assert check_asset("stamp.png", PNG) == "image/png"
    assert check_asset("sign_2-final.JPG", JPEG) == "image/jpeg"
    for name, data, code in [
        ("stamp.png", b"", "ASSET_EMPTY"),
        ("stamp.png", b"x" * (MAX_ASSET_BYTES + 1), "ASSET_TOO_LARGE"),
        ("stamp.svg", b"<svg/>", "ASSET_TYPE"),
        ("../stamp.png", PNG, "ASSET_NAME"),
        ("a b.png", PNG, "ASSET_NAME"),
        (".hidden.png", PNG, "ASSET_NAME"),
        ("x" * 81, PNG, "ASSET_NAME"),
        ("@logo", PNG, "ASSET_NAME"),
    ]:
        with pytest.raises(TemplateRuleError) as err:
            check_asset(name, data)
        assert err.value.code == code, name


def test_assets_are_few_and_uniquely_named():
    assert check_assets([("a.png", PNG), ("b.jpg", JPEG)]) == {
        "a.png": "image/png",
        "b.jpg": "image/jpeg",
    }
    with pytest.raises(TemplateRuleError) as err:
        check_assets([("a.png", PNG), ("A.png", PNG)])
    assert err.value.code == "ASSET_DUPLICATE"
    with pytest.raises(TemplateRuleError) as err:
        check_assets([(f"a{i}.png", PNG) for i in range(MAX_ASSETS + 1)])
    assert err.value.code == "ASSET_TOO_MANY"


# ------------------------------------------------------------------ the preview's sample


@pytest.mark.parametrize("slot", SLOTS)
def test_the_sample_fills_every_field_of_the_slot(slot):
    sample = sample_data(slot)
    assert isinstance(sample, BillData)
    offered = {f.key for f in fields_for(slot)}
    item_keys = {k for k in offered if k.startswith("item.")}
    hsn_keys = {k for k in offered if k.startswith("hsn.")}
    assert set(sample.fields) == offered - item_keys - hsn_keys
    assert len(sample.items) == 2 and all(set(row) == item_keys for row in sample.items)
    assert len(sample.hsn) == 1 and set(sample.hsn[0]) == hsn_keys
    assert sample.items[1]["item.lineNo"] == "2"


def test_the_sample_is_an_intra_state_bill():
    sample = sample_data("tax_invoice")
    assert sample.fields["totals.igst"] == "" and sample.fields["totals.cgst"]
    assert sample.items[0]["item.igstAmount"] == "" and sample.hsn[0]["hsn.igstRate"] == ""
    assert sample.fields["company.logo"] == IMAGE_URIS["company.logo"]
    assert sample.fields["invoice.title"] == "Tax Invoice"
    assert sample_data("credit_note").fields["invoice.title"] == "Credit Note"
