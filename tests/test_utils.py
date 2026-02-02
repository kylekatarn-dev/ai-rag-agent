"""
Unit tests for utility modules.
"""

import pytest
from app.utils.regions import (
    normalize_region,
    normalize_country,
    extract_region_from_text,
    KNOWN_REGIONS,
    REGION_ALIASES,
)


class TestRegionNormalization:
    """Tests for region normalization utilities."""

    @pytest.mark.unit
    def test_normalize_region_morava(self):
        """Test Morava region normalization."""
        test_cases = ["morava", "Morava", "MORAVA", "moravě", "moravia"]
        for text in test_cases:
            result = normalize_region(text)
            assert result == "Morava", f"Expected 'Morava' for '{text}', got '{result}'"

    @pytest.mark.unit
    def test_normalize_region_cechy(self):
        """Test Čechy region normalization."""
        test_cases = ["čechy", "Čechy", "čechách", "bohemia"]
        for text in test_cases:
            result = normalize_region(text)
            assert result == "Čechy", f"Expected 'Čechy' for '{text}', got '{result}'"

    @pytest.mark.unit
    def test_normalize_region_slezsko(self):
        """Test Slezsko region normalization."""
        test_cases = ["slezsko", "Slezsko", "silesia"]
        for text in test_cases:
            result = normalize_region(text)
            assert result == "Slezsko", f"Expected 'Slezsko' for '{text}', got '{result}'"

    @pytest.mark.unit
    def test_normalize_region_slovensko(self):
        """Test Slovensko region normalization."""
        test_cases = ["slovensko", "Slovensko", "slovakia"]
        for text in test_cases:
            result = normalize_region(text)
            assert result == "Slovensko", f"Expected 'Slovensko' for '{text}', got '{result}'"

    @pytest.mark.unit
    def test_normalize_region_unknown(self):
        """Test unknown regions return None."""
        test_cases = ["Unknown", "Praha", "Brno", ""]
        for text in test_cases:
            result = normalize_region(text)
            assert result is None, f"Expected None for '{text}', got '{result}'"

    @pytest.mark.unit
    def test_normalize_region_empty_input(self):
        """Test empty input handling."""
        assert normalize_region("") is None
        assert normalize_region("   ") is None

    @pytest.mark.unit
    def test_extract_region_from_text(self):
        """Test extracting region from longer text."""
        result = extract_region_from_text("Hledám sklad na Moravě")
        assert result == "Morava"

        result = extract_region_from_text("Kanceláře v Čechách")
        assert result == "Čechy"

    @pytest.mark.unit
    def test_normalize_country(self):
        """Test country normalization."""
        assert normalize_country("česko") == "CZ"
        assert normalize_country("česká republika") == "CZ"
        assert normalize_country("czechia") == "CZ"
        assert normalize_country("slovensko") == "SK"
        assert normalize_country("slovakia") == "SK"

    @pytest.mark.unit
    def test_known_regions_structure(self):
        """Test KNOWN_REGIONS has expected structure."""
        assert "Čechy" in KNOWN_REGIONS
        assert "Morava" in KNOWN_REGIONS
        assert "Slezsko" in KNOWN_REGIONS
        assert "Slovensko" in KNOWN_REGIONS

    @pytest.mark.unit
    def test_region_aliases_structure(self):
        """Test REGION_ALIASES has expected structure."""
        assert "morava" in REGION_ALIASES
        assert "čechy" in REGION_ALIASES
        assert REGION_ALIASES["morava"] == "Morava"
        assert REGION_ALIASES["čechy"] == "Čechy"


class TestLogging:
    """Tests for logging utilities."""

    @pytest.mark.unit
    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger instance."""
        from app.utils.logging import get_logger
        import logging

        logger = get_logger("test_module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_module"

    @pytest.mark.unit
    def test_get_logger_caches_instance(self):
        """Test that get_logger returns the same instance for same name."""
        from app.utils.logging import get_logger

        logger1 = get_logger("cached_test")
        logger2 = get_logger("cached_test")

        assert logger1 is logger2


class TestRetry:
    """Tests for retry utilities."""

    @pytest.mark.unit
    def test_with_retry_success_first_try(self):
        """Test successful execution on first try."""
        from app.utils.retry import with_retry

        call_count = 0

        @with_retry(max_retries=3)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_func()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.unit
    def test_with_retry_retries_on_failure(self):
        """Test retry on transient failure."""
        from app.utils.retry import with_retry
        from openai import APIConnectionError

        call_count = 0

        @with_retry(max_retries=3, initial_delay=0.01)
        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise APIConnectionError(request=None)
            return "success"

        result = fail_twice()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.unit
    def test_with_retry_exhausts_retries(self):
        """Test that max retries is respected."""
        from app.utils.retry import with_retry
        from openai import APIConnectionError

        call_count = 0

        @with_retry(max_retries=2, initial_delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise APIConnectionError(request=None)

        with pytest.raises(APIConnectionError):
            always_fails()

        assert call_count == 3  # Initial + 2 retries

    @pytest.mark.unit
    def test_with_retry_non_retryable_exception(self):
        """Test that non-retryable exceptions are not retried."""
        from app.utils.retry import with_retry

        call_count = 0

        @with_retry(max_retries=3)
        def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            raises_value_error()

        assert call_count == 1  # No retries for ValueError
