"""NambaOne принимает платежи только через свое приложение: p2p-реквизитов для плательщика нет."""

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData
from tests.conftest import API_VERSION
from tests.conftest import dump_terminal_data

P2P_AMOUNT = "1000.00"
P2P_CURRENCY = "KGS"
NOT_SUPPORTED_MESSAGE = "Operation is not supported by NambaOne"


def post_p2p_selector_sale(client: TestClient, terminal_data: TerminalData | dict[str, Any], **overrides: Any):
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/p2p_selector_sale",
        json={
            "invoice_id": str(uuid4()),
            "amount": P2P_AMOUNT,
            "currency_code": P2P_CURRENCY,
            "terminal_data": terminal_json,
            "customer_id": "CUSTOMER",
            **overrides,
        },
    )


def assert_not_supported(resp) -> dict[str, Any]:
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == "not_supported"
    assert data["message"] == NOT_SUPPORTED_MESSAGE
    assert data["external_id"] is None
    # Реквизиты не выдаются
    assert data["beneficiary"] == {}
    return data


def test_p2p_selector_sale_is_not_supported(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_p2p_selector_sale(client, terminal_data)

    data = assert_not_supported(resp)
    assert data["amount"] == P2P_AMOUNT
    assert data["currency_code"] == P2P_CURRENCY
    assert not httpx_mock.get_requests()


def test_p2p_selector_sale_in_other_currency_is_not_supported(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    resp = post_p2p_selector_sale(client, terminal_data, currency_code="USD")

    data = assert_not_supported(resp)
    assert data["currency_code"] == "USD"
    assert not httpx_mock.get_requests()


def test_invalid_terminal_data(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Данные терминала даже не читаются: ответ от них не зависит
    invalid_terminal = dump_terminal_data(terminal_data)
    invalid_terminal.pop("merchant_account_guid")

    resp = post_p2p_selector_sale(client, invalid_terminal)

    assert_not_supported(resp)
    assert not httpx_mock.get_requests()


@pytest.mark.parametrize(
    "overrides", [{"amount": "0"}, {"amount": "-1000"}, {"currency_code": "SOM1"}, {"invoice_id": ""}]
)
def test_request_validation(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, overrides: dict[str, str]
):
    resp = post_p2p_selector_sale(client, terminal_data, **overrides)

    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    # Невалидный запрос - это не неуспешная операция
    assert "status" not in data
    assert not httpx_mock.get_requests()
