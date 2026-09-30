class NambaOneError(Exception):
    """Базовая ошибка клиента API NambaOne."""


class NambaOneTransportError(NambaOneError):
    """Запрос не получил ответа: таймаут, ошибка соединения. Итог неизвестен."""


class NambaOneInvalidResponseError(NambaOneError):
    """
    Ответ нельзя разобрать: пустое тело, не JSON, неожиданный формат. Итог неизвестен.

    `is_empty` отмечает ответ со `"status": "OK"`, но без данных: NambaOne нечего
    вернуть на запрос. Что это значит, решает вызывающий код для конкретного метода.
    """

    def __init__(self, message: str, *, is_empty: bool = False):
        super().__init__(message)
        self.is_empty = is_empty


class NambaOneApiError(NambaOneError):
    """NambaOne обработал запрос и ответил `"status": "ERROR"`."""

    def __init__(self, error_code: str, message: str | None = None):
        super().__init__(f"{error_code}: {message}" if message else error_code)
        self.error_code = error_code
        self.message = message
