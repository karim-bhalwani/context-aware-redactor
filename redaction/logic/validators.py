# redaction/logic/validators.py

"""Validation strategies for Canadian provincial health numbers."""

import re
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class ValidationLogic:
    """Utility methods for validation algorithms."""

    # Pre-compiled regex patterns for performance
    NON_DIGIT = re.compile(r"[^0-9]")
    NON_ALPHANUM = re.compile(r"[^A-Z0-9]")

    @staticmethod
    def luhn_check(digits: str) -> bool:
        """Performs Modulus 10 (Luhn) checksum validation.

        Args:
            digits: Numeric string to validate

        Returns:
            True if checksum is valid
        """
        if not digits.isdigit():
            return False

        total = 0
        reverse_digits = digits[::-1]

        for i, digit in enumerate(reverse_digits):
            n = int(digit)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n

        return total % 10 == 0

    @staticmethod
    def sanitize(text: str) -> str:
        """Removes non-alphanumeric characters and converts to uppercase.

        Args:
            text: Input string to sanitize

        Returns:
            Sanitized uppercase alphanumeric string
        """
        return ValidationLogic.NON_ALPHANUM.sub("", text.upper())


class ValidatorStrategy(ABC):
    """Base class for province-specific validation strategies."""

    def __init__(self, context_keywords: Optional[List[str]] = None):
        self._context_keywords = context_keywords or []

    @abstractmethod
    def validate(self, text: str) -> bool:
        """Validates health number format and checksum.

        Args:
            text: Health number text to validate

        Returns:
            True if validation passes
        """
        pass

    def context_keywords(self) -> List[str]:
        """Returns context keywords for this province."""
        return self._context_keywords


class OntarioValidator(ValidatorStrategy):
    """Validator for Ontario Health Card Numbers (OHIP)."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        if len(digits) != 10:
            return False
        return ValidationLogic.luhn_check(digits)


class BCValidator(ValidatorStrategy):
    """Validator for British Columbia Personal Health Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        if len(digits) != 10:
            return False
        return ValidationLogic.luhn_check(digits)


class QuebecValidator(ValidatorStrategy):
    """Validator for Quebec RAMQ numbers."""

    # Pre-compiled pattern for RAMQ format (LLLL followed by 8 digits)
    RAMQ_PATTERN = re.compile(r"^[A-Z]{4}\d{8}$")

    def validate(self, text: str) -> bool:
        s = ValidationLogic.sanitize(text)

        if not self.RAMQ_PATTERN.match(s):
            return False

        # Fixed indices:
        # 0-3: Letters (LLLL)
        # 4-5: Year (YY)
        # 6-7: Month (MM)
        # 8-9: Day (DD)
        # 10-11: Sequence (SS)
        month_str = s[6:8]
        day_str = s[8:10]  # Fixed: Was extracting Year (4:6) previously

        if not (month_str.isdigit() and day_str.isdigit()):
            return False

        month = int(month_str)
        day = int(day_str)

        # Validate Month (1-12 male, 51-62 female)
        valid_month = (1 <= month <= 12) or (51 <= month <= 62)

        # Validate Day (Simple 1-31 check, ignoring specific month lengths)
        valid_day = 1 <= day <= 31

        return valid_month and valid_day


class AlbertaValidator(ValidatorStrategy):
    """Validator for Alberta Personal Health Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        if len(digits) != 9:
            return False
        return ValidationLogic.luhn_check(digits)


class SaskatchewanValidator(ValidatorStrategy):
    """Validator for Saskatchewan Health Services Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        if len(digits) != 9:
            return False
        return ValidationLogic.luhn_check(digits)


class ManitobaValidator(ValidatorStrategy):
    """Validator for Manitoba Personal Health Identification Numbers."""

    FAMILY_REG_PATTERN = re.compile(r"^[A-Z]\d{5}$")

    def validate(self, text: str) -> bool:
        s = ValidationLogic.sanitize(text)

        if self.FAMILY_REG_PATTERN.match(s):
            return True

        digits = ValidationLogic.NON_DIGIT.sub("", text)
        if len(digits) == 9:
            return ValidationLogic.luhn_check(digits)

        return False


class NovaScotiaValidator(ValidatorStrategy):
    """Validator for Nova Scotia Health Card Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        if len(digits) != 10:
            return False
        return ValidationLogic.luhn_check(digits)


class NewBrunswickValidator(ValidatorStrategy):
    """Validator for New Brunswick Medicare Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        if len(digits) != 9:
            return False
        return ValidationLogic.luhn_check(digits)


class NewfoundlandValidator(ValidatorStrategy):
    """Validator for Newfoundland and Labrador MCP Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        return len(digits) == 12 and digits.isdigit()


class PEIValidator(ValidatorStrategy):
    """Validator for Prince Edward Island Health Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)

        if not digits.isdigit():
            return False

        if len(digits) in (8, 10):
            return ValidationLogic.luhn_check(digits)

        return False


class NWTValidator(ValidatorStrategy):
    """Validator for Northwest Territories Health Services Numbers."""

    NWT_PATTERN = re.compile(r"^[HD]\d{7}$")

    def validate(self, text: str) -> bool:
        s = ValidationLogic.sanitize(text)
        return bool(self.NWT_PATTERN.match(s))


class NunavutValidator(ValidatorStrategy):
    """Validator for Nunavut Health Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        return len(digits) == 9 and digits.startswith("1") and digits.isdigit()


class YukonValidator(ValidatorStrategy):
    """Validator for Yukon Health Care Insurance Plan Numbers."""

    def validate(self, text: str) -> bool:
        digits = ValidationLogic.NON_DIGIT.sub("", text)
        return len(digits) == 9 and digits.isdigit()


# Cache for validator instances to avoid repeated construction
_validator_cache: Dict[str, ValidatorStrategy] = {}


def get_validator(
    province_code: str, keywords: Optional[List[str]] = None
) -> Optional[ValidatorStrategy]:
    """Factory method to retrieve province-specific validator.

    Uses caching to reuse validator instances (Flyweight pattern).

    Args:
        province_code: Two-letter province code (e.g., 'ON', 'BC')
        keywords: Context keywords for validation

    Returns:
        ValidatorStrategy instance or None if province not found
    """
    cache_key = f"{province_code}_{hash(tuple(keywords)) if keywords else 'None'}"

    if cache_key in _validator_cache:
        return _validator_cache[cache_key]

    lookup = {
        "ON": OntarioValidator,
        "BC": BCValidator,
        "QC": QuebecValidator,
        "AB": AlbertaValidator,
        "SK": SaskatchewanValidator,
        "MB": ManitobaValidator,
        "NS": NovaScotiaValidator,
        "NB": NewBrunswickValidator,
        "NL": NewfoundlandValidator,
        "PE": PEIValidator,
        "NT": NWTValidator,
        "NU": NunavutValidator,
        "YT": YukonValidator,
    }

    validator_class = lookup.get(province_code)

    if validator_class:
        instance = validator_class(context_keywords=keywords)
        _validator_cache[cache_key] = instance
        return instance

    logger.warning(f"No validator found for province code: {province_code}")
    return None
