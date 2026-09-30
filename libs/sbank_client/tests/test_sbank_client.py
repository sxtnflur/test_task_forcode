import json
from decimal import Decimal

import httpx
import pytest
from pytest_httpx import HTTPXMock
from sbank_client.client import SbankClient
from sbank_client.exceptions import SbankError
from sbank_client.exceptions import SbankInvalidIdError
from sbank_client.exceptions import SbankNotConfiguredError
from sbank_client.exceptions import SbankResponseError

API_URL = "http://sbank.test"
RADMIN_URL = "http://radmin.test"


@pytest.fixture
async def sbank():
    async with httpx.AsyncClient() as client:
        yield SbankClient(client, API_URL, RADMIN_URL, "token")


@pytest.mark.anyio
async def test_get_invoice_info(sbank: SbankClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=f"{API_URL}/invoices/inv-1",
        match_headers={"Authorization": "Token token"},
        json={"id": "inv-1", "primary_terminal": 7, "currency_code": "RUB", "amount": "10.50", "extra": "ignored"},
    )

    info = await sbank.get_invoice_info("inv-1")

    assert info.id == "inv-1"
    assert info.primary_terminal == "7"
    assert info.amount == Decimal("10.50")
    assert info.external_id is None


@pytest.mark.anyio
async def test_get_terminal_info_uses_radmin(sbank: SbankClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{RADMIN_URL}/terminals/7", json={"id": 7, "data": {"key": "value"}})

    info = await sbank.get_terminal_info("7")

    assert info.data == {"key": "value"}


@pytest.mark.anyio
async def test_invoice_income(sbank: SbankClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="POST", url=f"{API_URL}/invoices/inv-1/income")

    await sbank.invoice_income("inv-1", Decimal("10.50"), "ext-1")

    request = httpx_mock.get_request()
    assert json.loads(request.content) == {"amount_paid": "10.50", "external_transaction_id": "ext-1"}


@pytest.mark.anyio
async def test_update_withdrawal_request_skips_empty_fields(sbank: SbankClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="PATCH", url=f"{API_URL}/withdrawals/w-1", json={"ok": True})

    await sbank.update_withdrawal_request(withdrawal_id="w-1", status="complete", amount="5", source="gate")

    request = httpx_mock.get_request()
    assert json.loads(request.content) == {"status": "complete", "amount": "5", "source": "gate"}


@pytest.mark.anyio
async def test_error_status(sbank: SbankClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{API_URL}/invoices/inv-1", status_code=503)

    with pytest.raises(SbankResponseError) as exc_info:
        await sbank.get_invoice_info("inv-1")

    assert exc_info.value.status_code == 503


@pytest.mark.anyio
async def test_timeout(sbank: SbankClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ConnectTimeout("timeout"), url=f"{API_URL}/invoices/inv-1")

    with pytest.raises(SbankError):
        await sbank.get_invoice_info("inv-1")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [{"text": "<html>oops</html>"}, {"json": {"id": "inv-1"}}, {"content": b""}],
    ids=["not-json", "missing-fields", "empty"],
)
async def test_invalid_response(sbank: SbankClient, httpx_mock: HTTPXMock, response: dict):
    httpx_mock.add_response(url=f"{API_URL}/invoices/inv-1", **response)

    with pytest.raises(SbankResponseError):
        await sbank.get_invoice_info("inv-1")


@pytest.mark.anyio
async def test_not_configured():
    async with httpx.AsyncClient() as client:
        sbank = SbankClient(client, "", "", "token")
        with pytest.raises(SbankNotConfiguredError):
            await sbank.get_invoice_info("inv-1")


@pytest.mark.anyio
async def test_id_is_escaped_in_path(sbank: SbankClient, httpx_mock: HTTPXMock):
    # Id из неподписанного вебхука не должен вести к другому ресурсу API
    httpx_mock.add_response(method="GET", url=f"{API_URL}/invoices/..%2Fwithdrawals%2F42", status_code=404)

    with pytest.raises(SbankResponseError):
        await sbank.get_invoice_info("../withdrawals/42")

    assert httpx_mock.get_request().url.raw_path == b"/invoices/..%2Fwithdrawals%2F42"


@pytest.mark.anyio
@pytest.mark.parametrize("invoice_id", ["", ".", ".."])
async def test_dot_segment_id_is_rejected(sbank: SbankClient, httpx_mock: HTTPXMock, invoice_id: str):
    # HTTP-клиент разворачивает "." и "..", поэтому такой id вообще нельзя отправить
    with pytest.raises(SbankInvalidIdError):
        await sbank.get_invoice_info(invoice_id)

    assert not httpx_mock.get_requests()
