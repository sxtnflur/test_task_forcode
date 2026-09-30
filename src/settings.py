from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    class Config:
        env_file = ".env"
        extra = "allow"

    # Сервис
    WEB_SERVICE_HOST: str = "0.0.0.0"
    WEB_SERVICE_PORT: int = 8000
    LOG_LEVEL: str = "info"
    DEBUG: bool = False
    NOTIFICATIONS_PREFIX: str = "/prefix"
    PROXY_URL: str | None = None
    REQUEST_TIMEOUT: int = 15
    SECURE_REDIRECT_KEY: str = ""
    SECURE_REDIRECT_URL: str = ""
    INTERNAL_SECRET_KEY: str = ""

    # CDS
    CDS_URL: str = ""
    CDS_AUTH_TOKEN: str = ""

    # Sbank
    SBANK_API_BASE_URL: str = ""
    SBANK_RADMIN_BASE_URL: str = ""
    SBANK_API_AUTH_TOKEN: str = ""

    # Sentry
    SENTRY_DSN: str | None = None
    SENTRY_SAMPLE_RATE: float | None = None

    # APM
    ELASTIC_APM_ENABLED: bool = True
    ELASTIC_APM_SERVICE_NAME: str = "gate-nambaone"
    ELASTIC_APM_SERVER_URL: str = ""
    ELASTIC_APM_SECRET_TOKEN: str = ""
    ELASTIC_APM_ENVIRONMENT: str = ""
    ELASTIC_APM_VERIFY_SERVER_CERT: bool = False

    MAX_RETRY_ATTEMPTS: int = 10
    RETRY_DELAY: int = 1

