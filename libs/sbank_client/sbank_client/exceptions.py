class SbankError(Exception):
    pass


class SbankNotConfiguredError(SbankError):
    pass


class SbankResponseError(SbankError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SbankInvalidIdError(SbankError):
    """Id нельзя подставить в путь URL: он указывал бы на другой ресурс."""
