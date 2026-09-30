import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from starlette.types import ASGIApp
from starlette.types import Message
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send

from utils.masking import MaskedField
from utils.masking import mask_body

__all__ = ["IgnoredRoute", "LoggingMiddleware", "MaskedField"]

logger = structlog.get_logger()

# Поля тела запроса, привязываемые к контексту логов, когда включен log_invoice_id
OPERATION_ID_FIELDS = ("invoice_id", "withdrawal_id", "refund_id")


@dataclass(frozen=True)
class IgnoredRoute:
    path: str
    method: str | None = None

    def matches(self, path: str, method: str) -> bool:
        return self.path == path and (self.method is None or self.method.upper() == method)


class LoggingMiddleware:
    """
    Логирует входящие запросы и исходящие ответы с замаскированными телами.

    Сделан как чистый ASGI middleware: тело запроса читается один раз и передается
    приложению повторно, тело ответа собирается из отправленных сообщений.
    """

    def __init__(
        self,
        app: ASGIApp,
        ignored_routes: Sequence[IgnoredRoute] = (),
        masked_fields: Sequence[MaskedField] = (),
        log_invoice_id: bool = False,
        max_body_length: int = 10_000,
    ):
        self.app = app
        self.ignored_routes = ignored_routes
        self.masked_fields = masked_fields
        self.log_invoice_id = log_invoice_id
        self.max_body_length = max_body_length

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._is_ignored(scope):
            await self.app(scope, receive, send)
            return

        request_body = await self._read_body(receive)
        request_payload = mask_body(request_body, self.masked_fields, self.max_body_length)
        if self.log_invoice_id and isinstance(request_payload, dict):
            self._bind_operation_ids(request_payload)

        log = logger.bind(method=scope["method"], path=scope["path"])
        log.info("request", body=request_payload)

        body_sent = False

        async def replay_receive() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            return await receive()

        status_code: int | None = None
        response_chunks: list[bytes] = []

        async def capture_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                response_chunks.append(message.get("body", b""))
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, replay_receive, capture_send)
        except Exception:
            log.exception("request_failed", duration_ms=self._elapsed_ms(started))
            raise

        log.info(
            "response",
            status_code=status_code,
            duration_ms=self._elapsed_ms(started),
            body=mask_body(b"".join(response_chunks), self.masked_fields, self.max_body_length),
        )

    def _is_ignored(self, scope: Scope) -> bool:
        return any(route.matches(scope["path"], scope["method"]) for route in self.ignored_routes)

    @staticmethod
    async def _read_body(receive: Receive) -> bytes:
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    @staticmethod
    def _bind_operation_ids(payload: dict[str, Any]) -> None:
        ids = {field: payload[field] for field in OPERATION_ID_FIELDS if isinstance(payload.get(field), str)}
        if ids:
            structlog.contextvars.bind_contextvars(**ids)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
