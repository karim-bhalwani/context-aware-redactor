# redaction/core/loader.py

"""Configuration and pattern loader for redaction engine."""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

from redaction.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class PatternLoader:
    """Singleton loader for patterns, vocabulary, and configuration.

    Loads configuration once from patterns.yaml and caches it for the
    application lifecycle. Thread-safe for concurrent requests.
    """

    _instance: Optional["PatternLoader"] = None
    _config: Dict[str, Any] = {}
    _loaded: bool = False
    _cached_stop_words: Set[str] = set()

    def __new__(cls) -> "PatternLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not PatternLoader._loaded:
            self._load_config()

    def _load_config(self) -> None:
        """Loads patterns.yaml from the module directory.

        Raises:
            ConfigurationError: If file is missing, invalid, or empty.
        """
        try:
            config_path = Path(__file__).parent / "patterns.yaml"

            if not config_path.exists():
                error_msg = f"Configuration file not found: {config_path}"
                logger.error(error_msg)
                raise ConfigurationError(error_msg)

            with open(config_path, "r", encoding="utf-8") as f:
                PatternLoader._config = yaml.safe_load(f)

            if not PatternLoader._config:
                raise ConfigurationError("Configuration file is empty or invalid")

            self._validate_config()

            # Pre-compute stop words for fast access
            stop_list = PatternLoader._config.get("vocabulary", {}).get(
                "stop_words", []
            )
            PatternLoader._cached_stop_words = set(stop_list)

            PatternLoader._loaded = True
            logger.info(
                "Configuration loaded successfully",
                extra={
                    "config_path": str(config_path),
                    "pattern_count": len(PatternLoader._config.get("patterns", {})),
                    "vocab_count": len(PatternLoader._config.get("vocabulary", {})),
                },
            )

        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}", exc_info=True)
            raise ConfigurationError(f"Failed to parse patterns.yaml: {e}") from e
        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            logger.error(f"Configuration loading failed: {e}", exc_info=True)
            raise ConfigurationError(f"Failed to load configuration: {e}") from e

    def _validate_config(self) -> None:
        """Validates required configuration sections exist.

        Raises:
            ConfigurationError: If required sections are missing.
        """
        required_sections = ["patterns", "vocabulary", "provinces"]
        missing = [s for s in required_sections if s not in PatternLoader._config]

        if missing:
            error_msg = f"Missing required configuration sections: {missing}"
            logger.error(error_msg)
            raise ConfigurationError(error_msg)

    @classmethod
    def get_instance(cls) -> "PatternLoader":
        """Returns the singleton instance of PatternLoader."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_patterns(self, entity_type: str) -> List[Dict[str, Any]]:
        """Returns regex patterns for a specific entity type.

        Args:
            entity_type: Entity type constant (e.g., EntityType.PATIENT_NAME)

        Returns:
            List of pattern dictionaries with 'name', 'regex', 'score' keys
        """
        patterns = self._config.get("patterns", {}).get(entity_type, [])
        return patterns if patterns else []

    def get_vocabulary(self, category: str) -> List[str]:
        """Retrieves vocabulary list by category name.

        Args:
            category: Vocabulary category (e.g., 'healthcare_titles')

        Returns:
            List of vocabulary terms, empty list if category not found
        """
        vocab = self._config.get("vocabulary", {}).get(category, [])
        return vocab if vocab else []

    def get_stop_words(self) -> Set[str]:
        """Returns the pre-computed set of stop words."""
        return self._cached_stop_words

    def get_province_keywords(self, province_code: str) -> List[str]:
        """Retrieves validation keywords for a specific province.

        Args:
            province_code: Two-letter province code (e.g., 'ON', 'BC')

        Returns:
            List of context keywords for validation
        """
        keywords = (
            self._config.get("provinces", {}).get(province_code, {}).get("keywords", [])
        )
        return keywords if keywords else []
