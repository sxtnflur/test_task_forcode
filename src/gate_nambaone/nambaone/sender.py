import base64
import hashlib
import hmac
import json
import uuid
from typing import TypeVar
from urllib.parse import quote

from pydantic import BaseModel
from pydantic import ValidationError

from client import BaseAPIClient
from client import ClientRequestError
from client import HttpClientError
from gate_nambaone.nambaone.error_codes import ErrorCodeEnum
from gate_nambaone.nambaone.errors import NambaOneApiError
from gate_nambaone.nambaone.errors import NambaOneInvalidResponseError
from gate_nambaone.nambaone.errors import NambaOneTransportError
from gate_nambaone.nambaone.schemas import Envelope

ModelT = TypeVar("ModelT", bound=BaseModel)

API_PREFIX = "/public/merchant/payment"
SALT_HEADER = "x-merchant-api-salt"
SIGNATURE_HEADER = "x-merchant-api-signature"


def sign(secret_key: str, path: str, body: str, salt: str) -> str:
    """HMAC-SHA512 от `path + body + salt` с секретом мерчанта, в кодировке Base64."""
    digest = hmac.new(secret_key.encode(), f"{path}{body}{salt}".encode(), hashlib.sha512).digest()
    return base64.b64encode(digest).decode()


def segment(value: str) -> str:
    """Наши id попадают в путь URL, поэтому экранируются (подпись считается по экранированному пути)."""
    return quote(value, safe="")


def serialize_model(payload: BaseModel) -> str:
    return json.dumps(
        payload.model_dump(mode="json", by_alias=True, exclude_none=True),
        ensure_ascii=False,
        separators=(",", ":"),
    )


class NambaOneRequestSender:
    """
    Отправляет подписанные запросы в NambaOne Merchant Web API и распаковывает конверт ответа.

    Ничего не знает о конкретных методах. Ошибки поднимаются так:
    - NambaOneApiError: NambaOne ответил ошибкой, запрос отклонен;
    - NambaOneTransportError / NambaOneInvalidResponseError: итог неизвестен.
    """

    def __init__(self, transport: BaseAPIClient, base_url: str, secret_key: str):
        self._transport = transport
        self._base_url = base_url.rstrip("/")
        self._secret_key = secret_key

    async def request(
        self,
        method: str,
        path: str,
        payload: BaseModel | None = None,
        *,
        response_model: type[ModelT]
    ) -> ModelT:
        path = f"{API_PREFIX}{path}"
        # Подпись покрывает точные байты тела, поэтому тело сериализуется здесь и отправляется как есть. Запросы без
        # тела подписываются пустой строкой, как требует документация.
        body = "" if payload is None else serialize_model(payload)
        try:
            response = await self._transport.request(
                method=method,
                path=f"{self._base_url}{path}",
                body=body,
                headers=self._headers(path, body),
            )
        except ClientRequestError as e:
            raise NambaOneTransportError(f"NambaOne request failed: {e!r}") from e
        except HttpClientError as e:
            raise NambaOneInvalidResponseError(str(e)) from e

        try:
            envelope = Envelope.model_validate(response.data)
        except ValueError as e:
            # ValidationError - тоже ValueError: оба означают, что тело не то, что присылает NambaOne
            raise NambaOneInvalidResponseError(f"Unexpected response, HTTP {response!r}") from e

        if not envelope.is_ok:
            error = envelope.error
            raise NambaOneApiError(
                error_code=(error.error_code if error else None) or ErrorCodeEnum.UNKNOWN_ERROR,
                message=error.message if error else None,
            )

        if not response.is_ok:
            raise NambaOneInvalidResponseError(f"Status OK with HTTP {response!r}")

        if envelope.data in (None, {}, []):
            raise NambaOneInvalidResponseError(f"Empty {response_model.__name__}, HTTP {response!r}", is_empty=True)

        try:
            return response_model.model_validate(envelope.data)
        except ValidationError as e:
            fields = sorted({".".join(map(str, err["loc"])) for err in e.errors()})
            raise NambaOneInvalidResponseError(
                f"Unexpected {response_model.__name__}, invalid fields: {fields}"
            ) from e

    def _headers(self, path: str, body: str) -> dict[str, str]:
        salt = str(uuid.uuid4())
        return {
            "Accept": "application/json",
            SALT_HEADER: salt,
            SIGNATURE_HEADER: sign(self._secret_key, path, body, salt),
        }
