# redaction/engine/presidio_wrapper.py

"""Presidio-based redaction engine with custom NLP and recognizers."""

import logging
from typing import List, Tuple
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NerModelConfiguration
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from redaction.engine.spacy_driver import CanadianClinicalNlpEngine
from redaction.engine.cache import PatientNameCache
from redaction.core.domain import RedactionResult, RedactedEntity
from redaction.core.definitions import EntityType
from redaction.core.exceptions import (
    InitializationError,
    PipelineError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class PresidioRedactionEngine:
    """Presidio-based engine with Canadian clinical NLP extensions.

    Manages lifecycle of Analyzer and Anonymizer engines with custom
    recognizers for Canadian healthcare PII/PHI.
    """

    def __init__(self, spacy_model_name: str = "en_core_web_lg") -> None:
        """Initialize redaction engine.

        Args:
            spacy_model_name: SpaCy model to use for NLP processing

        Raises:
            InitializationError: If model loading or engine setup fails.
        """
        self.spacy_model = spacy_model_name
        self._analyzer: AnalyzerEngine
        self._anonymizer: AnonymizerEngine
        self._initialize()

    def _initialize(self) -> None:
        """Sets up NLP engine, registry, and Presidio components.

        Raises:
            InitializationError: If components cannot be initialized.
        """
        # Lazy import to prevent circular dependency
        from redaction.engine.recognizers import create_all_recognizers

        ner_mapping = NerModelConfiguration(
            labels_to_ignore=[
                "CARDINAL",
                "ORDINAL",
                "FAC",
                "LAW",
                "PERCENT",
                "QUANTITY",
                "MONEY",
                "WORK_OF_ART",
                "PRODUCT",
                "EVENT",
                "TIME",
            ],
            model_to_presidio_entity_mapping={
                "PER": "PERSON",
                "PERSON": "PERSON",
                "LOC": "LOCATION",
                "GPE": "LOCATION",
                "ORG": "ORGANIZATION",
                "DATE": "DATE_TIME",
            },
        )

        nlp_config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": self.spacy_model}],
        }

        logger.info(f"Initializing NLP engine with model: {self.spacy_model}")

        try:
            # Require the SpaCy model to be installed in the environment.
            nlp_engine = CanadianClinicalNlpEngine(models_config=nlp_config)
            nlp_engine.ner_model_configuration = ner_mapping

        except OSError as e:
            logger.critical(
                f"SpaCy model '{self.spacy_model}' not found. "
                "Ensure it is installed in the environment."
            )
            raise InitializationError(
                f"Missing required SpaCy model '{self.spacy_model}'. Application cannot start."
            ) from e

        try:
            registry = RecognizerRegistry()
            recognizers = create_all_recognizers()

            for rec in recognizers:
                registry.add_recognizer(rec)

            self._analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine)
            self._anonymizer = AnonymizerEngine()

            logger.info(
                "Presidio engine initialized successfully",
                extra={"recognizer_count": len(recognizers)},
            )

        except Exception as e:
            logger.error("Engine initialization failed", exc_info=True)
            raise InitializationError("Failed to initialize Presidio engine") from e

    def process(
        self, text: str, entities: List[str], threshold: float
    ) -> RedactionResult:
        """Analyzes and redacts input text using a Two-Pass architecture.

        Args:
            text: Raw input text to redact
            entities: List of entity types to detect
            threshold: Confidence threshold for entity acceptance

        Returns:
            RedactionResult with redacted text and metadata
        """
        # Lazy import to prevent circular dependency
        from redaction.engine.recognizers import PatientNameRecognizer

        if not text:
            raise ValidationError("Input text cannot be empty")

        if not entities:
            raise ValidationError("Entity list cannot be empty")

        try:
            # 0. Safety: Reset the ContextVar cache
            cache = PatientNameCache.get_instance()
            cache.reset()

            # Parse text once (Request-Scoped NLP)
            # We explicitly run NLP pipeline here and pass artifacts to recognizers
            # to guarantee single-pass NLP processing.
            nlp_artifacts = self._analyzer.nlp_engine.process_text(text, language="en")

            # 1. Pass 1: Run standard recognizers using pre-computed artifacts
            results_pass_1 = self._analyzer.analyze(
                text=text,
                entities=entities,
                language="en",
                score_threshold=threshold,
                nlp_artifacts=nlp_artifacts,  # Pass artifacts to avoid re-parsing
            )

            # 2. Update Cache (Control Layer)
            for result in results_pass_1:
                if result.entity_type == EntityType.PATIENT_NAME:
                    entity_text = text[result.start : result.end]
                    cache.add_full_name(entity_text)

            # 3. Pass 2: Ad-Hoc Recognition using populated Cache
            results_pass_2 = []
            if cache.initialized and EntityType.PATIENT_NAME in entities:
                patient_recognizer = PatientNameRecognizer(cache=cache)
                results_pass_2 = patient_recognizer.analyze(
                    text=text,
                    entities=[EntityType.PATIENT_NAME],
                    nlp_artifacts=nlp_artifacts,  # Pass artifacts if needed for future logic
                )

            combined_results = list(results_pass_1)

            # Create list of exclusion intervals from Pass 1: [(start, end), ...]
            # Sort by start position for potential binary search optimization,
            # though linear scan over intervals is fast enough for typical doc sizes.
            exclusion_zones: List[Tuple[int, int]] = sorted(
                [(r.start, r.end) for r in results_pass_1], key=lambda x: x[0]
            )

            for r in results_pass_2:
                is_overlapping = False

                # Check overlap against exclusion zones
                # Interval A (r) overlaps Interval B (zone) if:
                # r.start < zone.end AND r.end > zone.start
                for zone_start, zone_end in exclusion_zones:
                    if zone_start >= r.end:
                        break

                    if r.start < zone_end and r.end > zone_start:
                        is_overlapping = True
                        break

                if not is_overlapping:
                    combined_results.append(r)
                    # Add new result to exclusion zones to prevent self-overlap in Pass 2
                    # (Insert in order to maintain sort)
                    # For simplicity in this implementation, we append and re-sort only if needed,
                    # but typically Pass 2 results don't overlap *each other* due to regex logic.
                    # We just rely on the initial Pass 1 exclusion zones for safety.
                else:
                    logger.debug(
                        "Discarding Pass 2 result due to overlap",
                        extra={"text": text[r.start : r.end], "type": r.entity_type},
                    )

            # 5. Anonymize
            operators = {
                entity_type: OperatorConfig(
                    "replace", {"new_value": f"<{entity_type}>"}
                )
                for entity_type in entities
            }

            operators.update(
                {
                    "PERSON": OperatorConfig("replace", {"new_value": "<PERSON>"}),
                    "LOCATION": OperatorConfig("replace", {"new_value": "<LOCATION>"}),
                    "ORGANIZATION": OperatorConfig(
                        "replace", {"new_value": "<ORGANIZATION>"}
                    ),
                    "DATE_TIME": OperatorConfig("replace", {"new_value": "<DATE>"}),
                }
            )

            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=combined_results,
                operators=operators,
            )

            domain_entities = [
                RedactedEntity(
                    entity_type=r.entity_type,
                    start=r.start,
                    end=r.end,
                    text=text[r.start : r.end],
                    score=r.score,
                    rule_name=(
                        r.analysis_explanation.recognizer
                        if r.analysis_explanation
                        else "Unknown"
                    ),
                )
                for r in combined_results
            ]

            logger.info(
                "Redaction completed",
                extra={
                    "entity_count": len(domain_entities),
                    "text_length": len(text),
                    "threshold": threshold,
                    "cache_size": len(cache.full_names),
                },
            )

            return RedactionResult(
                original_text=text,
                redacted_text=anonymized.text,
                entities=domain_entities,
                metadata={
                    "count": len(combined_results),
                    "engine": "CanadianClinicalNlpEngine",
                    "entity_types": list(set(e.entity_type for e in domain_entities)),
                },
            )

        except (ValidationError, InitializationError):
            raise
        except Exception as e:
            logger.error(
                "Redaction processing failed",
                exc_info=True,
                extra={"text_length": len(text), "threshold": threshold},
            )
            raise PipelineError(f"Failed to process redaction: {e}") from e
