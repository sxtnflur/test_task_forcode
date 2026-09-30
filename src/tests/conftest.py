import os
import sys
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

os.environ.update(
    {
        "CDS_URL": "http://test-cds.com",
        "CDS_AUTH_TOKEN": "test-cds-token",
        "SBANK_API_BASE_URL": "http://test-sbank-api.com",
        "SBANK_RADMIN_BASE_URL": "http://test-sbank-radmin.com",
        "SBANK_API_AUTH_TOKEN": "test-sbank-token",
        "SECURE_REDIRECT_KEY": "test-secure-redirect-key",
        # Тесты не отправляют данные в APM
        "ELASTIC_APM_ENABLED": "false",
    }
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Импортируется после установки окружения: main читает настройки при импорте
from gate_nambaone.schemas.terminal_data import TerminalData  # noqa: E402
from main import create_app  # noqa: E402

API_VERSION = "v2"
CDS_URL = "http://test-cds.com"
SBANK_API_URL = "http://test-sbank-api.com"

MERCHANT_ACCOUNT_GUID = "test-merchant-account-guid"
SECRET_KEY = "test-secret-key"
CALLBACK_URL_INVOICE = "https://test-gate.com/callback/invoice"

app = create_app()


@pytest.fixture(scope="session")
def client() -> Generator:
    # Одно приложение на всю сессию: его запуск (новый httpx-клиент с SSL-контекстом) занимает ~0,5 с. pytest_httpx
    # подменяет транспорт httpx, поэтому мокает запросы этого клиента в каждом тесте.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def terminal_data() -> TerminalData:
    return TerminalData(
        provider_base_url="https://test-provider.com",
        merchant_account_guid=MERCHANT_ACCOUNT_GUID,
        provider_secret_key=SECRET_KEY,
        provider_callback_url_invoice=CALLBACK_URL_INVOICE,
        proxy_url="http://localhost:8080",
    )


def dump_terminal_data(terminal_data) -> dict:
    """Данные терминала, готовые для JSON; секрет раскрыт, потому что mode="json" маскирует SecretStr."""
    return {
        **terminal_data.model_dump(mode="json"),
        "provider_secret_key": terminal_data.provider_secret_key.get_secret_value(),
    }


def nambaone_path(path: str) -> str:
    """Путь метода NambaOne Merchant Web API, например `/v1/{guid}/one-time/{id}`. Именно он подписывается."""
    return f"/public/merchant/payment{path}"


def nambaone_url(terminal_data: TerminalData, path: str) -> str:
    base_url = str(terminal_data.provider_base_url).rstrip("/")
    return f"{base_url}{nambaone_path(path)}"


def nambaone_ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"status": "OK", "data": data}


def nambaone_error(error_code: str, message: str) -> dict[str, Any]:
    return {"status": "ERROR", "error": {"errorCode": error_code, "message": message}}
