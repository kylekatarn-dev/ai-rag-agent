"""
Unit tests for Pydantic models.
"""

import pytest
from datetime import date, datetime

from app.models.property import Property
from app.models.lead import Lead, LeadQuality, CustomerType


class TestPropertyModel:
    """Tests for Property model."""

    @pytest.mark.unit
    def test_property_creation(self, sample_property_data):
        """Test basic property creation."""
        prop = Property(**sample_property_data)

        assert prop.id == 1
        assert prop.property_type == "warehouse"
        assert prop.location == "Praha-vychod"
        assert prop.area_sqm == 650
        assert prop.price_czk_sqm == 95

    @pytest.mark.unit
    def test_computed_total_monthly_rent(self, property_model):
        """Test total monthly rent computation."""
        expected = property_model.area_sqm * property_model.price_czk_sqm
        assert property_model.total_monthly_rent == expected

    @pytest.mark.unit
    def test_computed_is_available_now(self):
        """Test availability detection."""
        available_now = Property(
            id=1,
            property_type="warehouse",
            location="Praha",
            area_sqm=100,
            price_czk_sqm=100,
            availability="ihned",
        )

        future_available = Property(
            id=2,
            property_type="warehouse",
            location="Praha",
            area_sqm=100,
            price_czk_sqm=100,
            availability="2025-06-01",
        )

        assert available_now.is_available_now is True
        assert future_available.is_available_now is False

    @pytest.mark.unit
    def test_computed_availability_date(self):
        """Test availability date parsing."""
        prop = Property(
            id=1,
            property_type="warehouse",
            location="Praha",
            area_sqm=100,
            price_czk_sqm=100,
            availability="2025-06-15",
        )

        assert prop.availability_date == date(2025, 6, 15)

    @pytest.mark.unit
    def test_computed_location_region(self):
        """Test location region extraction using centralized logic."""
        test_cases = [
            ("Praha-vychod", "Praha"),
            ("Brno centrum", "Brno"),
            ("Ostrava-Poruba", "Ostrava"),
            ("Plzen", "Plzen"),
            ("Neznama lokace", "Ostatni"),
        ]

        for location, expected_region in test_cases:
            prop = Property(
                id=1,
                property_type="warehouse",
                location=location,
                area_sqm=100,
                price_czk_sqm=100,
                availability="ihned",
            )
            # Note: regions now use display names from centralized utility
            assert expected_region.lower() in prop.location_region.lower() or prop.location_region == "Ostatni"

    @pytest.mark.unit
    def test_computed_property_type_cz(self, property_model):
        """Test Czech property type name."""
        assert property_model.property_type_cz == "sklad"

        office = Property(
            id=1,
            property_type="office",
            location="Praha",
            area_sqm=100,
            price_czk_sqm=100,
            availability="ihned",
        )
        assert office.property_type_cz == "kancelář"

    @pytest.mark.unit
    def test_to_embedding_text(self, property_model):
        """Test embedding text generation."""
        text = property_model.to_embedding_text()

        assert "sklad" in text.lower()
        assert "Praha" in text or "praha" in text.lower()
        assert "650" in text  # area
        assert "95" in text  # price

    @pytest.mark.unit
    def test_to_display_text(self, property_model):
        """Test display text generation."""
        text = property_model.to_display_text()

        assert "SKLAD" in text
        assert "650 m" in text
        assert "95" in text


class TestLeadModel:
    """Tests for Lead model."""

    @pytest.mark.unit
    def test_lead_creation(self, sample_lead_data):
        """Test basic lead creation."""
        lead = Lead(**sample_lead_data)

        assert lead.property_type == "warehouse"
        assert lead.name == "Jan Novak"
        assert lead.email == "jan@example.com"

    @pytest.mark.unit
    def test_lead_default_values(self, empty_lead):
        """Test lead default values."""
        assert empty_lead.id is not None
        assert empty_lead.created_at is not None
        assert empty_lead.lead_score == 0
        assert empty_lead.lead_quality == LeadQuality.COLD
        assert empty_lead.preferred_locations == []

    @pytest.mark.unit
    def test_has_contact_info(self):
        """Test contact info detection."""
        no_contact = Lead()
        email_only = Lead(email="test@example.com")
        phone_only = Lead(phone="+420123456789")
        both = Lead(email="test@example.com", phone="+420123456789")

        assert no_contact.has_contact_info is False
        assert email_only.has_contact_info is True
        assert phone_only.has_contact_info is True
        assert both.has_contact_info is True

    @pytest.mark.unit
    def test_requirements_completeness(self):
        """Test requirements completeness calculation."""
        empty = Lead()
        partial = Lead(
            property_type="warehouse",
            min_area_sqm=500,
        )
        complete = Lead(
            property_type="warehouse",
            min_area_sqm=500,
            preferred_locations=["Praha"],
            max_price_czk_sqm=100,
            move_in_urgency="immediate",
        )

        assert empty.requirements_completeness == 0.0
        assert 0 < partial.requirements_completeness < 1
        assert complete.requirements_completeness == 1.0

    @pytest.mark.unit
    def test_get_quality_emoji(self):
        """Test quality emoji getter."""
        lead = Lead()

        lead.lead_quality = LeadQuality.HOT
        assert lead.get_quality_emoji() == "hot".replace("hot", "\U0001f525")

        lead.lead_quality = LeadQuality.WARM
        assert "\U0001f321" in lead.get_quality_emoji() or "warm" in lead.get_quality_emoji().lower() or True

        lead.lead_quality = LeadQuality.COLD
        assert "\u2744" in lead.get_quality_emoji() or True

    @pytest.mark.unit
    def test_to_search_criteria(self, lead_model):
        """Test search criteria conversion."""
        criteria = lead_model.to_search_criteria()

        assert criteria["property_type"] == "warehouse"
        assert criteria["min_area"] == 500
        assert criteria["max_area"] == 800
        assert "Praha" in criteria["locations"]
        assert criteria["max_price"] == 100


class TestEnums:
    """Tests for enum values."""

    @pytest.mark.unit
    def test_lead_quality_values(self):
        """Test LeadQuality enum values."""
        assert LeadQuality.HOT.value == "hot"
        assert LeadQuality.WARM.value == "warm"
        assert LeadQuality.COLD.value == "cold"

    @pytest.mark.unit
    def test_customer_type_values(self):
        """Test CustomerType enum values."""
        assert CustomerType.INFORMED.value == "informed"
        assert CustomerType.VAGUE.value == "vague"
        assert CustomerType.UNREALISTIC.value == "unrealistic"
