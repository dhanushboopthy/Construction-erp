"""Tally vouchers (FM4). Every voucher must balance: debits equal credits to the paisa.

Hand-worked bills (amounts in ₹; debit positive, credit negative):

A sales bill, 1,000 kg TMT at ₹56: taxable 56,000.00 + CGST 5,040.00 + SGST 5,040.00 = 66,080.00.
  Dr Ravi Builders 66,080.00 · Cr Sales 56,000.00 · Cr Output CGST 5,040.00 · Cr Output SGST 5,040.00

A bill that rounds: taxable 1,001.00 + CGST 90.09 + SGST 90.09 = 1,181.18, billed 1,181.00.
  round off = 1,181.00 - 1,181.18 = -0.18, so Dr Round off 0.18.
  Dr party 1,181.00 + Dr round off 0.18 = Cr 1,001.00 + 90.09 + 90.09 = 1,181.18.

A supplier bill: goods 1,00,000 + 18% IGST 18,000 + freight on the bill 2,000 = 1,20,000 payable.
  Dr Purchases 1,02,000 (payable less tax) · Dr Input IGST 18,000 · Cr supplier 1,20,000.

A credit note for 2 bags returned: taxable 760.90, CGST 106.53, SGST 106.53... kept simple here:
  taxable 760.00 + CGST 106.40 + SGST 106.40 = 972.80 → Dr Sales 760.00, Dr taxes, Cr party.
"""

from datetime import date
from decimal import Decimal
from xml.etree import ElementTree

import pytest

from app.domain import tally as t
from app.domain.finance import CashEntryKind as K

D = Decimal
ON = date(2026, 10, 9)
NAMES = t.ledger_names({})


def amounts(voucher: t.Voucher) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for line in voucher.lines:
        out[line.ledger] = out.get(line.ledger, D("0")) + line.amount
    return out


def sales(**over) -> t.Voucher:
    args = {
        "number": "S1/26-27/00001",
        "on": ON,
        "party": "Ravi Builders",
        "narration": "Sales bill",
        "grand": D("66080.00"),
        "taxable": D("56000.00"),
        "cgst": D("5040.00"),
        "sgst": D("5040.00"),
        "igst": D("0"),
        "round_off": D("0"),
        "names": NAMES,
        "outward": True,
        "party_debit": True,
    }
    return t.tax_document(t.VoucherKind.SALES, **(args | over))


def test_defaults_and_overrides_of_ledger_names() -> None:
    assert NAMES[t.Purpose.SALES] == "Sales" and NAMES[t.Purpose.CASH] == "Cash"
    custom = t.ledger_names({"sales": "Sales - TMT", "unknown": "ignored", "cash": ""})
    assert custom[t.Purpose.SALES] == "Sales - TMT"
    assert custom[t.Purpose.CASH] == "Cash"  # a blank name keeps the default
    assert set(NAMES) == set(t.Purpose)


def test_a_sales_bill_debits_the_customer_and_credits_sales_and_tax() -> None:
    v = sales()
    assert amounts(v) == {
        "Ravi Builders": D("66080.00"),
        "Sales": D("-56000.00"),
        "Output CGST": D("-5040.00"),
        "Output SGST": D("-5040.00"),
    }
    assert v.kind is t.VoucherKind.SALES and v.account is t.PartyAccount.RECEIVABLE
    assert v.party_effect == D("66080.00")  # the customer owes this much more


def test_a_rounded_bill_puts_the_difference_in_round_off() -> None:
    v = sales(
        grand=D("1181.00"),
        taxable=D("1001.00"),
        cgst=D("90.09"),
        sgst=D("90.09"),
        round_off=D("-0.18"),
    )
    assert amounts(v)["Round off"] == D("0.18")  # a debit: the shop gave 18 paise away
    assert sum(line.amount for line in v.lines) == D("0")
    up = sales(
        grand=D("1181.00"),
        taxable=D("1000.50"),
        cgst=D("90.02"),
        sgst=D("90.02"),
        round_off=D("0.46"),
    )
    assert amounts(up)["Round off"] == D("-0.46")  # a credit


def test_inter_state_bills_use_igst() -> None:
    v = sales(
        grand=D("66080.00"), taxable=D("56000.00"), cgst=D("0"), sgst=D("0"), igst=D("10080.00")
    )
    assert amounts(v)["Output IGST"] == D("-10080.00")
    assert "Output CGST" not in amounts(v)


def test_a_credit_note_reverses_a_sale() -> None:
    v = t.tax_document(
        t.VoucherKind.CREDIT_NOTE,
        number="S1C/26-27/00001",
        on=ON,
        party="Ravi Builders",
        narration="Credit note",
        grand=D("972.80"),
        taxable=D("760.00"),
        cgst=D("106.40"),
        sgst=D("106.40"),
        igst=D("0"),
        round_off=D("0"),
        names=NAMES,
        outward=True,
        party_debit=False,
    )
    assert amounts(v) == {
        "Ravi Builders": D("-972.80"),
        "Sales": D("760.00"),
        "Output CGST": D("106.40"),
        "Output SGST": D("106.40"),
    }
    assert v.party_effect == D("-972.80") and v.account is t.PartyAccount.RECEIVABLE


def test_a_supplier_bill_debits_purchases_and_input_tax_and_credits_the_supplier() -> None:
    v = t.tax_document(
        t.VoucherKind.PURCHASE,
        number="S1P/26-27/00001",
        on=ON,
        party="Mills",
        narration="Bill M-77",
        grand=D("120000.00"),
        taxable=D("102000.00"),  # goods 1,00,000 + 2,000 freight on the supplier's bill
        cgst=D("0"),
        sgst=D("0"),
        igst=D("18000.00"),
        round_off=D("0"),
        names=NAMES,
        outward=False,
        party_debit=False,
    )
    assert amounts(v) == {
        "Mills": D("-120000.00"),
        "Purchases": D("102000.00"),
        "Input IGST": D("18000.00"),
    }
    assert v.account is t.PartyAccount.PAYABLE
    assert v.party_effect == D("120000.00")  # we owe the supplier this much more


def test_a_debit_note_gives_goods_back_to_the_supplier() -> None:
    v = t.tax_document(
        t.VoucherKind.DEBIT_NOTE,
        number="S1D/26-27/00001",
        on=ON,
        party="Mills",
        narration="Debit note",
        grand=D("11800.00"),
        taxable=D("10000.00"),
        cgst=D("900.00"),
        sgst=D("900.00"),
        igst=D("0"),
        round_off=D("0"),
        names=NAMES,
        outward=False,
        party_debit=True,
    )
    assert amounts(v) == {
        "Mills": D("11800.00"),
        "Purchases": D("-10000.00"),
        "Input CGST": D("-900.00"),
        "Input SGST": D("-900.00"),
    }
    assert v.party_effect == D("-11800.00")  # we owe the supplier less


def test_an_unbalanced_voucher_is_refused() -> None:
    with pytest.raises(t.UnbalancedVoucherError, match="S1/26-27/00001"):
        sales(grand=D("66080.01"))
    with pytest.raises(t.UnbalancedVoucherError):
        t.Voucher(t.VoucherKind.JOURNAL, "J1", ON, None, "", (t.Line("A", D("1")),), None)


def test_receipts_and_payments_use_cash_or_bank_by_mode() -> None:
    cash = t.settlement(
        "R1", ON, "Ravi Builders", D("25000.00"), "cash", received=True, names=NAMES
    )
    assert amounts(cash) == {"Cash": D("25000.00"), "Ravi Builders": D("-25000.00")}
    assert cash.kind is t.VoucherKind.RECEIPT and cash.party_effect == D("-25000.00")
    upi = t.settlement("R2", ON, "Ravi Builders", D("5000.00"), "upi", received=True, names=NAMES)
    assert amounts(upi)["Bank"] == D("5000.00")
    paid = t.settlement("P1", ON, "Mills", D("100000.00"), "bank", received=False, names=NAMES)
    assert amounts(paid) == {"Mills": D("100000.00"), "Bank": D("-100000.00")}
    assert paid.kind is t.VoucherKind.PAYMENT and paid.account is t.PartyAccount.PAYABLE
    assert paid.party_effect == D("-100000.00")  # we owe the supplier less


def test_cash_book_vouchers() -> None:
    def book(kind, in_cash=True, reversal=False, head="Loading labour"):
        return t.cash_entry_voucher(
            kind,
            "S1V/26-27/00001",
            ON,
            D("2000.00"),
            in_cash=in_cash,
            head=head,
            reversal=reversal,
            narration="",
            names=NAMES,
        )

    # ₹2,000 loading labour paid in cash: Dr the head, Cr Cash.
    labour = book(K.EXPENSE)
    assert amounts(labour) == {"Loading labour": D("2000.00"), "Cash": D("-2000.00")}
    assert labour.kind is t.VoucherKind.PAYMENT and labour.party_effect == D("0")
    assert amounts(book(K.EXPENSE, in_cash=False))["Bank"] == D("-2000.00")
    # ₹2,000 of notes taken to the bank: a contra, Dr Bank Cr Cash; a withdrawal is the reverse.
    deposit = book(K.BANK_DEPOSIT)
    assert amounts(deposit) == {"Bank": D("2000.00"), "Cash": D("-2000.00")}
    assert deposit.kind is t.VoucherKind.CONTRA
    assert amounts(book(K.BANK_WITHDRAWAL)) == {"Cash": D("2000.00"), "Bank": D("-2000.00")}
    assert amounts(book(K.OWNER_DRAWING)) == {
        "Owner's Drawings": D("2000.00"),
        "Cash": D("-2000.00"),
    }
    capital = book(K.OWNER_CAPITAL, in_cash=False)
    assert amounts(capital) == {"Bank": D("2000.00"), "Owner's Capital": D("-2000.00")}
    assert capital.kind is t.VoucherKind.RECEIPT
    # A reversal undoes the original exactly.
    undo = book(K.EXPENSE, reversal=True)
    assert amounts(undo) == {"Loading labour": D("-2000.00"), "Cash": D("2000.00")}


def test_journals_for_rebates_and_freight() -> None:
    # Mills allows a ₹5,000 rebate: Dr Mills (we owe less), Cr Rebate Received.
    rebate = t.journal(
        "RB-1", ON, "Mills", D("5000.00"), t.Purpose.REBATE, names=NAMES, party_debit=True
    )
    assert amounts(rebate) == {"Mills": D("5000.00"), "Rebate Received": D("-5000.00")}
    assert rebate.account is t.PartyAccount.PAYABLE and rebate.party_effect == D("-5000.00")
    # ₹3,500 owed to the transporter: Dr Freight, Cr the transporter.
    freight = t.journal(
        "TRIP-4", ON, "Raja Lorry", D("3500.00"), t.Purpose.FREIGHT, names=NAMES, party_debit=False
    )
    assert amounts(freight) == {"Raja Lorry": D("-3500.00"), "Freight": D("3500.00")}
    assert freight.party_effect == D("3500.00")


def test_totals_by_kind_count_and_sum_the_debits() -> None:
    vouchers = [sales(), sales(number="S1/26-27/00002", grand=D("66080.00"))]
    summary = t.totals_by_kind(vouchers)
    assert summary[t.VoucherKind.SALES] == (2, D("132160.00"))


def test_the_xml_is_well_formed_and_signs_amounts_the_tally_way() -> None:
    v = sales(party="Ravi & Sons <Builders>", narration='5% "bulk" & more')
    masters = [
        t.Master("Ravi & Sons <Builders>", "Sundry Debtors"),
        t.Master("Sales", "Sales Accounts"),
    ]
    xml = t.render_xml("Demo Construction Materials", [v], masters)
    root = ElementTree.fromstring(xml)  # well-formed, with the special characters escaped
    assert root.tag == "ENVELOPE"
    assert root.findtext("HEADER/TALLYREQUEST") == "Import Data"
    assert root.findtext(".//SVCURRENTCOMPANY") == "Demo Construction Materials"
    voucher = root.find(".//VOUCHER")
    assert voucher is not None
    assert voucher.get("VCHTYPE") == "Sales" and voucher.get("ACTION") == "Create"
    assert voucher.findtext("DATE") == "20261009"
    assert voucher.findtext("VOUCHERNUMBER") == "S1/26-27/00001"
    assert voucher.findtext("PARTYLEDGERNAME") == "Ravi & Sons <Builders>"
    assert voucher.findtext("NARRATION") == '5% "bulk" & more'
    assert voucher.findtext("GUID") == "ERP-Sales-S1/26-27/00001"
    entries = voucher.findall("ALLLEDGERENTRIES.LIST")
    first = entries[0]
    # A debit has ISDEEMEDPOSITIVE Yes and a negative amount; a credit has No and a positive one.
    assert first.findtext("LEDGERNAME") == "Ravi & Sons <Builders>"
    assert (first.findtext("ISDEEMEDPOSITIVE"), first.findtext("AMOUNT")) == ("Yes", "-66080.00")
    credit = next(e for e in entries if e.findtext("LEDGERNAME") == "Sales")
    assert (credit.findtext("ISDEEMEDPOSITIVE"), credit.findtext("AMOUNT")) == ("No", "56000.00")
    names = [m.get("NAME") for m in root.findall(".//LEDGER")]
    assert names == ["Ravi & Sons <Builders>", "Sales"]
    assert root.find(".//LEDGER/PARENT").text == "Sundry Debtors"


def test_the_xml_without_masters_has_only_vouchers() -> None:
    root = ElementTree.fromstring(t.render_xml("Co", [sales()], []))
    assert root.findall(".//LEDGER") == [] and len(root.findall(".//VOUCHER")) == 1


def test_control_characters_never_reach_the_xml() -> None:
    v = sales(narration="bad\x00\x0bchars")
    root = ElementTree.fromstring(t.render_xml("Co", [v], []))
    assert root.findtext(".//NARRATION") == "badchars"


def test_master_groups_follow_the_ledger_purpose() -> None:
    masters = t.masters_for(
        NAMES, customers=["Ravi Builders"], suppliers=["Mills"], expense_heads=["Rent"]
    )
    by_name = {m.name: m.parent for m in masters}
    assert by_name["Ravi Builders"] == "Sundry Debtors"
    assert by_name["Mills"] == "Sundry Creditors"
    assert by_name["Rent"] == "Indirect Expenses"
    assert by_name["Sales"] == "Sales Accounts" and by_name["Purchases"] == "Purchase Accounts"
    assert by_name["Output CGST"] == "Duties & Taxes" and by_name["Input IGST"] == "Duties & Taxes"
    assert by_name["Cash"] == "Cash-in-Hand" and by_name["Bank"] == "Bank Accounts"
    assert by_name["Round off"] == "Indirect Expenses"
    assert by_name["Owner's Capital"] == "Capital Account"
    assert by_name["Rebate Received"] == "Indirect Incomes"
    assert by_name["Freight"] == "Direct Expenses"
    assert len(by_name) == len(masters), "no ledger is listed twice"


def test_a_party_named_like_a_ledger_is_listed_once() -> None:
    masters = t.masters_for(NAMES, customers=["Sales"], suppliers=[], expense_heads=["Cash"])
    assert [m.name for m in masters].count("Sales") == 1
    assert [m.name for m in masters].count("Cash") == 1


def test_purpose_totals_ignore_what_the_ledgers_are_called() -> None:
    # Two bills and a credit note, with the accountant naming every ledger "GST".
    names = t.ledger_names({"output_cgst": "GST", "output_sgst": "GST", "sales": "Sales A/c"})
    bill = sales(names=names)
    note = t.tax_document(
        t.VoucherKind.CREDIT_NOTE,
        number="C1",
        on=ON,
        party="Ravi Builders",
        narration="",
        grand=D("1180.00"),
        taxable=D("1000.00"),
        cgst=D("90.00"),
        sgst=D("90.00"),
        igst=D("0"),
        round_off=D("0"),
        names=names,
        outward=True,
        party_debit=False,
    )
    totals = t.purpose_totals([bill, note])
    # Sales net of the note: 56,000 - 1,000 = 55,000, shown as a credit (negative).
    assert totals[t.Purpose.SALES] == D("-55000.00")
    assert totals[t.Purpose.OUTPUT_CGST] == D("-4950.00")  # 5,040 - 90
    assert totals[t.Purpose.OUTPUT_SGST] == D("-4950.00")
    assert t.Purpose.OUTPUT_IGST not in totals
    cash = t.settlement("R1", ON, "Ravi Builders", D("100"), "cash", received=True, names=names)
    assert t.purpose_totals([cash])[t.Purpose.CASH] == D("100.00")


def test_whole_months_finds_the_gst_periods_a_range_covers() -> None:
    assert t.whole_months(date(2026, 10, 1), date(2026, 10, 31)) == ["2026-10"]
    assert t.whole_months(date(2026, 11, 1), date(2027, 1, 31)) == ["2026-11", "2026-12", "2027-01"]
    assert t.whole_months(date(2026, 12, 1), date(2026, 12, 31)) == ["2026-12"]
    assert t.whole_months(date(2026, 10, 2), date(2026, 10, 31)) is None  # starts part way
    assert t.whole_months(date(2026, 10, 1), date(2026, 10, 30)) is None  # ends part way
    assert t.whole_months(date(2026, 10, 31), date(2026, 10, 1)) is None  # backwards
