from typing import Any

import httpx
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData
from tests.conftest import API_VERSION
from tests.conftest import MERCHANT_ACCOUNT_GUID
from tests.conftest import dump_terminal_data
from tests.conftest import nambaone_url

BALANCE_CURRENCY = "KGS"


def get_provider_balance_url(terminal_data: TerminalData) -> str:
    return nambaone_url(terminal_data, f"/v1/{MERCHANT_ACCOUNT_GUID}")


def merchant_info(**overrides: Any) -> dict[str, Any]:
    """Ответ NambaOne "получить информацию о мерчанте"; суммы в минорных единицах (тыйынах)."""
    data = {
        "guid": "test-merchant-account-guid",
        "status": "AVAILABLE",
        "balance": "4995360",
        "currency": BALANCE_CURRENCY,
        "balanceHold": "0",
        "availableBalance": "4995360",
    }
    return {"status": "OK", "data": {**data, **overrides}}


def post_balance(
    client: TestClient, terminal_data: TerminalData | dict[str, Any], currency: str = BALANCE_CURRENCY
):
    terminal_json = (
        dump_terminal_data(terminal_data)
        if isinstance(terminal_data, TerminalData)
        else terminal_data
    )
    return client.post(
        f"/{API_VERSION}/balance",
        json={
            "currency": currency,
            "terminal_data": terminal_json,
        },
    )


def test_balance_positive(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    httpx_mock.add_response(method="GET", url=url, json=merchant_info(), status_code=200)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "49953.60"
    assert data["currency"] == BALANCE_CURRENCY
    assert data["code"] is None

    request = httpx_mock.get_request()
    assert request.headers["x-merchant-api-salt"]
    assert request.headers["x-merchant-api-signature"]


def test_balance_is_available_balance(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    mock_response = merchant_info(balance="4995360", balanceHold="995360", availableBalance="4000000")
    httpx_mock.add_response(method="GET", url=url, json=mock_response, status_code=200)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    assert resp.json()["balance"] == "40000.00"


def test_balance_negative(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    mock_response = merchant_info(balance="-4995360", availableBalance="-4995360")
    httpx_mock.add_response(method="GET", url=url, json=mock_response, status_code=200)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "-49953.60"
    assert data["currency"] == BALANCE_CURRENCY


def test_balance_unsupported_currency(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_balance(client, terminal_data, currency="USD")

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == "USD"
    assert data["code"] == "validation_error"
    assert data["message"] == "Currency USD is not supported"
    assert not httpx_mock.get_requests()


def test_balance_account_in_other_currency(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    httpx_mock.add_response(method="GET", url=url, json=merchant_info(currency="USD"), status_code=200)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["code"] == "validation_error"


def test_balance_provider_error(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    mock_response = {"status": "ERROR", "error": {"errorCode": "MERCHANT_API_WRONG_SIGNATURE", "message": "Wrong signature"}}
    httpx_mock.add_response(method="GET", url=url, json=mock_response, status_code=400)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["code"] == "provider_error"


def test_balance_timeout(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    httpx_mock.add_exception(httpx.ReadTimeout("Simulated timeout"), method="GET", url=url)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == BALANCE_CURRENCY
    assert data["code"] == "provider_unavailable"


def test_balance_incorrect_response_with_status_code200(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    url = get_provider_balance_url(terminal_data)
    httpx_mock.add_response(method="GET", url=url, json={}, status_code=200)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == BALANCE_CURRENCY
    assert data["code"] == "provider_unavailable"


def test_balance_incorrect_response_with_status_code500(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    url = get_provider_balance_url(terminal_data)
    httpx_mock.add_response(
        method="GET",
        url=url,
        status_code=500,
        text="Internal Server Error",
    )

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == BALANCE_CURRENCY
    assert data["code"] == "provider_unavailable"


def test_invalid_terminal_data(client: TestClient, terminal_data: TerminalData):
    invalid_data = dump_terminal_data(terminal_data)
    invalid_data.pop("merchant_account_guid")

    resp = post_balance(client, invalid_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == BALANCE_CURRENCY
    assert data["code"] == "validation_error"
