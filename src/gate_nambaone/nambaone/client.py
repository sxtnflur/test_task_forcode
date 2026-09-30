from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import asynccontextmanager

from client import BaseAPIClient
from gate_nambaone.nambaone.api.merchant import MerchantApi
from gate_nambaone.nambaone.api.payments import PaymentsApi
from gate_nambaone.nambaone.api.refunds import RefundsApi
from gate_nambaone.nambaone.sender import NambaOneRequestSender

# Создает транспорт для заданного URL прокси (None - без прокси)
TransportFactory = Callable[[str | None], BaseAPIClient]


class NambaOneClient:
    """NambaOne Merchant Web API одного аккаунта мерчанта, сгруппированный по ресурсам."""

    def __init__(self, sender: NambaOneRequestSender, merchant_account_guid: str):
        self.payments = PaymentsApi(sender, merchant_account_guid)
        self.refunds = RefundsApi(sender, merchant_account_guid)
        self.merchant = MerchantApi(sender, merchant_account_guid)


class NambaOneConnector:
    """
    Открывает клиенты NambaOne для аккаунтов мерчантов.

    Транспорт передается фабрикой, поэтому ни гейт, ни клиент NambaOne
    не зависят от конкретной HTTP-библиотеки.
    """

    def __init__(self, transport_factory: TransportFactory):
        self._transport_factory = transport_factory

    @asynccontextmanager
    async def connect(
        self,
        base_url: str,
        merchant_account_guid: str,
        secret_key: str,
        proxy_url: str | None = None,
    ) -> AsyncIterator[NambaOneClient]:
        """Клиент для одного аккаунта мерчанта; при выходе транспорт закрывается."""
        async with self._transport_factory(proxy_url) as transport:
            sender = NambaOneRequestSender(transport, base_url, secret_key)
            yield NambaOneClient(sender, merchant_account_guid)
