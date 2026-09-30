from decimal import Decimal
from typing import Annotated
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import StringConstraints

# Должно совпадать с gate_lib.const.STATUSES
Status = Literal["pending", "complete", "failed"]

Amount = Annotated[Decimal, Field(allow_inf_nan=False)]
PositiveAmount = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
CurrencyCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{3}$")]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class GateRequest(BaseModel):
    """
    Базовый запрос процессинга к гейту.

    `terminal_data` намеренно остается сырым dict: его схема своя
    у каждого гейта, и гейт проверяет ее сам.
    """

    model_config = ConfigDict(extra="ignore")

    terminal_data: dict[str, Any]


class GateResponse(BaseModel):
    status: Status
    code: str | None = None
    message: str | None = None
