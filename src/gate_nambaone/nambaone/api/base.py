from gate_nambaone.nambaone.sender import NambaOneRequestSender


class NambaOneApi:
    """Методы одного ресурса NambaOne для одного аккаунта мерчанта."""

    def __init__(self, sender: NambaOneRequestSender, merchant_account_guid: str):
        self._sender = sender
        self._merchant_account_guid = merchant_account_guid
