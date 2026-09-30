from gate_nambaone.nambaone.schemas.base import MinorUnitsAmount
from gate_nambaone.nambaone.schemas.base import NambaOneModel


class MerchantInfo(NambaOneModel):
    guid: str
    status: str
    currency: str
    balance: MinorUnitsAmount
    # Баланс без холдов: деньги, которыми мерчант реально может распоряжаться
    available_balance: MinorUnitsAmount
