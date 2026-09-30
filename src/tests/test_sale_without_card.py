"""Sale без card_token: плательщика перенаправляют на одноразовую платежную ссылку NambaOne."""

import json
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from gate_lib import const as gate_lib_const
from pytest_httpx import HTTPXMock

from gate_nambaone.nambaone.sender import sign
from gate_nambaone.schemas.terminal_data import TerminalData
from main import settings
from tests.conftest import API_VERSION
from tests.conftest import CALLBACK_URL_INVOICE
from tests.conftest import MERCHANT_ACCOUNT_GUID
from tests.conftest import SBANK_API_URL
from tests.conftest import SECRET_KEY
from tests.conftest import dump_terminal_data
from tests.conftest import nambaone_error
from tests.conftest import nambaone_ok
from tests.conftest import nambaone_path
from tests.conftest import nambaone_url

SALE_AMOUNT = "100.00"
SALE_CURRENCY = "KGS"
LINK_GUID = "00000000-0000-4000-8000-000000000021"
LINK_TOKEN = "https://app.nambaone.kg/pay/test-token"
SECURE_REDIRECT_URL = "https://secure.test-gate.com/redirect"

CREATE_LINK_PATH = f"/v2/{MERCHANT_ACCOUNT_GUID}/one-time"


@pytest.fixture
def invoice_id() -> str:
    return str(uuid.uuid4())


def get_provider_sale_url(terminal_data: TerminalData) -> str:
    return nambaone_url(terminal_data, CREATE_LINK_PATH)


def payment_link(**overrides: Any) -> dict[str, Any]:
    """Ответ NambaOne "создать одноразовую платежную ссылку"."""
    return nambaone_ok({"guid": LINK_GUID, "token": LINK_TOKEN, "status": "ACTIVE", **overrides})


def post_sale(
    client: TestClient,
    terminal_data: TerminalData | dict[str, Any],
    invoice_id: str,
    **overrides: Any,
):
    terminal_json = dump_terminal_data(terminal_data) if isinstance(terminal_data, TerminalData) else terminal_data
    return client.post(
        f"/{API_VERSION}/sale",
        json={
            "invoice_id": invoice_id,
            "amount": SALE_AMOUNT,
            "currency_code": SALE_CURRENCY,
            "exchange_currency_code": None,
            "terminal_data": terminal_json,
            "email": "user@example.com",
            **overrides,
        },
    )


def assert_failed(resp, code: str) -> dict[str, Any]:
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.FAILED
    assert data["code"] == code
    assert data["redirect"] is None
    return data


def test_sale_without_card_success(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(method="POST", url=get_provider_sale_url(terminal_data), json=payment_link())

    resp = post_sale(client, terminal_data, invoice_id)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["amount"] == SALE_AMOUNT
    assert data["currency_code"] == SALE_CURRENCY
    assert data["external_id"] == LINK_GUID
    assert data["redirect"] == {"url": LINK_TOKEN, "method": "GET", "params": {}}
    assert data["code"] is None

    request = httpx_mock.get_request()
    assert json.loads(request.content) == {
        "externalId": invoice_id,
        "amount": "10000",
        "amountCanBeChanged": False,
        "webhookUrl": CALLBACK_URL_INVOICE,
    }


def test_sale_without_card_request_is_signed(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(method="POST", url=get_provider_sale_url(terminal_data), json=payment_link())

    post_sale(client, terminal_data, invoice_id)

    request = httpx_mock.get_request()
    salt = request.headers["x-merchant-api-salt"]
    expected = sign(SECRET_KEY, nambaone_path(CREATE_LINK_PATH), request.content.decode(), salt)
    assert request.headers["x-merchant-api-signature"] == expected


def test_sale_without_card_with_finish_url_and_employee(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(method="POST", url=get_provider_sale_url(terminal_data), json=payment_link())
    terminal_json = {**dump_terminal_data(terminal_data), "merchant_employee_guid": "test-employee-guid"}

    resp = post_sale(client, terminal_json, invoice_id, finish_url="https://finish.com")

    assert resp.json()["status"] == gate_lib_const.PENDING
    body = json.loads(httpx_mock.get_request().content)
    assert body["webOptions"] == {"redirectLink": "https://finish.com"}
    assert body["merchantEmployeeGuid"] == "test-employee-guid"


def test_sale_without_card_with_secure_redirect(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(method="POST", url=get_provider_sale_url(terminal_data), json=payment_link())
    httpx_mock.add_response(method="PATCH", url=f"{SBANK_API_URL}/invoices/{invoice_id}", json={})
    terminal_json = {**dump_terminal_data(terminal_data), "secure_redirect_url": SECURE_REDIRECT_URL}

    resp = post_sale(client, terminal_json, invoice_id)

    data = resp.json()
    assert data["status"] == gate_lib_const.PENDING
    assert data["external_id"] == LINK_GUID

    # Плательщик попадает на страницу secure redirect, а сама платежная ссылка сохраняется в процессинге
    redirect_url = urlparse(data["redirect"]["url"])
    assert f"{redirect_url.scheme}://{redirect_url.netloc}{redirect_url.path}" == SECURE_REDIRECT_URL
    query: dict[str, list[str]] = parse_qs(redirect_url.query)
    assert query["invoice_id"] == [invoice_id]
    assert set(query) == {"invoice_id", "nonce", "timestamp", "signature"}

    sbank_request = httpx_mock.get_request(method="PATCH")
    secure_redirect_data = json.loads(json.loads(sbank_request.content)["secure_redirect_data"])
    assert secure_redirect_data == {"url": LINK_TOKEN, "method": "GET", "payload": []}


def test_sale_without_card_secure_redirect_is_not_saved(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(method="POST", url=get_provider_sale_url(terminal_data), json=payment_link())
    httpx_mock.add_response(method="PATCH", url=f"{SBANK_API_URL}/invoices/{invoice_id}", status_code=500)
    terminal_json = {**dump_terminal_data(terminal_data), "secure_redirect_url": SECURE_REDIRECT_URL}

    resp = post_sale(client, terminal_json, invoice_id)

    data = assert_failed(resp, gate_lib_const.INTERNAL_ERROR)
    assert data["message"] == "Failed to create payment"


def test_sale_without_card_rejected_by_provider(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(
        method="POST",
        url=get_provider_sale_url(terminal_data),
        json=nambaone_error("VALIDATION_ERROR", "amount must be positive"),
        status_code=400,
    )

    resp = post_sale(client, terminal_data, invoice_id)

    data = assert_failed(resp, gate_lib_const.PROVIDER_ERROR)
    assert data["message"] == "amount must be positive"


def test_sale_without_card_unknown_provider_error(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    # Ссылку плательщику не отдали, поэтому даже непонятный ответ отклоняет продажу
    httpx_mock.add_response(
        method="POST",
        url=get_provider_sale_url(terminal_data),
        json=nambaone_error("UNKNOWN_ERROR", "Something went wrong"),
        status_code=500,
    )

    resp = post_sale(client, terminal_data, invoice_id)

    assert_failed(resp, gate_lib_const.PROVIDER_ERROR)


def test_timeout(terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str):
    httpx_mock.add_exception(
        httpx.ReadTimeout("Simulated timeout"), method="POST", url=get_provider_sale_url(terminal_data)
    )

    resp = post_sale(client, terminal_data, invoice_id)

    data = assert_failed(resp, "provider_unavailable")
    assert data["message"] == "NambaOne is unavailable"


def test_incorrect_response_with_status_code200(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(method="POST", url=get_provider_sale_url(terminal_data), json={}, status_code=200)

    resp = post_sale(client, terminal_data, invoice_id)

    assert_failed(resp, "provider_unavailable")


def test_incorrect_response_without_token(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(
        method="POST", url=get_provider_sale_url(terminal_data), json=nambaone_ok({"guid": LINK_GUID})
    )

    resp = post_sale(client, terminal_data, invoice_id)

    assert_failed(resp, "provider_unavailable")


def test_incorrect_response_with_status_code500(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    httpx_mock.add_response(
        method="POST", url=get_provider_sale_url(terminal_data), status_code=500, text="Internal Server Error"
    )

    resp = post_sale(client, terminal_data, invoice_id)

    assert_failed(resp, "provider_unavailable")


def test_invalid_terminal_data(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str
):
    terminal_json = dump_terminal_data(terminal_data)
    terminal_json.pop("provider_secret_key")

    resp = post_sale(client, terminal_json, invoice_id)

    data = assert_failed(resp, gate_lib_const.VALIDATION_ERROR)
    assert data["message"] == "Terminal data is not valid"
    assert not httpx_mock.get_requests()


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"currency_code": "USD"}, "Currency USD is not supported"),
        ({"amount": "100.001"}, "Amount 100.001 has more than 2 decimal places"),
    ],
)
def test_sale_without_card_is_not_sent_to_provider(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
    invoice_id: str,
    overrides: dict[str, str],
    message: str,
):
    # NambaOne работает только с KGS и суммами в целых тыйынах
    resp = post_sale(client, terminal_data, invoice_id, **overrides)

    data = assert_failed(resp, gate_lib_const.VALIDATION_ERROR)
    assert data["message"] == message
    assert not httpx_mock.get_requests()


def test_sale_without_card_secure_redirect_without_key(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
    invoice_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    # С пустым ключом подписать редирект мог бы кто угодно, поэтому такая продажа не выполняется вовсе
    monkeypatch.setattr(settings, "SECURE_REDIRECT_KEY", "")
    terminal_json = {**dump_terminal_data(terminal_data), "secure_redirect_url": SECURE_REDIRECT_URL}

    resp = post_sale(client, terminal_json, invoice_id)

    data = assert_failed(resp, gate_lib_const.INTERNAL_ERROR)
    assert data["message"] == "Secure redirect is not configured"
    # Ссылка даже не создается: отправить на нее плательщика все равно нельзя
    assert not httpx_mock.get_requests()


def test_sale_without_card_without_secure_redirect_does_not_need_key(
    terminal_data: TerminalData,
    client: TestClient,
    httpx_mock: HTTPXMock,
    invoice_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "SECURE_REDIRECT_KEY", "")
    httpx_mock.add_response(method="POST", url=get_provider_sale_url(terminal_data), json=payment_link())

    resp = post_sale(client, terminal_data, invoice_id)

    assert resp.json()["status"] == gate_lib_const.PENDING


@pytest.mark.parametrize(
    "overrides", [{"amount": "0"}, {"amount": "-1"}, {"currency_code": "SOM1"}, {"invoice_id": ""}]
)
def test_request_validation(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, invoice_id: str, overrides: dict[str, str]
):
    resp = post_sale(client, terminal_data, **{"invoice_id": invoice_id, **overrides})

    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == gate_lib_const.VALIDATION_ERROR
    # Невалидный запрос - это не неуспешная операция
    assert "status" not in data
    assert not httpx_mock.get_requests()
