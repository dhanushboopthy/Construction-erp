"""Razorpay's Orders API over HTTP (https://razorpay.com/docs/api/orders/). Keys come from the
environment and are sent only as HTTP basic auth; they are never logged or put in an error."""

from typing import Any

import httpx

from app.core.config import Settings
from app.services.razorpay.base import RazorpayError, RazorpayOrder


class HttpRazorpay:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self._base = settings.razorpay_base_url.rstrip("/")
        self._auth = (
            settings.razorpay_key_id.get_secret_value(),
            settings.razorpay_key_secret.get_secret_value(),
        )
        self._timeout = settings.razorpay_timeout_seconds
        self._transport = transport  # tests pass httpx.MockTransport

    def create_order(
        self, *, amount_paise: int, currency: str, receipt: str, notes: dict[str, str]
    ) -> RazorpayOrder:
        body = {"amount": amount_paise, "currency": currency, "receipt": receipt, "notes": notes}
        try:
            with httpx.Client(
                auth=self._auth, timeout=self._timeout, transport=self._transport
            ) as client:
                response = client.post(f"{self._base}/orders", json=body)
        except httpx.HTTPError as exc:
            raise RazorpayError("Razorpay could not be reached. Try again in a minute.") from exc
        if response.status_code >= 400:
            raise RazorpayError(
                f"Razorpay refused the order (HTTP {response.status_code}). Try again, or "
                "contact Duolink if it keeps happening."
            )
        return _read_order(response)


def _read_order(response: httpx.Response) -> RazorpayOrder:
    try:
        data: Any = response.json()
    except ValueError as exc:
        raise RazorpayError("Razorpay sent an answer that could not be read.") from exc
    order_id = data.get("id") if isinstance(data, dict) else None
    amount = data.get("amount") if isinstance(data, dict) else None
    currency = data.get("currency") if isinstance(data, dict) else None
    if not (isinstance(order_id, str) and isinstance(amount, int) and isinstance(currency, str)):
        raise RazorpayError("Razorpay sent an answer that could not be read.")
    return RazorpayOrder(id=order_id, amount_paise=amount, currency=currency)
