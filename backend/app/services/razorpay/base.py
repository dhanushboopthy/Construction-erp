"""The contract every Razorpay adapter meets (Milestone 30). The rest of the app only knows these
types, so tests run on a pretend gateway and nothing here needs the network."""

from dataclasses import dataclass
from typing import Protocol


class RazorpayError(Exception):
    """Razorpay refused or could not be reached. Nothing was saved; the owner can try again.
    The message never carries a key or the provider's raw answer."""

    def __init__(self, message: str, *, code: str = "RAZORPAY_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class RazorpayOrder:
    id: str  # order_...
    amount_paise: int
    currency: str


class RazorpayGateway(Protocol):
    def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, notes: dict[str, str]
    ) -> RazorpayOrder: ...
