from decimal import Decimal
from decimal import InvalidOperation

# NambaOne работает с суммами в минорных единицах (тыйынах): 1 KGS = 100 тыйынов
MINOR_UNITS_IN_MAJOR = Decimal(100)
MAJOR_UNITS_QUANT = Decimal("0.01")


def to_minor_units(amount: Decimal) -> str:
    minor = amount * MINOR_UNITS_IN_MAJOR
    if minor != minor.to_integral_value():
        raise ValueError(f"Amount {amount} has more than 2 decimal places")
    return str(int(minor))


def from_minor_units(value: str | int | Decimal) -> Decimal:
    try:
        minor = Decimal(str(value))
    except InvalidOperation as e:
        raise ValueError(f"Amount {value!r} is not a number") from e
    if not minor.is_finite() or minor != minor.to_integral_value():
        raise ValueError(f"Amount {value!r} is not a whole number of minor units")
    return (minor / MINOR_UNITS_IN_MAJOR).quantize(MAJOR_UNITS_QUANT)
