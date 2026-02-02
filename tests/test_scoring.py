"""
Unit tests for lead scoring.
"""

import pytest
from app.models.lead import Lead, LeadQuality, CustomerType
from app.models.property import Property
from app.scoring.lead_scorer import LeadScorer, calculate_lead_score


class TestLeadScorer:
    """Tests for LeadScorer class."""

    @pytest.mark.unit
    def test_empty_lead_has_low_score(self, lead_scorer, empty_lead):
        """Test that an empty lead has a low score."""
        score, breakdown = lead_scorer.calculate_score(empty_lead)

        assert score < 30, "Empty lead should have low score"
        assert breakdown["completeness"] == 0, "No completeness without info"
        assert breakdown["engagement"] == 0, "No engagement without contact"

    @pytest.mark.unit
    def test_complete_lead_has_high_score(self, lead_scorer, lead_model, property_model):
        """Test that a complete lead with matches has a high score."""
        matched_properties = [property_model]

        score, breakdown = lead_scorer.calculate_score(lead_model, matched_properties)

        assert score >= 70, "Complete lead with match should be HOT"
        assert breakdown["completeness"] == 30, "All info = full completeness"
        assert breakdown["engagement"] == 15, "Full contact = full engagement"

    @pytest.mark.unit
    def test_unrealistic_budget_lowers_score(self, lead_scorer):
        """Test that an unrealistic budget lowers the realism score."""
        lead = Lead(
            property_type="office",
            min_area_sqm=500,
            preferred_locations=["Praha"],
            max_price_czk_sqm=50,  # Way below market (avg is 320)
            move_in_urgency="immediate",
        )

        score, breakdown = lead_scorer.calculate_score(lead, [])

        assert breakdown["realism"] < 20, "Unrealistic budget should lower realism score"

    @pytest.mark.unit
    def test_lead_quality_tiers(self, lead_scorer):
        """Test lead quality tier assignment."""
        assert lead_scorer.determine_quality(85) == LeadQuality.HOT
        assert lead_scorer.determine_quality(70) == LeadQuality.HOT
        assert lead_scorer.determine_quality(55) == LeadQuality.WARM
        assert lead_scorer.determine_quality(40) == LeadQuality.WARM
        assert lead_scorer.determine_quality(30) == LeadQuality.COLD
        assert lead_scorer.determine_quality(0) == LeadQuality.COLD

    @pytest.mark.unit
    def test_customer_type_informed(self, lead_scorer, lead_model):
        """Test detection of informed customer type."""
        customer_type = lead_scorer.determine_customer_type(lead_model)
        assert customer_type == CustomerType.INFORMED

    @pytest.mark.unit
    def test_customer_type_vague(self, lead_scorer):
        """Test detection of vague customer type."""
        vague_lead = Lead(property_type="office")

        customer_type = lead_scorer.determine_customer_type(vague_lead)
        assert customer_type == CustomerType.VAGUE

    @pytest.mark.unit
    def test_customer_type_unrealistic(self, lead_scorer):
        """Test detection of unrealistic customer type."""
        unrealistic_lead = Lead(
            property_type="office",
            min_area_sqm=500,
            preferred_locations=["Praha"],
            max_price_czk_sqm=30,  # Way too low for Prague offices
            move_in_urgency="immediate",
        )

        customer_type = lead_scorer.determine_customer_type(unrealistic_lead)
        assert customer_type == CustomerType.UNREALISTIC

    @pytest.mark.unit
    def test_score_lead_updates_fields(self, lead_scorer, empty_lead, property_model):
        """Test that score_lead updates lead fields."""
        matched = [property_model]

        result = lead_scorer.score_lead(empty_lead, matched)

        assert result.lead_score >= 0
        assert result.lead_quality is not None
        assert result.matched_properties == [property_model.id]
        assert result.best_match_id == property_model.id

    @pytest.mark.unit
    def test_convenience_function(self, lead_model, property_model):
        """Test the calculate_lead_score convenience function."""
        score, quality, breakdown = calculate_lead_score(lead_model, [property_model])

        assert isinstance(score, int)
        assert isinstance(quality, LeadQuality)
        assert isinstance(breakdown, dict)
        assert "completeness" in breakdown
        assert "realism" in breakdown


class TestScoringEdgeCases:
    """Edge case tests for scoring."""

    @pytest.mark.unit
    def test_partial_completeness(self, lead_scorer):
        """Test partial completeness scoring."""
        lead = Lead(
            property_type="warehouse",
            min_area_sqm=500,
            # Missing: locations, price, urgency
        )

        score, breakdown = lead_scorer.calculate_score(lead)

        assert 0 < breakdown["completeness"] < 30

    @pytest.mark.unit
    def test_multiple_matches_bonus(self, lead_scorer, lead_model, sample_properties):
        """Test that multiple matches give a bonus."""
        properties = [Property(**p) for p in sample_properties[:3]]

        score, breakdown = lead_scorer.calculate_score(lead_model, properties)

        # Should have match bonus for 3+ properties
        assert breakdown["match_quality"] > 20

    @pytest.mark.unit
    def test_different_regions_affect_realism(self, lead_scorer):
        """Test that different regions have different market averages."""
        # Prague office
        prague_lead = Lead(
            property_type="office",
            preferred_locations=["Praha"],
            max_price_czk_sqm=320,  # Average for Prague
            move_in_urgency="immediate",
        )

        # Ostrava office (cheaper market)
        ostrava_lead = Lead(
            property_type="office",
            preferred_locations=["Ostrava"],
            max_price_czk_sqm=150,  # Average for Ostrava
            move_in_urgency="immediate",
        )

        _, prague_breakdown = lead_scorer.calculate_score(prague_lead)
        _, ostrava_breakdown = lead_scorer.calculate_score(ostrava_lead)

        # Both should have similar realism scores (both are at market average)
        assert prague_breakdown["realism"] > 0
        assert ostrava_breakdown["realism"] > 0

    @pytest.mark.unit
    def test_urgency_affects_realism(self, lead_scorer):
        """Test that urgency level affects realism score."""
        immediate = Lead(
            property_type="warehouse",
            move_in_urgency="immediate",
        )

        flexible = Lead(
            property_type="warehouse",
            move_in_urgency="flexible",
        )

        _, immediate_breakdown = lead_scorer.calculate_score(immediate)
        _, flexible_breakdown = lead_scorer.calculate_score(flexible)

        # Immediate urgency should score higher
        assert immediate_breakdown["realism"] > flexible_breakdown["realism"]
