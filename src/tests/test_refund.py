import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.nambaone.sender import sign
from gate_nambaone.schemas.terminal_data import TerminalData
from tests.conftest import API_VERSION
from tests.conftest import CALLBACK_URL_INVOICE
from tests.conftest import MERCHANT_ACCOUNT_GUID
from tests.conftest import SECRET_KEY
from tests.conftest import dump_terminal_data
from tests.conftest import nambaone_error
from tests.conftest import nambaone_ok
from tests.conftest import nambaone_path
from tests.conftest import nambaone_url

REFUND_ID = "00000000-0000-4000-8000-000000000031"
REFUND_INVOICE_ID = "00000000-0000-4000-8000-000000000032"
# guid заказа на оплату, сделанного по платежной ссылке
REFUND_ORDER_GUID = "00000000-0000-4000-8000-000000000033"
# guid заказа на возврат в NambaOne
REFUND_GUID = "00000000-0000-4000-8000-000000000034"
REFUND_AMOUNT = "100.00"
REFUND_CURRENCY = "KGS"
CALLBACK_URL_REFUND = "https://test-gate.com/callback/refund"

# Платеж для возврата ищется по externalId платежной ссылки, то есть по id счета
GET_ORDER_PATH = f"/v1/{MERCHANT_ACCOUNT_GUID}/one-time/{REFUND_INVOICE_ID}"
CREATE_REFUND_PATH = f"/v1/{MERCHANT_ACCOUNT_GUID}/refund/{REFUND_ID}"


def get_provider_order_url(terminal_data: TerminalData) -> str:
    return nambaone_url(terminal_data, GET_ORDER_PATH)


def get_provider_refund_url(terminal_data: TerminalData) -> str:
    return nambaone_url(terminal_data, CREATE_REFUND_PATH)


def payment_order(status: str = "COMPLETED") -> dict[str, Any]:
    """Ответ NambaOne "получить платеж по одноразовой ссылке"; суммы в минорных единицах (тыйынах)."""
    return nambaone_ok(
        {
            "guid": REFUND_ORDER_GUID,
            "status": status,
            "currency": REFUND_CURRENCY,
            "amount": "10000",
            "paymentAmount": "10000",
        }
    )


def refund_order(status: str, **overrides: Any) -> dict[str, Any]:
    """Ответ NambaOne "создать возврат"; суммы в минорных единицах (тыйынах)."""
    data = {
        "guid": REFUND_GUID,
        "status": status,
        "currency": REFUND_CURRENCY,
        "amount": "10000",
        "externalGuid": REFUND_ID,
    }
    return nambaone_ok({**data, **overrides})


def mock_payment_order(httpx_mock: HTTPXMock, terminal_data: TerminalData) -> None:
    httpx_mock.add_response(method="GET", url=get_provider_order_url(terminal_data), json=payment_order())


def mock_refund_not_found(httpx_mock: HTTPXMock, terminal_data: TerminalData) -> None:
    """После отказа гейт проверяет, существует ли уже возврат: здесь его нет."""
    httpx_mock.add_response(
        method="GET",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error("REFUND_ORDER_NOT_FOUND", "Refund order not found"),
        status_code=404,
    )


def post_refund(client: TestClient, terminal_data: TerminalData | dict[str, Any], **overrides: Any):
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/refund",
        json={
            "refund_id": REFUND_ID,
            "invoice_id": REFUND_INVOICE_ID,
            "external_id": REFUND_ORDER_GUID,
            "amount": REFUND_AMOUNT,
            "currency_code": REFUND_CURRENCY,
            "terminal_data": terminal_json,
            **overrides,
        },
    )


def assert_refund(resp, status: str, code: str | None) -> dict[str, Any]:
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == status
    assert data["code"] == code
    assert data["amount"] == REFUND_AMOUNT
    assert data["currency_code"] == REFUND_CURRENCY
    return data


def test_refund_success(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(method="POST", url=get_provider_refund_url(terminal_data), json=refund_order("COMPLETED"))

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.COMPLETE, None)
    assert data["external_id"] == REFUND_GUID
    assert data["message"] is None

    request = httpx_mock.get_request(method="POST")
    assert json.loads(request.content) == {
        "parentType": "PAYMENT_QR",
        "paymentOrderGuid": REFUND_ORDER_GUID,
        "webhookUrl": CALLBACK_URL_INVOICE,
        "amount": "10000",
        "comment": f"Refund {REFUND_ID} of invoice {REFUND_INVOICE_ID}",
    }


def test_refund_request_is_signed(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(method="POST", url=get_provider_refund_url(terminal_data), json=refund_order("CREATED"))

    post_refund(client, terminal_data)

    request = httpx_mock.get_request(method="POST")
    salt = request.headers["x-merchant-api-salt"]
    expected = sign(SECRET_KEY, nambaone_path(CREATE_REFUND_PATH), request.content.decode(), salt)
    assert request.headers["x-merchant-api-signature"] == expected


def test_refund_with_refund_callback_url(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(method="POST", url=get_provider_refund_url(terminal_data), json=refund_order("CREATED"))
    terminal_json = {**dump_terminal_data(terminal_data), "provider_callback_url_refund": CALLBACK_URL_REFUND}

    post_refund(client, terminal_json)

    body = json.loads(httpx_mock.get_request(method="POST").content)
    assert body["webhookUrl"] == CALLBACK_URL_REFUND


def test_refund_partial_amount(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST", url=get_provider_refund_url(terminal_data), json=refund_order("CREATED", amount="2550")
    )

    resp = post_refund(client, terminal_data, amount="25.50")

    assert resp.json()["amount"] == "25.50"
    assert json.loads(httpx_mock.get_request(method="POST").content)["amount"] == "2550"


@pytest.mark.parametrize("provider_status", ["CREATED", "STUCK", "SOMETHING_NEW"])
def test_refund_pending(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, provider_status: str
):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST", url=get_provider_refund_url(terminal_data), json=refund_order(provider_status)
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.PENDING, None)
    assert data["external_id"] == REFUND_GUID


@pytest.mark.parametrize(
    "error_code,message",
    [
        ("01", "Requisites not found"),
        ("02", "Provider is unavailable"),
        ("03", "Unrecognized response"),
        (None, "Refund FAILED"),
    ],
)
def test_refund_failed(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
    error_code: str | None,
    message: str,
):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST", url=get_provider_refund_url(terminal_data), json=refund_order("FAILED", errorCode=error_code)
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, gate_lib_const.PROVIDER_ERROR)
    assert data["external_id"] == REFUND_GUID
    assert data["message"] == message


@pytest.mark.parametrize("provider_status", ["CANCELED", "EXPIRED"])
def test_refund_canceled(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, provider_status: str
):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST", url=get_provider_refund_url(terminal_data), json=refund_order(provider_status)
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == f"Refund {provider_status}"


def test_refund_of_refunded_payment(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Частично возвращенный платеж можно вернуть еще раз: осталось ли что вернуть, проверяет NambaOne
    httpx_mock.add_response(
        method="GET", url=get_provider_order_url(terminal_data), json=payment_order("REFUNDED")
    )
    httpx_mock.add_response(method="POST", url=get_provider_refund_url(terminal_data), json=refund_order("CREATED"))

    resp = post_refund(client, terminal_data)

    assert_refund(resp, gate_lib_const.PENDING, None)


@pytest.mark.parametrize(
    "provider_status",
    [
        "CREATED",
        "PAYER_DEBIT",
        "PAYER_DEBIT_SUCCESSFUL",
        "PROCESSING",
        "CANCELED",
        "FAILED",
        "EXPIRED",
        "CANCELLATION_ATTEMPTED",
        "CANCELLATION_FAILED",
        "SOMETHING_NEW",
    ],
)
def test_refund_payment_is_not_completed(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, provider_status: str
):
    # Деньги не получены (или платеж не прошел): возвращать нечего
    httpx_mock.add_response(
        method="GET", url=get_provider_order_url(terminal_data), json=payment_order(provider_status)
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == f"Payment {provider_status} cannot be refunded"
    assert not httpx_mock.get_requests(method="POST")


@pytest.mark.parametrize("data", [None, {}])
def test_refund_payment_order_not_found(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, data: dict[str, Any] | None
):
    # Пустой ответ: NambaOne не знает платежную ссылку, возвращать нечего
    httpx_mock.add_response(method="GET", url=get_provider_order_url(terminal_data), json=nambaone_ok(data))

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == "Payment order not found"
    assert not httpx_mock.get_requests(method="POST")


@pytest.mark.parametrize(
    "response",
    [
        {"json": {}},
        {"json": nambaone_ok({"guid": REFUND_ORDER_GUID})},
        {"status_code": 500, "text": "Internal Server Error"},
    ],
)
def test_refund_payment_lookup_invalid_response(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, response: dict[str, Any]
):
    # Непонятный ответ - это сбой NambaOne, а не неоплаченная ссылка; возврат не отправлен, поэтому отказ
    httpx_mock.add_response(method="GET", url=get_provider_order_url(terminal_data), **response)

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, "provider_unavailable")
    assert data["message"] == "Failed to find the payment to refund"
    assert not httpx_mock.get_requests(method="POST")


def test_refund_payment_lookup_timeout(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Возврат еще не отправлен, поэтому даже таймаут поиска платежа означает точный отказ
    httpx_mock.add_exception(
        httpx.ReadTimeout("Simulated timeout"), method="GET", url=get_provider_order_url(terminal_data)
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, "provider_unavailable")
    assert data["message"] == "Failed to find the payment to refund"
    assert not httpx_mock.get_requests(method="POST")


def test_refund_payment_lookup_rejected(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=get_provider_order_url(terminal_data),
        json=nambaone_error("MERCHANT_API_WRONG_SIGNATURE", "Wrong signature"),
        status_code=401,
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, "provider_unavailable")
    assert data["message"] == "Failed to find the payment to refund"
    assert not httpx_mock.get_requests(method="POST")


def test_refund_rejected_by_provider(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error("VALIDATION_ERROR", "amount is greater than the payment"),
        status_code=400,
    )

    mock_refund_not_found(httpx_mock, terminal_data)

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == "amount is greater than the payment"


@pytest.mark.parametrize("error_code", ["UNKNOWN_ERROR", "UKNOWN_ERROR"])
def test_refund_unknown_provider_error(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, error_code: str
):
    # Возврат мог быть создан, поэтому его итог выясняется через refund_status. UKNOWN_ERROR - написание из документации
    # NambaOne, означает то же самое.
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error(error_code, "Something went wrong"),
        status_code=500,
    )

    mock_refund_not_found(httpx_mock, terminal_data)

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.PENDING, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == "Something went wrong"


def test_refund_rejected_with_new_error_code(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Код, которого нет в ErrorCodeEnum, - все равно отказ со своим сообщением, а не нечитаемый ответ
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error("REFUND_AMOUNT_EXCEEDED", "Refund amount exceeds the payment"),
        status_code=400,
    )

    mock_refund_not_found(httpx_mock, terminal_data)

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == "Refund amount exceeds the payment"


def test_refund_rejected_without_message(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json={"status": "ERROR", "error": {"errorCode": "REFUND_AMOUNT_EXCEEDED"}},
        status_code=400,
    )

    mock_refund_not_found(httpx_mock, terminal_data)

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.FAILED, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == "REFUND_AMOUNT_EXCEEDED"


@pytest.mark.parametrize(
    "provider_status,status",
    [
        ("COMPLETED", gate_lib_const.COMPLETE),
        ("CREATED", gate_lib_const.PENDING),
        ("FAILED", gate_lib_const.FAILED),
    ],
)
def test_refund_repeat_returns_existing_refund(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, provider_status: str, status: str
):
    # Первая попытка упала по таймауту, но возврат создала: повтор отклоняется как дубль, и гейт отвечает статусом
    # существующего возврата, а не отклоняет его
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error("REFUND_ORDER_ALREADY_EXISTS", "Refund order already exists"),
        status_code=400,
    )
    httpx_mock.add_response(
        method="GET", url=get_provider_refund_url(terminal_data), json=refund_order(provider_status)
    )

    resp = post_refund(client, terminal_data)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == status
    assert data["external_id"] == REFUND_GUID
    assert data["amount"] == REFUND_AMOUNT
    # Проверка идет по тому же id возврата
    lookup = httpx_mock.get_request(method="GET", url=get_provider_refund_url(terminal_data))
    assert lookup.content == b""


@pytest.mark.parametrize("existing_amount,is_reported", [("2550", True), ("10000", False), (None, False)])
def test_refund_repeat_with_other_amount_is_reported(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
    capfd: pytest.CaptureFixture[str],
    existing_amount: str | None,
    is_reported: bool,
):
    # Существующий возврат все равно возвращается, но повтор с другой суммой - это не тот же возврат
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error("REFUND_ORDER_ALREADY_EXISTS", "Refund order already exists"),
        status_code=400,
    )
    httpx_mock.add_response(
        method="GET",
        url=get_provider_refund_url(terminal_data),
        json=refund_order("COMPLETED", amount=existing_amount),
    )
    capfd.readouterr()

    resp = post_refund(client, terminal_data)

    assert resp.json()["status"] == gate_lib_const.COMPLETE
    # structlog пишет в файловый дескриптор stdout
    assert ("nambaone_refund_already_exists_with_other_amount" in capfd.readouterr().out) is is_reported


def test_refund_unknown_error_returns_existing_refund(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # UNKNOWN_ERROR оставляет итог неясным: если возврат существует, возвращается его настоящий статус
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error("UNKNOWN_ERROR", "Something went wrong"),
        status_code=500,
    )
    httpx_mock.add_response(
        method="GET", url=get_provider_refund_url(terminal_data), json=refund_order("COMPLETED")
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.COMPLETE, None)
    assert data["external_id"] == REFUND_GUID


def test_refund_rejected_and_lookup_timeout(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Возврат мог быть создан предыдущей попыткой, и проверить его нельзя: итог неизвестен
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error("REFUND_ORDER_ALREADY_EXISTS", "Refund order already exists"),
        status_code=400,
    )
    httpx_mock.add_exception(
        httpx.ReadTimeout("Simulated timeout"), method="GET", url=get_provider_refund_url(terminal_data)
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.PENDING, "provider_unavailable")
    assert data["message"] == "NambaOne is unavailable"


def test_refund_rejected_and_lookup_invalid_response(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST",
        url=get_provider_refund_url(terminal_data),
        json=nambaone_error("REFUND_ORDER_ALREADY_EXISTS", "Refund order already exists"),
        status_code=400,
    )
    httpx_mock.add_response(
        method="GET", url=get_provider_refund_url(terminal_data), status_code=500, text="Internal Server Error"
    )

    resp = post_refund(client, terminal_data)

    assert_refund(resp, gate_lib_const.PENDING, "provider_unavailable")


def test_refund_timeout_is_not_checked(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # Проверяется только отказ: после таймаута итог выясняется через refund_status
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_exception(
        httpx.ReadTimeout("Simulated timeout"), method="POST", url=get_provider_refund_url(terminal_data)
    )

    post_refund(client, terminal_data)

    assert not httpx_mock.get_requests(method="GET", url=get_provider_refund_url(terminal_data))


def test_timeout(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_exception(
        httpx.ReadTimeout("Simulated timeout"), method="POST", url=get_provider_refund_url(terminal_data)
    )

    resp = post_refund(client, terminal_data)

    data = assert_refund(resp, gate_lib_const.PENDING, "provider_unavailable")
    assert data["message"] == "NambaOne is unavailable"


def test_incorrect_response_with_status_code200(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(method="POST", url=get_provider_refund_url(terminal_data), json={}, status_code=200)

    resp = post_refund(client, terminal_data)

    assert_refund(resp, gate_lib_const.PENDING, "provider_unavailable")


def test_incorrect_response_with_status_code500(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    mock_payment_order(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="POST", url=get_provider_refund_url(terminal_data), status_code=500, text="Internal Server Error"
    )

    resp = post_refund(client, terminal_data)

    assert_refund(resp, gate_lib_const.PENDING, "provider_unavailable")


def test_invalid_terminal_data(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    invalid_terminal = dump_terminal_data(terminal_data)
    invalid_terminal.pop("provider_secret_key")

    resp = post_refund(client, invalid_terminal)

    data = assert_refund(resp, gate_lib_const.FAILED, gate_lib_const.VALIDATION_ERROR)
    assert data["message"] == "Terminal data is not valid"
    assert not httpx_mock.get_requests()


def test_refund_unsupported_currency(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    resp = post_refund(client, terminal_data, currency_code="USD")

    assert resp.status_code == 200
    data = resp.json()
    # Возврат никуда не отправлен, поэтому это точный отказ, а не pending
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    assert data["message"] == "Currency USD is not supported"
    assert data["amount"] == REFUND_AMOUNT
    assert data["currency_code"] == "USD"
    # NambaOne работает только с KGS, поэтому провайдера даже не спрашивают
    assert not httpx_mock.get_requests()


def test_refund_amount_in_fractions_of_tyiyn(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    # NambaOne работает в целых тыйынах: такой возврат нельзя отправить, поэтому это точный отказ
    resp = post_refund(client, terminal_data, amount="100.001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    assert data["message"] == "Amount 100.001 has more than 2 decimal places"
    # Даже платеж не ищется
    assert not httpx_mock.get_requests()


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "0"},
        {"amount": "-1"},
        {"currency_code": "SOM1"},
        {"refund_id": ""},
        {"invoice_id": ""},
        {"invoice_id": None},
    ],
)
def test_request_validation(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, overrides: dict[str, Any]
):
    resp = post_refund(client, terminal_data, **overrides)

    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    # Невалидный запрос - это не неуспешная операция
    assert "status" not in data
    assert not httpx_mock.get_requests()
