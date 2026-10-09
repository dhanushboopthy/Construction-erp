"""Amount in words for invoices (Indian system: thousand, lakh, crore)."""

from decimal import Decimal as D

import pytest

from app.domain.words import amount_in_words


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        ("0", "Zero Rupees Only"),
        ("1", "One Rupee Only"),
        ("19", "Nineteen Rupees Only"),
        ("20", "Twenty Rupees Only"),
        ("100", "One Hundred Rupees Only"),
        ("118000", "One Lakh Eighteen Thousand Rupees Only"),
        ("1180.50", "One Thousand One Hundred Eighty Rupees and Fifty Paise Only"),
        ("0.01", "Zero Rupees and One Paisa Only"),
        ("100000", "One Lakh Rupees Only"),
        ("10000000", "One Crore Rupees Only"),
        (
            "123456789",
            "Twelve Crore Thirty Four Lakh Fifty Six Thousand Seven Hundred Eighty Nine Rupees Only",
        ),
        ("649000", "Six Lakh Forty Nine Thousand Rupees Only"),
        ("2001", "Two Thousand One Rupees Only"),
    ],
)
def test_amounts(amount, words):
    assert amount_in_words(D(amount)) == words


def test_negative_amounts_are_refused():
    with pytest.raises(ValueError, match="negative"):
        amount_in_words(D("-1"))
