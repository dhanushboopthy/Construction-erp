from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.domain.gst import is_valid_cin, is_valid_gstin, is_valid_pan


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class Page[T](Schema):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorResponse(Schema):
    code: str
    message: str
    field: str | None = None
    request_id: str | None = None


def _gstin(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    value = value.upper()
    if not is_valid_gstin(value):
        raise ValueError("GSTIN is not valid (format or check digit)")
    return value


def _pan(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    value = value.strip().upper()
    if not is_valid_pan(value):
        raise ValueError("PAN is not valid (5 letters, 4 digits, 1 letter)")
    return value


def _cin(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    value = value.strip().upper()
    if not is_valid_cin(value):
        raise ValueError("CIN is not valid (21 characters, e.g. U45200TN2015PTC098765)")
    return value


Gstin = Annotated[str | None, AfterValidator(_gstin)]
Pan = Annotated[str | None, AfterValidator(_pan)]
Cin = Annotated[str | None, AfterValidator(_cin)]
StateCode = Annotated[str, Field(pattern=r"^[0-9]{2}$", description="GST state code, e.g. 33")]
LimitParam = Annotated[int, Field(ge=1, le=200)]
