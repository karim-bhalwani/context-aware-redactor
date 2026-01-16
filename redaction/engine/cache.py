# redaction/engine/cache.py

"""Context-aware cache for patient names identified during redaction."""

import logging
import re
from contextvars import ContextVar
from typing import Set, Optional, Dict, Any, Pattern
from redaction.core.loader import PatternLoader

logger = logging.getLogger(__name__)

_patient_cache_var: ContextVar[Optional["PatientNameCache"]] = ContextVar(
    "patient_cache", default=None
)


class PatientNameCache:
    """Request-scoped storage for identified patient names.

    Uses contextvars to ensure thread-safety in Azure Web Apps environment.
    Each request gets an isolated cache instance to prevent data contamination
    between concurrent users.
    """

    def __init__(self):
        """Initialize empty cache. Use get_instance() for context-safe access."""
        self.full_names: Set[str] = set()
        self.name_parts: Set[str] = set()
        self.initialized: bool = False

        self._cached_regex: Optional[Pattern] = None

        loader = PatternLoader.get_instance()
        self.stop_words: Set[str] = loader.get_stop_words()

        if not self.stop_words:
            if not loader.get_vocabulary("stop_words"):
                logger.debug("Stop words list is empty.")

        logger.debug("PatientNameCache instance created for current context")

    @classmethod
    def get_instance(cls) -> "PatientNameCache":
        """Returns cache instance for current execution context (request)."""
        instance = _patient_cache_var.get()

        if instance is None:
            instance = cls()
            _patient_cache_var.set(instance)

        return instance

    def add_full_name(self, name: str) -> None:
        """Adds confirmed patient name to cache."""
        if not name:
            return

        clean_name = name.strip().lower()

        if clean_name in self.stop_words:
            return

        if clean_name not in self.full_names:
            self.full_names.add(clean_name)

        # Split into parts and store parts
        parts = clean_name.split()
        added_new_part = False

        for part in parts:
            # Stricter filter: Part must be > 2 chars and not a stop word
            if len(part) > 2 and part not in self.stop_words:
                if part not in self.name_parts:
                    self.name_parts.add(part)
                    added_new_part = True

        if added_new_part:
            self._cached_regex = None

        self.initialized = True

    def get_optimized_regex(self) -> Optional[Pattern]:
        """Returns a pre-compiled, optimized regex for all cached name parts.

        Uses lazy instantiation (compile only on read) and memoization.
        """
        if self._cached_regex:
            return self._cached_regex

        if not self.name_parts:
            return None

        # Sort parts by length (descending) to match "Robert" before "Rob"
        sorted_parts = sorted(self.name_parts, key=len, reverse=True)

        # Build optimized regex: \b(?:Part1|Part2|Part3)\b
        pattern_str = r"\b(?:" + "|".join(re.escape(p) for p in sorted_parts) + r")\b"

        try:
            self._cached_regex = re.compile(pattern_str, re.IGNORECASE)
            return self._cached_regex
        except re.error as e:
            logger.error(f"Failed to compile patient name regex: {e}")
            return None

    def is_patient_name(self, text: str) -> bool:
        """Checks if text matches known patient name or name part."""
        text_lower = text.lower().strip()

        if text_lower in self.full_names:
            return True

        if " " not in text_lower and text_lower in self.name_parts:
            return True

        return False

    def mark_initialized(self) -> None:
        """Marks cache as populated by initial recognition stages."""
        self.initialized = True

    def get_summary(self) -> Dict[str, Any]:
        """Returns cache state summary for logging and debugging."""
        return {
            "full_names_count": len(self.full_names),
            "name_parts_count": len(self.name_parts),
            "initialized": self.initialized,
            "regex_cached": self._cached_regex is not None,
        }

    def reset(self) -> None:
        """Clears cache for current context."""
        self.full_names.clear()
        self.name_parts.clear()
        self.initialized = False
        self._cached_regex = None
        logger.debug("PatientNameCache reset for current context")

    def __repr__(self):
        return (
            f"<PatientNameCache "
            f"names={len(self.full_names)} "
            f"parts={len(self.name_parts)} "
            f"context_id={id(self)}>"
        )
