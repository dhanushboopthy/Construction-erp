"""Milestone 10: e-way bill and e-invoice rules, with hand-worked numbers."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain import eway


@pytest.mark.parametrize(
    ("km", "days"),
    [(1, 1), (200, 1), (201, 2), (400, 2), (401, 3), (1000, 5)],
)
def test_validity_is_one_day_for_each_200_km_or_part(km, days):
    assert eway.validity_days(km) == days


def test_distance_must_be_positive_and_within_the_portal_limit():
    with pytest.raises(ValueError, match="distance"):
        eway.validity_days(0)
    with pytest.raises(ValueError, match="distance"):
        eway.validity_days(4001)


def test_valid_until_counts_from_the_day_of_generation():
    # 250 km = 2 days; generated on 9 Oct, so it runs to midnight of 11 Oct.
    assert eway.valid_until(date(2026, 10, 9), 250) == date(2026, 10, 11)
    assert eway.valid_until(date(2026, 10, 9), 50) == date(2026, 10, 10)


def test_an_e_way_bill_can_be_cancelled_for_24_hours_only():
    made = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    assert eway.can_cancel(made, made + timedelta(hours=24))  # exactly 24 hours is still fine
    assert not eway.can_cancel(made, made + timedelta(hours=24, seconds=1))
    assert not eway.can_cancel(made, made - timedelta(seconds=1))  # clock before generation


@pytest.mark.parametrize(
    ("raw", "clean"),
    [("TN 09 AB 1234", "TN09AB1234"), ("tn09a1234", "TN09A1234"), ("TN-01-1234", "TN011234")],
)
def test_vehicle_numbers_are_cleaned_and_accepted(raw, clean):
    assert eway.normalize_vehicle(raw) == clean


@pytest.mark.parametrize("raw", ["1234", "TN09AB12", "T09AB1234", "TNABAB1234", ""])
def test_bad_vehicle_numbers_are_refused(raw):
    with pytest.raises(ValueError, match="vehicle"):
        eway.normalize_vehicle(raw)


def test_pincodes_have_six_digits_and_do_not_start_with_zero():
    assert eway.is_valid_pincode("600001")
    for bad in ("060001", "6000", "60000a", "6000011"):
        assert not eway.is_valid_pincode(bad)


def test_recipient_without_gstin_is_urp():
    assert eway.recipient_gstin("33AAPFU0939F1Z2") == "33AAPFU0939F1Z2"
    assert eway.recipient_gstin(None) == "URP"
    assert eway.recipient_gstin("") == "URP"


def test_einvoice_is_for_b2b_bills_once_switched_on():
    assert eway.einvoice_required(True, "33AAPFU0939F1Z2")
    assert not eway.einvoice_required(False, "33AAPFU0939F1Z2")  # switched off
    assert not eway.einvoice_required(True, None)  # B2C needs no IRN


def test_manual_numbers_have_twelve_digits():
    assert eway.is_valid_ewb_number("391012345678")
    assert not eway.is_valid_ewb_number("39101234567")
    assert not eway.is_valid_ewb_number("3910123456789")
    assert not eway.is_valid_ewb_number("39101234567a")
