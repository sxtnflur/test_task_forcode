from typing import Any
from typing import Generator

import httpx
import pytest
from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData

from main import app

API_VERSION = "v2"

STATUS_INVOICE_ID = "00000000-0000-4000-8000-000000000001"
STATUS_EXTERNAL_ID = "00000000-0000-4000-8000-000000000002"
STATUS_AMOUNT = 1000
STATUS_CURRENCY = "USD"


@pytest.fixture
def client() -> Generator:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def terminal_data() -> TerminalData:
    return TerminalData(
        provider_base_url="https://test-provider.com",
        proxy_url="http://localhost:8080",
    )


def get_provider_status_url(terminal_data: TerminalData) -> str:
    return f"{terminal_data.provider_base_url}/invoice_status/{STATUS_EXTERNAL_ID}"


def post_status(client: TestClient, terminal_data: TerminalData | dict[str, Any]):
    terminal_json = terminal_data.model_dump() if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/status",
        json={
            "invoice_id": STATUS_INVOICE_ID,
            "external_id": STATUS_EXTERNAL_ID,
            "amount": str(STATUS_AMOUNT),
            "currency_code": STATUS_CURRENCY,
            "terminal_data": terminal_json,
        },
    )


def test_status_success(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_status_url(terminal_data)

    mock_response = {
        "order_id": STATUS_INVOICE_ID,
        "id": STATUS_EXTERNAL_ID,
        "amount": STATUS_AMOUNT,
        "status": "completed"
    }

    httpx_mock.add_response(
        method="GET",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    print(f'{data=}')
    assert data["status"] == gate_lib_const.COMPLETE
    assert data["amount"] == str(STATUS_AMOUNT)
    assert data["currency_code"] == STATUS_CURRENCY
    assert data["external_id"] == STATUS_EXTERNAL_ID
    assert data["code"] is None
    assert data["message"] is None


def test_status_failed(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    provider_msg = "Failed to complete payment"

    url = get_provider_status_url(terminal_data)

    mock_response = {
        "order_id": STATUS_INVOICE_ID,
        "id": STATUS_EXTERNAL_ID,
        "amount": STATUS_AMOUNT,
        "status": "failed",
        "provider_error": provider_msg,
    }

    httpx_mock.add_response(
        method="GET",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["amount"] == str(STATUS_AMOUNT)
    assert data["currency_code"] == STATUS_CURRENCY
    assert data["external_id"] == STATUS_EXTERNAL_ID
    assert data["code"] == "provider_error"
    assert data["message"] == provider_msg


def test_status_pending(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_status_url(terminal_data)

    mock_response = {
        "order_id": STATUS_INVOICE_ID,
        "id": STATUS_EXTERNAL_ID,
        "amount": STATUS_AMOUNT,
        "status": "pending",
    }

    httpx_mock.add_response(
        method="GET",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["amount"] == str(STATUS_AMOUNT)
    assert data["currency_code"] == STATUS_CURRENCY
    assert data["external_id"] == STATUS_EXTERNAL_ID
    assert data["code"] is None
    assert data["message"] is None


def test_status_unexpected_status(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_status_url(terminal_data)

    mock_response = {
        "order_id": STATUS_INVOICE_ID,
        "id": STATUS_EXTERNAL_ID,
        "amount": STATUS_AMOUNT,
        "status": "unknown",
    }

    httpx_mock.add_response(
        method="GET",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["amount"] == str(STATUS_AMOUNT)
    assert data["external_id"] == STATUS_EXTERNAL_ID


def test_timeout(terminal_data, client, httpx_mock):
    url = get_provider_status_url(terminal_data)

    httpx_mock.add_exception(httpx.ReadTimeout("Simulated timeout"), method="GET", url=url)

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING


def test_invalid_terminal_data(terminal_data, client):
    invalid_terminal = terminal_data.model_dump()
    invalid_terminal.pop("proxy_url", None)

    resp = post_status(client, invalid_terminal)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING


def test_incorrect_response_with_status_code200(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    url = get_provider_status_url(terminal_data)

    httpx_mock.add_response(
        method="GET",
        url=url,
        json={},
        status_code=200,
    )

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["external_id"] == STATUS_EXTERNAL_ID


def test_incorrect_response_with_status_code500(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    url = get_provider_status_url(terminal_data)

    httpx_mock.add_response(
        method="GET",
        url=url,
        status_code=500,
        text="Internal Server Error",
    )

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["external_id"] == STATUS_EXTERNAL_ID
