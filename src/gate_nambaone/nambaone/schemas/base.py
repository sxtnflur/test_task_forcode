"""
Модели NambaOne Merchant Web API (https://merchant-api-docs.rps.kg/).

Суммы приходят от NambaOne в минорных единицах (тыйынах) и при разборе переводятся в основные,
поэтому остальной гейт работает с обычными суммами в KGS.
"""

from decimal import Decimal
from typing import Annotated
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import BeforeValidator
from pydantic import ConfigDict
from pydantic import field_validator
from pydantic.alias_generators import to_camel

from gate_nambaone.nambaone.amounts import from_minor_units
from gate_nambaone.nambaone.amounts import to_minor_units
from gate_nambaone.nambaone.error_codes import ErrorCodeEnum

ToMinorUnitsAmount = Annotated[Decimal, BeforeValidator(to_minor_units)]
MinorUnitsAmount = Annotated[Decimal, BeforeValidator(from_minor_units)]


class NambaOneModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class ErrorDetails(NambaOneModel):
    # Обычная строка, а не ErrorCodeEnum: код, которого нет в enum, не должен ломать разбор всего ответа, иначе ошибка и
    # ее сообщение потеряются. Известные коды сравниваются с ErrorCodeEnum.
    error_code: str | None = None
    message: str | None = None

    # field_validator должен быть внешним декоратором, иначе pydantic молча игнорирует валидатор
    @field_validator("error_code", mode="before")
    @classmethod
    def validate_error_code(cls, value: Any) -> Any:
        # Опечатка в коде ошибки в документации
        if value == "UKNOWN_ERROR":
            return ErrorCodeEnum.UNKNOWN_ERROR.value
        return value


class Envelope(NambaOneModel):
    """Любой ответ NambaOne: `{"status": "OK" | "ERROR", "data": ..., "error": ...}`."""

    status: Literal["OK", "ERROR"]
    data: Any = None
    error: ErrorDetails | None = None

    @property
    def is_ok(self) -> bool:
        return self.status == "OK"
