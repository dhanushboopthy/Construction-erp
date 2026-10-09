"""A pretend GSP for development and tests. It never talks to the government portal, so it is
refused in production (ADR 0005: no unaccounted documents). Numbers are made from the document
number and the call count, so they are unique and repeatable in a test run."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.domain.eway import valid_until
from app.services.gsp.base import EwayRequest, EwayResult, GspError, IrnRequest, IrnResult


def _digits(seed: str, length: int) -> str:
    return str(int(hashlib.sha256(seed.encode()).hexdigest(), 16))[:length].rjust(length, "0")


class FakeGsp:
    def __init__(self) -> None:
        self.failures: list[GspError] = []  # tests queue errors here; each call pops one
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _maybe_fail(self, name: str, detail: dict[str, Any]) -> None:
        self.calls.append((name, detail))
        if self.failures:
            raise self.failures.pop(0)

    def generate_eway(self, request: EwayRequest) -> EwayResult:
        self._maybe_fail("generate_eway", {"doc_no": request.doc_no})
        now = datetime.now(UTC)
        return EwayResult(
            number="39"
            + _digits(f"{request.doc_no}|{request.supplier.gstin}|{len(self.calls)}", 10),
            generated_at=now,
            valid_until=valid_until(now.date(), request.distance_km),
            raw={"fake": True, "doc_no": request.doc_no, "vehicle": request.vehicle_no},
        )

    def update_vehicle(
        self, number: str, vehicle_no: str, reason: str, from_place: str
    ) -> dict[str, Any]:
        self._maybe_fail("update_vehicle", {"number": number})
        return {"fake": True, "number": number, "vehicle": vehicle_no, "reason": reason}

    def cancel_eway(self, number: str, reason: str) -> dict[str, Any]:
        self._maybe_fail("cancel_eway", {"number": number})
        return {"fake": True, "number": number, "cancelled": True, "reason": reason}

    def generate_irn(self, request: IrnRequest) -> IrnResult:
        self._maybe_fail("generate_irn", {"doc_no": request.doc_no})
        irn = hashlib.sha256(
            f"{request.supplier.gstin}|{request.doc_no}|{request.doc_date}".encode()
        ).hexdigest()
        now = datetime.now(UTC)
        return IrnResult(
            irn=irn,
            ack_no=_digits(irn, 15),
            ack_date=now,
            signed_qr=f"FAKE-QR|{irn}|{request.doc_no}|{request.totals.grand_total}",
            raw={"fake": True, "irn": irn},
        )

    def cancel_irn(self, irn: str, reason: str) -> dict[str, Any]:
        self._maybe_fail("cancel_irn", {"irn": irn})
        return {"fake": True, "irn": irn, "cancelled": True, "reason": reason}
