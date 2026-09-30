import json
import secrets
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import hmac
from sbank_client.client import SbankClient
from yarl import URL


class SecureRedirect:
    """
    Скрывает от плательщика URL оплаты у провайдера.

    URL сохраняется в процессинге, а плательщик отправляется на страницу secure redirect
    с подписанной ссылкой на него. Не зависит от провайдера.
    """

    def __init__(self, sbank: SbankClient, key: str):
        self._sbank = sbank
        self._key = key

    @property
    def is_configured(self) -> bool:
        # С пустым ключом подписать редирект мог бы кто угодно
        return bool(self._key)

    async def create(self, invoice_id: str, payment_url: str, secure_redirect_url: str) -> str:
        """
        Сохраняет URL оплаты в процессинге и возвращает подписанный URL страницы secure redirect.

        raises: SbankError
        """
        if not self.is_configured:
            raise RuntimeError("Secure redirect key is not set")
        await self._sbank.update_invoice(
            invoice_id=invoice_id,
            secure_redirect_data=json.dumps({"url": payment_url, "method": "GET", "payload": []}),
        )
        return self._signed_url(invoice_id, secure_redirect_url)

    def _signed_url(self, invoice_id: str, secure_redirect_url: str) -> str:
        params = {
            "invoice_id": invoice_id,
            "nonce": secrets.token_urlsafe(16),
            "timestamp": str(int(time.time())),
        }
        h = hmac.HMAC(self._key.encode(), hashes.SHA256())
        h.update("".join(params.values()).encode())
        params["signature"] = h.finalize().hex()
        return str(URL(secure_redirect_url).with_query(params))
