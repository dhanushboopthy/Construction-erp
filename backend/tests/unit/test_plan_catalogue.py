"""The plan catalogue's rules: codes, prices, limits, features, copies and deletion (Milestone 20)."""

from decimal import Decimal

import pytest

from app.domain.plan_features import FEATURE_CODES, FEATURES, unknown_features
from app.domain.plans import (
    MAX_PRICES,
    PlanRuleError,
    PriceTerms,
    check_assignable,
    check_deletable,
    check_features,
    check_limits,
    check_plan_code,
    check_prices,
    copy_code,
    is_trial_plan,
)


def price(value=1, unit="month", amount="999.90"):
    return PriceTerms(duration_value=value, duration_unit=unit, price=Decimal(amount))


def refused(call, *args, **kwargs) -> str:
    with pytest.raises(PlanRuleError) as caught:
        call(*args, **kwargs)
    return caught.value.code


# ------------------------------------------------------------------ codes


@pytest.mark.parametrize(
    ("typed", "code"),
    [("pro", "PRO"), (" Basic Plus ", "BASIC_PLUS"), ("pro-2027", "PRO_2027"), ("TRIAL", "TRIAL")],
)
def test_a_plan_code_is_upper_snake_case(typed, code):
    assert check_plan_code(typed) == code


@pytest.mark.parametrize("typed", ["", "a", "1pro", "pro!", "x" * 31, "_pro", "pro__"])
def test_a_bad_plan_code_is_refused(typed):
    assert refused(check_plan_code, typed) == "PLAN_CODE_INVALID"


def test_only_the_trial_code_is_a_trial_plan():
    assert is_trial_plan("TRIAL") and not is_trial_plan("PRO") and not is_trial_plan("TRIAL_2")


# ------------------------------------------------------------------ limits and features


def test_limits_must_be_at_least_one():
    check_limits(1, 1)
    assert refused(check_limits, 0, 3) == "PLAN_LIMIT_INVALID"
    assert refused(check_limits, 3, 0) == "PLAN_LIMIT_INVALID"


def test_the_catalogue_lists_the_five_features_and_each_has_a_name():
    assert set(FEATURE_CODES) == {
        "EWAY_BILL",
        "GST_EXPORTS",
        "TALLY_EXPORT",
        "MULTI_SHOP",
        "ATTACHMENTS",
    }
    assert all(f.name and f.description for f in FEATURES)
    assert unknown_features(["EWAY_BILL", "TELEPORT", "X"]) == ["TELEPORT", "X"]


def test_features_are_checked_and_listed_once_in_order():
    assert check_features(["ATTACHMENTS", "EWAY_BILL", "ATTACHMENTS"]) == [
        "ATTACHMENTS",
        "EWAY_BILL",
    ]
    assert check_features([]) == []
    assert refused(check_features, ["EWAY_BILL", "TELEPORT"]) == "PLAN_FEATURE_UNKNOWN"


# ------------------------------------------------------------------ prices


def test_a_plan_has_one_to_six_prices():
    check_prices([price()])
    check_prices([price(n) for n in range(1, MAX_PRICES + 1)])
    assert MAX_PRICES == 6
    assert refused(check_prices, []) == "PLAN_PRICE_COUNT"
    assert refused(check_prices, [price(n) for n in range(1, MAX_PRICES + 2)]) == "PLAN_PRICE_COUNT"


def test_two_prices_cannot_have_the_same_duration():
    check_prices([price(1, "month"), price(12, "month"), price(1, "year")])
    assert (
        refused(check_prices, [price(1, "month"), price(1, "month", "5")]) == "PLAN_PRICE_DUPLICATE"
    )


@pytest.mark.parametrize(
    ("value", "unit"), [(0, "month"), (-1, "day"), (1, "week"), (3651, "day"), (1, "")]
)
def test_a_price_needs_a_whole_positive_duration_in_days_months_or_years(value, unit):
    assert refused(check_prices, [price(value, unit)]) == "PLAN_PRICE_DURATION"


@pytest.mark.parametrize("amount", ["0", "0.00", "1", "999.90", "9999999999.99"])
def test_prices_up_to_two_decimals_are_accepted(amount):
    check_prices([price(amount=amount)])


@pytest.mark.parametrize("amount", ["-0.01", "1.001", "10000000000.00", "NaN", "Infinity"])
def test_a_negative_fractional_paisa_or_enormous_price_is_refused(amount):
    assert refused(check_prices, [price(amount=amount)]) == "PLAN_PRICE_AMOUNT"


def test_a_float_price_is_refused():
    bad = PriceTerms(duration_value=1, duration_unit="month", price=999.9)  # type: ignore[arg-type]
    assert refused(check_prices, [bad]) == "PLAN_PRICE_AMOUNT"


# ------------------------------------------------------------------ copies, use and deletion


def test_a_copy_gets_the_next_free_code():
    assert copy_code("PRO", {"PRO"}) == "PRO_COPY"
    assert copy_code("PRO", {"PRO", "PRO_COPY"}) == "PRO_COPY_2"
    assert copy_code("PRO", {"PRO", "PRO_COPY", "PRO_COPY_2"}) == "PRO_COPY_3"


def test_a_copy_code_still_fits_in_thirty_characters():
    long = "A" * 30
    code = copy_code(long, {long})
    assert len(code) <= 30 and code.endswith("_COPY") and check_plan_code(code) == code
    taken = {long, code}
    second = copy_code(long, taken)
    assert len(second) <= 30 and second not in taken and second.endswith("_COPY_2")


def test_a_plan_in_use_cannot_be_deleted():
    check_deletable(0)
    assert refused(check_deletable, 1) == "PLAN_IN_USE"
    assert refused(check_deletable, 40) == "PLAN_IN_USE"


def test_only_an_active_plan_can_be_given_to_a_company():
    check_assignable(True)
    assert refused(check_assignable, False) == "PLAN_INACTIVE"
