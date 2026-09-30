from gate_nambaone.nambaone.api.base import NambaOneApi
from gate_nambaone.nambaone.schemas import CreateRefundRequest
from gate_nambaone.nambaone.schemas import RefundOrder
from gate_nambaone.nambaone.sender import segment


class RefundsApi(NambaOneApi):
    async def create_refund(self, refund_id: str, request: CreateRefundRequest) -> RefundOrder:
        return await self._sender.request(
            "POST",
            f"/v1/{self._merchant_account_guid}/refund/{segment(refund_id)}",
            request,
            response_model=RefundOrder,
        )

    async def get_refund(self, refund_id: str) -> RefundOrder:
        return await self._sender.request(
            "GET", f"/v1/{self._merchant_account_guid}/refund/{segment(refund_id)}", response_model=RefundOrder
        )
