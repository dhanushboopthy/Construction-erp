"""Milestone 26: the numbering floor and the gaps an audited change explains (pure rules)."""

import pytest

from app.domain import numbering as rules


def test_the_next_number_must_clear_the_highest_existing_one():
    with pytest.raises(rules.NumberingError) as caught:
        rules.check_next(5, 7, "MAIN/26-27/00007", "sales_invoice")
    assert str(caught.value) == (
        "Bill MAIN/26-27/00007 already exists. The next number must be 8 or higher."
    )
    with pytest.raises(rules.NumberingError):
        rules.check_next(7, 7, "MAIN/26-27/00007", "sales_invoice")
    rules.check_next(8, 7, "MAIN/26-27/00007", "sales_invoice")
    rules.check_next(20, 7, "MAIN/26-27/00007", "sales_invoice")


def test_with_no_documents_left_one_is_accepted():
    rules.check_next(1, None, None, "sales_invoice")
    with pytest.raises(rules.NumberingError, match="at least 1"):
        rules.check_next(0, None, None, "sales_invoice")


def test_a_deleted_number_below_the_highest_is_not_reusable():
    # 1 to 5 exist and 3 was deleted: the highest is still 5, so the floor is 6.
    assert rules.floor_for(5) == 6
    assert rules.floor_for(None) == 1
    with pytest.raises(rules.NumberingError):
        rules.check_next(3, 5, "S1/26-27/00005", "sales_invoice")


def test_the_largest_number_the_series_can_write_is_capped():
    rules.check_next(rules.MAX_NEXT, None, None, "sales_invoice")
    with pytest.raises(rules.NumberingError, match=str(rules.MAX_NEXT)):
        rules.check_next(rules.MAX_NEXT + 1, None, None, "sales_invoice")


def test_every_document_type_has_a_name_for_the_message():
    for kind in ("credit_note", "payment_receipt", "quotation", "delivery_challan"):
        assert rules.label_of(kind)
    assert rules.label_of("something_new") == "Document"
    with pytest.raises(rules.NumberingError, match="Credit note S1C/26-27/00002"):
        rules.check_next(1, 2, "S1C/26-27/00002", "credit_note")


def test_parse_number_splits_series_year_and_sequence():
    assert rules.parse_number("MAIN/26-27/00025") == ("MAIN", "26-27", 25)
    assert rules.parse_number("S1/27/00001") == ("S1", "27", 1)
    assert rules.parse_number("garbage") is None
    assert rules.parse_number("S1/26-27/") is None


def test_the_next_document_is_written_out_in_full():
    assert rules.next_document("MAIN", "26-27", 25) == "MAIN/26-27/00025"
    assert rules.next_document("S1C", "26-27", 1) == "S1C/26-27/00001"


def test_a_counter_ahead_of_its_documents_offers_the_value_that_closes_the_gap():
    assert rules.is_ahead(20, 7) is True
    assert rules.suggested_next(20, 7) == 8
    assert rules.is_ahead(8, 7) is False
    assert rules.suggested_next(8, 7) is None
    assert rules.is_ahead(1, None) is False
    assert rules.is_ahead(4, None) is True
    assert rules.suggested_next(4, None) == 1


def test_a_reason_is_required_and_trimmed():
    assert rules.clean_reason("  Starting a new book  ") == "Starting a new book"
    for bad in (None, "", "   "):
        with pytest.raises(rules.NumberingError, match="reason"):
            rules.clean_reason(bad)
    with pytest.raises(rules.NumberingError, match="too long"):
        rules.clean_reason("x" * 301)


def test_the_numbers_an_audited_change_skipped():
    assert list(rules.skipped(8, 20, 8)) == list(range(8, 20))
    # The counter was already ahead of the documents: the earlier numbers were burnt too.
    assert list(rules.skipped(12, 20, 8)) == list(range(8, 20))
    # A reset moves the counter down; nothing is skipped.
    assert list(rules.skipped(88, 1, 1)) == []


def test_gaps_are_unexplained_unless_a_change_covers_them():
    covered = [rules.skipped(8, 20, 8)]
    assert rules.unexplained_gaps([8, 9, 19], covered) == []
    assert rules.unexplained_gaps([8, 20], covered) == [20]
    assert rules.unexplained_gaps([3], []) == [3]
    assert rules.unexplained_gaps([], covered) == []
