"""Ошибки операций гейта. Ошибки самого API NambaOne лежат в gate_nambaone.nambaone.errors."""

from gate_lib import const as gate_lib_const

import const


class GateOperationError(Exception):
    """Операцию гейта не удалось выполнить. Публичный метод превращает ошибку в ответ протокола."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class OperationRejected(GateOperationError):
    """Операция точно не состоялась: деньги не двигались."""


class OperationUncertain(GateOperationError):
    """Итог операции неизвестен: деньги могли двинуться."""


class InvalidTerminalData(OperationRejected):
    def __init__(self):
        super().__init__(gate_lib_const.VALIDATION_ERROR, "Terminal data is not valid")


class UnsupportedCurrency(OperationRejected):
    def __init__(self, currency_code: str | None):
        super().__init__(gate_lib_const.VALIDATION_ERROR, f"Currency {currency_code} is not supported")


class UnsupportedAmount(OperationRejected):
    """NambaOne работает в целых тыйынах: сумму с более чем 2 знаками после запятой отправить нельзя."""

    def __init__(self, amount: object):
        super().__init__(gate_lib_const.VALIDATION_ERROR, f"Amount {amount} has more than 2 decimal places")


class SecureRedirectNotConfigured(OperationRejected):
    """Терминал использует secure redirect, но у гейта нет ключа, чтобы его подписать."""

    def __init__(self):
        super().__init__(gate_lib_const.INTERNAL_ERROR, "Secure redirect is not configured")


class ProviderUnavailable(OperationUncertain):
    """NambaOne не ответил или ответил что-то непонятное: запрос мог быть обработан."""

    def __init__(self):
        super().__init__(const.PROVIDER_UNAVAILABLE, "NambaOne is unavailable")


class PaymentOrderNotFound(OperationRejected):
    """NambaOne не вернул заказ по счету: платежная ссылка ему неизвестна."""

    def __init__(self):
        super().__init__(gate_lib_const.PROVIDER_ERROR, "Payment order not found")


class PaymentCreationFailed(OperationRejected):
    """Платежная ссылка создана, но отправить на нее плательщика нельзя."""

    def __init__(self):
        super().__init__(gate_lib_const.INTERNAL_ERROR, "Failed to create payment")


class NotificationRetryableError(Exception):
    """
    Вебхук сейчас нельзя обработать.

    Эндпоинт отвечает кодом не 2xx, поэтому NambaOne повторяет вебхук
    (каждые 5 секунд в течение часа).
    """
