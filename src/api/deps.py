from fastapi import Depends
from fastapi import Request
from sbank_client.client import SbankClient
from typing_extensions import Annotated

from client import HttpxAPIClient
from gate_nambaone.gate_nambaone import GateNambaOne
from gate_nambaone.nambaone import NambaOneConnector
from gate_nambaone.secure_redirect import SecureRedirect


def get_sbank_client(request: Request):
    return SbankClient(
        httpx_client=request.app.state.httpx_client,
        base_url=request.app.state.settings.SBANK_API_BASE_URL,
        radmin_base_url=request.app.state.settings.SBANK_RADMIN_BASE_URL,
        auth_token=request.app.state.settings.SBANK_API_AUTH_TOKEN
    )


SbankDependency = Annotated[SbankClient, Depends(get_sbank_client)]


def get_nambaone_connector(request: Request) -> NambaOneConnector:
    # Единственное место, которое знает, что к NambaOne ходим через httpx: общий клиент или клиент прокси терминала. Оба
    # живут столько же, сколько приложение, поэтому HttpxAPIClient не закрывает их после запроса.
    def transport(proxy_url: str | None) -> HttpxAPIClient:
        if proxy_url is None:
            return HttpxAPIClient(request.app.state.httpx_client)
        return HttpxAPIClient(request.app.state.proxy_clients.get(proxy_url))

    return NambaOneConnector(transport)


NambaOneConnectorDependency = Annotated[NambaOneConnector, Depends(get_nambaone_connector)]


def get_secure_redirect(request: Request, sbank_client: SbankDependency) -> SecureRedirect:
    return SecureRedirect(sbank_client, request.app.state.settings.SECURE_REDIRECT_KEY)


SecureRedirectDependency = Annotated[SecureRedirect, Depends(get_secure_redirect)]


def gate_nambaone(
    request: Request,
    sbank_client: SbankDependency,
    nambaone_connector: NambaOneConnectorDependency,
    secure_redirect: SecureRedirectDependency,
) -> GateNambaOne:
    return GateNambaOne(
        sbank_client=sbank_client,
        nambaone_connector=nambaone_connector,
        secure_redirect=secure_redirect,
        settings=request.app.state.settings
    )


GateNambaOneDependency = Annotated[GateNambaOne, Depends(gate_nambaone)]
