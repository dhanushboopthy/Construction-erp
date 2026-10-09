"""E-way bill and e-invoice rules (Milestone 10). Pure: times and dates are passed in.

Thresholds live in shop settings (`compliance.eway_bill_required`); confirm the rules below with
the shop's accountant before go-live (docs/GAP_ANALYSIS.md, G12 and G13)."""

import re
from datetime import date, datetime, timedelta

MAX_DISTANCE_KM = 4000
CANCEL_WINDOW = timedelta(hours=24)

_VEHICLE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$")
_PINCODE = re.compile(r"^[1-9][0-9]{5}$")
_EWB_NUMBER = re.compile(r"^[0-9]{12}$")


def validity_days(distance_km: int) -> int:
    """One day for each 200 km or part of it (ordinary cargo)."""
    if not 0 < distance_km <= MAX_DISTANCE_KM:
        raise ValueError(f"distance must be between 1 and {MAX_DISTANCE_KM} km")
    return -(-distance_km // 200)


def valid_until(generated_on: date, distance_km: int) -> date:
    """Last day the bill is valid: it runs to midnight of that day."""
    return generated_on + timedelta(days=validity_days(distance_km))


def can_cancel(generated_at: datetime, now: datetime) -> bool:
    """A bill can be cancelled within 24 hours of generation."""
    return timedelta(0) <= now - generated_at <= CANCEL_WINDOW


def normalize_vehicle(raw: str) -> str:
    """Upper-case, letters and digits only; raises ValueError if it is not an Indian plate."""
    clean = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not _VEHICLE.match(clean):
        raise ValueError("enter the vehicle number like TN09AB1234")
    return clean


def is_valid_pincode(value: str) -> bool:
    return bool(_PINCODE.match(value))


def is_valid_ewb_number(value: str) -> bool:
    return bool(_EWB_NUMBER.match(value))


def recipient_gstin(bill_to_gstin: str | None) -> str:
    """Buyers without a GSTIN go on the bill as URP (unregistered person), G13."""
    return bill_to_gstin or "URP"


def einvoice_required(enabled: bool, bill_to_gstin: str | None) -> bool:
    """Only B2B bills carry an IRN, and only once the shop has switched e-invoicing on (G12)."""
    return enabled and bool(bill_to_gstin)
