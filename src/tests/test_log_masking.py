"""Секрет терминала никогда не должен попадать в логи входящих запросов и вызовов процессинга."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock

from gate_nambaone.schemas.terminal_data import TerminalData
from main import settings
from tests.conftest import API_VERSION
from tests.conftest import MERCHANT_ACCOUNT_GUID
from tests.conftest import SBANK_API_URL
from tests.conftest import SECRET_KEY
from tests.conftest import dump_terminal_data
from tests.conftest import nambaone_ok
from tests.conftest import nambaone_url

SBANK_RADMIN_URL = "http://test-sbank-radmin.com"
INVOICE_ID = "00000000-0000-4000-8000-000000000061"
TERMINAL_ID = "7"


def log_records(output: str) -> list[dict[str, Any]]:
    """JSON-записи логов, выведенные structlog; прочий вывод (если есть) пропускается."""
    records = []
    for line in output.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def find_record(records: list[dict[str, Any]], event: str, **fields: Any) -> dict[str, Any]:
    matching = [
        record
        for record in records
        if record.get("event") == event and all(record.get(key) == value for key, value in fields.items())
    ]
    assert matching, f"No {event} record with {fields}"
    return matching[0]


@pytest.fixture
def captured_logs(capfd: pytest.CaptureFixture[str]):
    """structlog пишет в файловый дескриптор stdout, поэтому вывод перехватывается на уровне fd."""
    capfd.readouterr()

    def read() -> tuple[str, list[dict[str, Any]]]:
        output = capfd.readouterr().out
        return output, log_records(output)

    return read


def test_secret_is_masked_in_incoming_request(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, captured_logs
):
    httpx_mock.add_response(
        method="GET",
        url=nambaone_url(terminal_data, f"/v1/{MERCHANT_ACCOUNT_GUID}"),
        json=nambaone_ok(
            {"guid": "g", "status": "AVAILABLE", "currency": "KGS", "balance": "100", "availableBalance": "100"}
        ),
    )

    client.post(f"/{API_VERSION}/balance", json={"currency": "KGS", "terminal_data": dump_terminal_data(terminal_data)})

    output, records = captured_logs()
    request = find_record(records, "request", path=f"/{API_VERSION}/balance")
    assert request["body"]["terminal_data"]["provider_secret_key"] == "***"
    # Остальные поля terminal_data остаются читаемыми
    assert request["body"]["terminal_data"]["merchant_account_guid"] == MERCHANT_ACCOUNT_GUID
    assert SECRET_KEY not in output


def test_secret_is_masked_in_processing_response(
    terminal_data: TerminalData, client: TestClient, httpx_mock: HTTPXMock, captured_logs
):
    # Настройки терминала приходят из процессинга при обработке вебхука
    terminal_url = f"{SBANK_RADMIN_URL}/terminals/{TERMINAL_ID}"
    httpx_mock.add_response(
        method="GET",
        url=f"{SBANK_API_URL}/invoices/{INVOICE_ID}",
        json={"id": INVOICE_ID, "primary_terminal": TERMINAL_ID, "currency_code": "KGS"},
    )
    httpx_mock.add_response(
        method="GET", url=terminal_url, json={"id": TERMINAL_ID, "data": dump_terminal_data(terminal_data)}
    )
    httpx_mock.add_response(
        method="GET",
        url=nambaone_url(terminal_data, f"/v1/{MERCHANT_ACCOUNT_GUID}/one-time/{INVOICE_ID}"),
        json=nambaone_ok({"guid": "order-guid", "status": "PROCESSING"}),
    )

    client.post(
        f"{settings.NOTIFICATIONS_PREFIX}/callback/invoice",
        json={"type": "PAYMENT_ORDER", "data": {"guid": "order-guid", "externalId": INVOICE_ID}},
    )

    output, records = captured_logs()
    response = find_record(records, "http_response", url=terminal_url)
    assert response["body"]["data"]["provider_secret_key"] == "***"
    assert SECRET_KEY not in output
