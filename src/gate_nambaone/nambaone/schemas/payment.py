from enum import StrEnum

from gate_nambaone.nambaone.schemas.base import MinorUnitsAmount
from gate_nambaone.nambaone.schemas.base import NambaOneModel
from gate_nambaone.nambaone.schemas.base import ToMinorUnitsAmount


class PaymentOrderStatus(StrEnum):
    """Статусы заказа на оплату по платежной ссылке."""

    # Ссылка создана, но еще не оплачена
    CREATED = "CREATED"
    PAYER_DEBIT = "PAYER_DEBIT"
    PAYER_DEBIT_SUCCESSFUL = "PAYER_DEBIT_SUCCESSFUL"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLATION_ATTEMPTED = "CANCELLATION_ATTEMPTED"
    CANCELLATION_FAILED = "CANCELLATION_FAILED"


class WebOptions(NambaOneModel):
    redirect_link: str | None = None


class CreateOneTimeLinkRequest(NambaOneModel):
    external_id: str
    amount: ToMinorUnitsAmount
    amount_can_be_changed: bool = False
    webhook_url: str | None = None
    comment: str | None = None
    merchant_employee_guid: str | None = None
    web_options: WebOptions | None = None


class PaymentLink(NambaOneModel):
    guid: str
    # Сама платежная ссылка: открывает приложение Namba One, ее можно показать и как QR-код
    token: str
    status: str | None = None
    currency_code: str | None = None


class PaymentOrder(NambaOneModel):
    guid: str
    # Обычная строка, а не PaymentOrderStatus: новый статус не должен ломать разбор, он сопоставляется с pending
    status: str
    currency: str | None = None
    amount: MinorUnitsAmount | None = None
    # Сколько клиент фактически заплатил
    payment_amount: MinorUnitsAmount | None = None
    refund_amount: MinorUnitsAmount | None = None
