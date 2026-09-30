from typing import Any, Generator

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData

from ..main import app

API_VERSION = "v2"

BALANCE_CURRENCY = "USD"


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


def get_provider_balance_url(terminal_data: TerminalData) -> str:
    return f"{terminal_data.provider_base_url}/balance"


def post_balance(client: TestClient, terminal_data: TerminalData | dict[str, Any]):
    terminal_json = (
        terminal_data.model_dump()
        if isinstance(terminal_data, TerminalData)
        else terminal_data
    )
    return client.post(
        f"/{API_VERSION}/balance",
        json={
            "currency": BALANCE_CURRENCY,
            "terminal_data": terminal_json,
        },
    )


def test_balance_positive(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    mock_response = {"balance": 4995360}

    httpx_mock.add_response(method="POST", url=url, json=mock_response, status_code=200)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "4995360.0"
    assert data["currency"] == BALANCE_CURRENCY


def test_balance_negative(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    mock_response = {"balance": -4995360}

    httpx_mock.add_response(method="POST", url=url, json=mock_response, status_code=200)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "-4995360.0"
    assert data["currency"] == BALANCE_CURRENCY


def test_balance_timeout(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    url = get_provider_balance_url(terminal_data)
    httpx_mock.add_exception(httpx.ReadTimeout("Simulated timeout"), method="POST", url=url)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == BALANCE_CURRENCY


def test_balance_incorrect_response_with_status_code200(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    url = get_provider_balance_url(terminal_data)
    httpx_mock.add_response(method="POST", url=url, json={}, status_code=200)

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == BALANCE_CURRENCY


def test_balance_incorrect_response_with_status_code500(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    url = get_provider_balance_url(terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=url,
        status_code=500,
        text="Internal Server Error",
    )

    resp = post_balance(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == BALANCE_CURRENCY


def test_invalid_terminal_data(client: TestClient, terminal_data: TerminalData):
    invalid_data = terminal_data.model_dump()
    invalid_data.pop("proxy_url")

    resp = post_balance(client, invalid_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == "0.0"
    assert data["currency"] == BALANCE_CURRENCY
