from decimal import Decimal

import const
from gate_nambaone.errors import UnsupportedAmount, UnsupportedCurrency
from gate_nambaone.nambaone.amounts import to_minor_units


def validate_money(currency_code: str, amount: Decimal) -> None:
    """Проверяет валюту и сумму операции до отправки в NambaOne."""
    validate_currency(currency_code)
    try:
        to_minor_units(amount)
    except ValueError:
        raise UnsupportedAmount(amount) from None


def validate_currency(currency_code: str | None):
    """Проверяет валюту до отправки в NambaOne."""
    if currency_code != const.NAMBAONE_CURRENCY:
        raise UnsupportedCurrency(currency_code)