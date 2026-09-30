import structlog
from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from gate_lib import const as gate_lib_const
from gate_lib.handlers import request_validation_error_handler

from gate_nambaone.errors import NotificationRetryableError

logger = structlog.get_logger()

INTERNAL_ERROR_MESSAGE = "Internal gate error"


async def notification_retryable_error_handler(request: Request, exc: NotificationRetryableError) -> Response:
    # Ответ не 2xx заставляет NambaOne повторить вебхук
    logger.warning("notification_retry_requested", path=request.url.path, reason=str(exc))
    return Response(content="RETRY", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Возвращает 500 на ошибку, которую никто не обработал.

    Как и в ответе 422, в теле нет поля `status`: итог операции
    неизвестен, и вызывающая сторона не должна считать ее неуспешной. Детали ошибки остаются в логах.
    """
    logger.exception("unhandled_error", path=request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"code": gate_lib_const.INTERNAL_ERROR, "message": INTERNAL_ERROR_MESSAGE},
    )


def register_errors(app: FastAPI):
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(NotificationRetryableError, notification_retryable_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
