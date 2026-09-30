from decimal import Decimal

from pydantic import BaseModel

from gate_lib.protocol.v2.base import Amount
from gate_lib.protocol.v2.base import CurrencyCode
from gate_lib.protocol.v2.base import GateRequest


class BalanceRequest(GateRequest):
    currency: CurrencyCode


class BalanceResponse(BaseModel):
    # Баланс может быть отрицательным (овердрафт), поэтому это не PositiveAmount
    balance: Amount = Decimal("0.0")
    currency: str
    code: str | None = None
    message: str | None = None
