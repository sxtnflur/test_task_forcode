from typing_extensions import Annotated
from pydantic import BaseModel, ConfigDict, StringConstraints, Field


class CardData(BaseModel):
    """Данные карты из Card Data Storage. PAN и CVC маскируются в repr, чтобы никогда не попасть в логи."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    pan: Annotated[str, StringConstraints(pattern=r"^\d{12,19}$")]
    cvc: Annotated[str, StringConstraints(pattern=r"^\d{3,4}$")] | None = None
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2000, le=2100)
    holder: str | None = None

    def __repr_args__(self):
        for name, value in super().__repr_args__():
            if name == "pan" and value:
                value = f"{value[:6]}***{value[-4:]}"
            elif name == "cvc" and value:
                value = "***"
            yield name, value