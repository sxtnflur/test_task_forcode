from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from http import HTTPStatus
from typing import Any
from typing import NamedTuple
from pydantic import ValidationError
import structlog

from cds_client.services.cds import CardData
from gate_lib import const as gate_lib_const
from gate_lib.protocol.v2.balance import BalanceRequest
from gate_lib.protocol.v2.balance import BalanceResponse
from gate_lib.protocol.v2.p2p_selector import P2pSelectorSaleRequest
from gate_lib.protocol.v2.p2p_selector import P2pSelectorSaleResponse
from gate_lib.protocol.v2.refund import RefundRequest
from gate_lib.protocol.v2.refund import RefundResponse
from gate_lib.protocol.v2.refund import RefundStatusRequest
from gate_lib.protocol.v2.refund import RefundStatusResponse
from gate_lib.protocol.v2.sale import Redirect
from gate_lib.protocol.v2.sale import SaleConfirmRequest
from gate_lib.protocol.v2.sale import SaleConfirmResponse
from gate_lib.protocol.v2.sale import SaleRequest
from gate_lib.protocol.v2.sale import SaleResponse
from gate_lib.protocol.v2.status import StatusRequest
from gate_lib.protocol.v2.status import StatusResponse
from gate_lib.protocol.v2.withdrawal import WithdrawalRequest
from gate_lib.protocol.v2.withdrawal import WithdrawalResponse
from sbank_client.client import SbankClient
from sbank_client.exceptions import SbankError
from sbank_client.exceptions import SbankInvalidIdError
from sbank_client.exceptions import SbankResponseError

import const
from gate_nambaone.errors import GateOperationError
from gate_nambaone.errors import InvalidTerminalData
from gate_nambaone.errors import NotificationRetryableError
from gate_nambaone.errors import OperationRejected
from gate_nambaone.errors import OperationUncertain
from gate_nambaone.errors import PaymentOrderNotFound
from gate_nambaone.errors import ProviderUnavailable
from gate_nambaone.nambaone import NambaOneClient
from gate_nambaone.nambaone import NambaOneConnector
from gate_nambaone.nambaone.error_codes import ErrorCodeEnum
from gate_nambaone.nambaone.errors import NambaOneApiError
from gate_nambaone.nambaone.errors import NambaOneError
from gate_nambaone.nambaone.schemas import RefundOrder
from gate_nambaone.operations.payment import get_payment_order
from gate_nambaone.operations.refund import create_refund
from gate_nambaone.operations.sale import create_payment_link
from gate_nambaone.schemas.notifications import InvoiceNotification
from gate_nambaone.schemas.notifications import WithdrawalNotification
from gate_nambaone.schemas.terminal_data import TerminalData
from gate_nambaone.secure_redirect import SecureRedirect
from gate_nambaone.settings import GateNamabaOneSettingsProtocol
from gate_nambaone.validators import validate_currency, validate_money
from status_mapper import map_payment_status
from status_mapper import map_refund_status

logger = structlog.get_logger()

NOT_SUPPORTED_MESSAGE = "Operation is not supported by NambaOne"


class NambaOneSession(NamedTuple):
    client: NambaOneClient
    terminal: TerminalData


class GateNambaOne:
    """
    Интеграция с NambaOne Merchant Web API (https://merchant-api-docs.rps.kg/).

    Поток платежа: sale_without_card создает одноразовую платежную ссылку, плательщик оплачивает ее
    в приложении Namba One, NambaOne присылает вебхук, гейт проверяет статус через API и
    сообщает результат процессингу.

    Гейт адаптирует протокол процессинга: проверяет запрос, вызывает API NambaOne
    (или многошаговый сценарий из gate_nambaone.operations) и превращает результат или ошибку
    в ответ протокола. Ошибки - это OperationRejected (деньги не двигались) или
    OperationUncertain (деньги могли двинуться); какой статус они означают, зависит от операции.

    NambaOne принимает платежи только через свое приложение, поэтому операции с данными карты, p2p
    и выплаты не поддерживаются и отвечают `not_supported`.
    """

    def __init__(
        self,
        sbank_client: SbankClient,
        nambaone_connector: NambaOneConnector,
        secure_redirect: SecureRedirect,
        settings: GateNamabaOneSettingsProtocol,
    ):
        self._nambaone_connector = nambaone_connector
        self._secure_redirect = secure_redirect
        self.sbank = sbank_client
        self._settings = settings

    async def terminal_data_schema(self) -> dict[str, Any]:
        return {
            "title": "NambaOne settings",
            "groups": [
                {
                    "name": "connection",
                    "label": "Connection",
                    "fields": [
                        {"name": "provider_base_url", "label": "Provider Base URL", "type": "text", "required": True},
                        {
                            "name": "gate_connection.url",
                            "label": "Gate Connection URL",
                            "type": "text",
                            "required": True,
                        },
                        {"name": "proxy_url", "label": "Proxy URL", "type": "text", "required": False},
                    ],
                },
                {
                    "name": "provider",
                    "label": "Provider",
                    "fields": [
                        {
                            "name": "merchant_account_guid",
                            "label": "Merchant Account GUID",
                            "type": "text",
                            "required": True,
                        },
                        {"name": "provider_secret_key", "label": "Secret Key", "type": "password", "required": True},
                        {
                            "name": "merchant_employee_guid",
                            "label": "Merchant Employee GUID",
                            "type": "text",
                            "required": False,
                        },
                    ],
                },
                {
                    "name": "urls",
                    "label": "URLs",
                    "fields": [
                        {
                            "name": "provider_callback_url_invoice",
                            "label": "Callback URL Invoice",
                            "type": "text",
                            "required": True,
                        },
                        {
                            "name": "provider_callback_url_refund",
                            "label": "Callback URL Refund",
                            "type": "text",
                            "required": False,
                        },
                        {
                            "name": "secure_redirect_url",
                            "label": "Secure Redirect URL",
                            "type": "text",
                            "required": False,
                        },
                    ],
                },
            ],
        }

    # ------------------------------------------------------------------ платежи

    async def sale(self, req: SaleRequest, card_data: CardData) -> SaleResponse:
        """Sale - оплата картой. NambaOne не принимает карточные данные: оплата только в приложении."""
        return SaleResponse(
            status=gate_lib_const.FAILED,
            amount=req.amount,
            currency_code=req.currency_code,
            code=const.NOT_SUPPORTED,
            message=NOT_SUPPORTED_MESSAGE,
        )

    async def sale_without_card(self, req: SaleRequest) -> SaleResponse:
        """
        Sale - оплата с редиректом

        Создает одноразовую платежную ссылку NambaOne (externalId = invoice_id) и возвращает
        редирект на нее. Любая ошибка -> FAILED: ссылка не отдана плательщику, оплаты быть не может.
        """
        respond = partial(SaleResponse, amount=req.amount, currency_code=req.currency_code)
        try:
            validate_money(req.currency_code, req.amount)
            async with self._nambaone(req.terminal_data, "create_payment_link") as (nambaone, terminal):
                link, redirect_url = await create_payment_link(nambaone, terminal, self._secure_redirect, req)
        except GateOperationError as e:
            return respond(status=gate_lib_const.FAILED, code=e.code, message=e.message)
        return respond(status=gate_lib_const.PENDING, external_id=link.guid, redirect=Redirect(url=redirect_url))

    async def sale_confirm(self, req: SaleConfirmRequest) -> SaleConfirmResponse:
        """SaleConfirm - в NambaOne нет шага подтверждения, итог платежа определяет status."""
        return SaleConfirmResponse(
            status=gate_lib_const.PENDING,
            code=const.NOT_SUPPORTED,
            message=NOT_SUPPORTED_MESSAGE,
        )

    async def status(self, req: StatusRequest) -> StatusResponse:
        """
        Status - получение статуса платежа по externalId платежной ссылки (= invoice_id).

        Ошибки и неизвестные статусы -> PENDING: итог платежа не известен, запрос повторится.
        """
        respond = partial(StatusResponse, currency_code=req.currency_code, external_id=req.external_id)

        if not req.invoice_id:
            return respond(
                status=gate_lib_const.PENDING, code=gate_lib_const.VALIDATION_ERROR, message="invoice_id is required"
            )

        try:
            validate_currency(req.currency_code)
            async with self._nambaone(req.terminal_data, "get_payment_order") as (nambaone, _):
                order = await get_payment_order(nambaone, req.invoice_id)
        except PaymentOrderNotFound as e:
            # Это не сбой NambaOne: платежная ссылка ему неизвестна, поэтому статуса еще нет
            return respond(status=gate_lib_const.PENDING, message=e.message)
        except GateOperationError as e:
            return respond(status=gate_lib_const.PENDING, code=e.code, message=e.message)

        # Еще не оплаченная ссылка - это заказ в статусе CREATED, он тоже pending
        status = map_payment_status(order.status)
        failed = status == gate_lib_const.FAILED
        return respond(
            status=status,
            amount=order.payment_amount if order.payment_amount is not None else order.amount,
            currency_code=order.currency or req.currency_code,
            external_id=order.guid,
            code=gate_lib_const.PROVIDER_ERROR if failed else None,
            message=f"Payment {order.status}" if failed else None,
        )

    async def notification_invoice(self, notification: InvoiceNotification) -> None:
        """
        Вебхук NambaOne о платеже.

        Вебхуки не подписаны, поэтому из них берется только invoice_id, а статус запрашивается
        через API. Если результат еще не финальный или процессинг недоступен, поднимается
        NotificationRetryableError: эндпоинт ответит не-2xx и NambaOne повторит вебхук.
        Процессинг должен обрабатывать повторные invoice_income/mark_invoice_fail идемпотентно.
        """
        log = logger.bind(webhook_type=notification.type, provider_guid=notification.data.guid)
        if notification.type == const.REFUND_ORDER_WEBHOOK:
            # Статус возврата процессинг опрашивает сам через refund_status
            log.info("nambaone_refund_webhook_received", refund_id=notification.data.external_guid)
            return

        if notification.type != const.PAYMENT_ORDER_WEBHOOK:
            log.warning("nambaone_unknown_webhook_ignored")
            return

        invoice_id = notification.data.external_id
        if not invoice_id:
            log.warning("nambaone_webhook_without_external_id")
            return

        try:
            invoice = await self.sbank.get_invoice_info(invoice_id)
        except (SbankInvalidIdError, SbankResponseError) as e:
            if not isinstance(e, SbankInvalidIdError) and e.status_code != HTTPStatus.NOT_FOUND:
                raise NotificationRetryableError(f"Invoice {invoice_id} is unavailable: {e}") from e
            # Это не счет процессинга, например платежная ссылка, созданная не через гейт: счет не появится, поэтому
            # повторять вебхук в течение часа бесполезно
            log.warning("nambaone_webhook_for_unknown_invoice", invoice_id=invoice_id, error=str(e))
            return
        except SbankError as e:
            raise NotificationRetryableError(f"Invoice {invoice_id} is unavailable: {e}") from e

        try:
            # Терминал известного счета обязан существовать: сбой здесь временный или это проблема настроек
            terminal = await self.sbank.get_terminal_info(invoice.primary_terminal)
        except SbankError as e:
            raise NotificationRetryableError(f"Terminal of invoice {invoice_id} is unavailable: {e}") from e

        if invoice.currency_code != const.NAMBAONE_CURRENCY:
            # Для такого счета платежная ссылка не создается, поэтому вебхук не может быть о нем: повторять его
            # бесполезно
            log.error(
                "nambaone_webhook_for_unsupported_currency", invoice_id=invoice_id, currency=invoice.currency_code
            )
            return

        # Невалидные настройки терминала дают статус pending, поэтому вебхук повторяется, и настройки можно исправить,
        # пока NambaOne продолжает его присылать
        result = await self.status(
            StatusRequest(
                invoice_id=invoice.id,
                external_id=invoice.external_id,
                currency_code=invoice.currency_code,
                terminal_data=terminal.data,
            )
        )

        try:
            if result.status == gate_lib_const.COMPLETE:
                await self.sbank.invoice_income(
                    invoice_id=invoice.id,
                    amount_paid=result.amount,
                    external_transaction_id=str(result.external_id),
                )
            elif result.status == gate_lib_const.FAILED:
                await self.sbank.mark_invoice_fail(
                    invoice_id=invoice.id,
                    error_code=result.code,
                    error_message=result.message,
                    external_id=result.external_id,
                    payment_gate_iname=self._settings.ELASTIC_APM_SERVICE_NAME,
                )
            else:
                raise NotificationRetryableError(f"Invoice {invoice_id} status is still pending: {result.message}")
        except SbankError as e:
            raise NotificationRetryableError(f"Failed to update invoice {invoice_id}: {e}") from e

        log.info("nambaone_payment_webhook_processed", invoice_id=invoice_id, status=result.status)

    # ------------------------------------------------------------------ возвраты

    async def refund(self, req: RefundRequest) -> RefundResponse:
        """
        Refund - возврат платежа (externalRefundId = refund_id).

        Отказ (возврат точно не создан) -> FAILED, неизвестный исход -> PENDING.
        """
        respond = partial(RefundResponse, amount=req.amount, currency_code=req.currency_code)
        try:
            # В NambaOne еще ничего не отправлено, поэтому неподдерживаемые валюта или сумма - это точный отказ
            validate_money(req.currency_code, req.amount)
            async with self._nambaone(req.terminal_data, "create_refund") as (nambaone, terminal):
                refund_order = await create_refund(nambaone, terminal, req)
        except OperationRejected as e:
            return respond(status=gate_lib_const.FAILED, code=e.code, message=e.message)
        except OperationUncertain as e:
            return respond(status=gate_lib_const.PENDING, code=e.code, message=e.message)
        return respond(**refund_result(refund_order))

    async def refund_status(self, req: RefundStatusRequest) -> RefundStatusResponse:
        """
        RefundStatus - статус возврата по externalRefundId (= refund_id). Ошибки -> PENDING.

        Валюта не проверяется: она необязательна в запросе и не нужна, чтобы найти возврат.
        """
        respond = partial(
            RefundStatusResponse, amount=req.amount, currency_code=req.currency_code, external_id=req.external_id
        )
        try:
            async with self._nambaone(req.terminal_data, "get_refund") as (nambaone, _):
                refund_order = await nambaone.refunds.get_refund(req.refund_id)
        except GateOperationError as e:
            return respond(status=gate_lib_const.PENDING, code=e.code, message=e.message)
        return respond(**refund_result(refund_order))

    # ------------------------------------------------------------------ баланс

    async def balance(self, req: BalanceRequest) -> BalanceResponse:
        """Balance - доступный баланс счета продавца (без захолдированных средств). Ошибки -> balance 0 и code."""
        respond = partial(BalanceResponse, currency=req.currency)
        try:
            validate_currency(req.currency)
            async with self._nambaone(req.terminal_data, "get_merchant_info") as (nambaone, _):
                merchant = await nambaone.merchant.get_info()
        except GateOperationError as e:
            return respond(code=e.code, message=e.message)

        if merchant.currency != req.currency:
            return respond(
                code=gate_lib_const.VALIDATION_ERROR,
                message=f"Currency {req.currency} is not supported, the account is in {merchant.currency}",
            )
        return respond(balance=merchant.available_balance)

    # ------------------------------------------------------------------ не поддерживается NambaOne

    async def p2p_selector_sale(self, req: P2pSelectorSaleRequest) -> P2pSelectorSaleResponse:
        return P2pSelectorSaleResponse(
            status=gate_lib_const.FAILED,
            amount=req.amount,
            currency_code=req.currency_code,
            code=const.NOT_SUPPORTED,
            message=NOT_SUPPORTED_MESSAGE,
        )

    async def withdrawal(self, req: WithdrawalRequest, card_data: CardData | None) -> WithdrawalResponse:
        # Провайдеру ничего не отправляется, поэтому выплату можно безопасно отклонить
        return WithdrawalResponse(
            status=gate_lib_const.FAILED,
            amount=req.amount,
            currency_code=req.currency_code,
            code=const.NOT_SUPPORTED,
            message=NOT_SUPPORTED_MESSAGE,
        )

    async def withdrawal_status(self, req: StatusRequest) -> StatusResponse:
        return StatusResponse(
            status=gate_lib_const.PENDING,
            currency_code=req.currency_code,
            external_id=req.external_id,
            source=self._settings.ELASTIC_APM_SERVICE_NAME,
            code=const.NOT_SUPPORTED,
            message=NOT_SUPPORTED_MESSAGE,
        )

    async def notification_withdrawal(self, notification: WithdrawalNotification) -> None:
        logger.warning("withdrawal_notification_ignored", reason=NOT_SUPPORTED_MESSAGE)

    # ------------------------------------------------------------------ вспомогательное

    @asynccontextmanager
    async def _nambaone(self, raw_terminal_data: dict[str, Any], operation: str) -> AsyncIterator[NambaOneSession]:
        """
        Клиент NambaOne для терминала из запроса (учетные данные и прокси приходят в terminal_data).

        Ошибки NambaOne, поднятые внутри блока, превращаются в ошибки операции:
        отказ -> OperationRejected, нет ответа или ответ непонятен -> OperationUncertain.
        Остальные исключения проходят без изменений.
        """
        try:
            terminal = TerminalData.model_validate(raw_terminal_data)
        except ValidationError as e:
            # Логируются только пути полей: значения могут содержать секретный ключ
            logger.warning("terminal_data_invalid", fields=[".".join(map(str, err["loc"])) for err in e.errors()])
            raise InvalidTerminalData from None

        try:
            async with self._nambaone_connector.connect(
                base_url=str(terminal.provider_base_url),
                merchant_account_guid=terminal.merchant_account_guid,
                secret_key=terminal.provider_secret_key.get_secret_value(),
                proxy_url=terminal.proxy_url,
            ) as client:
                yield NambaOneSession(client, terminal)
        except NambaOneApiError as e:
            logger.warning("nambaone_request_rejected", operation=operation, error_code=e.error_code, error=e.message)
            error = OperationUncertain if e.error_code == ErrorCodeEnum.UNKNOWN_ERROR else OperationRejected
            raise error(gate_lib_const.PROVIDER_ERROR, e.message or e.error_code) from e
        except NambaOneError as e:
            logger.warning("nambaone_request_failed", operation=operation, error=str(e))
            raise ProviderUnavailable from e


def refund_result(order: RefundOrder) -> dict[str, Any]:
    """Поля RefundResponse/RefundStatusResponse из заказа на возврат NambaOne."""
    status = map_refund_status(order.status)
    if order.status == "STUCK":
        logger.error("nambaone_refund_stuck", refund_guid=order.guid)

    result: dict[str, Any] = {"status": status, "external_id": order.guid}
    if order.amount is not None:
        result["amount"] = order.amount
    if order.currency:
        result["currency_code"] = order.currency
    if status == gate_lib_const.FAILED:
        result["code"] = gate_lib_const.PROVIDER_ERROR
        result["message"] = const.REFUND_ERROR_MESSAGES.get(order.error_code or "", f"Refund {order.status}")
    return result
