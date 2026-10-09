from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.domain.gst import is_valid_gstin


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


Gstin = Annotated[str | None, AfterValidator(_gstin)]
StateCode = Annotated[str, Field(pattern=r"^[0-9]{2}$", description="GST state code, e.g. 33")]
LimitParam = Annotated[int, Field(ge=1, le=200)]
