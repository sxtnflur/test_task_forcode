# Статусы операций протокола гейта

PENDING = "pending"
COMPLETE = "complete"
FAILED = "failed"

STATUSES = (PENDING, COMPLETE, FAILED)

# Коды ошибок, возвращаемые в поле `code` ответа
VALIDATION_ERROR = "validation_error"
PROVIDER_ERROR = "provider_error"
INTERNAL_ERROR = "internal_error"
CARD_DATA_ERROR = "card_data_error"
