from gate_nambaone.nambaone.api.base import NambaOneApi
from gate_nambaone.nambaone.schemas import CreateOneTimeLinkRequest
from gate_nambaone.nambaone.schemas import PaymentLink
from gate_nambaone.nambaone.schemas import PaymentOrder
from gate_nambaone.nambaone.sender import segment


class PaymentsApi(NambaOneApi):
    async def create_one_time_link(self, request: CreateOneTimeLinkRequest) -> PaymentLink:
        return await self._sender.request(
            "POST", f"/v2/{self._merchant_account_guid}/one-time", request, response_model=PaymentLink
        )

    async def get_one_time_order(self, external_id: str) -> PaymentOrder:
        """
        Заказ на оплату по одноразовой ссылке.

        Заказ существует с момента создания ссылки: у еще не оплаченной ссылки
        заказ в статусе CREATED. Поэтому ответ без заказа - это невалидный ответ.
        """
        return await self._sender.request(
            "GET",
            f"/v1/{self._merchant_account_guid}/one-time/{segment(external_id)}",
            response_model=PaymentOrder,
        )
