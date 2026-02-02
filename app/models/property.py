from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, computed_field


class PropertyImage(BaseModel):
    """Property image model."""
    url: str
    alt: str = ""
    is_primary: bool = False
    order: int = 0
    width: Optional[int] = None
    height: Optional[int] = None


class Property(BaseModel):
    """Commercial real estate property model."""

    # Core fields (from source data)
    id: int
    property_type: Literal["warehouse", "office"]
    location: str
    region: Optional[str] = None  # e.g., "Morava", "Čechy", "Slezsko" (optional)
    country: str = "CZ"  # Country code
    area_sqm: int
    price_czk_sqm: int
    availability: str  # "ihned" or ISO date
    parking_spaces: int = 0
    amenities: list[str] = Field(default_factory=list)

    # Image fields
    images: list[PropertyImage] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    virtual_tour_url: Optional[str] = None

    # Business priority fields
    is_featured: bool = False
    is_hot: bool = False
    priority_score: int = 0  # 0-100
    commission_rate: float = 0.0

    # Extended fields
    description: Optional[str] = None
    floor: Optional[int] = None
    building_class: Optional[Literal["A", "B", "C"]] = None
    energy_rating: Optional[str] = None
    last_updated: Optional[datetime] = None

    # Transport/logistics access (mainly for warehouses)
    highway_access: Optional[str] = None  # e.g., "D1 (2 km)", "D5 (5 km)"
    transport_notes: Optional[str] = None  # e.g., "Logistická zóna, 24/7 přístup"

    @computed_field
    @property
    def total_monthly_rent(self) -> int:
        """Calculate total monthly rent."""
        return self.area_sqm * self.price_czk_sqm

    @computed_field
    @property
    def value_score(self) -> int:
        """
        Compute dynamic value score (0-100) based on price vs. market average.
        Higher score = better value for money.
        """
        # Average prices by type (could be computed from data)
        avg_prices = {
            "warehouse": 90,  # Average warehouse price/m²
            "office": 280,    # Average office price/m²
        }

        avg_price = avg_prices.get(self.property_type, 100)

        # Calculate how much below average this property is
        # If price is 50% of average, that's great value
        price_ratio = self.price_czk_sqm / avg_price

        if price_ratio <= 0.7:
            # 30% or more below average = excellent value
            base_score = 90
        elif price_ratio <= 0.85:
            # 15-30% below average = good value
            base_score = 75
        elif price_ratio <= 1.0:
            # At or below average = fair value
            base_score = 60
        elif price_ratio <= 1.2:
            # Up to 20% above average = premium
            base_score = 45
        else:
            # More than 20% above average = luxury
            base_score = 30

        # Bonus for immediate availability
        if self.is_available_now:
            base_score += 5

        # Bonus for highway access (warehouses)
        if self.highway_access and self.property_type == "warehouse":
            base_score += 5

        # Bonus for size (larger = more value for logistics)
        if self.property_type == "warehouse" and self.area_sqm >= 1000:
            base_score += 5

        return min(100, base_score)

    @computed_field
    @property
    def is_best_value(self) -> bool:
        """Property offers exceptional value (top value_score)."""
        return self.value_score >= 80

    @computed_field
    @property
    def is_trending(self) -> bool:
        """Check if property is trending (high demand) based on view analytics."""
        try:
            from app.analytics import get_property_tracker
            tracker = get_property_tracker()
            return tracker.is_hot(self.id)
        except Exception:
            return False

    @computed_field
    @property
    def value_badge(self) -> str:
        """Get appropriate badge based on value, popularity and status."""
        badges = []
        # Dynamic HOT based on popularity (trending)
        if self.is_trending:
            badges.append("🔥 TRENDY")
        # Manual HOT for special offers
        elif self.is_hot:
            badges.append("🔥 AKCE")
        # Value-based badge
        if self.is_best_value:
            badges.append("💰 NEJLEPŠÍ CENA")
        # Manual featured
        if self.is_featured:
            badges.append("⭐ DOPORUČENO")
        return " ".join(badges)

    @computed_field
    @property
    def is_available_now(self) -> bool:
        """Check if available immediately."""
        return self.availability.lower() == "ihned"

    @computed_field
    @property
    def availability_date(self) -> date | None:
        """Parse availability date."""
        if self.is_available_now:
            return None
        try:
            return datetime.strptime(self.availability, "%Y-%m-%d").date()
        except ValueError:
            return None

    @computed_field
    @property
    def property_type_cz(self) -> str:
        """Czech name for property type."""
        return "sklad" if self.property_type == "warehouse" else "kancelář"

    @computed_field
    @property
    def location_normalized(self) -> str:
        """Normalized lowercase location for matching."""
        return self.location.lower().split()[0].split("-")[0]

    @computed_field
    @property
    def location_region(self) -> str:
        """Get property region. Falls back to country if region not set."""
        if self.region:
            return self.region
        # Fallback to country name
        country_names = {"CZ": "Česko", "SK": "Slovensko"}
        return country_names.get(self.country, self.country)

    @computed_field
    @property
    def amenities_cz(self) -> str:
        """Amenities as Czech readable string."""
        amenity_map = {
            "rampa": "nakládací rampa",
            "vytapeni": "vytápění",
            "vyska_6m": "výška 6m",
            "vysoke_stropy_10m": "vysoké stropy 10m",
            "vysoke_stropy_9m": "vysoké stropy 9m",
            "prizemni": "přízemní",
            "kancelare_v_cene_50m2": "kanceláře v ceně (50m²)",
            "klimatizovany": "klimatizovaný",
            "moderni": "moderní",
            "klimatizace": "klimatizace",
            "meeting_room": "zasedací místnost",
            "open_space": "open space",
            "bez_parkovani": "bez parkování",
            "reprezentativni": "reprezentativní",
            "recepce": "recepce",
            "moderni_budova": "moderní budova",
            "terasa": "terasa",
            "zakladni_standard": "základní standard",
            "po_rekonstrukci": "po rekonstrukci",
            "standard": "standard",
            "bez_rampy": "bez rampy",
        }
        return ", ".join(amenity_map.get(a, a) for a in self.amenities)

    @computed_field
    @property
    def primary_image_url(self) -> Optional[str]:
        """Get the primary image URL."""
        if self.thumbnail_url:
            return self.thumbnail_url

        primary = next((img for img in self.images if img.is_primary), None)
        if primary:
            return primary.url

        if self.images:
            return self.images[0].url

        return None

    @computed_field
    @property
    def image_count(self) -> int:
        """Get the number of images."""
        return len(self.images)

    @computed_field
    @property
    def has_images(self) -> bool:
        """Check if property has images."""
        return len(self.images) > 0 or self.thumbnail_url is not None

    @computed_field
    @property
    def has_virtual_tour(self) -> bool:
        """Check if property has a virtual tour."""
        return self.virtual_tour_url is not None

    def to_embedding_text(self) -> str:
        """Generate text for vector embedding."""
        availability_text = "ihned k dispozici" if self.is_available_now else f"od {self.availability}"
        parking_text = f"{self.parking_spaces} parkovacích míst" if self.parking_spaces > 0 else "bez parkování"

        return f"""Typ: {self.property_type_cz}
Lokalita: {self.location}
Region: {self.location_region}
Plocha: {self.area_sqm} m²
Cena: {self.price_czk_sqm} Kč/m²/měsíc
Celkový nájem: {self.total_monthly_rent:,} Kč/měsíc
Dostupnost: {availability_text}
Parkování: {parking_text}
Vybavení: {self.amenities_cz if self.amenities else 'základní'}"""

    def to_display_text(self, include_images: bool = True) -> str:
        """Generate formatted text for chat display with image."""
        import urllib.parse

        availability_text = "ihned" if self.is_available_now else f"od {self.availability}"
        badges = f" {self.value_badge}" if self.value_badge else ""
        tour_badge = " 🎥" if self.has_virtual_tour else ""

        # Google Maps link
        maps_query = urllib.parse.quote(f"{self.location}, Česká republika")
        maps_link = f"[📍 Mapa](https://www.google.com/maps/search/{maps_query})"

        # Start with image if available
        image_md = ""
        if include_images and self.primary_image_url:
            image_md = f"![{self.property_type_cz} {self.location}]({self.primary_image_url})\n\n"

        text = f"""{image_md}**{self.property_type_cz.upper()} - {self.location}** {maps_link}{badges}{tour_badge}
- 📐 Plocha: {self.area_sqm} m²
- 💰 Cena: {self.price_czk_sqm} Kč/m²/měsíc ({self.total_monthly_rent:,} Kč celkem)
- 📅 Dostupnost: {availability_text}
- 🚗 Parkování: {self.parking_spaces} míst
- ✅ Vybavení: {self.amenities_cz if self.amenities else 'základní'}"""

        # Add transport info for warehouses
        if self.highway_access:
            text += f"\n- 🛣️ Dálnice: {self.highway_access}"
        if self.transport_notes:
            text += f"\n- 🚛 {self.transport_notes}"

        if self.description:
            text += f"\n- 📝 {self.description[:200]}..."

        return text

    def to_card_dict(self) -> dict:
        """Convert to dictionary suitable for UI card display."""
        return {
            "id": self.id,
            "title": f"{self.property_type_cz.upper()} - {self.location}",
            "type": self.property_type,
            "location": self.location,
            "region": self.location_region,
            "area_sqm": self.area_sqm,
            "price_czk_sqm": self.price_czk_sqm,
            "total_rent": self.total_monthly_rent,
            "availability": self.availability,
            "is_available_now": self.is_available_now,
            "parking_spaces": self.parking_spaces,
            "amenities": self.amenities,
            "amenities_display": self.amenities_cz,
            "is_featured": self.is_featured,
            "is_hot": self.is_hot,
            "image_url": self.primary_image_url,
            "image_count": self.image_count,
            "has_virtual_tour": self.has_virtual_tour,
            "virtual_tour_url": self.virtual_tour_url,
        }
