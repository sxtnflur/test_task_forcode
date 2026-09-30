import structlog
from gate_lib.protocol.v2.sale import SaleRequest
from sbank_client.exceptions import SbankError

from gate_nambaone.errors import PaymentCreationFailed
from gate_nambaone.errors import SecureRedirectNotConfigured
from gate_nambaone.nambaone import NambaOneClient
from gate_nambaone.nambaone.schemas import CreateOneTimeLinkRequest
from gate_nambaone.nambaone.schemas import PaymentLink
from gate_nambaone.nambaone.schemas import WebOptions
from gate_nambaone.schemas.terminal_data import TerminalData
from gate_nambaone.secure_redirect import SecureRedirect

logger = structlog.get_logger()


async def create_payment_link(
    nambaone: NambaOneClient,
    terminal: TerminalData,
    secure_redirect: SecureRedirect,
    req: SaleRequest,
) -> tuple[PaymentLink, str]:
    """
    Создает одноразовую платежную ссылку (externalId = invoice_id).

    Возвращает ссылку и URL, на который перенаправить плательщика: саму ссылку
    или страницу secure redirect, если терминал ее использует.
    """
    if terminal.secure_redirect_url and not secure_redirect.is_configured:
        # Проверяется до создания ссылки: отправить на нее плательщика все равно было бы нельзя
        logger.error("secure_redirect_not_configured", reason="SECURE_REDIRECT_KEY is not set")
        raise SecureRedirectNotConfigured

    link = await nambaone.payments.create_one_time_link(
        CreateOneTimeLinkRequest(
            external_id=req.invoice_id,
            amount=req.amount,
            amount_can_be_changed=False,
            webhook_url=str(terminal.provider_callback_url_invoice),
            merchant_employee_guid=terminal.merchant_employee_guid,
            web_options=WebOptions(redirect_link=req.finish_url) if req.finish_url else None,
        )
    )

    if not terminal.secure_redirect_url:
        return link, link.token

    try:
        redirect_url = await secure_redirect.create(req.invoice_id, link.token, str(terminal.secure_redirect_url))
    except SbankError as e:
        logger.error("secure_redirect_save_failed", error=str(e))
        raise PaymentCreationFailed from e
    return link, redirect_url
