from typing import Protocol


class GateNamabaOneSettingsProtocol(Protocol):
    MAX_RETRY_ATTEMPTS: int
    RETRY_DELAY: float
    ELASTIC_APM_SERVICE_NAME: str
    REQUEST_TIMEOUT: int

