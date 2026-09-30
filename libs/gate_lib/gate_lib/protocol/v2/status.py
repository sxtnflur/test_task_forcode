from typing import Self

from pydantic import model_validator

from gate_lib.protocol.v2.base import Amount
from gate_lib.protocol.v2.base import CurrencyCode
from gate_lib.protocol.v2.base import GateRequest
from gate_lib.protocol.v2.base import GateResponse
from gate_lib.protocol.v2.base import PositiveAmount


class StatusRequest(GateRequest):
    """Запрос статуса и для счета (платежа), и для выплаты."""

    invoice_id: str | None = None
    withdrawal_id: str | None = None
    external_id: str | None = None
    amount: PositiveAmount | None = None
    currency_code: CurrencyCode

    @model_validator(mode="after")
    def check_operation_id(self) -> Self:
        if not self.invoice_id and not self.withdrawal_id:
            raise ValueError("Either invoice_id or withdrawal_id is required")
        return self


class StatusResponse(GateResponse):
    amount: Amount | None = None
    currency_code: str | None = None
    external_id: str | None = None
    rrn: str | None = None
    # Имя гейта, выдавшего статус (используется для выплат)
    source: str | None = None
