from typing import Literal

from gate_nambaone.nambaone.schemas.base import MinorUnitsAmount
from gate_nambaone.nambaone.schemas.base import NambaOneModel
from gate_nambaone.nambaone.schemas.base import ToMinorUnitsAmount


class CreateRefundRequest(NambaOneModel):
    parent_type: Literal["PAYMENT_QR", "PAYMENT_EXTERNAL", "PAYMENT_MERCHANT"] = "PAYMENT_QR"
    payment_order_guid: str
    webhook_url: str
    # Отправляется в минорных единицах
    amount: ToMinorUnitsAmount
    comment: str


class RefundOrder(NambaOneModel):
    guid: str
    status: str
    currency: str | None = None
    amount: MinorUnitsAmount | None = None
    external_guid: str | None = None
    # Почему возврат не прошел: "01", "02", "03" (см. const.REFUND_ERROR_MESSAGES)
    error_code: str | None = None
