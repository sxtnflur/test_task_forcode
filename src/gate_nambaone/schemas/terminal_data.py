from typing import Annotated

from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import SecretStr
from pydantic import StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TerminalData(BaseModel):
    """Настройки терминала NambaOne (один аккаунт мерчанта)."""

    model_config = ConfigDict(extra="ignore")

    provider_base_url: AnyHttpUrl
    # "Идентификатор" issued by NambaOne
    merchant_account_guid: NonEmptyStr
    # "Секрет" issued by NambaOne, used to sign requests. SecretStr keeps it out of logs and repr.
    provider_secret_key: SecretStr
    # URL эндпоинта /callback/invoice этого гейта: туда NambaOne присылает вебхуки о платежах и возвратах
    provider_callback_url_invoice: AnyHttpUrl
    # Отдельный URL для вебхуков о возвратах, если нужен; по умолчанию они идут на callback счетов
    provider_callback_url_refund: AnyHttpUrl | None = None
    # Point of sale ("точка приема платежей"), optional
    merchant_employee_guid: str | None = None
    proxy_url: str | None = None
    # Если задан, плательщик попадает на платежную ссылку через страницу secure redirect
    secure_redirect_url: AnyHttpUrl | None = None
