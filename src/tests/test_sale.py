"""Sale с card_token: NambaOne не принимает данные карты, платежи проходят только в его приложении."""

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData
from tests.conftest import API_VERSION
from tests.conftest import CDS_URL
from tests.conftest import dump_terminal_data

SALE_AMOUNT = "100.00"
SALE_CURRENCY = "KGS"
CARD_TOKEN = "test-card-token"
CARD = {"pan": "4111111111111111", "cvc": "123", "exp_month": 12, "exp_year": 2030, "holder": "JOHN DOE"}
NOT_SUPPORTED_MESSAGE = "Operation is not supported by NambaOne"


def post_sale(client: TestClient, terminal_data: TerminalData | dict[str, Any], **overrides: Any):
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/sale",
        json={
            "invoice_id": str(uuid4()),
            "amount": SALE_AMOUNT,
            "currency_code": SALE_CURRENCY,
            "terminal_data": terminal_json,
            "email": "user@example.com",
            "card_token": CARD_TOKEN,
            **overrides,
        },
    )


def mock_card(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=f"{CDS_URL}/cards/{CARD_TOKEN}", json=CARD)


def assert_not_supported(resp) -> dict[str, Any]:
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == "not_supported"
    assert data["message"] == NOT_SUPPORTED_MESSAGE
    assert data["external_id"] is None
    # Плательщика никуда не отправляют
    assert data["redirect"] is None
    return data


def assert_only_cds_requested(httpx_mock: HTTPXMock) -> None:
    # Данные карты берет gate_lib до вызова гейта; в NambaOne ничего не уходит
    assert [request.url.host for request in httpx_mock.get_requests()] == ["test-cds.com"]


def test_sale_is_not_supported(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_card(httpx_mock)

    resp = post_sale(client, terminal_data)

    data = assert_not_supported(resp)
    assert data["amount"] == SALE_AMOUNT
    assert data["currency_code"] == SALE_CURRENCY
    assert_only_cds_requested(httpx_mock)


def test_sale_in_other_currency_is_not_supported(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    mock_card(httpx_mock)

    resp = post_sale(client, terminal_data, currency_code="USD")

    data = assert_not_supported(resp)
    assert data["currency_code"] == "USD"
    assert_only_cds_requested(httpx_mock)


def test_invalid_terminal_data(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Данные терминала даже не читаются: ответ от них не зависит
    mock_card(httpx_mock)
    invalid_terminal = dump_terminal_data(terminal_data)
    invalid_terminal.pop("merchant_account_guid")

    resp = post_sale(client, invalid_terminal)

    assert_not_supported(resp)
    assert_only_cds_requested(httpx_mock)


@pytest.mark.parametrize("status_code", [404, 500])
def test_sale_card_data_is_unavailable(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, status_code: int
):
    httpx_mock.add_response(method="GET", url=f"{CDS_URL}/cards/{CARD_TOKEN}", status_code=status_code)

    resp = post_sale(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == gate_lib_const.CARD_DATA_ERROR
    assert data["redirect"] is None


@pytest.mark.parametrize(
    "overrides", [{"amount": "0"}, {"amount": "-1"}, {"currency_code": "SOM1"}, {"invoice_id": ""}]
)
def test_request_validation(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, overrides: dict[str, str]
):
    resp = post_sale(client, terminal_data, **overrides)

    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    # Невалидный запрос - это не неуспешная операция
    assert "status" not in data
    # Для невалидного запроса данные карты не запрашиваются
    assert not httpx_mock.get_requests()
