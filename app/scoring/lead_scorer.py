from app.models.lead import Lead, LeadQuality, CustomerType
from app.models.property import Property
from app.config import SCORING_WEIGHTS, LEAD_QUALITY_THRESHOLDS, MARKET_AVERAGES
from app.utils.regions import normalize_location_list


class LeadScorer:
    """Lead scoring calculator."""

    def __init__(self):
        self.weights = SCORING_WEIGHTS
        self.thresholds = LEAD_QUALITY_THRESHOLDS

    def calculate_score(
        self,
        lead: Lead,
        matched_properties: list[Property] | None = None
    ) -> tuple[int, dict]:
        """
        Calculate lead score (0-100) with breakdown.

        Returns:
            Tuple of (total_score, breakdown_dict)
        """
        breakdown = {
            "completeness": 0,
            "realism": 0,
            "match_quality": 0,
            "engagement": 0,
        }

        # === COMPLETENESS (max 30) ===
        completeness_checks = [
            (lead.property_type is not None, 6),
            (lead.min_area_sqm is not None or lead.max_area_sqm is not None, 6),
            (len(lead.preferred_locations) > 0, 6),
            (lead.max_price_czk_sqm is not None, 6),
            (lead.move_in_date is not None or lead.move_in_urgency is not None, 6),
        ]
        breakdown["completeness"] = sum(
            points for condition, points in completeness_checks if condition
        )

        # === REALISM (max 30) ===
        realism_score = 0

        # Check budget realism (using centralized region detection)
        if lead.max_price_czk_sqm and lead.property_type:
            region = normalize_location_list(lead.preferred_locations) or "praha"
            market_avg = MARKET_AVERAGES.get(lead.property_type, {}).get(region, 100)

            if lead.max_price_czk_sqm >= market_avg * 0.9:
                realism_score += 12  # Very realistic budget
            elif lead.max_price_czk_sqm >= market_avg * 0.7:
                realism_score += 8   # Realistic budget
            elif lead.max_price_czk_sqm >= market_avg * 0.5:
                realism_score += 4   # Tight but possible
            # else: 0 points (unrealistic)

        # Check area realism
        if lead.min_area_sqm:
            if lead.min_area_sqm <= 500:
                realism_score += 8   # Standard size
            elif lead.min_area_sqm <= 1000:
                realism_score += 6   # Medium size
            elif lead.min_area_sqm <= 2000:
                realism_score += 4   # Large
            else:
                realism_score += 2   # Very large (harder to fill)

        # Check urgency (urgent = serious buyer)
        if lead.move_in_urgency in ["immediate", "1-3months"]:
            realism_score += 10
        elif lead.move_in_urgency == "3-6months":
            realism_score += 6
        elif lead.move_in_urgency == "flexible":
            realism_score += 4

        breakdown["realism"] = min(realism_score, 30)

        # === MATCH QUALITY (max 25) ===
        match_score = 0
        if matched_properties:
            best_match = matched_properties[0]

            # Check if best match fits criteria
            fits_type = (
                lead.property_type is None or
                best_match.property_type == lead.property_type
            )
            fits_area = (
                lead.min_area_sqm is None or
                best_match.area_sqm >= lead.min_area_sqm
            )
            fits_price = (
                lead.max_price_czk_sqm is None or
                best_match.price_czk_sqm <= lead.max_price_czk_sqm
            )
            fits_location = (
                not lead.preferred_locations or
                any(loc.lower() in best_match.location.lower()
                    for loc in lead.preferred_locations)
            )

            criteria_met = sum([fits_type, fits_area, fits_price, fits_location])
            match_score = int((criteria_met / 4) * 20)

            # Bonus for multiple good matches
            if len(matched_properties) >= 3:
                match_score += 5
            elif len(matched_properties) >= 2:
                match_score += 3

        breakdown["match_quality"] = min(match_score, 25)

        # === ENGAGEMENT (max 15) ===
        engagement_score = 0

        if lead.email:
            engagement_score += 6
        if lead.phone:
            engagement_score += 4
        if lead.company:
            engagement_score += 3
        if lead.name:
            engagement_score += 2

        breakdown["engagement"] = min(engagement_score, 15)

        # Calculate total
        total_score = sum(breakdown.values())
        total_score = min(total_score, 100)

        return total_score, breakdown

    def determine_quality(self, score: int) -> LeadQuality:
        """Determine lead quality tier from score."""
        if score >= self.thresholds["hot"]:
            return LeadQuality.HOT
        elif score >= self.thresholds["warm"]:
            return LeadQuality.WARM
        else:
            return LeadQuality.COLD

    def determine_customer_type(self, lead: Lead) -> CustomerType:
        """Determine customer type based on requirements."""
        # Check completeness
        completeness = lead.requirements_completeness

        if completeness >= 0.8:
            # Check if requirements are realistic
            if self._is_realistic(lead):
                return CustomerType.INFORMED
            else:
                return CustomerType.UNREALISTIC
        else:
            return CustomerType.VAGUE

    def _is_realistic(self, lead: Lead) -> bool:
        """Check if lead requirements are realistic (using centralized region detection)."""
        if not lead.max_price_czk_sqm or not lead.property_type:
            return True  # Can't determine, assume realistic

        region = normalize_location_list(lead.preferred_locations) or "other"
        market_avg = MARKET_AVERAGES.get(lead.property_type, {}).get(region, 100)

        # If budget is less than 50% of market average, unrealistic
        return lead.max_price_czk_sqm >= market_avg * 0.5

    def score_lead(
        self,
        lead: Lead,
        matched_properties: list[Property] | None = None
    ) -> Lead:
        """Score lead and update its fields."""
        score, breakdown = self.calculate_score(lead, matched_properties)

        lead.lead_score = score
        lead.lead_quality = self.determine_quality(score)
        lead.customer_type = self.determine_customer_type(lead)

        if matched_properties:
            lead.matched_properties = [p.id for p in matched_properties]
            lead.best_match_id = matched_properties[0].id if matched_properties else None

        return lead


def calculate_lead_score(
    lead: Lead,
    matched_properties: list[Property] | None = None
) -> tuple[int, LeadQuality, dict]:
    """
    Convenience function to calculate lead score.

    Returns:
        Tuple of (score, quality, breakdown)
    """
    scorer = LeadScorer()
    score, breakdown = scorer.calculate_score(lead, matched_properties)
    quality = scorer.determine_quality(score)
    return score, quality, breakdown
