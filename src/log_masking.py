from utils.masking import DEFAULT_MASKED_FIELDS
from utils.masking import MASK
from utils.masking import MaskedField


def mask_secret(value: object) -> str:
    return MASK


# Поля, скрываемые в логах входящих и исходящих HTTP-тел: данные карты и секрет терминала. Секрет приходит в
# terminal_data каждого запроса /v2 и в настройках терминала из процессинга.
MASKED_FIELDS = (
    *DEFAULT_MASKED_FIELDS,
    MaskedField(name="provider_secret_key", method=mask_secret),
)
