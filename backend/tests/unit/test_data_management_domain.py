"""Milestone 26: choosing, ordering and confirming a company data deletion (pure rules)."""

import pytest

from app.domain import data_management as rules

ORDER = ["quotes", "sales", "items", "parties"]


def test_an_unknown_key_is_refused_never_skipped():
    with pytest.raises(rules.DataError) as caught:
        rules.resolve(["sales", "saels"], ORDER)
    assert "saels" in str(caught.value)
    assert caught.value.code == "UNKNOWN_DATA_KIND"


def test_a_selection_is_deduplicated_and_put_in_catalogue_order():
    assert rules.resolve(["parties", "quotes", "parties"], ORDER) == ["quotes", "parties"]
    assert rules.resolve(["all"], ORDER) == ORDER
    assert rules.resolve("all", ORDER) == ORDER


def test_an_empty_selection_is_refused():
    with pytest.raises(rules.DataError) as caught:
        rules.resolve([], ORDER)
    assert caught.value.code == "NOTHING_SELECTED"


def test_all_cannot_be_mixed_with_other_keys():
    with pytest.raises(rules.DataError):
        rules.resolve(["all", "sales"], ORDER)


def test_only_blockers_outside_the_selection_with_rows_count():
    blockers = {
        "parties": {"sales": 120, "quotes": 0, "items": 3},
        "items": {"sales": 4},
    }
    assert rules.unselected_blockers(["parties", "items", "sales"], blockers) == {}
    found = rules.unselected_blockers(["parties"], blockers)
    assert found == {"parties": {"sales": 120, "items": 3}}
    assert rules.unselected_blockers(["items"], blockers) == {"items": {"sales": 4}}
    assert rules.unselected_blockers(["quotes"], blockers) == {}


def test_the_message_names_each_blocker_and_its_count():
    labels = {"parties": "Parties", "sales": "Sales bills", "items": "Items"}
    text = rules.blocked_message({"parties": {"sales": 120, "items": 3}}, labels)
    assert text == "Parties is blocked by 120 Sales bills, 3 Items."
    two = rules.blocked_message({"parties": {"sales": 1}, "items": {"sales": 2}}, labels)
    assert "Parties is blocked by 1 Sales bills." in two
    assert "Items is blocked by 2 Sales bills." in two


def test_selected_deletion_needs_the_word_delete_exactly():
    assert rules.selected_confirmation_ok("DELETE")
    for bad in ("delete", "Delete", " DELETE", "DELETE ", "", None):
        assert not rules.selected_confirmation_ok(bad)


def test_delete_everything_needs_the_word_the_exact_name_and_the_tick():
    ok = rules.all_confirmation_ok
    assert ok("DELETE", "Acme Steels", "Acme Steels", True)
    assert not ok("delete", "Acme Steels", "Acme Steels", True)
    assert not ok("DELETE", "acme steels", "Acme Steels", True)
    assert not ok("DELETE", "Acme Steels ", "Acme Steels", True)
    assert not ok("DELETE", "Acme Steels", "Acme Steels", False)
    assert not ok("DELETE", None, "Acme Steels", True)
    assert not ok(None, "Acme Steels", "Acme Steels", True)


def test_a_valid_topological_order_has_blockers_first():
    deps = {"parties": {"sales", "items"}, "items": {"sales"}, "sales": set()}
    assert rules.order_is_valid(["sales", "items", "parties"], deps)
    assert not rules.order_is_valid(["parties", "items", "sales"], deps)
    assert not rules.order_is_valid(["sales", "items"], deps)  # parties is missing
    assert not rules.order_is_valid(["sales", "sales", "items", "parties"], deps)
