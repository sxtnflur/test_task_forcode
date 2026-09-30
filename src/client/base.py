from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from typing_extensions import Any
from typing_extensions import Self


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    data: dict | None = None

    @property
    def is_ok(self):
        return self.status < 400


class BaseAPIClient(ABC):
    """
    Abstract API Client. Requires override the method _request()

    Используется как async context manager: реализация, которая владеет соединениями,
    закрывает их в aclose.
    """

    @abstractmethod
    async def _request(self, method: str, path: str, content: bytes, headers: dict[str, Any]) -> Response:
        """
        Нужно реализовать

        raises: ClientRequestError
        returns: Response
        """
        raise NotImplementedError

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Освобождает ресурсы, которыми владеет клиент. По умолчанию освобождать нечего."""

    async def request(
            self,
            method: str,
            path: str,
            body: str = "",
            headers: dict[str, Any] | None = None
    ) -> Response:
        """
        Отправляет уже сериализованное тело: код, подписывающий запросы, должен отправить ровно те байты, что подписал.

        returns: Response
        """
        headers = dict(headers or {})
        if body:
            headers["Content-Type"] = "application/json"

        return await self._request(method, path, content=body.encode(), headers=headers)
