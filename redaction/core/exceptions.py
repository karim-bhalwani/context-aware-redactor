# redaction/core/exceptions.py

"""Custom exception hierarchy for the PII Redaction System.

This module defines the specific error types used throughout the application
to differentiate between configuration, initialization, and runtime errors.
"""


class RedactionError(Exception):
    """Base exception for all application-specific errors."""

    pass


class ConfigurationError(RedactionError):
    """Raised when configuration loading or validation fails."""

    pass


class InitializationError(RedactionError):
    """Raised when the engine or external resources fail to initialize."""

    pass


class PipelineError(RedactionError):
    """Raised when a specific processing step in the pipeline fails."""

    pass


class ValidationError(RedactionError):
    """Raised when input validation fails (e.g., invalid text input)."""

    pass
