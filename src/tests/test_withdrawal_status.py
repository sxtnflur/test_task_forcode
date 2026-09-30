"""NambaOne принимает только платежи: выплаты там быть не может, поэтому гейт никогда не выясняет ее статус."""

from typing import Any

from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData
from main import settings
from tests.conftest import API_VERSION
from tests.conftest import dump_terminal_data

WITHDRAWAL_STATUS_WITHDRAWAL_ID = "00000000-0000-4000-8000-000000000011"
WITHDRAWAL_STATUS_EXTERNAL_ID = "00000000-0000-4000-8000-000000000012"
WITHDRAWAL_STATUS_AMOUNT = "1000.00"
WITHDRAWAL_STATUS_CURRENCY = "KGS"
NOT_SUPPORTED_MESSAGE = "Operation is not supported by NambaOne"


def post_withdrawal_status(client: TestClient, terminal_data: TerminalData | dict[str, Any], **overrides: Any):
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/withdrawal_status",
        json={
            "withdrawal_id": WITHDRAWAL_STATUS_WITHDRAWAL_ID,
            "external_id": WITHDRAWAL_STATUS_EXTERNAL_ID,
            "amount": WITHDRAWAL_STATUS_AMOUNT,
            "currency_code": WITHDRAWAL_STATUS_CURRENCY,
            "terminal_data": terminal_json,
            **overrides,
        },
    )


def assert_not_supported(resp) -> dict[str, Any]:
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["code"] == "not_supported"
    assert data["message"] == NOT_SUPPORTED_MESSAGE
    assert data["external_id"] == WITHDRAWAL_STATUS_EXTERNAL_ID
    assert data["source"] == settings.ELASTIC_APM_SERVICE_NAME
    return data


def test_withdrawal_status_is_not_supported(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_withdrawal_status(client, terminal_data)

    data = assert_not_supported(resp)
    assert data["currency_code"] == WITHDRAWAL_STATUS_CURRENCY
    assert data["amount"] is None
    assert not httpx_mock.get_requests()


def test_withdrawal_status_in_other_currency_is_not_supported(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    resp = post_withdrawal_status(client, terminal_data, currency_code="USD")

    data = assert_not_supported(resp)
    assert data["currency_code"] == "USD"
    assert not httpx_mock.get_requests()


def test_invalid_terminal_data(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Данные терминала даже не читаются: ответ от них не зависит
    invalid_terminal = dump_terminal_data(terminal_data)
    invalid_terminal.pop("merchant_account_guid")

    resp = post_withdrawal_status(client, invalid_terminal)

    assert_not_supported(resp)
    assert not httpx_mock.get_requests()


def test_request_validation(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_withdrawal_status(client, terminal_data, withdrawal_id=None)

    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    assert "status" not in data
    assert not httpx_mock.get_requests()
