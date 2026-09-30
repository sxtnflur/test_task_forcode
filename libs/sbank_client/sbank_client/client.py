from decimal import Decimal
from typing import Any
from typing import TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel
from pydantic import ValidationError

from sbank_client.exceptions import SbankError
from sbank_client.exceptions import SbankInvalidIdError
from sbank_client.exceptions import SbankNotConfiguredError
from sbank_client.exceptions import SbankResponseError
from sbank_client.models import InvoiceInfo
from sbank_client.models import TerminalInfo
from sbank_client.models import WithdrawalInfo

ModelT = TypeVar("ModelT", bound=BaseModel)


def _segment(value: Any) -> str:
    """
    Id как один сегмент пути URL.

    Id могут прийти извне (например, из неподписанного вебхука провайдера), поэтому "/" и другие спецсимволы
    экранируются, а "." / ".." отклоняются: HTTP-клиент их разворачивает, и запрос ушел бы
    к другому ресурсу API с токеном сервиса.
    """
    value = str(value)
    if value in ("", ".", ".."):
        raise SbankInvalidIdError(f"Invalid id: {value!r}")
    return quote(value, safe="")


class SbankClient:
    """
    Клиент API процессинга (Sbank).

    `base_url` обслуживает счета и выплаты, `radmin_base_url` - настройки терминалов.
    Любой сбой поднимается как SbankError, чтобы вызывающий код обрабатывал один тип исключения.
    """

    def __init__(
        self,
        httpx_client: httpx.AsyncClient,
        base_url: str,
        radmin_base_url: str,
        auth_token: str,
    ):
        self.httpx_client = httpx_client
        self.base_url = base_url.rstrip("/")
        self.radmin_base_url = radmin_base_url.rstrip("/")
        self.auth_token = auth_token

    async def get_invoice_info(self, invoice_id: str) -> InvoiceInfo:
        data = await self._request("GET", self.base_url, f"/invoices/{_segment(invoice_id)}")
        return self._parse(InvoiceInfo, data)

    async def get_withdrawal_info(self, withdrawal_id: str) -> WithdrawalInfo:
        data = await self._request("GET", self.base_url, f"/withdrawals/{_segment(withdrawal_id)}")
        return self._parse(WithdrawalInfo, data)

    async def get_terminal_info(self, terminal_id: str) -> TerminalInfo:
        data = await self._request("GET", self.radmin_base_url, f"/terminals/{_segment(terminal_id)}")
        return self._parse(TerminalInfo, data)

    async def update_invoice(self, invoice_id: str, **fields: Any) -> None:
        await self._request("PATCH", self.base_url, f"/invoices/{_segment(invoice_id)}", json=fields)

    async def invoice_income(
        self,
        invoice_id: str,
        amount_paid: Decimal | str,
        external_transaction_id: str,
    ) -> None:
        """Отмечает счет как оплаченный."""
        await self._request(
            "POST",
            self.base_url,
            f"/invoices/{_segment(invoice_id)}/income",
            json={"amount_paid": str(amount_paid), "external_transaction_id": external_transaction_id},
        )

    async def mark_invoice_fail(
            self,
            invoice_id: str,
            *,
            error_code: str,
            error_message: str,
            external_id: str,
            payment_gate_iname: str
    ) -> None:
        await self._request(
            "POST", self.base_url,
            f"/invoices/{_segment(invoice_id)}/fail",
            json={
                "error_code": error_code,
                "error_message": error_message,
                "external_id": external_id,
                "payment_gate_iname": payment_gate_iname,
            }
        )

    async def update_withdrawal_request(
        self,
        withdrawal_id: str,
        status: str,
        amount: Decimal | str,
        source: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        payload = {
            "status": status,
            "amount": str(amount),
            "source": source,
            "error_code": error_code,
            "error_message": error_message,
        }
        await self._request(
            "PATCH",
            self.base_url,
            f"/withdrawals/{_segment(withdrawal_id)}",
            json={key: value for key, value in payload.items() if value is not None},
        )

    async def _request(self, method: str, base_url: str, path: str, json: dict[str, Any] | None = None) -> Any:
        if not base_url:
            raise SbankNotConfiguredError("Sbank API base URL is not configured")
        try:
            resp = await self.httpx_client.request(
                method,
                f"{base_url}{path}",
                json=json,
                headers={"Authorization": f"Token {self.auth_token}"},
            )
        except httpx.HTTPError as e:
            raise SbankError(f"Sbank request failed: {e!r}") from e

        if not resp.is_success:
            raise SbankResponseError(f"Sbank responded with status {resp.status_code}", resp.status_code)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as e:
            raise SbankResponseError("Sbank responded with invalid JSON", resp.status_code) from e

    @staticmethod
    def _parse(model: type[ModelT], data: Any) -> ModelT:
        try:
            return model.model_validate(data)
        except ValidationError as e:
            raise SbankResponseError(f"Unexpected Sbank response for {model.__name__}: {e}") from e
