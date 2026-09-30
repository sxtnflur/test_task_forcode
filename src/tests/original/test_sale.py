import uuid
from typing import Generator

import httpx
import pytest
from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData

from ..main import app

API_VERSION = "v2"


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


def test_sale_success(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    invoice_id = str(uuid.uuid4())
    external_id = str(uuid.uuid4())

    url = f"{terminal_data.provider_base_url}/payin"

    mock_response = {"order-id": invoice_id, "id": external_id, "amount": "100.00"}

    httpx_mock.add_response(
        method="POST",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/sale",
        json={
            "invoice_id": invoice_id,
            "amount": "100.00",
            "currency_code": "RUB",
            "exchange_currency_code": None,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["external_id"] == external_id
    assert data["code"] is None


def test_timeout(terminal_data, client: TestClient, httpx_mock):
    invoice_id = str(uuid.uuid4())

    url = f"{terminal_data.provider_base_url}/payin"

    httpx_mock.add_exception(httpx.ReadTimeout("Simulated timeout"), method="POST", url=url)

    resp = client.post(
        f"/{API_VERSION}/sale",
        json={
            "invoice_id": invoice_id,
            "amount": "100.00",
            "currency_code": "RUB",
            "exchange_currency_code": None,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["code"] == "validation_error"
    assert data["message"] == "Failed to create payment"


def test_invalid_terminal_data(terminal_data, client: TestClient):
    invoice_id = str(uuid.uuid4())

    terminal_data = terminal_data.model_dump()
    terminal_data.pop("proxy_url", None)

    resp = client.post(
        f"/{API_VERSION}/sale",
        json={
            "invoice_id": invoice_id,
            "amount": "100.00",
            "currency_code": "RUB",
            "exchange_currency_code": None,
            "terminal_data": terminal_data,
            "email": "user@example.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "failed"
    assert data["code"] == "validation_error"
    assert data["message"] == "Terminal data is not valid"


def test_incorrect_response(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    invoice_id = str(uuid.uuid4())

    url = f"{terminal_data.provider_base_url}/payin"

    httpx_mock.add_response(
        method="POST",
        url=url,
        json={},
        status_code=400,
    )

    resp = client.post(
        f"/{API_VERSION}/sale",
        json={
            "invoice_id": invoice_id,
            "amount": "100.00",
            "currency_code": "RUB",
            "exchange_currency_code": None,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
            "finish_url": "https://finish.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == "validation_error"
    assert data["message"] == "Failed to create payment"
