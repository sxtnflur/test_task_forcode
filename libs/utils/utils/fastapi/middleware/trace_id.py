import uuid

import structlog
from starlette.datastructures import Headers
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp
from starlette.types import Message
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send

TRACE_ID_HEADER = "X-Trace-ID"


class TraceIDMiddleware:
    """
    Привязывает trace id к каждой записи лога запроса.

    Id берется из входящего заголовка (чтобы продолжить трассировку, начатую выше по цепочке)
    или генерируется и возвращается в заголовке ответа.
    """

    def __init__(self, app: ASGIApp, header_name: str = TRACE_ID_HEADER):
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = Headers(scope=scope).get(self.header_name) or uuid.uuid4().hex

        async def send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[self.header_name] = trace_id
            await send(message)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            structlog.contextvars.clear_contextvars()
