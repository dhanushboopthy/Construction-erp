"""An amount in words for the tax invoice, in the Indian system (thousand, lakh, crore)."""

from decimal import Decimal

from app.domain.money import ZERO, money

_ONES = [
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]  # fmt: skip
_TENS = ["_", "_", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} Hundred")
    if rest:
        parts.append(_below_hundred(rest))
    return " ".join(parts)


def _integer_in_words(n: int) -> str:
    if n == 0:
        return "Zero"
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1000)
    parts = []
    if crore:
        parts.append(f"{_integer_in_words(crore)} Crore")
    if lakh:
        parts.append(f"{_below_hundred(lakh)} Lakh")
    if thousand:
        parts.append(f"{_below_hundred(thousand)} Thousand")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def amount_in_words(amount: Decimal) -> str:
    value = money(amount)
    if value < ZERO:
        raise ValueError("an amount in words cannot be negative")
    rupees, paise = divmod(int(value * 100), 100)
    text = f"{_integer_in_words(rupees)} {'Rupee' if rupees == 1 else 'Rupees'}"
    if paise:
        text += f" and {_integer_in_words(paise)} {'Paisa' if paise == 1 else 'Paise'}"
    return f"{text} Only"
