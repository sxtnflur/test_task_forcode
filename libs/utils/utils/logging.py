import logging
import sys

import structlog
from structlog.typing import EventDict
from structlog.typing import Processor
from structlog.typing import WrappedLogger


def configure_structlog(service_name: str, service_version: str, log_level: str = "info") -> None:
    """Настраивает JSON-логи в stdout с данными сервиса и контекстом запроса (trace_id, invoice_id)."""
    level = logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)

    def add_service_info(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service", service_name)
        event_dict.setdefault("version", service_version)
        return event_dict

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_service_info,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(ensure_ascii=False, default=str),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    # Сторонние библиотеки логируют через стандартный модуль logging
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
