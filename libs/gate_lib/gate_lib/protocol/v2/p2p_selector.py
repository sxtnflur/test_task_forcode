from typing import Any

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_serializer

from gate_lib.protocol.v2.base import Amount
from gate_lib.protocol.v2.base import CurrencyCode
from gate_lib.protocol.v2.base import GateRequest
from gate_lib.protocol.v2.base import GateResponse
from gate_lib.protocol.v2.base import NonEmptyStr
from gate_lib.protocol.v2.base import PositiveAmount


class Beneficiary(BaseModel):
    """Платежные реквизиты, выдаваемые плательщику: карта или номер телефона (СБП)."""

    pan: str | None = None
    phone: str | None = None
    name: str | None = None
    bank_name: str | None = None

    @model_serializer(mode="wrap")
    def _drop_empty(self, handler) -> dict[str, Any]:
        # Отсутствующие реквизиты сериализуются как {}, а не как dict из null
        return {key: value for key, value in handler(self).items() if value is not None}


class P2pSelectorSaleRequest(GateRequest):
    invoice_id: NonEmptyStr
    amount: PositiveAmount
    currency_code: CurrencyCode
    customer_id: str | None = None


class P2pSelectorSaleResponse(GateResponse):
    amount: Amount | None = None
    currency_code: str | None = None
    external_id: str | None = None
    beneficiary: Beneficiary = Field(default_factory=Beneficiary)
