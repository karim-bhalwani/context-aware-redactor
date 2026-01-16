# redaction/service/config.py

"""Application configuration using Pydantic Settings.

Manages environment variables, defaults, and validation rules.
"""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from redaction.core.definitions import EntityType


class Settings(BaseSettings):
    """Global application settings.

    Loads values from environment variables (prefix 'REDACTION_') or .env file.
    """

    model_config = SettingsConfigDict(
        env_prefix="REDACTION_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core Settings
    spacy_model: str = Field(
        default="en_core_web_lg", description="SpaCy model name to use for NLP."
    )

    confidence_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score (0.0-1.0) for entity retention.",
    )

    # Entity Configuration
    default_entities: List[str] = Field(
        default_factory=lambda: [
            # Provincial Health Numbers
            EntityType.ON_HCN,
            EntityType.BC_PHN,
            EntityType.QC_RAMQ,
            EntityType.AB_PHN,
            EntityType.SK_HSN,
            EntityType.MB_PHIN,
            EntityType.NS_HCN,
            EntityType.NB_MEDICARE,
            EntityType.NL_MCP,
            EntityType.PE_HEALTH,
            EntityType.NT_HSN,
            EntityType.NU_HEALTH,
            EntityType.YT_YHCIP,
            # General PII/PHI
            EntityType.PATIENT_NAME,
            EntityType.DOB,
            EntityType.PHONE,
            EntityType.EMAIL,
            EntityType.ADDRESS,
            EntityType.POSTAL_CODE,
            EntityType.PROVINCE,
            EntityType.BANK_ACCT,
            EntityType.CREDIT_CARD,
            EntityType.TX_ID,
            EntityType.BANK_NAME,
            EntityType.MRN,
        ],
        description="List of entity types to detect by default.",
    )

    @field_validator("spacy_model")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Ensure model name is not empty."""
        if not v.strip():
            raise ValueError("SpaCy model name cannot be empty")
        return v


# Singleton settings instance
settings = Settings()
