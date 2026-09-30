import json
from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

MASK = "***"


@dataclass(frozen=True)
class MaskedField:
    """Поле, которое маскируется везде, где встречается в логируемых данных, на любом уровне вложенности."""

    name: str
    method: Callable[[Any], Any]


def mask_pan(value: Any) -> str:
    pan = str(value)
    if len(pan) < 13:
        return MASK
    return f"{pan[:6]}{'*' * (len(pan) - 10)}{pan[-4:]}"


def mask_cvc(value: Any) -> str:
    return MASK


DEFAULT_MASKED_FIELDS = (
    MaskedField(name="pan", method=mask_pan),
    MaskedField(name="cvc", method=mask_cvc),
)


def mask_data(data: Any, fields: Sequence[MaskedField]) -> Any:
    methods = {field.name: field.method for field in fields}
    return _mask(data, methods)


def _mask(data: Any, methods: dict[str, Callable[[Any], Any]]) -> Any:
    if isinstance(data, dict):
        return {
            key: methods[key](value) if key in methods and value is not None else _mask(value, methods)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_mask(item, methods) for item in data]
    return data


def mask_body(body: bytes, fields: Sequence[MaskedField], max_length: int) -> Any:
    """Готовит сырое тело HTTP к логированию: JSON маскируется, все остальное обрезается как текст."""
    if not body:
        return None
    try:
        return mask_data(json.loads(body), fields)
    except ValueError:
        text = body.decode(errors="replace")
        return text if len(text) <= max_length else f"{text[:max_length]}...<truncated>"
