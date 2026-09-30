from gate_nambaone.errors import PaymentOrderNotFound
from gate_nambaone.nambaone import NambaOneClient
from gate_nambaone.nambaone.errors import NambaOneInvalidResponseError
from gate_nambaone.nambaone.schemas import PaymentOrder


async def get_payment_order(nambaone: NambaOneClient, invoice_id: str) -> PaymentOrder:
    """
    Заказ на оплату по платежной ссылке счета (externalId = invoice_id).

    У неоплаченной ссылки заказ в статусе CREATED, поэтому пустой ответ значит, что NambaOne
    вообще не знает ссылку: поднимается PaymentOrderNotFound. Остальные ошибки поднимаются как NambaOneError.
    """
    try:
        return await nambaone.payments.get_one_time_order(invoice_id)
    except NambaOneInvalidResponseError as e:
        if e.is_empty:
            raise PaymentOrderNotFound from e
        raise
