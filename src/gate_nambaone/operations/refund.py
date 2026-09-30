import structlog
from gate_lib import const as gate_lib_const
from gate_lib.protocol.v2.refund import RefundRequest

import const
from gate_nambaone.errors import OperationRejected
from gate_nambaone.errors import ProviderUnavailable
from gate_nambaone.nambaone import NambaOneClient
from gate_nambaone.nambaone.errors import NambaOneApiError
from gate_nambaone.nambaone.errors import NambaOneError
from gate_nambaone.nambaone.schemas import CreateRefundRequest
from gate_nambaone.nambaone.schemas import PaymentOrderStatus
from gate_nambaone.nambaone.schemas import RefundOrder
from gate_nambaone.operations.payment import get_payment_order
from gate_nambaone.schemas.terminal_data import TerminalData

logger = structlog.get_logger()

# Платеж можно вернуть, только когда деньги получены. REFUNDED допускает еще один частичный возврат: осталось ли что
# вернуть, проверяет NambaOne.
REFUNDABLE_STATUSES = {PaymentOrderStatus.COMPLETED, PaymentOrderStatus.REFUNDED}


async def create_refund(nambaone: NambaOneClient, terminal: TerminalData, req: RefundRequest) -> RefundOrder:
    """
    Создает возврат платежа, сделанного по платежной ссылке (externalRefundId = refund_id).

    Отказ на создание проверяется в NambaOne: процессинг повторяет возврат
    после таймаута, и возврат, созданный первой попыткой, нельзя отдавать как неуспешный.
    Остальные ошибки запроса на создание поднимаются как NambaOneError.
    """
    # Для возврата нужен guid заказа на оплату в NambaOne, он ищется по id счета. PaymentOrderNotFound - не
    # NambaOneError: он проходит дальше как отказ со своим сообщением.
    try:
        order = await get_payment_order(nambaone, req.invoice_id)
    except NambaOneError as e:
        # Возврат еще не отправлен, поэтому даже таймаут здесь означает точный отказ
        logger.warning("nambaone_refund_payment_lookup_failed", error=str(e))
        raise OperationRejected(const.PROVIDER_UNAVAILABLE, "Failed to find the payment to refund") from e
    if order.status not in REFUNDABLE_STATUSES:
        # Возвращать пока (или уже) нечего: NambaOne тоже отказал бы
        raise OperationRejected(gate_lib_const.PROVIDER_ERROR, f"Payment {order.status} cannot be refunded")

    webhook_url = terminal.provider_callback_url_refund or terminal.provider_callback_url_invoice
    try:
        return await nambaone.refunds.create_refund(
            req.refund_id,
            CreateRefundRequest(
                payment_order_guid=order.guid,
                webhook_url=str(webhook_url),
                amount=req.amount,
                comment=f"Refund {req.refund_id} of invoice {req.invoice_id}",
            ),
        )
    except NambaOneApiError as rejection:
        return await _find_existing_refund(nambaone, req, rejection)


async def _find_existing_refund(
    nambaone: NambaOneClient, req: RefundRequest, rejection: NambaOneApiError
) -> RefundOrder:
    """
    Возврат с этим id, если запрос на создание отклонен, потому что возврат уже существует.

    Поднимает сам отказ, если NambaOne не знает такой возврат. Если возврат не удалось
    проверить, его итог неизвестен: он мог быть создан предыдущей попыткой.
    """
    try:
        existing = await nambaone.refunds.get_refund(req.refund_id)
    except NambaOneApiError as e:
        # NambaOne ответил, что такого возврата нет: отказ настоящий
        logger.info("nambaone_refund_rejected_not_found", rejection=str(rejection), lookup_error=str(e))
        raise rejection from None
    except NambaOneError as e:
        logger.warning("nambaone_refund_rejected_lookup_failed", rejection=str(rejection), error=str(e))
        raise ProviderUnavailable from e

    logger.warning("nambaone_refund_already_exists", refund_guid=existing.guid, rejection=str(rejection))
    if existing.amount is not None and existing.amount != req.amount:
        # Возврат с этим id все равно возвращается: он существует, и процессинг должен видеть его настоящий статус. Но
        # повтор - это не тот же возврат, поэтому нужно разобраться.
        logger.error(
            "nambaone_refund_already_exists_with_other_amount",
            refund_id=req.refund_id,
            refund_guid=existing.guid,
            requested_amount=str(req.amount),
            existing_amount=str(existing.amount),
        )
    return existing
