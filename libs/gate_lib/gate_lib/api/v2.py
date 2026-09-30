"""
Построители эндпоинтов протокола гейта v2.

Каждый построитель регистрирует один эндпоинт на роутере и передает работу объекту гейта,
который возвращает `gate_dependency`. Эндпоинт никогда не выпускает исключение гейта наружу:
оно логируется и превращается в ответ протокола. Статус по умолчанию зависит от того,
могли ли двигаться деньги:

- создание платежа (sale, p2p) -> FAILED: плательщика еще никуда не отправили;
- все остальное (статусы, возвраты, выплаты, confirm) -> PENDING: настоящий
  итог неизвестен и должен выясниться последующей проверкой статуса.
"""

from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any
from typing import TypeVar

import httpx
import structlog
from cds_client.services.cds import CardData
from cds_client.services.cds import CdsClient
from cds_client.services.cds import CdsError
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from gate_lib import const
from gate_lib.protocol.v2.balance import BalanceRequest
from gate_lib.protocol.v2.balance import BalanceResponse
from gate_lib.protocol.v2.p2p_selector import P2pSelectorSaleRequest
from gate_lib.protocol.v2.p2p_selector import P2pSelectorSaleResponse
from gate_lib.protocol.v2.refund import RefundRequest
from gate_lib.protocol.v2.refund import RefundResponse
from gate_lib.protocol.v2.refund import RefundStatusRequest
from gate_lib.protocol.v2.refund import RefundStatusResponse
from gate_lib.protocol.v2.sale import SaleConfirmRequest
from gate_lib.protocol.v2.sale import SaleConfirmResponse
from gate_lib.protocol.v2.sale import SaleRequest
from gate_lib.protocol.v2.sale import SaleResponse
from gate_lib.protocol.v2.status import StatusRequest
from gate_lib.protocol.v2.status import StatusResponse
from gate_lib.protocol.v2.withdrawal import WithdrawalRequest
from gate_lib.protocol.v2.withdrawal import WithdrawalResponse
from gate_lib.settings import get_settings

logger = structlog.get_logger()

GateDependency = Callable[..., Any]
ResponseT = TypeVar("ResponseT", bound=BaseModel)

INTERNAL_ERROR_MESSAGE = "Internal gate error"
CDS_TIMEOUT = 10


async def call_gate(
    method_name: str,
    call: Callable[[], Awaitable[Any]],
    response_model: type[ResponseT],
    fallback: Callable[[], ResponseT],
) -> ResponseT:
    """Вызывает метод гейта и гарантирует корректный ответ протокола."""
    try:
        result = await call()
        if isinstance(result, response_model):
            return result
        return response_model.model_validate(result, from_attributes=True)
    except Exception:
        logger.exception("gate_method_failed", gate_method=method_name)
        return fallback()


async def fetch_card_data(request: Request, card_token: str) -> CardData:
    settings = get_settings()
    httpx_client: httpx.AsyncClient | None = getattr(request.app.state, "httpx_client", None)
    if httpx_client is not None:
        return await CdsClient(httpx_client, settings.CDS_URL, settings.CDS_AUTH_TOKEN).get_card_data(card_token)
    async with httpx.AsyncClient(timeout=CDS_TIMEOUT) as client:
        return await CdsClient(client, settings.CDS_URL, settings.CDS_AUTH_TOKEN).get_card_data(card_token)


def build_ping_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.get("/ping", response_class=PlainTextResponse)
    async def ping() -> str:
        return "pong"


def build_terminal_data_schema_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.get("/terminal_data_schema")
    async def terminal_data_schema(gate: Any = Depends(gate_dependency)) -> dict[str, Any]:
        return await gate.terminal_data_schema()


def build_sale_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/sale", response_model=SaleResponse)
    async def sale(req: SaleRequest, request: Request, gate: Any = Depends(gate_dependency)) -> SaleResponse:
        def failed(code: str = const.INTERNAL_ERROR, message: str = INTERNAL_ERROR_MESSAGE) -> SaleResponse:
            return SaleResponse(
                status=const.FAILED,
                amount=req.amount,
                currency_code=req.currency_code,
                code=code,
                message=message,
            )

        if req.card_token is None:
            return await call_gate("sale_without_card", lambda: gate.sale_without_card(req), SaleResponse, failed)

        try:
            card_data = await fetch_card_data(request, req.card_token)
        except CdsError as e:
            logger.warning("card_data_unavailable", error=str(e))
            return failed(const.CARD_DATA_ERROR, "Card data is unavailable")

        return await call_gate("sale", lambda: gate.sale(req, card_data), SaleResponse, failed)


def build_sale_confirm_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/sale_confirm", response_model=SaleConfirmResponse)
    async def sale_confirm(req: SaleConfirmRequest, gate: Any = Depends(gate_dependency)) -> SaleConfirmResponse:
        return await call_gate(
            "sale_confirm",
            lambda: gate.sale_confirm(req),
            SaleConfirmResponse,
            lambda: SaleConfirmResponse(
                status=const.PENDING,
                code=const.INTERNAL_ERROR,
                message=INTERNAL_ERROR_MESSAGE,
            ),
        )


def build_status_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/status", response_model=StatusResponse)
    async def status(req: StatusRequest, gate: Any = Depends(gate_dependency)) -> StatusResponse:
        return await call_gate(
            "status",
            lambda: gate.status(req),
            StatusResponse,
            lambda: StatusResponse(
                status=const.PENDING,
                currency_code=req.currency_code,
                external_id=req.external_id,
                code=const.INTERNAL_ERROR,
                message=INTERNAL_ERROR_MESSAGE,
            ),
        )


def build_refund_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/refund", response_model=RefundResponse)
    async def refund(req: RefundRequest, gate: Any = Depends(gate_dependency)) -> RefundResponse:
        return await call_gate(
            "refund",
            lambda: gate.refund(req),
            RefundResponse,
            lambda: RefundResponse(
                status=const.PENDING,
                amount=req.amount,
                currency_code=req.currency_code,
                code=const.INTERNAL_ERROR,
                message=INTERNAL_ERROR_MESSAGE,
            ),
        )


def build_refund_status_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/refund_status", response_model=RefundStatusResponse)
    async def refund_status(req: RefundStatusRequest, gate: Any = Depends(gate_dependency)) -> RefundStatusResponse:
        return await call_gate(
            "refund_status",
            lambda: gate.refund_status(req),
            RefundStatusResponse,
            lambda: RefundStatusResponse(
                status=const.PENDING,
                amount=req.amount,
                currency_code=req.currency_code,
                external_id=req.external_id,
                code=const.INTERNAL_ERROR,
                message=INTERNAL_ERROR_MESSAGE,
            ),
        )


def build_balance_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/balance", response_model=BalanceResponse)
    async def balance(req: BalanceRequest, gate: Any = Depends(gate_dependency)) -> BalanceResponse:
        return await call_gate(
            "balance",
            lambda: gate.balance(req),
            BalanceResponse,
            lambda: BalanceResponse(
                currency=req.currency,
                code=const.INTERNAL_ERROR,
                message=INTERNAL_ERROR_MESSAGE,
            ),
        )


def build_p2p_selector_sale_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/p2p_selector_sale", response_model=P2pSelectorSaleResponse)
    async def p2p_selector_sale(
        req: P2pSelectorSaleRequest,
        gate: Any = Depends(gate_dependency),
    ) -> P2pSelectorSaleResponse:
        return await call_gate(
            "p2p_selector_sale",
            lambda: gate.p2p_selector_sale(req),
            P2pSelectorSaleResponse,
            lambda: P2pSelectorSaleResponse(
                status=const.FAILED,
                amount=req.amount,
                currency_code=req.currency_code,
                code=const.INTERNAL_ERROR,
                message=INTERNAL_ERROR_MESSAGE,
            ),
        )


def build_withdrawal_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/withdrawal", response_model=WithdrawalResponse)
    async def withdrawal(
        req: WithdrawalRequest,
        request: Request,
        gate: Any = Depends(gate_dependency),
    ) -> WithdrawalResponse:
        def pending(code: str = const.INTERNAL_ERROR, message: str = INTERNAL_ERROR_MESSAGE) -> WithdrawalResponse:
            return WithdrawalResponse(
                status=const.PENDING,
                amount=req.amount,
                currency_code=req.currency_code,
                code=code,
                message=message,
            )

        card_data: CardData | None = None
        if req.card_token is not None:
            try:
                card_data = await fetch_card_data(request, req.card_token)
            except CdsError as e:
                # К провайдеру еще ничего не отправлено, поэтому выплату можно безопасно отклонить
                logger.warning("card_data_unavailable", error=str(e))
                return WithdrawalResponse(
                    status=const.FAILED,
                    amount=req.amount,
                    currency_code=req.currency_code,
                    code=const.CARD_DATA_ERROR,
                    message="Card data is unavailable",
                )

        return await call_gate("withdrawal", lambda: gate.withdrawal(req, card_data), WithdrawalResponse, pending)


def build_withdrawal_status_method(router: APIRouter, gate_dependency: GateDependency) -> None:
    @router.post("/withdrawal_status", response_model=StatusResponse)
    async def withdrawal_status(req: StatusRequest, gate: Any = Depends(gate_dependency)) -> StatusResponse:
        return await call_gate(
            "withdrawal_status",
            lambda: gate.withdrawal_status(req),
            StatusResponse,
            lambda: StatusResponse(
                status=const.PENDING,
                currency_code=req.currency_code,
                external_id=req.external_id,
                code=const.INTERNAL_ERROR,
                message=INTERNAL_ERROR_MESSAGE,
            ),
        )
