import logging
import re
import sys
from typing import cast

import structlog
from structlog.typing import EventDict, WrappedLogger

_SECRET_PATTERN = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)")


def _redact_secrets(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Redact sensitive values from structured log fields."""
    for key in list(event_dict):
        if _SECRET_PATTERN.search(str(key)):
            event_dict[key] = "[REDACTED]"

    return event_dict


def configure_logging() -> None:
    """Configure application-wide structured logging."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _redact_secrets,
            structlog.stdlib.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
        force=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structured logger for the given module name."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
