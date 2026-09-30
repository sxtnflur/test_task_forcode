import httpx
import pytest
from cds_client.services.cds import CardData
from cds_client.services.cds import CdsClient
from cds_client.services.cds import CdsError
from pytest_httpx import HTTPXMock

CDS_URL = "http://cds.test"
CARD = {"pan": "4111111111111111", "cvc": "123", "exp_month": 12, "exp_year": 2030, "holder": "IVAN IVANOV"}


@pytest.fixture
async def cds():
    async with httpx.AsyncClient() as client:
        yield CdsClient(client, CDS_URL, "token")


@pytest.mark.anyio
async def test_get_card_data(cds: CdsClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url=f"{CDS_URL}/cards/card-1",
        match_headers={"Authorization": "Token token"},
        json=CARD,
    )

    card = await cds.get_card_data("card-1")

    assert card == CardData(**CARD)


def test_card_data_repr_is_masked():
    text = repr(CardData(**CARD))

    assert "4111111111111111" not in text
    assert "123" not in text
    assert "411111***1111" in text


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [404, 500])
async def test_error_status(cds: CdsClient, httpx_mock: HTTPXMock, status_code: int):
    httpx_mock.add_response(url=f"{CDS_URL}/cards/card-1", status_code=status_code)

    with pytest.raises(CdsError, match=str(status_code)):
        await cds.get_card_data("card-1")


@pytest.mark.anyio
async def test_timeout(cds: CdsClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ReadTimeout("timeout"), url=f"{CDS_URL}/cards/card-1")

    with pytest.raises(CdsError):
        await cds.get_card_data("card-1")


@pytest.mark.anyio
async def test_invalid_json(cds: CdsClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{CDS_URL}/cards/card-1", text="not json")

    with pytest.raises(CdsError, match="invalid JSON"):
        await cds.get_card_data("card-1")


@pytest.mark.anyio
async def test_invalid_card_does_not_leak_into_error(cds: CdsClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{CDS_URL}/cards/card-1", json=CARD | {"pan": "4111111111111111abc"})

    with pytest.raises(CdsError) as exc_info:
        await cds.get_card_data("card-1")

    assert "4111111111111111" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.anyio
async def test_not_configured():
    async with httpx.AsyncClient() as client:
        with pytest.raises(CdsError, match="not configured"):
            await CdsClient(client, "", "token").get_card_data("card-1")
