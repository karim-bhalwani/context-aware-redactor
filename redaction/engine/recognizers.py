# redaction/engine/recognizers.py

"""Custom Presidio recognizers for Canadian healthcare PII/PHI."""

import logging
import re
from typing import List, Dict
from presidio_analyzer import (
    Pattern,
    PatternRecognizer,
    RecognizerResult,
    EntityRecognizer,
    AnalysisExplanation,
)
from presidio_analyzer.nlp_engine import NlpArtifacts

from redaction.core.definitions import EntityType
from redaction.core.loader import PatternLoader
from redaction.logic.validators import get_validator
from redaction.engine.cache import PatientNameCache

logger = logging.getLogger(__name__)

_PATTERN_CACHE: Dict[str, List[Pattern]] = {}


def _get_cached_patterns(entity_type: str) -> List[Pattern]:
    """Retrieves list of Pattern objects from cache or creates them."""
    if entity_type in _PATTERN_CACHE:
        return _PATTERN_CACHE[entity_type]

    loader = PatternLoader.get_instance()
    pattern_defs = loader.get_patterns(entity_type)

    if not pattern_defs:
        patterns = []
    else:
        patterns = [
            Pattern(name=p["name"], regex=p["regex"], score=p["score"])
            for p in pattern_defs
        ]

    _PATTERN_CACHE[entity_type] = patterns
    return patterns


class ProvincialHealthRecognizer(PatternRecognizer):
    """Pattern recognizer with provincial health number validation."""

    def __init__(self, province_code: str, entity_type: str):
        loader = PatternLoader.get_instance()
        keywords = loader.get_province_keywords(province_code)

        self.validator = get_validator(province_code, keywords)
        self.province_code = province_code
        patterns = _get_cached_patterns(entity_type)

        super().__init__(
            supported_entity=entity_type,
            name=f"{province_code}_Recognizer",
            patterns=patterns,
            context=self.validator.context_keywords() if self.validator else [],
        )

    def validate_result(self, pattern_text: str) -> bool:
        if not self.validator:
            return True
        result = self.validator.validate(pattern_text)
        if not result:
            logger.debug(
                f"{self.province_code} validation failed for '{pattern_text}'. "
                "Accepting based on format match."
            )
            return True
        return True


class CreditCardRecognizer(PatternRecognizer):
    """Credit card recognizer with prefix and length validation."""

    def __init__(self):
        loader = PatternLoader.get_instance()
        patterns = _get_cached_patterns(EntityType.CREDIT_CARD)
        context = loader.get_vocabulary("credit_card_context")

        super().__init__(
            supported_entity=EntityType.CREDIT_CARD,
            name="CreditCard_Recognizer",
            patterns=patterns,
            context=context,
        )

    def validate_result(self, pattern_text: str) -> bool:
        digits = pattern_text.replace("-", "").replace(" ", "")
        if not (13 <= len(digits) <= 19):
            return False
        if digits[0] not in ["4", "5", "6", "3"]:
            return False
        return True


class PatientNamePatternRecognizer(PatternRecognizer):
    """Stage 1: Regex-based recognizer for explicit patient name patterns."""

    def __init__(self):
        patterns = _get_cached_patterns(EntityType.PATIENT_NAME)
        super().__init__(
            supported_entity=EntityType.PATIENT_NAME,
            name="PatientNamePattern_Recognizer",
            patterns=patterns,
        )


class PatientRoleRecognizer(EntityRecognizer):
    """Stage 2: Dependency-parsing recognizer for patient syntactic roles."""

    def __init__(self):
        super().__init__(
            supported_entities=[EntityType.PATIENT_NAME],
            name="PatientRoleRecognizer",
            supported_language="en",
        )

    def load(self):
        pass

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: NlpArtifacts = None
    ):
        results = []
        if not nlp_artifacts or not nlp_artifacts.tokens:
            return results

        doc = nlp_artifacts.tokens

        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue
            is_patient = any(
                token._.has("role") and token._.role == "PATIENT" for token in ent
            )
            if is_patient:
                score = 0.99
                results.append(
                    RecognizerResult(
                        entity_type=EntityType.PATIENT_NAME,
                        start=ent.start_char,
                        end=ent.end_char,
                        score=score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.name,
                            original_score=score,
                            textual_explanation="Derived from syntactic role (Dependency Parser)",
                        ),
                    )
                )
        return results


class PatientContextRecognizer(EntityRecognizer):
    """Stage 3: Context-based recognizer for patient-specific keywords."""

    def __init__(self):
        super().__init__(
            supported_entities=[EntityType.PATIENT_NAME],
            name="PatientContextRecognizer",
            supported_language="en",
        )
        loader = PatternLoader.get_instance()
        self.patient_keywords = loader.get_vocabulary("patient_context_keywords")

    def load(self):
        pass

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: NlpArtifacts = None
    ):
        results = []
        if not nlp_artifacts or not nlp_artifacts.tokens:
            return results

        doc = nlp_artifacts.tokens

        for ent in doc.ents:
            if ent.label_ != "PERSON":
                continue
            if any(
                t._.has("is_healthcare_provider") and t._.is_healthcare_provider
                for t in ent
            ):
                continue

            context_start = max(0, ent.start_char - 30)
            context = text[context_start : ent.start_char].lower()

            if any(keyword in context for keyword in self.patient_keywords):
                score = 0.90
                results.append(
                    RecognizerResult(
                        entity_type=EntityType.PATIENT_NAME,
                        start=ent.start_char,
                        end=ent.end_char,
                        score=score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.name,
                            original_score=score,
                            textual_explanation="Identified via contextual keywords",
                        ),
                    )
                )
        return results


class PatientNameRecognizer(EntityRecognizer):
    """Final pass recognizer that matches cached patient names.

    This recognizer performs high-confidence matching against full names
    and optimized matching against name parts stored in the request cache.
    """

    def __init__(self, cache: PatientNameCache):
        """Initialize with a specific cache instance (Dependency Injection)."""
        super().__init__(
            supported_entities=[EntityType.PATIENT_NAME],
            name="PatientNameRecognizer",
            supported_language="en",
        )
        self.cache = cache
        self.loader = PatternLoader.get_instance()

    def load(self):
        pass

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: NlpArtifacts = None
    ):
        results = []
        # Cache is provided via DI
        if not self.cache.initialized:
            return results

        healthcare_titles = self.loader.get_vocabulary("healthcare_titles")

        # 1. Match Full Names (High Confidence)
        for full_name in self.cache.full_names:
            if not full_name:
                continue
            pattern = re.escape(full_name)
            for match in re.finditer(pattern, text, re.IGNORECASE):
                score = 0.95
                results.append(
                    RecognizerResult(
                        entity_type=EntityType.PATIENT_NAME,
                        start=match.start(),
                        end=match.end(),
                        score=score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.name,
                            original_score=score,
                            textual_explanation="Matched to identified patient full name",
                        ),
                    )
                )

        # 2. Match Name Parts (One-Pass)
        pattern = self.cache.get_optimized_regex()

        if not pattern:
            return results

        for match in pattern.finditer(text):
            idx = match.start()
            end_idx = match.end()

            # Deduplicate: Don't add if covered by Full Name match
            if any(r.start <= idx and r.end >= end_idx for r in results):
                continue

            # Context check: Exclude doctor names
            context_start = max(0, idx - 15)
            context = text[context_start:idx].lower()

            is_provider = False
            for title in healthcare_titles:
                if re.search(r"\b" + re.escape(title) + r"\b", context):
                    is_provider = True
                    break
                if title.endswith(".") and title in context:
                    is_provider = True
                    break

            if is_provider:
                continue

            score = 0.85
            results.append(
                RecognizerResult(
                    entity_type=EntityType.PATIENT_NAME,
                    start=idx,
                    end=end_idx,
                    score=score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.name,
                        original_score=score,
                        textual_explanation="Matched to identified patient name part",
                    ),
                )
            )

        return results


def create_all_recognizers() -> List[EntityRecognizer]:
    """Create the standard set of recognizers used in the first pass."""
    recognizers = []
    loader = PatternLoader.get_instance()

    # Provincial Health Recognizers
    mapping = [
        ("ON", EntityType.ON_HCN),
        ("BC", EntityType.BC_PHN),
        ("QC", EntityType.QC_RAMQ),
        ("AB", EntityType.AB_PHN),
        ("SK", EntityType.SK_HSN),
        ("MB", EntityType.MB_PHIN),
        ("NS", EntityType.NS_HCN),
        ("NB", EntityType.NB_MEDICARE),
        ("NL", EntityType.NL_MCP),
        ("PE", EntityType.PE_HEALTH),
        ("NT", EntityType.NT_HSN),
        ("NU", EntityType.NU_HEALTH),
        ("YT", EntityType.YT_YHCIP),
    ]

    for code, entity in mapping:
        if not loader.get_patterns(entity):
            logger.warning(
                f"Skipping {code} Health Recognizer: No patterns found for {entity}"
            )
            continue
        recognizers.append(ProvincialHealthRecognizer(code, entity))

    # Regex Recognizers
    other_entities = [
        EntityType.PHONE,
        EntityType.EMAIL,
        EntityType.ADDRESS,
        EntityType.DOB,
        EntityType.POSTAL_CODE,
        EntityType.PROVINCE,
        EntityType.BANK_ACCT,
        EntityType.TX_ID,
        EntityType.BANK_NAME,
        EntityType.MRN,
    ]

    for entity in other_entities:
        patterns = _get_cached_patterns(entity)
        if patterns:
            recognizers.append(
                PatternRecognizer(
                    supported_entity=entity,
                    name=f"Regex_{entity}_Recognizer",
                    patterns=patterns,
                )
            )
        else:
            logger.warning(
                f"Skipping Regex Recognizer for {entity}: No patterns found."
            )

    # Credit Card
    if loader.get_patterns(EntityType.CREDIT_CARD):
        recognizers.append(CreditCardRecognizer())
    else:
        logger.warning("Skipping CreditCardRecognizer: No patterns found.")

    # Patient Name Recognizers
    if loader.get_patterns(EntityType.PATIENT_NAME):
        recognizers.append(PatientNamePatternRecognizer())
    else:
        logger.warning("Skipping PatientNamePatternRecognizer: No patterns found.")

    recognizers.append(PatientContextRecognizer())
    recognizers.append(PatientRoleRecognizer())

    logger.info(f"Initialized {len(recognizers)} recognizers (Pass 1 set)")
    return recognizers
