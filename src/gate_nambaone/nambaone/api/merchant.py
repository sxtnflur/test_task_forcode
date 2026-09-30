from gate_nambaone.nambaone.api.base import NambaOneApi
from gate_nambaone.nambaone.schemas import MerchantInfo


class MerchantApi(NambaOneApi):
    async def get_info(self) -> MerchantInfo:
        return await self._sender.request("GET", f"/v1/{self._merchant_account_guid}", response_model=MerchantInfo)
