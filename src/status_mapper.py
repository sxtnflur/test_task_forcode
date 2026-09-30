import structlog
from gate_lib.const import COMPLETE
from gate_lib.const import FAILED
from gate_lib.const import PENDING
from gate_lib.protocol.v2.base import Status

from gate_nambaone.nambaone.schemas import PaymentOrderStatus

logger = structlog.get_logger()


def map_status(mapping: dict[str, Status], provider_status: str, kind: str) -> Status:
    status = mapping.get(provider_status)
    if status is None:
        logger.warning("nambaone_unknown_status", kind=kind, provider_status=provider_status)
        return PENDING
    return status


# Статус заказа на возврат
REFUND_STATUS_MAPPING: dict[str, Status] = {
    "CREATED": PENDING,
    "COMPLETED": COMPLETE,
    "CANCELED": FAILED,
    "FAILED": FAILED,
    "EXPIRED": FAILED,
    # Завис на стороне NambaOne: разбирается вручную, деньги еще могут двинуться
    "STUCK": PENDING,
}


def map_refund_status(status: str) -> Status:
    return map_status(REFUND_STATUS_MAPPING, status, "refund")


# Статус заказа на оплату по платежной ссылке
PAYMENT_STATUS_MAPPING: dict[str, Status] = {
    # Ссылка еще не оплачена
    PaymentOrderStatus.CREATED: PENDING,
    PaymentOrderStatus.PAYER_DEBIT: PENDING,
    PaymentOrderStatus.PAYER_DEBIT_SUCCESSFUL: PENDING,
    PaymentOrderStatus.PROCESSING: PENDING,
    PaymentOrderStatus.COMPLETED: COMPLETE,
    # Сам платеж прошел успешно, его возвраты отслеживаются отдельно
    PaymentOrderStatus.REFUNDED: COMPLETE,
    PaymentOrderStatus.CANCELED: FAILED,
    PaymentOrderStatus.FAILED: FAILED,
    PaymentOrderStatus.EXPIRED: FAILED,
    # Итог попытки отмены не окончательный
    PaymentOrderStatus.CANCELLATION_ATTEMPTED: PENDING,
    PaymentOrderStatus.CANCELLATION_FAILED: PENDING,
}


def map_payment_status(status: str) -> Status:
    return map_status(PAYMENT_STATUS_MAPPING, status, "payment")
