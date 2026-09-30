"""
Клиент NambaOne Merchant Web API (https://merchant-api-docs.rps.kg/).

Знает только протокол провайдера: не должен зависеть от gate_lib, процессинга и настроек гейта.
"""

from .client import NambaOneClient
from .client import NambaOneConnector
from .client import TransportFactory

__all__ = ["NambaOneClient", "NambaOneConnector", "TransportFactory"]
