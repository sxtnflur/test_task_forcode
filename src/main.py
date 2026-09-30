from contextlib import asynccontextmanager
from pathlib import Path
import sentry_sdk
import structlog
import tomllib
import uvicorn
from fastapi import FastAPI

from api.server import FastAPIServer
from client import ProxyClientPool
from log_masking import MASKED_FIELDS
from utils.httpx import AsyncLoggingClient
from utils.logging import configure_structlog
from settings import Settings


settings = Settings()


def _get_service_version() -> str:
    # Путь не зависит от рабочей директории: тесты могут запускаться из любой
    with open(Path(__file__).resolve().parent.parent / "pyproject.toml", "rb") as f:
        project_data = tomllib.load(f)
    version: str = project_data["tool"]["poetry"]["version"]
    return version


configure_structlog(
    service_name=settings.ELASTIC_APM_SERVICE_NAME,
    service_version=_get_service_version(),
    log_level=settings.LOG_LEVEL,
)


def add_elasticapm_middleware(app_: FastAPI):
    from elasticapm.base import get_client
    from elasticapm.contrib.starlette import ElasticAPM
    from elasticapm.contrib.starlette import make_apm_client

    apm = get_client()
    if apm is None:
        apm = make_apm_client(
            {
                "SERVICE_NAME": settings.ELASTIC_APM_SERVICE_NAME,
                "SERVER_URL": settings.ELASTIC_APM_SERVER_URL,
                "SECRET_TOKEN": settings.ELASTIC_APM_SECRET_TOKEN,
                "ENVIRONMENT": settings.ELASTIC_APM_ENVIRONMENT,
            }
        )
    app_.add_middleware(ElasticAPM, client=apm)


def create_app(*args, **kwargs):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        if not settings.SECURE_REDIRECT_KEY:
            # Не критично: ключ нужен только терминалам с secure_redirect_url, их продажи отклоняются
            structlog.get_logger().warning("secure_redirect_key_not_set")
        # Используется и клиентом процессинга: настройки терминала в его ответах содержат секрет
        app.state.httpx_client = AsyncLoggingClient(timeout=settings.REQUEST_TIMEOUT, masked_fields=MASKED_FIELDS)
        app.state.proxy_clients = ProxyClientPool(timeout=settings.REQUEST_TIMEOUT, masked_fields=MASKED_FIELDS)
        yield
        await app.state.proxy_clients.aclose()
        await app.state.httpx_client.aclose()

    app = FastAPIServer(
        FastAPI(
            title="GateNambaOne",
            docs_url="/api/openapi",
            openapi_url="/api/openapi.json",
            version=_get_service_version(),
            lifespan=lifespan,
        ),
        settings
    ).get_app()

    if settings.ELASTIC_APM_ENABLED:
        add_elasticapm_middleware(app)

    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            # Установите traces_sample_rate в 1.0, чтобы собирать 100% транзакций для мониторинга производительности. В
            # продакшене рекомендуется подобрать это значение,
            traces_sample_rate=settings.SENTRY_SAMPLE_RATE,
        )

    return app


if __name__ == "__main__":
    uvicorn.run(
        "main:create_app",
        factory=True,
        host=settings.WEB_SERVICE_HOST,
        port=settings.WEB_SERVICE_PORT,
        log_level=settings.LOG_LEVEL,
        reload=settings.DEBUG,
        access_log=False,
    )
