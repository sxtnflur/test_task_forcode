"""
Вебхуки NambaOne о платежах.

Вебхуки не подписаны, поэтому из них берется только id счета: счет и его терминал
берутся из процессинга, а статус платежа запрашивается через API NambaOne.
Ответ не 2xx заставляет NambaOne повторить вебхук.
"""

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData
from main import settings
from tests.conftest import MERCHANT_ACCOUNT_GUID
from tests.conftest import SBANK_API_URL
from tests.conftest import dump_terminal_data
from tests.conftest import nambaone_error
from tests.conftest import nambaone_ok
from tests.conftest import nambaone_url

SBANK_RADMIN_URL = "http://test-sbank-radmin.com"

NOTIFICATION_INVOICE_ID = "00000000-0000-4000-8000-000000000051"
# То, что процессинг знает как external_id: guid платежной ссылки
NOTIFICATION_LINK_GUID = "00000000-0000-4000-8000-000000000052"
# guid заказа на оплату, сделанного по ссылке
NOTIFICATION_ORDER_GUID = "00000000-0000-4000-8000-000000000053"
NOTIFICATION_TERMINAL_ID = "7"
NOTIFICATION_CURRENCY = "KGS"

GET_ORDER_PATH = f"/v1/{MERCHANT_ACCOUNT_GUID}/one-time/{NOTIFICATION_INVOICE_ID}"
INVOICE_URL = f"{SBANK_API_URL}/invoices/{NOTIFICATION_INVOICE_ID}"
TERMINAL_URL = f"{SBANK_RADMIN_URL}/terminals/{NOTIFICATION_TERMINAL_ID}"


def get_provider_status_url(terminal_data: TerminalData) -> str:
    return nambaone_url(terminal_data, GET_ORDER_PATH)


def payment_webhook(**overrides: Any) -> dict[str, Any]:
    """Тело вебхука NambaOne "Payment Order Updated"."""
    data = {
        "guid": NOTIFICATION_ORDER_GUID,
        "status": "COMPLETED",
        "externalId": NOTIFICATION_INVOICE_ID,
        "amount": "100000",
    }
    return {"type": "PAYMENT_ORDER", "data": {**data, **overrides}}


def payment_order(status: str, **overrides: Any) -> dict[str, Any]:
    """Ответ NambaOne "получить платеж по одноразовой ссылке"; суммы в минорных единицах (тыйынах)."""
    data = {
        "guid": NOTIFICATION_ORDER_GUID,
        "status": status,
        "currency": NOTIFICATION_CURRENCY,
        "amount": "100000",
        "paymentAmount": "100000",
    }
    return nambaone_ok({**data, **overrides})


def mock_invoice(httpx_mock: HTTPXMock, terminal_data: TerminalData | dict[str, Any]) -> None:
    """Счет и настройки его терминала в процессинге."""
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    httpx_mock.add_response(
        method="GET",
        url=INVOICE_URL,
        json={
            "id": NOTIFICATION_INVOICE_ID,
            "primary_terminal": int(NOTIFICATION_TERMINAL_ID),
            "currency_code": NOTIFICATION_CURRENCY,
            "amount": "1000.00",
            "external_id": NOTIFICATION_LINK_GUID,
        },
    )
    httpx_mock.add_response(
        method="GET", url=TERMINAL_URL, json={"id": NOTIFICATION_TERMINAL_ID, "data": terminal_json}
    )


def post_notification(client: TestClient, body: dict[str, Any]):
    return client.post(f"{settings.NOTIFICATIONS_PREFIX}/callback/invoice", json=body)


def assert_ok(resp) -> None:
    assert resp.status_code == 200
    assert resp.text == "OK"


def assert_retry(resp) -> None:
    # NambaOne повторяет вебхук на любой ответ не 2xx
    assert resp.status_code == 503
    assert resp.text == "RETRY"


def assert_invoice_not_updated(httpx_mock: HTTPXMock) -> None:
    assert not httpx_mock.get_requests(method="POST", url=f"{INVOICE_URL}/income")
    assert not httpx_mock.get_requests(method="POST", url=f"{INVOICE_URL}/fail")


def test_invoice_notification_complete(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=payment_order("COMPLETED"))
    httpx_mock.add_response(method="POST", url=f"{INVOICE_URL}/income", json={})

    resp = post_notification(client, payment_webhook())

    assert_ok(resp)
    income = httpx_mock.get_request(method="POST", url=f"{INVOICE_URL}/income")
    assert json.loads(income.content) == {
        "amount_paid": "1000.00",
        "external_transaction_id": NOTIFICATION_ORDER_GUID,
    }


def test_invoice_notification_amount_is_what_was_paid(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="GET",
        url=get_provider_status_url(terminal_data),
        json=payment_order("COMPLETED", paymentAmount="99950"),
    )
    httpx_mock.add_response(method="POST", url=f"{INVOICE_URL}/income", json={})

    post_notification(client, payment_webhook())

    income = httpx_mock.get_request(method="POST", url=f"{INVOICE_URL}/income")
    assert json.loads(income.content)["amount_paid"] == "999.50"


@pytest.mark.parametrize("provider_status", ["CANCELED", "FAILED", "EXPIRED"])
def test_invoice_notification_failed(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, provider_status: str
):
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="GET", url=get_provider_status_url(terminal_data), json=payment_order(provider_status)
    )
    httpx_mock.add_response(method="POST", url=f"{INVOICE_URL}/fail", json={})

    resp = post_notification(client, payment_webhook(status=provider_status))

    assert_ok(resp)
    fail = httpx_mock.get_request(method="POST", url=f"{INVOICE_URL}/fail")
    assert json.loads(fail.content) == {
        "error_code": gate_lib_const.PROVIDER_ERROR,
        "error_message": f"Payment {provider_status}",
        "external_id": NOTIFICATION_ORDER_GUID,
        "payment_gate_iname": settings.ELASTIC_APM_SERVICE_NAME,
    }


def test_invoice_notification_status_is_taken_from_api(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # Вебхук не подписан: его статусу не доверяем, API говорит, что платеж еще в процессе
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=payment_order("PROCESSING"))

    resp = post_notification(client, payment_webhook(status="COMPLETED"))

    assert_retry(resp)
    assert_invoice_not_updated(httpx_mock)


def test_invoice_notification_link_is_not_paid(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # Еще не оплаченная ссылка - это заказ в статусе CREATED
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=payment_order("CREATED"))

    resp = post_notification(client, payment_webhook(status="CREATED"))

    assert_retry(resp)
    assert_invoice_not_updated(httpx_mock)


def test_invoice_notification_payment_order_not_found(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # NambaOne пока не знает ссылку: счет не отклоняется, вебхук повторяется
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=nambaone_ok(None))

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)
    assert_invoice_not_updated(httpx_mock)


def test_invoice_notification_provider_invalid_response(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json={})

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)
    assert_invoice_not_updated(httpx_mock)


def test_invoice_notification_provider_timeout(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_exception(
        httpx.ReadTimeout("Simulated timeout"), method="GET", url=get_provider_status_url(terminal_data)
    )

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)
    assert_invoice_not_updated(httpx_mock)


def test_invoice_notification_rejected_by_provider(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # Отказ на запрос статуса ничего не говорит о платеже: счет не отклоняется
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="GET",
        url=get_provider_status_url(terminal_data),
        json=nambaone_error("MERCHANT_API_WRONG_SIGNATURE", "Wrong signature"),
        status_code=401,
    )

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)
    assert_invoice_not_updated(httpx_mock)


def test_invoice_notification_invalid_terminal_data(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # Вебхук повторяется, поэтому настройки терминала можно исправить, пока NambaOne продолжает его присылать
    invalid_terminal = dump_terminal_data(terminal_data)
    invalid_terminal.pop("provider_secret_key")
    mock_invoice(httpx_mock, invalid_terminal)

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)
    assert not httpx_mock.get_requests(url=get_provider_status_url(terminal_data))
    assert_invoice_not_updated(httpx_mock)


def test_invoice_notification_external_id_cannot_change_processing_path(client: TestClient, httpx_mock: HTTPXMock):
    # Вебхук не подписан: его id экранируется и не может вести к другому ресурсу процессинга
    escaped_url = f"{SBANK_API_URL}/invoices/..%2Fwithdrawals%2F42"
    httpx_mock.add_response(method="GET", url=escaped_url, status_code=404)

    resp = post_notification(client, payment_webhook(externalId="../withdrawals/42"))

    # Процессинг не знает такой счет: вебхук игнорируется
    assert_ok(resp)
    assert [request.url.raw_path for request in httpx_mock.get_requests()] == [b"/invoices/..%2Fwithdrawals%2F42"]


@pytest.mark.parametrize("external_id", [".", ".."])
def test_invoice_notification_dot_segment_external_id(
    client: TestClient, httpx_mock: HTTPXMock, external_id: str
):
    resp = post_notification(client, payment_webhook(externalId=external_id))

    # Такой id никогда не может быть счетом процессинга: повторять вебхук бесполезно
    assert_ok(resp)
    # Его вообще нельзя подставить в путь
    assert not httpx_mock.get_requests()


def test_invoice_notification_invoice_in_other_currency(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # Для такого счета платежная ссылка не создается: вебхук игнорируется, а не повторяется в течение часа
    httpx_mock.add_response(
        method="GET",
        url=INVOICE_URL,
        json={"id": NOTIFICATION_INVOICE_ID, "primary_terminal": NOTIFICATION_TERMINAL_ID, "currency_code": "USD"},
    )
    httpx_mock.add_response(
        method="GET", url=TERMINAL_URL, json={"id": NOTIFICATION_TERMINAL_ID, "data": dump_terminal_data(terminal_data)}
    )

    resp = post_notification(client, payment_webhook())

    assert_ok(resp)
    assert not httpx_mock.get_requests(url=get_provider_status_url(terminal_data))
    assert_invoice_not_updated(httpx_mock)


def test_invoice_notification_invoice_is_unknown(client: TestClient, httpx_mock: HTTPXMock):
    # Например, платежная ссылка, созданная не через гейт: счет не появится, поэтому вебхук игнорируется, а не
    # повторяется в течение часа
    httpx_mock.add_response(method="GET", url=INVOICE_URL, status_code=404)

    resp = post_notification(client, payment_webhook())

    assert_ok(resp)
    # NambaOne не спрашивают о счете, который процессинг не знает
    assert [request.url for request in httpx_mock.get_requests()] == [INVOICE_URL]


@pytest.mark.parametrize("status_code", [401, 500, 503])
def test_invoice_notification_invoice_is_unavailable(client: TestClient, httpx_mock: HTTPXMock, status_code: int):
    httpx_mock.add_response(method="GET", url=INVOICE_URL, status_code=status_code)

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)
    assert [request.url for request in httpx_mock.get_requests()] == [INVOICE_URL]


def test_invoice_notification_invoice_request_failed(client: TestClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"), method="GET", url=INVOICE_URL)

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)


def test_invoice_notification_terminal_is_not_found(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    # Счет существует, значит, должен существовать и его терминал: 404 здесь - проблема настроек, вебхук повторяется
    httpx_mock.add_response(
        method="GET",
        url=INVOICE_URL,
        json={
            "id": NOTIFICATION_INVOICE_ID,
            "primary_terminal": NOTIFICATION_TERMINAL_ID,
            "currency_code": NOTIFICATION_CURRENCY,
        },
    )
    httpx_mock.add_response(method="GET", url=TERMINAL_URL, status_code=404)

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)
    assert not httpx_mock.get_requests(url=get_provider_status_url(terminal_data))


def test_invoice_notification_terminal_is_unavailable(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock
):
    httpx_mock.add_response(
        method="GET",
        url=INVOICE_URL,
        json={
            "id": NOTIFICATION_INVOICE_ID,
            "primary_terminal": NOTIFICATION_TERMINAL_ID,
            "currency_code": NOTIFICATION_CURRENCY,
        },
    )
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"), method="GET", url=TERMINAL_URL)

    resp = post_notification(client, payment_webhook())

    assert_retry(resp)
    assert not httpx_mock.get_requests(url=get_provider_status_url(terminal_data))


@pytest.mark.parametrize("provider_status,sbank_path", [("COMPLETED", "income"), ("FAILED", "fail")])
def test_invoice_notification_invoice_is_not_updated(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
    provider_status: str,
    sbank_path: str,
):
    # Процессинг не сохранил результат: вебхук повторяется, процессинг должен обрабатывать повторы
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(
        method="GET", url=get_provider_status_url(terminal_data), json=payment_order(provider_status)
    )
    httpx_mock.add_response(method="POST", url=f"{INVOICE_URL}/{sbank_path}", status_code=500)

    resp = post_notification(client, payment_webhook(status=provider_status))

    assert_retry(resp)


def test_refund_notification_is_ignored(client: TestClient, httpx_mock: HTTPXMock):
    # Статус возврата процессинг опрашивает сам через refund_status
    body = {
        "type": "REFUND_ORDER",
        "data": {"guid": "test-refund-guid", "status": "COMPLETED", "externalGuid": "test-refund-id"},
    }

    resp = post_notification(client, body)

    assert_ok(resp)
    assert not httpx_mock.get_requests()


def test_unknown_notification_is_ignored(client: TestClient, httpx_mock: HTTPXMock):
    resp = post_notification(client, {"type": "SOMETHING_NEW", "data": {"guid": "test-guid"}})

    assert_ok(resp)
    assert not httpx_mock.get_requests()


def test_payment_notification_without_external_id_is_ignored(client: TestClient, httpx_mock: HTTPXMock):
    # Платеж, сделанный не по нашей платежной ссылке, нельзя сопоставить со счетом
    resp = post_notification(client, payment_webhook(externalId=None))

    assert_ok(resp)
    assert not httpx_mock.get_requests()


def test_notification_with_unknown_fields(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock):
    mock_invoice(httpx_mock, terminal_data)
    httpx_mock.add_response(method="GET", url=get_provider_status_url(terminal_data), json=payment_order("COMPLETED"))
    httpx_mock.add_response(method="POST", url=f"{INVOICE_URL}/income", json={})
    body = payment_webhook(newField="value")
    body["eventId"] = "test-event-id"

    resp = post_notification(client, body)

    assert_ok(resp)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"type": "PAYMENT_ORDER"},
        {"data": {"guid": NOTIFICATION_ORDER_GUID}},
        {"type": "PAYMENT_ORDER", "data": {"externalId": NOTIFICATION_INVOICE_ID}},
    ],
)
def test_request_validation(client: TestClient, httpx_mock: HTTPXMock, body: dict[str, Any]):
    resp = post_notification(client, body)

    assert resp.status_code == 422
    assert not httpx_mock.get_requests()
