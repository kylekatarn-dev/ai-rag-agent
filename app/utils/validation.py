"""
Input validation and sanitization utilities.

Provides protection against prompt injection and handles edge cases.
"""

import re
from typing import Optional

from app.utils import get_logger

logger = get_logger(__name__)


# Maximum allowed message length (characters)
MAX_MESSAGE_LENGTH = 10000

# Patterns that might indicate prompt injection attempts
SUSPICIOUS_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"new\s+instructions?:",
    r"system\s*:\s*",
    r"<\s*system\s*>",
    r"\[\s*system\s*\]",
    r"you\s+are\s+now\s+a",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if",
    r"jailbreak",
    r"bypass\s+(all\s+)?restrictions",
]

# Compiled patterns for efficiency
_SUSPICIOUS_REGEX = [
    re.compile(pattern, re.IGNORECASE) for pattern in SUSPICIOUS_PATTERNS
]


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class InputValidator:
    """
    Validates and sanitizes user input before processing.

    Features:
    - Length validation
    - Suspicious pattern detection
    - Character sanitization
    - Encoding normalization
    """

    def __init__(
        self,
        max_length: int = MAX_MESSAGE_LENGTH,
        detect_injection: bool = True,
        log_suspicious: bool = True,
    ):
        """
        Initialize validator.

        Args:
            max_length: Maximum allowed message length
            detect_injection: Whether to detect prompt injection attempts
            log_suspicious: Whether to log suspicious patterns
        """
        self.max_length = max_length
        self.detect_injection = detect_injection
        self.log_suspicious = log_suspicious

    def validate(self, message: str) -> tuple[bool, Optional[str]]:
        """
        Validate user message.

        Args:
            message: User input message

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for None or empty
        if not message:
            return False, "Zprava je prazdna."

        # Check length
        if len(message) > self.max_length:
            return False, f"Zprava je prilis dlouha (max {self.max_length} znaku)."

        # Check for suspicious patterns
        if self.detect_injection:
            suspicious = self._detect_suspicious_patterns(message)
            if suspicious:
                if self.log_suspicious:
                    logger.warning(f"Suspicious pattern detected: {suspicious}")
                # Don't reject, but log for monitoring
                # In production, you might want to flag these for review

        return True, None

    def sanitize(self, message: str) -> str:
        """
        Sanitize user message.

        Args:
            message: User input message

        Returns:
            Sanitized message
        """
        if not message:
            return ""

        # Normalize unicode
        sanitized = message.strip()

        # Remove null bytes
        sanitized = sanitized.replace("\x00", "")

        # Normalize newlines
        sanitized = sanitized.replace("\r\n", "\n").replace("\r", "\n")

        # Limit consecutive newlines
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)

        # Limit consecutive spaces
        sanitized = re.sub(r" {3,}", "  ", sanitized)

        # Truncate if too long
        if len(sanitized) > self.max_length:
            sanitized = sanitized[: self.max_length - 3] + "..."
            logger.warning(f"Message truncated from {len(message)} to {self.max_length} chars")

        return sanitized

    def validate_and_sanitize(self, message: str) -> tuple[str, Optional[str]]:
        """
        Validate and sanitize message in one step.

        Args:
            message: User input message

        Returns:
            Tuple of (sanitized_message, error_message or None)
        """
        # Sanitize first
        sanitized = self.sanitize(message)

        # Then validate
        is_valid, error = self.validate(sanitized)

        if not is_valid:
            return "", error

        return sanitized, None

    def _detect_suspicious_patterns(self, message: str) -> Optional[str]:
        """
        Detect suspicious patterns that might indicate prompt injection.

        Args:
            message: Message to check

        Returns:
            First matched pattern or None
        """
        for pattern in _SUSPICIOUS_REGEX:
            match = pattern.search(message)
            if match:
                return match.group()
        return None


class EmailValidator:
    """Validates email addresses."""

    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    @classmethod
    def validate(cls, email: str) -> bool:
        """
        Validate email address format.

        Args:
            email: Email address to validate

        Returns:
            True if valid, False otherwise
        """
        if not email:
            return False
        return bool(cls.EMAIL_PATTERN.match(email.strip()))

    @classmethod
    def sanitize(cls, email: str) -> str:
        """
        Sanitize email address.

        Args:
            email: Email to sanitize

        Returns:
            Sanitized email (lowercase, trimmed)
        """
        if not email:
            return ""
        return email.strip().lower()


class PhoneValidator:
    """Validates Czech phone numbers."""

    # Czech phone patterns
    PHONE_PATTERNS = [
        re.compile(r"^\+420\s?\d{3}\s?\d{3}\s?\d{3}$"),  # +420 XXX XXX XXX
        re.compile(r"^00420\s?\d{3}\s?\d{3}\s?\d{3}$"),  # 00420 XXX XXX XXX
        re.compile(r"^\d{3}\s?\d{3}\s?\d{3}$"),  # XXX XXX XXX
    ]

    @classmethod
    def validate(cls, phone: str) -> bool:
        """
        Validate Czech phone number format.

        Args:
            phone: Phone number to validate

        Returns:
            True if valid, False otherwise
        """
        if not phone:
            return False

        cleaned = cls._clean(phone)
        return any(pattern.match(cleaned) for pattern in cls.PHONE_PATTERNS)

    @classmethod
    def sanitize(cls, phone: str) -> str:
        """
        Sanitize and normalize phone number.

        Args:
            phone: Phone number to sanitize

        Returns:
            Normalized phone number with +420 prefix
        """
        if not phone:
            return ""

        cleaned = cls._clean(phone)

        # Remove all non-digits
        digits = re.sub(r"\D", "", cleaned)

        # Handle different formats
        if digits.startswith("420"):
            digits = digits[3:]
        elif digits.startswith("00420"):
            digits = digits[5:]

        if len(digits) == 9:
            return f"+420{digits}"

        return phone.strip()  # Return original if can't normalize

    @classmethod
    def _clean(cls, phone: str) -> str:
        """Remove extra whitespace."""
        return re.sub(r"\s+", " ", phone.strip())


# Singleton validator instance
_input_validator: InputValidator | None = None


def get_input_validator() -> InputValidator:
    """Get singleton InputValidator instance."""
    global _input_validator
    if _input_validator is None:
        _input_validator = InputValidator()
    return _input_validator


def validate_message(message: str) -> tuple[str, Optional[str]]:
    """
    Convenience function to validate and sanitize a message.

    Args:
        message: User input message

    Returns:
        Tuple of (sanitized_message, error_message or None)
    """
    validator = get_input_validator()
    return validator.validate_and_sanitize(message)
