"""HTTP adapter for a real GSP, used for its sandbox and, once the owner is ready, live.

Every GSP words its API a little differently. This adapter speaks a plain JSON shape (below) and
keeps all field naming in `_eway_body`, `_irn_body` and the `_read_*` helpers, so changing to the
chosen provider's exact format touches only this file. Credentials come from the environment."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import Settings
from app.services.gsp.base import (
    DocItem,
    DocTotals,
    EwayRequest,
    EwayResult,
    GspError,
    IrnRequest,
    IrnResult,
    Party,
)


def _num(value: Decimal) -> str:
    return f"{value:f}"


def _party(p: Party) -> dict[str, str]:
    return {
        "name": p.name,
        "gstin": p.gstin,
        "address": p.address,
        "state_code": p.state_code,
        "pincode": p.pincode,
    }


def _items(items: list[DocItem]) -> list[dict[str, str]]:
    return [
        {
            "hsn": i.hsn,
            "description": i.description,
            "quantity": _num(i.quantity),
            "unit": i.unit,
            "taxable": _num(i.taxable),
            "gst_rate": _num(i.gst_rate),
            "cgst": _num(i.cgst),
            "sgst": _num(i.sgst),
            "igst": _num(i.igst),
        }
        for i in items
    ]


def _totals(t: DocTotals) -> dict[str, str]:
    return {
        "taxable": _num(t.taxable),
        "cgst": _num(t.cgst),
        "sgst": _num(t.sgst),
        "igst": _num(t.igst),
        "round_off": _num(t.round_off),
        "grand_total": _num(t.grand_total),
    }


def _parse_when(value: str) -> datetime:
    when = datetime.fromisoformat(value)
    return when if when.tzinfo else when.replace(tzinfo=UTC)


class SandboxGsp:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        if not settings.gsp_base_url:
            raise GspError("GSP_BASE_URL is not set", code="GSP_NOT_CONFIGURED")
        self._settings = settings
        self._http = httpx.Client(
            base_url=settings.gsp_base_url.rstrip("/"),
            timeout=settings.gsp_timeout_seconds,
            transport=transport,
        )
        self._token: str | None = None

    # -------------------------------------------------------------- plumbing

    def _login(self) -> str:
        s = self._settings
        body = {
            "client_id": s.gsp_client_id,
            "client_secret": s.gsp_client_secret.get_secret_value(),
            "username": s.gsp_username,
            "password": s.gsp_password.get_secret_value(),
        }
        data = self._send("POST", "/auth", body, authed=False)
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise GspError("The GSP did not return a login token", code="GSP_AUTH_FAILED")
        return token

    def _send(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        *,
        authed: bool = True,
        retried: bool = False,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if authed:
            self._token = self._token or self._login()
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            response = self._http.request(method, path, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise GspError(
                "The GSP did not answer in time", code="GSP_TIMEOUT", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise GspError("Cannot reach the GSP", code="GSP_UNREACHABLE", retryable=True) from exc
        if response.status_code == 401 and authed and not retried:
            self._token = None  # expired: log in once more
            return self._send(method, path, body, authed=True, retried=True)
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 500:
            raise GspError("The GSP had a problem", code="GSP_DOWN", retryable=True)
        if response.status_code >= 400 or data.get("status") == "error":
            raise GspError(
                str(data.get("message") or "The GSP refused this request"), code="GSP_REFUSED"
            )
        return data if isinstance(data, dict) else {}

    # -------------------------------------------------------------- e-way bill

    def generate_eway(self, request: EwayRequest) -> EwayResult:
        body = {
            "doc_no": request.doc_no,
            "doc_date": request.doc_date.isoformat(),
            "supplier": _party(request.supplier),
            "recipient": _party(request.recipient),
            "ship_to": _party(request.ship_to) if request.ship_to else None,
            "totals": _totals(request.totals),
            "items": _items(request.items),
            "distance_km": request.distance_km,
            "vehicle_no": request.vehicle_no,
            "inter_state": request.inter_state,
        }
        data = self._send("POST", "/ewaybill/generate", body)
        number = str(data.get("ewb_no") or "")
        if not number:
            raise GspError("The GSP did not return an e-way bill number", code="GSP_BAD_RESPONSE")
        until = data.get("valid_until")
        return EwayResult(
            number=number,
            generated_at=_parse_when(str(data["generated_at"]))
            if data.get("generated_at")
            else datetime.now(UTC),
            valid_until=date.fromisoformat(str(until)[:10]) if until else None,
            raw=data,
        )

    def update_vehicle(
        self, number: str, vehicle_no: str, reason: str, from_place: str
    ) -> dict[str, Any]:
        return self._send(
            "POST",
            "/ewaybill/vehicle",
            {
                "ewb_no": number,
                "vehicle_no": vehicle_no,
                "reason": reason,
                "from_place": from_place,
            },
        )

    def cancel_eway(self, number: str, reason: str) -> dict[str, Any]:
        return self._send("POST", "/ewaybill/cancel", {"ewb_no": number, "reason": reason})

    # -------------------------------------------------------------- e-invoice

    def generate_irn(self, request: IrnRequest) -> IrnResult:
        body = {
            "doc_no": request.doc_no,
            "doc_date": request.doc_date.isoformat(),
            "supplier": _party(request.supplier),
            "buyer": _party(request.buyer),
            "ship_to": _party(request.ship_to) if request.ship_to else None,
            "totals": _totals(request.totals),
            "items": _items(request.items),
        }
        data = self._send("POST", "/einvoice/generate", body)
        irn, ack_no, qr = (str(data.get(k) or "") for k in ("irn", "ack_no", "signed_qr"))
        if not (irn and ack_no and qr):
            raise GspError("The GSP did not return the IRN details", code="GSP_BAD_RESPONSE")
        return IrnResult(
            irn=irn,
            ack_no=ack_no,
            ack_date=_parse_when(str(data["ack_date"]))
            if data.get("ack_date")
            else datetime.now(UTC),
            signed_qr=qr,
            raw=data,
        )

    def cancel_irn(self, irn: str, reason: str) -> dict[str, Any]:
        return self._send("POST", "/einvoice/cancel", {"irn": irn, "reason": reason})
