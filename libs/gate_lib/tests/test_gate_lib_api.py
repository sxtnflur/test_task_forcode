from typing import Any

import httpx
import pytest
from cds_client.services.cds import CardData
from fastapi import APIRouter
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from gate_lib import const
from gate_lib.api import v2
from gate_lib.handlers import request_validation_error_handler
from gate_lib.protocol.v2.p2p_selector import P2pSelectorSaleResponse
from gate_lib.protocol.v2.sale import SaleResponse
from gate_lib.settings import get_settings
from pytest_httpx import HTTPXMock

CDS_URL = "http://cds.test"
TERMINAL_DATA = {"provider_base_url": "https://provider.test"}
CARD = {"pan": "4111111111111111", "cvc": "123", "exp_month": 12, "exp_year": 2030}


class FakeGate:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.error: Exception | None = None

    async def _handle(self, name: str, *args: Any) -> Any:
        self.calls.append((name, args))
        if self.error:
            raise self.error

    async def sale(self, req, card_data):
        await self._handle("sale", req, card_data)
        return SaleResponse(status=const.PENDING, amount=req.amount, currency_code=req.currency_code)

    async def sale_without_card(self, req):
        await self._handle("sale_without_card", req)
        return SaleResponse(status=const.PENDING, amount=req.amount, currency_code=req.currency_code)

    async def status(self, req):
        await self._handle("status", req)
        # dict тоже принимается: call_gate проверяет его по модели ответа
        return {"status": const.COMPLETE, "amount": "10.00", "external_id": req.external_id}

    async def p2p_selector_sale(self, req):
        await self._handle("p2p_selector_sale", req)
        return P2pSelectorSaleResponse(status=const.FAILED, amount=req.amount)

    async def refund(self, req):
        await self._handle("refund", req)

    async def withdrawal(self, req, card_data):
        await self._handle("withdrawal", req, card_data)


@pytest.fixture
def gate() -> FakeGate:
    return FakeGate()


@pytest.fixture
def client(gate: FakeGate, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CDS_URL", CDS_URL)
    monkeypatch.setenv("CDS_AUTH_TOKEN", "token")
    get_settings.cache_clear()

    router = APIRouter()
    for build in (
        v2.build_ping_method,
        v2.build_sale_method,
        v2.build_status_method,
        v2.build_refund_method,
        v2.build_p2p_selector_sale_method,
        v2.build_withdrawal_method,
    ):
        build(router, lambda: gate)

    app = FastAPI()
    app.include_router(router, prefix="/v2")
    app.exception_handler(RequestValidationError)(request_validation_error_handler)
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def sale_body(**overrides: Any) -> dict[str, Any]:
    body = {"invoice_id": "inv-1", "amount": "100.00", "currency_code": "RUB", "terminal_data": TERMINAL_DATA}
    return body | overrides


def test_ping(client: TestClient):
    resp = client.get("/v2/ping")

    assert resp.status_code == 200
    assert resp.text == "pong"


def test_sale_without_card_token_calls_sale_without_card(client: TestClient, gate: FakeGate):
    resp = client.post("/v2/sale", json=sale_body())

    assert resp.status_code == 200
    assert resp.json()["status"] == const.PENDING
    assert resp.json()["amount"] == "100.00"
    assert [name for name, _ in gate.calls] == ["sale_without_card"]


def test_sale_with_card_token_fetches_card_from_cds(client: TestClient, gate: FakeGate, httpx_mock: HTTPXMock):
    httpx_mock.add_response(method="GET", url=f"{CDS_URL}/cards/card-1", json=CARD)

    resp = client.post("/v2/sale", json=sale_body(card_token="card-1"))

    assert resp.json()["status"] == const.PENDING
    name, (_, card_data) = gate.calls[0]
    assert name == "sale"
    assert card_data == CardData(**CARD)
    assert "4111111111111111" not in repr(card_data)


def test_sale_fails_when_cds_is_unavailable(client: TestClient, gate: FakeGate, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ReadTimeout("timeout"), url=f"{CDS_URL}/cards/card-1")

    resp = client.post("/v2/sale", json=sale_body(card_token="card-1"))

    data = resp.json()
    assert data["status"] == const.FAILED
    assert data["code"] == const.CARD_DATA_ERROR
    assert gate.calls == []


def test_sale_gate_exception_returns_failed(client: TestClient, gate: FakeGate):
    gate.error = RuntimeError("boom")

    resp = client.post("/v2/sale", json=sale_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == const.FAILED
    assert data["code"] == const.INTERNAL_ERROR
    assert data["amount"] == "100.00"


def test_status_accepts_dict_from_gate(client: TestClient):
    resp = client.post(
        "/v2/status",
        json={"invoice_id": "inv-1", "external_id": "ext-1", "currency_code": "RUB", "terminal_data": TERMINAL_DATA},
    )

    assert resp.json()["status"] == const.COMPLETE
    assert resp.json()["external_id"] == "ext-1"


def test_status_gate_exception_returns_pending(client: TestClient, gate: FakeGate):
    gate.error = httpx.ReadTimeout("timeout")

    resp = client.post(
        "/v2/status",
        json={"invoice_id": "inv-1", "external_id": "ext-1", "currency_code": "RUB", "terminal_data": TERMINAL_DATA},
    )

    data = resp.json()
    assert data["status"] == const.PENDING
    assert data["external_id"] == "ext-1"
    assert data["code"] == const.INTERNAL_ERROR


def test_refund_invalid_gate_response_returns_pending(client: TestClient):
    # FakeGate.refund возвращает None, а это не валидный RefundResponse
    resp = client.post(
        "/v2/refund",
        json={"refund_id": "r-1", "invoice_id": "inv-1", "amount": "5", "currency_code": "RUB",
              "terminal_data": TERMINAL_DATA},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == const.PENDING


def test_withdrawal_gate_exception_returns_pending(client: TestClient, gate: FakeGate):
    gate.error = RuntimeError("boom")

    resp = client.post(
        "/v2/withdrawal",
        json={"withdrawal_id": "w-1", "amount": "5", "currency_code": "RUB", "terminal_data": TERMINAL_DATA},
    )

    assert resp.json()["status"] == const.PENDING
    _, (_, card_data) = gate.calls[0]
    assert card_data is None


def test_p2p_empty_beneficiary_is_serialized_as_empty_dict(client: TestClient):
    resp = client.post("/v2/p2p_selector_sale", json=sale_body())

    assert resp.json()["beneficiary"] == {}


@pytest.mark.parametrize(
    "body",
    [
        sale_body(amount="-1"),
        sale_body(amount="abc"),
        sale_body(currency_code="RUBLES"),
        sale_body(invoice_id="  "),
        {k: v for k, v in sale_body().items() if k != "terminal_data"},
    ],
)
def test_invalid_sale_request_returns_422_without_status(client: TestClient, gate: FakeGate, body: dict[str, Any]):
    resp = client.post("/v2/sale", json=body)

    assert resp.status_code == 422
    data = resp.json()
    assert "status" not in data
    assert data["code"] == const.VALIDATION_ERROR
    assert data["errors"]
    assert gate.calls == []


def test_validation_errors_do_not_echo_input(client: TestClient):
    resp = client.post("/v2/sale", json=sale_body(amount="4111111111111111x"))

    assert "4111111111111111" not in resp.text


def test_status_requires_operation_id(client: TestClient):
    resp = client.post("/v2/status", json={"currency_code": "RUB", "terminal_data": TERMINAL_DATA})

    assert resp.status_code == 422
