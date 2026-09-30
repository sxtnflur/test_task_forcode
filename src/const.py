# NambaOne работает только с кыргызским сомом
NAMBAONE_CURRENCY = "KGS"

# Коды ошибок гейта (в дополнение к gate_lib.const)
PROVIDER_UNAVAILABLE = "provider_unavailable"
NOT_SUPPORTED = "not_supported"


# errorCode неуспешного заказа на возврат
REFUND_ERROR_MESSAGES = {
    "01": "Requisites not found",
    "02": "Provider is unavailable",
    "03": "Unrecognized response",
}

# Типы вебхуков
PAYMENT_ORDER_WEBHOOK = "PAYMENT_ORDER"
REFUND_ORDER_WEBHOOK = "REFUND_ORDER"
