from typing import Any

import httpx
from cds_client.schemas import CardData
from pydantic import ValidationError

from cds_client.errors import CdsError


class CdsClient:
    def __init__(self, httpx_client: httpx.AsyncClient, base_url: str, auth_token: str):
        self.httpx_client = httpx_client
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token

    async def get_card_data(self, card_token: str) -> CardData:
        payload = await self._get(f"/cards/{card_token}")
        try:
            return CardData.model_validate(payload)
        except ValidationError as e:
            # Детали ошибки отбрасываются намеренно: в них содержатся сами данные карты
            raise CdsError(f"Invalid card data in CDS response ({e.error_count()} errors)") from None

    async def _get(self, path: str) -> Any:
        if not self.base_url:
            raise CdsError("CDS is not configured")
        try:
            resp = await self.httpx_client.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Token {self.auth_token}"},
            )
        except httpx.HTTPError as e:
            raise CdsError(f"CDS request failed: {e!r}") from e
        if resp.status_code != httpx.codes.OK:
            raise CdsError(f"CDS responded with status {resp.status_code}")
        try:
            return resp.json()
        except ValueError as e:
            raise CdsError("CDS responded with invalid JSON") from e
