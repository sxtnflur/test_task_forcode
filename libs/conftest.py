import pytest


@pytest.fixture
def anyio_backend() -> str:
    # Сервис работает только на asyncio
    return "asyncio"
