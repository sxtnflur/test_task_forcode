from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.nambaone.sender import sign
from gate_nambaone.schemas.terminal_data import TerminalData
from tests.conftest import API_VERSION
from tests.conftest import MERCHANT_ACCOUNT_GUID
from tests.conftest import SECRET_KEY
from tests.conftest import dump_terminal_data
from tests.conftest import nambaone_error
from tests.conftest import nambaone_ok
from tests.conftest import nambaone_path
from tests.conftest import nambaone_url

REFUND_STATUS_REFUND_ID = "00000000-0000-4000-8000-000000000041"
REFUND_STATUS_INVOICE_ID = "00000000-0000-4000-8000-000000000042"
# То, что процессинг знает как external_id: guid заказа на возврат, который вернул refund
REFUND_STATUS_EXTERNAL_ID = "00000000-0000-4000-8000-000000000043"
# guid заказа на возврат в том виде, как NambaOne возвращает его сейчас
REFUND_STATUS_GUID = "00000000-0000-4000-8000-000000000044"
REFUND_STATUS_AMOUNT = "100.00"
REFUND_STATUS_CURRENCY = "KGS"

# Возврат ищется по его externalRefundId, то есть по id возврата
GET_REFUND_PATH = f"/v1/{MERCHANT_ACCOUNT_GUID}/refund/{REFUND_STATUS_REFUND_ID}"


def get_provider_refund_status_url(terminal_data: TerminalData) -> str:
    return nambaone_url(terminal_data, GET_REFUND_PATH)


def refund_order(status: str, **overrides: Any) -> dict[str, Any]:
    """Ответ NambaOne "получить возврат"; суммы в минорных единицах (тыйынах)."""
    data = {
        "guid": REFUND_STATUS_GUID,
        "status": status,
        "currency": REFUND_STATUS_CURRENCY,
        "amount": "10000",
        "externalGuid": REFUND_STATUS_REFUND_ID,
    }
    return nambaone_ok({**data, **overrides})


def post_refund_status(client: TestClient, terminal_data: TerminalData | dict[str, Any], **overrides: Any):
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/refund_status",
        json={
            "refund_id": REFUND_STATUS_REFUND_ID,
            "invoice_id": REFUND_STATUS_INVOICE_ID,
            "external_id": REFUND_STATUS_EXTERNAL_ID,
            "amount": REFUND_STATUS_AMOUNT,
            "currency_code": REFUND_STATUS_CURRENCY,
            "terminal_data": terminal_json,
            **overrides,
        },
    )


def assert_pending(resp, code: str | None) -> dict[str, Any]:
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["code"] == code
    assert data["amount"] == REFUND_STATUS_AMOUNT
    assert data["currency_code"] == REFUND_STATUS_CURRENCY
    # Возврат не найден, поэтому id, известный процессингу, возвращается как есть
    assert data["external_id"] == REFUND_STATUS_EXTERNAL_ID
    return data


def test_refund_status_success(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET", url=get_provider_refund_status_url(terminal_data), json=refund_order("COMPLETED")
    )

    resp = post_refund_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.COMPLETE
    assert data["amount"] == REFUND_STATUS_AMOUNT
    assert data["currency_code"] == REFUND_STATUS_CURRENCY
    assert data["external_id"] == REFUND_STATUS_GUID
    assert data["code"] is None
    assert data["message"] is None


def test_refund_status_request_is_signed(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET", url=get_provider_refund_status_url(terminal_data), json=refund_order("COMPLETED")
    )

    post_refund_status(client, terminal_data)

    # Запрос без тела подписывается пустой строкой в качестве тела
    request = httpx_mock.get_request()
    assert request.content == b""
    salt = request.headers["x-merchant-api-salt"]
    expected = sign(SECRET_KEY, nambaone_path(GET_REFUND_PATH), "", salt)
    assert request.headers["x-merchant-api-signature"] == expected


def test_refund_status_amount_is_what_was_refunded(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    httpx_mock.add_response(
        method="GET",
        url=get_provider_refund_status_url(terminal_data),
        json=refund_order("COMPLETED", amount="2550"),
    )

    resp = post_refund_status(client, terminal_data)

    assert resp.json()["amount"] == "25.50"


def test_refund_status_amount_without_provider_amount(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    httpx_mock.add_response(
        method="GET",
        url=get_provider_refund_status_url(terminal_data),
        json=refund_order("COMPLETED", amount=None, currency=None),
    )

    resp = post_refund_status(client, terminal_data)

    data = resp.json()
    assert data["amount"] == REFUND_STATUS_AMOUNT
    assert data["currency_code"] == REFUND_STATUS_CURRENCY


@pytest.mark.parametrize("provider_status", ["CREATED", "STUCK", "SOMETHING_NEW"])
def test_refund_status_pending(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, provider_status: str
):
    # STUCK разбирается вручную на стороне NambaOne, неизвестный статус тоже не окончательный
    httpx_mock.add_response(
        method="GET", url=get_provider_refund_status_url(terminal_data), json=refund_order(provider_status)
    )

    resp = post_refund_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["external_id"] == REFUND_STATUS_GUID
    assert data["code"] is None


@pytest.mark.parametrize(
    "provider_status,error_code,message",
    [
        ("FAILED", "01", "Requisites not found"),
        ("FAILED", "02", "Provider is unavailable"),
        ("FAILED", "03", "Unrecognized response"),
        ("FAILED", "99", "Refund FAILED"),
        ("FAILED", None, "Refund FAILED"),
        ("CANCELED", None, "Refund CANCELED"),
        ("EXPIRED", None, "Refund EXPIRED"),
    ],
)
def test_refund_status_failed(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
    provider_status: str,
    error_code: str | None,
    message: str,
):
    httpx_mock.add_response(
        method="GET",
        url=get_provider_refund_status_url(terminal_data),
        json=refund_order(provider_status, errorCode=error_code),
    )

    resp = post_refund_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["external_id"] == REFUND_STATUS_GUID
    assert data["code"] == gate_lib_const.PROVIDER_ERROR
    assert data["message"] == message


def test_refund_status_rejected_by_provider(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Даже отказ ничего не говорит о самом возврате, поэтому он остается pending
    httpx_mock.add_response(
        method="GET",
        url=get_provider_refund_status_url(terminal_data),
        json=nambaone_error("MERCHANT_API_WRONG_SIGNATURE", "Wrong signature"),
        status_code=401,
    )

    resp = post_refund_status(client, terminal_data)

    data = assert_pending(resp, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == "Wrong signature"


def test_timeout(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ReadTimeout("Simulated timeout"), method="GET", url=get_provider_refund_status_url(terminal_data)
    )

    resp = post_refund_status(client, terminal_data)

    data = assert_pending(resp, "provider_unavailable")
    assert data["message"] == "NambaOne is unavailable"


def test_incorrect_response_with_status_code200(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    httpx_mock.add_response(
        method="GET", url=get_provider_refund_status_url(terminal_data), json={}, status_code=200
    )

    resp = post_refund_status(client, terminal_data)

    assert_pending(resp, "provider_unavailable")


def test_incorrect_response_with_status_code500(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    httpx_mock.add_response(
        method="GET",
        url=get_provider_refund_status_url(terminal_data),
        status_code=500,
        text="Internal Server Error",
    )

    resp = post_refund_status(client, terminal_data)

    assert_pending(resp, "provider_unavailable")


def test_invalid_terminal_data(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    invalid_terminal = dump_terminal_data(terminal_data)
    invalid_terminal.pop("merchant_account_guid")

    resp = post_refund_status(client, invalid_terminal)

    data = assert_pending(resp, gate_lib_const.VALIDATION_ERROR)
    assert data["message"] == "Terminal data is not valid"
    assert not httpx_mock.get_requests()


def test_refund_status_optional_values(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Возврат находится только по refund_id, поэтому необязательные поля для получения статуса не нужны
    httpx_mock.add_response(
        method="GET", url=get_provider_refund_status_url(terminal_data), json=refund_order("COMPLETED")
    )

    resp = post_refund_status(
        client,
        terminal_data,
        currency_code=None,
        invoice_id=None,
        external_id=None,
        amount=None,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.COMPLETE
    assert data["code"] is None
    assert data["message"] is None
    # То, чего не было в запросе, берется из заказа на возврат
    assert data["amount"] == REFUND_STATUS_AMOUNT
    assert data["currency_code"] == REFUND_STATUS_CURRENCY
    assert data["external_id"] == REFUND_STATUS_GUID


def test_refund_status_optional_values_without_provider_values(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # Ни в запросе, ни в заказе на возврат нет суммы и валюты: они остаются пустыми
    httpx_mock.add_response(
        method="GET",
        url=get_provider_refund_status_url(terminal_data),
        json=refund_order("CREATED", amount=None, currency=None),
    )

    resp = post_refund_status(client, terminal_data, currency_code=None, amount=None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["code"] is None
    assert data["amount"] is None
    assert data["currency_code"] is None
    assert data["external_id"] == REFUND_STATUS_GUID


@pytest.mark.parametrize("overrides", [{"refund_id": ""}, {"refund_id": None}, {"currency_code": "SOM1"}])
def test_request_validation(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, overrides: dict[str, Any]
):
    resp = post_refund_status(client, terminal_data, **overrides)

    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    assert "status" not in data
    assert not httpx_mock.get_requests()
