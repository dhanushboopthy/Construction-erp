"""A pretend Razorpay for development and tests. It never takes money, so it is refused in
production. Order ids are made from a counter and the receipt, so they are unique in a run."""

import hashlib
from typing import Any

from app.services.razorpay.base import RazorpayError, RazorpayOrder


class FakeRazorpay:
    def __init__(self) -> None:
        self.failures: list[RazorpayError] = []  # tests queue errors here; each call pops one
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, notes: dict[str, str]
    ) -> RazorpayOrder:
        self.calls.append(
            ("create_order", {"amount": amount_paise, "currency": currency, "receipt": receipt})
        )
        if self.failures:
            raise self.failures.pop(0)
        digest = hashlib.sha256(f"{receipt}|{len(self.calls)}".encode()).hexdigest()[:14]
        return RazorpayOrder(id=f"order_{digest}", amount_paise=amount_paise, currency=currency)
