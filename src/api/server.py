from fastapi import FastAPI

from settings import Settings
from api.errors import register_errors
from api.routers import v2_router, notifications_router
from utils.fastapi.middleware import LoggingMiddleware, TraceIDMiddleware, IgnoredRoute
from log_masking import MASKED_FIELDS


class FastAPIServer:
    def __init__(self, app: FastAPI, settings: Settings):
        self._register_routers(
            app,
            notifications_prefix=settings.NOTIFICATIONS_PREFIX
        )
        self._register_middlewares(app)
        self._register_errors(app)
        self.__app = app

    @staticmethod
    def _register_routers(app, notifications_prefix: str):
        app.include_router(v2_router, prefix="/v2")
        app.include_router(notifications_router, prefix=notifications_prefix)

    @staticmethod
    def _register_errors(app):
        register_errors(app)

    @staticmethod
    def _register_middlewares(app):
        app.add_middleware(
            LoggingMiddleware,
            ignored_routes=[
                IgnoredRoute(path="/api/openapi"),
                IgnoredRoute(path="/api/openapi.json"),
                IgnoredRoute(path="/v2/ping"),
            ],
            masked_fields=MASKED_FIELDS,
            log_invoice_id=True,
        )
        app.add_middleware(TraceIDMiddleware)

    def get_app(self):
        return self.__app
