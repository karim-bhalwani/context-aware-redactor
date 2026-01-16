# redaction/core/domain.py

"""Domain models for redaction results."""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class RedactedEntity:
    """Represents a single identified and redacted entity.

    Attributes:
        entity_type: Type of entity (e.g., PATIENT_NAME, PHONE_NUMBER)
        start: Starting character position in original text
        end: Ending character position in original text
        text: Original text of the entity
        score: Confidence score (0.0 to 1.0)
        rule_name: Name of the recognizer that detected this entity
    """

    entity_type: str
    start: int
    end: int
    text: str
    score: float
    rule_name: str = "Unknown"


@dataclass
class RedactionResult:
    """Result object returned by the redaction service.

    Attributes:
        original_text: Unredacted input text
        redacted_text: Text with PII/PHI replaced
        entities: List of detected entities
        metadata: Additional processing information
    """

    original_text: str
    redacted_text: str
    entities: List[RedactedEntity] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
