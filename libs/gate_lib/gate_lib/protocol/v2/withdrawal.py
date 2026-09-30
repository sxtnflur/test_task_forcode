from typing import Any

from gate_lib.protocol.v2.base import Amount
from gate_lib.protocol.v2.base import CurrencyCode
from gate_lib.protocol.v2.base import GateRequest
from gate_lib.protocol.v2.base import GateResponse
from gate_lib.protocol.v2.base import NonEmptyStr
from gate_lib.protocol.v2.base import PositiveAmount
from gate_lib.protocol.v2.sale import Redirect


class WithdrawalRequest(GateRequest):
    withdrawal_id: NonEmptyStr
    amount: PositiveAmount
    currency_code: CurrencyCode
    email: str | None = None
    # Банк получателя для выплат на счет/по СБП
    beneficiary_bank_id: str | None = None
    # Токен карты в Card Data Storage для выплат на карту
    card_token: str | None = None


class WithdrawalResponse(GateResponse):
    amount: Amount | None = None
    # Разбиение выплаты на несколько переводов, если провайдер так делает
    withdrawal_amounts: list[dict[str, Any]] | None = None
    currency_code: str | None = None
    external_id: str | None = None
    redirect: Redirect | None = None
