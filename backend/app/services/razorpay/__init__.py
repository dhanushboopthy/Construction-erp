"""Razorpay access (Milestone 30): pick the adapter named by configuration, like `services/gsp`.

Online renewal is off unless both keys are set (`Settings.online_renewal_enabled`)."""

from functools import lru_cache

from app.core.config import RazorpayProvider, get_settings
from app.services.razorpay.base import RazorpayError, RazorpayGateway, RazorpayOrder
from app.services.razorpay.fake import FakeRazorpay
from app.services.razorpay.http import HttpRazorpay

__all__ = [
    "FakeRazorpay",
    "RazorpayError",
    "RazorpayGateway",
    "RazorpayOrder",
    "get_gateway",
    "reset_gateway",
]


@lru_cache
def _build() -> RazorpayGateway:
    settings = get_settings()
    if not settings.online_renewal_enabled:
        raise RazorpayError(
            "Online renewal is not set up. Contact Duolink to renew.", code="ONLINE_RENEWAL_OFF"
        )
    if settings.razorpay_provider is RazorpayProvider.FAKE:
        if settings.is_production:
            raise RazorpayError(
                "The pretend payment gateway is never used in production. Set "
                "RAZORPAY_PROVIDER=live.",
                code="ONLINE_RENEWAL_OFF",
            )
        return FakeRazorpay()
    return HttpRazorpay(settings)


def get_gateway() -> RazorpayGateway:
    return _build()


def reset_gateway() -> None:
    _build.cache_clear()
