from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import status

from gate_lib import const


async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Возвращает 422 с описанием невалидных полей.

    В теле намеренно нет поля `status`: невалидный запрос - это не неуспешная
    операция, и вызывающая сторона не должна считать его таковой. Входные значения убираются
    из деталей ошибки, чтобы данные карты никогда не попали в ответ.
    """
    errors = [
        {"loc": list(error.get("loc", ())), "type": error.get("type"), "msg": error.get("msg")}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "code": const.VALIDATION_ERROR,
            "message": "Request validation failed",
            "errors": errors,
        },
    )
