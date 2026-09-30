import httpx
from typing_extensions import Any
from utils.httpx import AsyncLoggingClient

from client.base import BaseAPIClient, Response
from client.errors import ClientInvalidResponseError
from client.errors import ClientRequestFailed
from client.errors import ClientTimeoutError


class HttpxAPIClient(BaseAPIClient):
    """
    Транспорт поверх httpx.
    """

    def __init__(self,
                 httpx_client: httpx.AsyncClient | None = None,
                 **httpx_client_params
                 ):
        """
        httpx_client: httpx.AsyncClient | None = None
        auth: tuple[str | bytes, str | bytes] | (Request) -> Request | Auth | None = None,
        params: QueryParams | Mapping[str, str | int | float | bool | None | Sequence[str | int | float | bool | None]] | list[tuple[str, str | int | float | bool | None]] | tuple[tuple[str, str | int | float | bool | None], ...] | str | bytes | None = None,
        headers: Headers | Mapping[str, str] | Mapping[bytes, bytes] | Sequence[tuple[str, str]] | Sequence[tuple[bytes, bytes]] | None = None,
        cookies: Cookies | CookieJar | dict[str, str] | list[tuple[str, str]] | None = None,
        verify: str | bool | SSLContext = True,
        cert: str | tuple[str, str | None] | tuple[str, str | None, str | None] | None = None,
        http1: bool = True,
        http2: bool = False,
        proxy: URL | str | Proxy | None = None,
        proxies: URL | str | Proxy | dict[URL | str, None | URL | str | Proxy] | None = None,
        mounts: Mapping[str, AsyncBaseTransport | None] | None = None,
        timeout: float | None | tuple[float | None, float | None, float | None, float | None] | Timeout = DEFAULT_TIMEOUT_CONFIG,
        follow_redirects: bool = False,
        limits: Limits = DEFAULT_LIMITS,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        event_hooks: Mapping[str, list[(...) -> Any]] | None = None,
        base_url: URL | str = "",
        transport: AsyncBaseTransport | None = None,
        app: (...) -> Any | None = None,
        trust_env: bool = True,
        default_encoding: str | (bytes) -> str = "utf-8")
        """

        if httpx_client is not None and httpx_client_params:
            raise ValueError('Set either: httpx_client or httpx_client_params')

        # Клиент, переданный снаружи, общий, поэтому здесь он не закрывается
        self._owns_client = httpx_client is None
        self._client = httpx_client or AsyncLoggingClient(**httpx_client_params)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(self, method: str, path: str, content: bytes, headers: dict[str, Any]) -> Response:
        try:
            resp = await self._client.request(method, path, content=content, headers=headers)
        except httpx.TimeoutException as e:
            raise ClientTimeoutError(f"Request failed with timeout: {e!r}") from e
        except httpx.HTTPError as e:
            raise ClientRequestFailed(f"Request failed: {e!r}") from e

        if not resp.content.strip():
            raise ClientInvalidResponseError(f"Empty response, HTTP {resp.status_code}")
        try:
            return Response(
                status=resp.status_code,
                data=resp.json()
            )
        except ValueError as e:
            raise ClientInvalidResponseError(f"Response is not JSON, HTTP {resp.status_code}") from e


class ProxyClientPool:
    """
    Один httpx-клиент на каждый URL прокси, общий для всех запросов через этот прокси.

    Создание клиента собирает SSL-контекст и новый пул соединений, а это слишком медленно для каждого запроса.
    Клиенты живут столько же, сколько приложение, и закрываются при остановке.
    """

    def __init__(self, **httpx_client_params: Any):
        self._params = httpx_client_params
        self._clients: dict[str, AsyncLoggingClient] = {}

    def get(self, proxy_url: str) -> AsyncLoggingClient:
        # Метод синхронный, поэтому два одновременных запроса не могут создать два клиента для одного прокси
        client = self._clients.get(proxy_url)
        if client is None:
            client = self._clients[proxy_url] = AsyncLoggingClient(proxy=proxy_url, **self._params)
        return client

    async def aclose(self) -> None:
        clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            await client.aclose()
