from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field


class LeadQuality(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class CustomerType(str, Enum):
    INFORMED = "informed"
    VAGUE = "vague"
    UNREALISTIC = "unrealistic"


class Lead(BaseModel):
    """Potential client/lead model."""

    # Identification
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)

    # Contact info (goal: capture this)
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None

    # Contact preferences
    preferred_contact_method: Literal["email", "phone", "sms"] | None = None
    preferred_call_time: str | None = None  # e.g., "morning", "afternoon", "evening", or specific time

    # Notification preferences (for "no match" scenario)
    wants_notifications: bool = False
    notification_criteria: dict = Field(default_factory=dict)  # Search criteria to watch

    # Broker connection preferences
    wants_broker_contact: bool = False
    scheduled_meeting: datetime | None = None
    meeting_type: Literal["call", "video", "in_person"] | None = None

    # Requirements (extracted from conversation)
    property_type: Literal["warehouse", "office"] | None = None
    min_area_sqm: int | None = None
    max_area_sqm: int | None = None
    preferred_locations: list[str] = Field(default_factory=list)
    max_price_czk_sqm: int | None = None
    move_in_date: date | None = None
    move_in_urgency: Literal["immediate", "1-3months", "3-6months", "flexible"] | None = None

    # Additional preferences
    required_amenities: list[str] = Field(default_factory=list)
    parking_needed: int = 0

    # Qualification
    lead_score: int = 0
    lead_quality: LeadQuality = LeadQuality.COLD
    customer_type: CustomerType | None = None

    # Matching
    matched_properties: list[int] = Field(default_factory=list)
    best_match_id: int | None = None

    # Status
    status: Literal["new", "qualified", "contacted", "meeting_scheduled", "closed"] = "new"
    assigned_broker_id: int | None = None

    # Conversation
    conversation_summary: str = ""
    key_objections: list[str] = Field(default_factory=list)
    follow_up_actions: list[str] = Field(default_factory=list)

    @property
    def has_contact_info(self) -> bool:
        """Check if we have any contact info."""
        return bool(self.email or self.phone)

    @property
    def requirements_completeness(self) -> float:
        """Calculate how complete the requirements are (0-1)."""
        fields = [
            self.property_type is not None,
            self.min_area_sqm is not None or self.max_area_sqm is not None,
            len(self.preferred_locations) > 0,
            self.max_price_czk_sqm is not None,
            self.move_in_date is not None or self.move_in_urgency is not None,
        ]
        return sum(fields) / len(fields)

    def get_quality_emoji(self) -> str:
        """Get emoji for lead quality."""
        return {
            LeadQuality.HOT: "🔥",
            LeadQuality.WARM: "🌡️",
            LeadQuality.COLD: "❄️",
        }[self.lead_quality]

    def to_search_criteria(self) -> dict:
        """Convert lead requirements to search criteria."""
        criteria = {}

        if self.property_type:
            criteria["property_type"] = self.property_type
        if self.preferred_locations:
            criteria["locations"] = self.preferred_locations
        if self.min_area_sqm:
            criteria["min_area"] = self.min_area_sqm
        if self.max_area_sqm:
            criteria["max_area"] = self.max_area_sqm
        if self.max_price_czk_sqm:
            criteria["max_price"] = self.max_price_czk_sqm
        if self.move_in_date:
            criteria["available_by"] = self.move_in_date

        return criteria
