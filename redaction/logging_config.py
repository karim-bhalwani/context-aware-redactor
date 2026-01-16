# redaction/logging_config.py

"""Structured logging configuration for production deployment."""

import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging in Azure environments."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        current_time = datetime.now(timezone.utc).isoformat()

        log_data: Dict[str, Any] = {
            "timestamp": current_time,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra"):
            log_data.update(record.extra)  # type: ignore

        return json.dumps(log_data)


def configure_logging(level: str = "INFO") -> None:
    """Configure application logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if root_logger.handlers:
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(StructuredFormatter())

    root_logger.addHandler(handler)

    # Suppress noisy libraries
    logging.getLogger("presidio").setLevel(logging.WARNING)
    logging.getLogger("spacy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # We use the root logger to log this initialization event
    logging.info(
        "Logging configured successfully",
        extra={"log_level": level, "python_version": sys.version},
    )
