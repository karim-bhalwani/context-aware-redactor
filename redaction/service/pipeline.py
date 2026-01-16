# redaction/service/pipeline.py

"""Main redaction service pipeline."""

import logging
import threading
from typing import Optional

from redaction.service.config import settings
from redaction.engine.presidio_wrapper import PresidioRedactionEngine
from redaction.core.domain import RedactionResult
from redaction.core.exceptions import (
    InitializationError,
    PipelineError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class RedactionService:
    """Singleton service wrapper for the redaction engine.

    Manages engine lifecycle and provides thread-safe access to
    the redaction functionality.
    """

    _instance: Optional[PresidioRedactionEngine] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> PresidioRedactionEngine:
        """Returns singleton redaction engine instance.

        Returns:
            Initialized PresidioRedactionEngine

        Raises:
            InitializationError: If engine initialization fails
        """
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking pattern
                if cls._instance is None:
                    try:
                        logger.info("Initializing redaction engine")
                        cls._instance = PresidioRedactionEngine(settings.spacy_model)
                        logger.info("Redaction engine initialized successfully")

                    except Exception as e:
                        logger.error(
                            "Failed to initialize redaction engine", exc_info=True
                        )
                        if isinstance(e, InitializationError):
                            raise
                        raise InitializationError(
                            "Redaction engine initialization failed"
                        ) from e

        return cls._instance


def redact_text(text: str) -> RedactionResult:
    """Main entry point for text redaction.

    Args:
        text: Input text to redact

    Returns:
        RedactionResult with redacted text and metadata.
        On failure, returns a result indicating the error safely.
    """
    if not text:
        logger.warning("Empty text provided for redaction")
        return RedactionResult(
            original_text="",
            redacted_text="",
            metadata={"error": "Empty input provided"},
        )

    if not isinstance(text, str):
        logger.error(f"Invalid input type received: {type(text)}")
        return RedactionResult(
            original_text=str(text),
            redacted_text=str(text),
            metadata={"error": "Invalid input format"},
        )

    try:
        engine = RedactionService.get_instance()

        logger.info(
            "Starting redaction request",
            extra={
                "text_length": len(text),
                "threshold": settings.confidence_threshold,
            },
        )

        result = engine.process(
            text=text,
            entities=settings.default_entities,
            threshold=settings.confidence_threshold,
        )

        return result

    except (InitializationError, PipelineError, ValidationError) as e:
        # These are known errors, log with context but hide internal details in response
        logger.error(
            f"Known error during redaction: {type(e).__name__}",
            exc_info=True,
            extra={"text_length": len(text)},
        )
        return RedactionResult(
            original_text=text,
            redacted_text=text,
            metadata={
                "error": "The redaction service encountered a processing error.",
                "status": "failed",
                "error_type": type(e).__name__,
            },
        )

    except Exception:
        # Catch-all for unexpected bugs
        logger.error(
            "Unexpected critical error in redaction pipeline",
            exc_info=True,
            extra={"text_length": len(text)},
        )
        return RedactionResult(
            original_text=text,
            redacted_text=text,
            metadata={
                "error": "An unexpected system error occurred.",
                "status": "failed",
            },
        )
