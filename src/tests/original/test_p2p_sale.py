from typing import Generator
from uuid import uuid4

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


def get_provider_p2p_sale_url(terminal_data: TerminalData) -> str:
    return f"{terminal_data.provider_base_url}/p2p_sale"


def test_p2p_selector_sale_success(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    invoice_id = str(uuid4())
    external_id = str(uuid4())
    amount = "1000.0000"
    currency = "USD"
    card = "**** 1234"
    name = "John Doe"
    bank = "T-Bank"

    url = get_provider_p2p_sale_url(terminal_data)

    mock_response = {
        "order_id": invoice_id,
        "id": external_id,
        "amount": amount,
        "status": "pending",
        "pay_data": card,
    }

    httpx_mock.add_response(
        method="POST",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/p2p-selector/sale",
        json={
            "invoice_id": invoice_id,
            "amount": amount,
            "currency_code": currency,
            "terminal_data": terminal_data.model_dump(),
            "customer_id": "CUSTOMER",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["amount"] == amount
    assert data["external_id"] == external_id
    assert data["beneficiary"]["pan"] == card
    assert data["beneficiary"]["name"] == name
    assert data["beneficiary"]["bank_name"] == bank
    assert data["code"] is None
    assert data["message"] is None


def test_p2p_selector_sale_failed(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    invoice_id = str(uuid4())
    amount = "1000.0000"
    currency = "USD"
    provider_msg = "Signature verification failed!"

    url = get_provider_p2p_sale_url(terminal_data)

    mock_response = {"code": 19, "msg": provider_msg}

    httpx_mock.add_response(
        method="POST",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/p2p-selector/sale",
        json={
            "invoice_id": invoice_id,
            "amount": amount,
            "currency_code": currency,
            "terminal_data": terminal_data.model_dump(),
            "customer_id": "CUSTOMER",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["amount"] == amount
    assert data["external_id"] is None
    assert data["beneficiary"] == {}
    assert data["code"] == "validation_error"
    assert data["message"] == provider_msg


def test_response_successful_but_missing_beneficiary_requisite(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    invoice_id = str(uuid4())
    external_id = str(uuid4())
    amount = "1000.0000"
    currency = "USD"
    deeplink = None

    url = get_provider_p2p_sale_url(terminal_data)

    mock_response = {
        "order_id": invoice_id,
        "id": external_id,
        "amount": amount,
        "status": "pending",
        "deeplink": deeplink,
    }

    httpx_mock.add_response(
        method="POST",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/p2p-selector/sale",
        json={
            "invoice_id": invoice_id,
            "amount": amount,
            "currency_code": currency,
            "terminal_data": terminal_data.model_dump(),
            "customer_id": "CUSTOMER",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["amount"] == amount
    assert data["currency_code"] == currency
    assert data["external_id"] == external_id
    assert data["beneficiary"] == {}
    assert data["code"] == "validation_error"
    assert data["message"] == "Payment requisite is missing in provider response"


def test_timeout(terminal_data, client, httpx_mock):
    invoice_id = str(uuid4())
    amount = "1000.0000"
    currency = "USD"

    url = get_provider_p2p_sale_url(terminal_data)

    httpx_mock.add_exception(httpx.ReadTimeout("Simulated timeout"), method="POST", url=url)

    resp = client.post(
        f"/{API_VERSION}/p2p-selector/sale",
        json={
            "invoice_id": invoice_id,
            "amount": amount,
            "currency_code": currency,
            "terminal_data": terminal_data.model_dump(),
            "customer_id": "CUSTOMER",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == "validation_error"
    assert data["message"] == "Failed to create payment"


def test_invalid_terminal_data(terminal_data, client):
    invoice_id = str(uuid4())
    amount = "1000.0000"
    currency = "USD"

    terminal_data = terminal_data.model_dump()
    terminal_data.pop("proxy_url", None)

    resp = client.post(
        f"/{API_VERSION}/p2p-selector/sale",
        json={
            "invoice_id": invoice_id,
            "amount": amount,
            "currency_code": currency,
            "terminal_data": terminal_data,
            "customer_id": "CUSTOMER",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == "validation_error"
    assert data["message"] == "Terminal data is not valid"


def test_incorrect_response_with_status_code200(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    invoice_id = str(uuid4())
    amount = "1000.0000"
    currency = "USD"

    url = get_provider_p2p_sale_url(terminal_data)

    httpx_mock.add_response(
        method="POST",
        url=url,
        json={},
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/p2p-selector/sale",
        json={
            "invoice_id": invoice_id,
            "amount": amount,
            "currency_code": currency,
            "terminal_data": terminal_data.model_dump(),
            "customer_id": "CUSTOMER",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == "validation_error"
    assert data["message"] == "Failed to create payment"


def test_incorrect_response_with_status_code500(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    invoice_id = str(uuid4())
    amount = "1000.0000"
    currency = "USD"

    url = get_provider_p2p_sale_url(terminal_data)

    httpx_mock.add_response(
        method="POST",
        url=url,
        status_code=500,
        text="Internal Server Error",
    )

    resp = client.post(
        f"/{API_VERSION}/p2p-selector/sale",
        json={
            "invoice_id": invoice_id,
            "amount": amount,
            "currency_code": currency,
            "terminal_data": terminal_data.model_dump(),
            "customer_id": "CUSTOMER",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == "validation_error"
    assert data["message"] == "Failed to create payment"
