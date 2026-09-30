"""NambaOne принимает только платежи, поэтому выплата отклоняется без запроса к провайдеру."""

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

WITHDRAWAL_AMOUNT = "1000.00"
WITHDRAWAL_CURRENCY = "KGS"
NOT_SUPPORTED_MESSAGE = "Operation is not supported by NambaOne"


def post_withdrawal(client: TestClient, terminal_data: TerminalData | dict[str, Any], **overrides: Any):
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": str(uuid4()),
            "amount": WITHDRAWAL_AMOUNT,
            "currency_code": WITHDRAWAL_CURRENCY,
            "beneficiary_bank_id": "1000000003",
            "terminal_data": terminal_json,
            "email": "user@example.com",
            **overrides,
        },
    )


def assert_not_supported(resp) -> dict[str, Any]:
    assert resp.status_code == 200
    data = resp.json()
    # Провайдеру ничего не отправляется, поэтому выплата точно отклонена, а не оставлена в pending
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == "not_supported"
    assert data["message"] == NOT_SUPPORTED_MESSAGE
    assert data["external_id"] is None
    assert data["redirect"] is None
    return data


def test_withdrawal_is_not_supported(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_withdrawal(client, terminal_data)

    data = assert_not_supported(resp)
    assert data["amount"] == WITHDRAWAL_AMOUNT
    assert data["currency_code"] == WITHDRAWAL_CURRENCY
    assert not httpx_mock.get_requests()


def test_withdrawal_in_other_currency_is_not_supported(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    resp = post_withdrawal(client, terminal_data, currency_code="USD")

    data = assert_not_supported(resp)
    assert data["currency_code"] == "USD"
    assert not httpx_mock.get_requests()


def test_withdrawal_to_card_is_not_supported(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    card = {"pan": "4111111111111111", "exp_month": 12, "exp_year": 2030}
    httpx_mock.add_response(method="GET", url=f"{CDS_URL}/cards/test-card-token", json=card)

    resp = post_withdrawal(client, terminal_data, card_token="test-card-token", beneficiary_bank_id=None)

    assert_not_supported(resp)
    assert [request.url.host for request in httpx_mock.get_requests()] == ["test-cds.com"]


def test_withdrawal_card_data_is_unavailable(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="GET", url=f"{CDS_URL}/cards/test-card-token", status_code=500)

    resp = post_withdrawal(client, terminal_data, card_token="test-card-token")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == gate_lib_const.CARD_DATA_ERROR


def test_invalid_terminal_data(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Данные терминала даже не читаются: ответ от них не зависит
    invalid_terminal = dump_terminal_data(terminal_data)
    invalid_terminal.pop("merchant_account_guid")

    resp = post_withdrawal(client, invalid_terminal)

    assert_not_supported(resp)
    assert not httpx_mock.get_requests()


@pytest.mark.parametrize(
    "overrides", [{"amount": "0"}, {"amount": "-1000"}, {"currency_code": "SOM1"}, {"withdrawal_id": ""}]
)
def test_request_validation(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, overrides: dict[str, str]
):
    resp = post_withdrawal(client, terminal_data, **overrides)

    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    # Невалидный запрос - это не неуспешная операция
    assert "status" not in data
    assert not httpx_mock.get_requests()
