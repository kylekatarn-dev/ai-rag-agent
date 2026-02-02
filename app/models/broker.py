from typing import Literal
from pydantic import BaseModel, Field


class Broker(BaseModel):
    """Real estate broker model."""

    id: int
    name: str
    email: str
    phone: str
    specialization: list[Literal["warehouse", "office"]] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    is_available: bool = True
    current_leads_count: int = 0
    max_leads: int = 10

    @property
    def can_accept_leads(self) -> bool:
        """Check if broker can accept more leads."""
        return self.is_available and self.current_leads_count < self.max_leads

    def matches_property_type(self, property_type: str) -> bool:
        """Check if broker handles this property type."""
        return property_type in self.specialization

    def matches_region(self, region: str) -> bool:
        """Check if broker covers this region."""
        return any(r.lower() in region.lower() for r in self.regions)


# Default brokers for the prototype
DEFAULT_BROKERS = [
    Broker(
        id=1,
        name="Jan Procházka",
        email="jan.prochazka@realitka.cz",
        phone="+420 777 111 222",
        specialization=["warehouse", "office"],
        regions=["Praha", "Kladno"],
    ),
    Broker(
        id=2,
        name="Petra Nováková",
        email="petra.novakova@realitka.cz",
        phone="+420 777 333 444",
        specialization=["office"],
        regions=["Praha", "Brno"],
    ),
    Broker(
        id=3,
        name="Martin Svoboda",
        email="martin.svoboda@realitka.cz",
        phone="+420 777 555 666",
        specialization=["warehouse"],
        regions=["Brno", "Ostrava", "Olomouc"],
    ),
]
