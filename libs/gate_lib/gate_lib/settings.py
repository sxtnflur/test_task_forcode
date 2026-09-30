from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class GateLibSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Card Data Storage: из него по токену карты берутся данные карты для sale/withdrawal
    CDS_URL: str = ""
    CDS_AUTH_TOKEN: str = ""


@lru_cache
def get_settings() -> GateLibSettings:
    return GateLibSettings()
