from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field

from gate_lib.protocol.v2.base import Amount
from gate_lib.protocol.v2.base import CurrencyCode
from gate_lib.protocol.v2.base import GateRequest
from gate_lib.protocol.v2.base import GateResponse
from gate_lib.protocol.v2.base import NonEmptyStr
from gate_lib.protocol.v2.base import PositiveAmount


class Redirect(BaseModel):
    url: str
    method: Literal["GET", "POST"] = "GET"
    params: dict[str, Any] = Field(default_factory=dict)


class SaleRequest(GateRequest):
    invoice_id: NonEmptyStr
    amount: PositiveAmount
    currency_code: CurrencyCode
    exchange_currency_code: CurrencyCode | None = None
    email: str | None = None
    customer_id: str | None = None
    finish_url: str | None = None
    # Токен карты в Card Data Storage. Без него плательщик вводит данные карты на стороне провайдера.
    card_token: str | None = None


class SaleResponse(GateResponse):
    amount: Amount | None = None
    currency_code: str | None = None
    external_id: str | None = None
    redirect: Redirect | None = None


class SaleConfirmRequest(GateRequest):
    invoice_id: NonEmptyStr
    external_id: str | None = None
    # Данные, которые браузер плательщика возвращает после 3DS/редиректа (PaRes, MD и т.п.)
    data: dict[str, Any] = Field(default_factory=dict)


class SaleConfirmResponse(GateResponse):
    pass
