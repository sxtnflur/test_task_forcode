from gate_lib.protocol.v2.base import Amount
from gate_lib.protocol.v2.base import CurrencyCode
from gate_lib.protocol.v2.base import GateRequest
from gate_lib.protocol.v2.base import GateResponse
from gate_lib.protocol.v2.base import NonEmptyStr
from gate_lib.protocol.v2.base import PositiveAmount


class RefundRequest(GateRequest):
    refund_id: NonEmptyStr
    invoice_id: NonEmptyStr
    # ID исходного платежа в системе провайдера
    external_id: str | None = None
    amount: PositiveAmount
    currency_code: CurrencyCode


class RefundResponse(GateResponse):
    amount: Amount | None = None
    currency_code: str | None = None
    # ID возврата в системе провайдера
    external_id: str | None = None


class RefundStatusRequest(GateRequest):
    refund_id: NonEmptyStr
    invoice_id: str | None = None
    # ID возврата в системе провайдера
    external_id: str | None = None
    amount: PositiveAmount | None = None
    currency_code: CurrencyCode | None = None


class RefundStatusResponse(GateResponse):
    amount: Amount | None = None
    currency_code: str | None = None
    external_id: str | None = None
