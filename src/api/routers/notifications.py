from fastapi import APIRouter
from fastapi import Response

from api.deps import GateNambaOneDependency
from gate_nambaone.schemas.notifications import InvoiceNotification
from gate_nambaone.schemas.notifications import WithdrawalNotification

router = APIRouter(prefix="/callback", tags=["Notifications"])


def ok_response() -> Response:
    # Новый Response на каждый запрос: общий экземпляр делил бы свои изменяемые заголовки между запросами
    return Response(content="OK")


@router.post("/invoice")
async def invoice_notification(req: InvoiceNotification, gate_nambaone: GateNambaOneDependency):
    # NotificationRetryableError превращается в ответ не 2xx в api.errors
    await gate_nambaone.notification_invoice(req)
    return ok_response()


@router.post("/withdrawal")
async def withdrawal_notification(req: WithdrawalNotification, gate_nambaone: GateNambaOneDependency):
    await gate_nambaone.notification_withdrawal(req)
    return ok_response()
