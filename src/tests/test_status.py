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

STATUS_INVOICE_ID = "00000000-0000-4000-8000-000000000001"
# То, что процессинг знает как external_id: guid платежной ссылки
STATUS_EXTERNAL_ID = "00000000-0000-4000-8000-000000000002"
# guid заказа на оплату, сделанного по ссылке
STATUS_ORDER_GUID = "00000000-0000-4000-8000-000000000003"
STATUS_AMOUNT = "1000.00"
STATUS_CURRENCY = "KGS"

# Платеж ищется по externalId платежной ссылки, то есть по id счета
GET_ORDER_PATH = f"/v1/{MERCHANT_ACCOUNT_GUID}/one-time/{STATUS_INVOICE_ID}"


def get_provider_status_url(terminal_data: TerminalData) -> str:
    return nambaone_url(terminal_data, GET_ORDER_PATH)


def payment_order(status: str, **overrides: Any) -> dict[str, Any]:
    """Ответ NambaOne "получить платеж по одноразовой ссылке"; суммы в минорных единицах (тыйынах)."""
    data = {
        "guid": STATUS_ORDER_GUID,
        "status": status,
        "currency": STATUS_CURRENCY,
        "amount": "100000",
        "paymentAmount": "100000",
    }
    return nambaone_ok({**data, **overrides})


def post_status(client: TestClient, terminal_data: TerminalData | dict[str, Any], **overrides: Any):
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/status",
        json={
            "invoice_id": STATUS_INVOICE_ID,
            "external_id": STATUS_EXTERNAL_ID,
            "amount": STATUS_AMOUNT,
            "currency_code": STATUS_CURRENCY,
            "terminal_data": terminal_json,
            **overrides,
        },
    )


def assert_pending(resp, code: str | None) -> dict[str, Any]:
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["code"] == code
    assert data["currency_code"] == STATUS_CURRENCY
    # Платеж не найден, поэтому id, известный процессингу, возвращается как есть
    assert data["external_id"] == STATUS_EXTERNAL_ID
    return data


def test_status_success(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    order = payment_order("COMPLETED")
    print(f'{order=}')
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=order)

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.COMPLETE
    assert data["amount"] == STATUS_AMOUNT
    assert data["currency_code"] == STATUS_CURRENCY
    assert data["external_id"] == STATUS_ORDER_GUID
    assert data["code"] is None
    assert data["message"] is None


def test_status_request_is_signed(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=payment_order("COMPLETED"))

    post_status(client, terminal_data)

    # Запрос без тела подписывается пустой строкой в качестве тела
    request = httpx_mock.get_request()
    assert request.content == b""
    salt = request.headers["x-merchant-api-salt"]
    expected = sign(SECRET_KEY, nambaone_path(GET_ORDER_PATH), "", salt)
    assert request.headers["x-merchant-api-signature"] == expected


def test_status_amount_is_what_was_paid(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_response = payment_order("COMPLETED", amount="100000", paymentAmount="99950")
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=mock_response)

    resp = post_status(client, terminal_data)

    assert resp.json()["amount"] == "999.50"


def test_status_amount_without_payment_amount(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_response = payment_order("COMPLETED", amount="100000", paymentAmount=None)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=mock_response)

    resp = post_status(client, terminal_data)

    assert resp.json()["amount"] == STATUS_AMOUNT


def test_status_refunded_payment_is_complete(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Сам платеж прошел успешно, его возвраты отслеживаются отдельно
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=payment_order("REFUNDED"))

    resp = post_status(client, terminal_data)

    assert resp.json()["status"] == gate_lib_const.COMPLETE


@pytest.mark.parametrize(
    "provider_status",
    [
        "CREATED",
        "PAYER_DEBIT",
        "PAYER_DEBIT_SUCCESSFUL",
        "PROCESSING",
        "CANCELLATION_ATTEMPTED",
        "CANCELLATION_FAILED",
    ],
)
def test_status_pending(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, provider_status: str):
    mock_response = payment_order(provider_status)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=mock_response)

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["external_id"] == STATUS_ORDER_GUID
    assert data["code"] is None


@pytest.mark.parametrize("provider_status", ["CANCELED", "FAILED", "EXPIRED"])
def test_status_failed(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, provider_status: str):
    mock_response = payment_order(provider_status)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=mock_response)

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["external_id"] == STATUS_ORDER_GUID
    assert data["code"] == gate_lib_const.PROVIDER_ERROR
    assert data["message"] == f"Payment {provider_status}"


def test_status_unexpected_status(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Неизвестный статус не окончательный: запрос будет повторен
    mock_response = payment_order("SOMETHING_NEW")
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=mock_response)

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["external_id"] == STATUS_ORDER_GUID


def test_status_rejected_by_provider(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=get_provider_status_url(terminal_data),
        json=nambaone_error("MERCHANT_API_WRONG_SIGNATURE", "Wrong signature"),
        status_code=401,
    )

    resp = post_status(client, terminal_data)

    data = assert_pending(resp, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == "Wrong signature"


def test_timeout(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ReadTimeout("Simulated timeout"), method="GET", url=get_provider_status_url(terminal_data)
    )

    resp = post_status(client, terminal_data)

    data = assert_pending(resp, "provider_unavailable")
    assert data["message"] == "NambaOne is unavailable"


def test_incorrect_response_with_status_code200(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # У неоплаченной ссылки все равно есть заказ (CREATED), поэтому ответ без него - это сбой провайдера
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json={}, status_code=200)

    resp = post_status(client, terminal_data)

    data = assert_pending(resp, "provider_unavailable")
    assert data["message"] == "NambaOne is unavailable"


def test_incorrect_response_with_incomplete_order(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    httpx_mock.add_response(
        method="GET", url=get_provider_status_url(terminal_data), json=nambaone_ok({"guid": STATUS_ORDER_GUID})
    )

    resp = post_status(client, terminal_data)

    assert_pending(resp, "provider_unavailable")


@pytest.mark.parametrize("data", [None, {}])
def test_status_payment_order_not_found(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, data: dict[str, Any] | None
):
    # Пустой ответ - не сбой NambaOne: он не знает ссылку, поэтому статуса еще нет
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=nambaone_ok(data))

    resp = post_status(client, terminal_data)

    data = assert_pending(resp, None)
    assert data["message"] == "Payment order not found"


def test_incorrect_response_with_status_code500(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    httpx_mock.add_response(
        method="GET", url=get_provider_status_url(terminal_data), status_code=500, text="Internal Server Error"
    )

    resp = post_status(client, terminal_data)

    data = assert_pending(resp, "provider_unavailable")
    assert data["message"] == "NambaOne is unavailable"


def test_status_link_is_not_paid(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Заказ существует с момента создания ссылки
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=payment_order("CREATED"))

    resp = post_status(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["code"] is None
    assert data["message"] is None
    assert data["external_id"] == STATUS_ORDER_GUID


def test_invalid_terminal_data(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    invalid_terminal = dump_terminal_data(terminal_data)
    invalid_terminal.pop("merchant_account_guid")

    resp = post_status(client, invalid_terminal)

    data = assert_pending(resp, gate_lib_const.VALIDATION_ERROR)
    assert data["message"] == "Terminal data is not valid"
    assert not httpx_mock.get_requests()


def test_status_unsupported_currency(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_status(client, terminal_data, currency_code="USD")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    assert data["message"] == "Currency USD is not supported"
    assert data["currency_code"] == "USD"
    # NambaOne работает только с KGS, поэтому провайдера даже не спрашивают
    assert not httpx_mock.get_requests()


def test_status_without_invoice_id(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_status(client, terminal_data, invoice_id=None, withdrawal_id="00000000-0000-4000-8000-000000000011")

    data = assert_pending(resp, gate_lib_const.VALIDATION_ERROR)
    assert data["message"] == "invoice_id is required"
    assert not httpx_mock.get_requests()


def test_request_validation(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_status(client, terminal_data, invoice_id=None)

    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    assert "status" not in data
    assert not httpx_mock.get_requests()
