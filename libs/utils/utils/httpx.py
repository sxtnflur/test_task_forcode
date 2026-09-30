import time
from collections.abc import Sequence
from typing import Any

import httpx
import structlog

from utils.masking import DEFAULT_MASKED_FIELDS
from utils.masking import MaskedField
from utils.masking import mask_body

logger = structlog.get_logger()


class AsyncLoggingClient(httpx.AsyncClient):
    """httpx.AsyncClient, который логирует каждый исходящий запрос, ответ и ошибку транспорта."""

    def __init__(
        self,
        *args: Any,
        masked_fields: Sequence[MaskedField] = DEFAULT_MASKED_FIELDS,
        max_body_length: int = 10_000,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._masked_fields = masked_fields
        self._max_body_length = max_body_length

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        log = logger.bind(method=request.method, url=str(request.url))
        log.info("http_request", body=self._body(self._request_content(request)))
        started = time.perf_counter()
        try:
            response = await super().send(request, **kwargs)
        except httpx.HTTPError as e:
            log.warning("http_request_failed", error=repr(e), duration_ms=self._elapsed_ms(started))
            raise

        body = None if kwargs.get("stream") else self._body(response.content)
        log.info(
            "http_response",
            status_code=response.status_code,
            duration_ms=self._elapsed_ms(started),
            body=body,
        )
        return response

    def _body(self, content: bytes) -> Any:
        return mask_body(content, self._masked_fields, self._max_body_length)

    @staticmethod
    def _request_content(request: httpx.Request) -> bytes:
        try:
            return request.content
        except httpx.RequestNotRead:
            return b""

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
