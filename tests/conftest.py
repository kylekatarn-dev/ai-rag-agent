"""
Pytest configuration and shared fixtures.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Generator

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_property_data() -> dict:
    """Sample property data for testing."""
    return {
        "id": 1,
        "property_type": "warehouse",
        "location": "Praha-vychod",
        "area_sqm": 650,
        "price_czk_sqm": 95,
        "availability": "ihned",
        "parking_spaces": 5,
        "amenities": ["rampa", "vytapeni"],
        "is_featured": True,
        "is_hot": False,
        "priority_score": 80,
        "commission_rate": 0.05,
    }


@pytest.fixture
def sample_lead_data() -> dict:
    """Sample lead data for testing."""
    return {
        "property_type": "warehouse",
        "min_area_sqm": 500,
        "max_area_sqm": 800,
        "preferred_locations": ["Praha"],
        "max_price_czk_sqm": 100,
        "move_in_urgency": "immediate",
        "name": "Jan Novak",
        "email": "jan@example.com",
        "phone": "+420777123456",
        "company": "ABC s.r.o.",
    }


@pytest.fixture
def sample_properties(sample_property_data) -> list[dict]:
    """List of sample properties for testing."""
    return [
        sample_property_data,
        {
            **sample_property_data,
            "id": 2,
            "location": "Brno-centrum",
            "area_sqm": 400,
            "price_czk_sqm": 85,
        },
        {
            **sample_property_data,
            "id": 3,
            "property_type": "office",
            "location": "Praha 1",
            "area_sqm": 200,
            "price_czk_sqm": 320,
        },
    ]


# ============================================================================
# Model Fixtures
# ============================================================================

@pytest.fixture
def property_model(sample_property_data):
    """Create a Property model instance."""
    from app.models.property import Property
    return Property(**sample_property_data)


@pytest.fixture
def lead_model(sample_lead_data):
    """Create a Lead model instance."""
    from app.models.lead import Lead
    return Lead(**sample_lead_data)


@pytest.fixture
def empty_lead():
    """Create an empty Lead model instance."""
    from app.models.lead import Lead
    return Lead()


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    def _create_response(content: str, tool_calls: list = None):
        mock_choice = MagicMock()
        mock_choice.message.content = content
        mock_choice.message.tool_calls = tool_calls

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    return _create_response


@pytest.fixture
def mock_openai_streaming_response():
    """Mock OpenAI streaming API response."""
    def _create_chunks(content: str):
        chunks = []
        for char in content:
            mock_delta = MagicMock()
            mock_delta.content = char
            mock_delta.tool_calls = None

            mock_choice = MagicMock()
            mock_choice.delta = mock_delta

            mock_chunk = MagicMock()
            mock_chunk.choices = [mock_choice]
            chunks.append(mock_chunk)
        return iter(chunks)

    return _create_chunks


@pytest.fixture
def mock_openai_client(mock_openai_response):
    """Mock OpenAI client with chat completions."""
    with patch("openai.OpenAI") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        # Default response
        mock_client.chat.completions.create.return_value = mock_openai_response(
            "Mock response from OpenAI"
        )

        yield mock_client


@pytest.fixture
def mock_embeddings():
    """Mock OpenAI embeddings."""
    with patch("openai.OpenAI") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        # Return a list of mock embeddings
        mock_embedding = MagicMock()
        mock_embedding.embedding = [0.1] * 1536  # OpenAI embedding dimension

        mock_response = MagicMock()
        mock_response.data = [mock_embedding]

        mock_client.embeddings.create.return_value = mock_response

        yield mock_client


# ============================================================================
# Service Fixtures
# ============================================================================

@pytest.fixture
def lead_scorer():
    """Create a LeadScorer instance."""
    from app.scoring.lead_scorer import LeadScorer
    return LeadScorer()


@pytest.fixture
def mock_retriever(sample_properties):
    """Mock PropertyRetriever that returns sample properties."""
    from app.models.property import Property

    properties = [Property(**p) for p in sample_properties]

    mock = MagicMock()
    mock.search_properties.return_value = properties[:2]
    mock.find_best_match.return_value = properties[0]
    mock.get_recommendations.return_value = {
        "exact_matches": properties[:2],
        "alternatives": [],
        "relaxed_criteria": [],
        "market_stats": {"warehouse": {"count": 10}, "office": {"count": 10}},
        "total_available": 20,
    }

    return mock


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def mock_config():
    """Mock configuration values."""
    config_values = {
        "OPENAI_API_KEY": "test-api-key",
        "OPENAI_MODEL": "gpt-4o-mini",
        "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
        "SCHEDULING_MODE": "simulated",
        "BROKER_NAME": "Test Broker",
        "BROKER_EMAIL": "broker@test.com",
    }

    with patch.dict("os.environ", config_values):
        yield config_values


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def capture_logs():
    """Capture log output for testing."""
    import logging
    from io import StringIO

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)

    logger = logging.getLogger()
    original_handlers = logger.handlers.copy()
    logger.handlers = [handler]

    yield log_capture

    logger.handlers = original_handlers


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests."""
    yield

    # Reset retriever singleton
    try:
        from app.agent.tools import RetrieverSingleton
        RetrieverSingleton.reset()
    except ImportError:
        pass


# ============================================================================
# Markers
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow tests")
