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

WITHDRAWAL_ID = "00000000-0000-4000-8000-000000000011"
WITHDRAWAL_EXTERNAL_ID = "00000000-0000-4000-8000-000000000012"
WITHDRAWAL_AMOUNT = 1000
WITHDRAWAL_CURRENCY = "USD"


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

def get_provider_request_url(terminal_data: TerminalData):
    return f"{terminal_data.provider_base_url}/create_withdrawal"


def test_withdrawal_create_success(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    withdrawal_id = str(uuid4())
    amount = 1000
    currency = "USD"
    external_id = str(uuid4())
    beneficiary_bank_id = "1000000003"

    url = get_provider_request_url(terminal_data)

    mock_response = {
        "order_id": withdrawal_id,
        "id": external_id,
        "amount": amount,
        "status": "pending",
    }

    httpx_mock.add_response(
        method="POST",
        url=url,
        json=mock_response,
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": withdrawal_id,
            "amount": str(amount),
            "currency_code": currency,
            "beneficiary_bank_id": beneficiary_bank_id,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == gate_lib_const.PENDING
    assert data["amount"] == str(amount)
    assert data["withdrawal_amounts"] is None
    assert data["currency_code"] == currency
    assert data["external_id"] == external_id
    assert data["redirect"] is None
    assert data["code"] is None
    assert data["message"] is None


def test_response_from_provider_with_final_error(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    withdrawal_id = str(uuid4())
    amount = 1000
    currency = "USD"
    beneficiary_bank_id = "1000000003"
    provider_msg = "Parameter error! [The minimum transfer limit is:10000]"

    url = get_provider_request_url(terminal_data)


    httpx_mock.add_response(
        method="POST",
        url=url,
        json={"code": 11, "msg": provider_msg},
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": withdrawal_id,
            "amount": str(amount),
            "currency_code": currency,
            "beneficiary_bank_id": beneficiary_bank_id,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )

    data = resp.json()

    assert resp.status_code == 200
    assert data["status"] == gate_lib_const.FAILED
    assert data["amount"] == str(amount)
    assert data["external_id"] is None
    assert data["code"] == "validation_error"
    assert data["message"] == provider_msg


def test_request_with_wrong_bank_id(terminal_data: TerminalData, client: TestClient):
    """
    тест применяется в случае, когда в запрос к провайдеру должно передаваться значение банка по маппингу
    """
    withdrawal_id = str(uuid4())
    amount = 1000
    currency = "USD"

    resp = client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": withdrawal_id,
            "amount": str(amount),
            "currency_code": currency,
            "beneficiary_bank_id": "WRONG_BANK_ID",
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )


    data = resp.json()

    assert resp.status_code == 200
    assert data["status"] == gate_lib_const.FAILED
    assert data["amount"] == str(amount)
    assert data["external_id"] is None
    assert data["code"] == "validation_error"
    assert data["message"] == "Wrong bank id"


def test_response_from_provider_with_pending_error(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    withdrawal_id = str(uuid4())
    amount = 1000
    currency = "USD"
    beneficiary_bank_id = "1000000003"
    provider_msg = "Internal error"

    url = get_provider_request_url(terminal_data)


    httpx_mock.add_response(
        method="POST",
        url=url,
        json={"code": 12, "msg": provider_msg},
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": withdrawal_id,
            "amount": str(amount),
            "currency_code": currency,
            "beneficiary_bank_id": beneficiary_bank_id,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )
    data = resp.json()

    assert resp.status_code == 200
    assert data["status"] == gate_lib_const.PENDING
    assert data["amount"] == str(amount)
    assert data["external_id"] is None
    assert data["code"] is None
    assert data["message"] is None


def test_timeout(terminal_data, client, httpx_mock):
    withdrawal_id = str(uuid4())
    amount = 1000
    currency = "USD"
    beneficiary_bank_id = "1000000003"

    url = get_provider_request_url(terminal_data)

    httpx_mock.add_exception(httpx.ReadTimeout("Simulated timeout"), method="POST", url=url)

    resp = client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": withdrawal_id,
            "amount": str(amount),
            "currency_code": currency,
            "beneficiary_bank_id": beneficiary_bank_id,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["amount"] == str(amount)

def test_invalid_terminal_data(terminal_data, client):
    withdrawal_id = str(uuid4())
    amount = 1000
    currency = "USD"
    beneficiary_bank_id = "1000000003"

    terminal_data = terminal_data.model_dump()
    terminal_data.pop("proxy_url", None)

    resp = client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": withdrawal_id,
            "amount": str(amount),
            "currency_code": currency,
            "beneficiary_bank_id": beneficiary_bank_id,
            "terminal_data": terminal_data,
            "email": "user@example.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["code"] == "validation_error"

def test_incorrect_response_with_status_code200(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    withdrawal_id = str(uuid4())
    amount = 1000
    currency = "USD"
    beneficiary_bank_id = "1000000003"

    url = get_provider_request_url(terminal_data)

    httpx_mock.add_response(
        method="POST",
        url=url,
        json={},
        status_code=200,
    )

    resp = client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": withdrawal_id,
            "amount": str(amount),
            "currency_code": currency,
            "beneficiary_bank_id": beneficiary_bank_id,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["amount"] == str(amount)
    assert data["external_id"] is None

def test_incorrect_response_with_status_code500(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
):
    withdrawal_id = str(uuid4())
    amount = 1000
    currency = "USD"
    beneficiary_bank_id = "1000000003"

    url = get_provider_request_url(terminal_data)

    httpx_mock.add_response(
        method="POST",
        url=url,
        status_code=500,
        text="Internal Server Error",
    )

    resp = client.post(
        f"/{API_VERSION}/withdrawal",
        json={
            "withdrawal_id": withdrawal_id,
            "amount": str(amount),
            "currency_code": currency,
            "beneficiary_bank_id": beneficiary_bank_id,
            "terminal_data": terminal_data.model_dump(),
            "email": "user@example.com",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["amount"] == str(amount)
    assert data["external_id"] is None
