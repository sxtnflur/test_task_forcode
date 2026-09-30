from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict


class SbankModel(BaseModel):
    # ID могут прийти числами, гейт работает с ними как со строками
    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)


class InvoiceInfo(SbankModel):
    id: str
    primary_terminal: str
    currency_code: str
    amount: Decimal | None = None
    external_id: str | None = None
    status: str | None = None


class WithdrawalInfo(SbankModel):
    id: str
    primary_terminal: str
    currency_code: str
    amount: Decimal | None = None
    external_id: str | None = None
    status: str | None = None


class TerminalInfo(SbankModel):
    id: str
    # Настройки терминала, свои для каждого гейта (гейт проверяет их сам)
    data: dict[str, Any]
