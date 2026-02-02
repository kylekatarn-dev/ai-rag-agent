"""
Location region detection utilities.

Simple region mapping - regions are stored directly on properties.
"""

from typing import Optional


# Known regions (for validation/normalization)
KNOWN_REGIONS = ["Čechy", "Morava", "Slezsko", "Slovensko"]

# Region aliases (user input → canonical name)
REGION_ALIASES = {
    # Morava
    "morava": "Morava",
    "moravě": "Morava",
    "moravia": "Morava",
    "jižní morava": "Morava",
    "severní morava": "Morava",
    # Čechy
    "čechy": "Čechy",
    "čechách": "Čechy",
    "cechy": "Čechy",
    "bohemia": "Čechy",
    # Slezsko
    "slezsko": "Slezsko",
    "silesia": "Slezsko",
    # Slovensko
    "slovensko": "Slovensko",
    "slovakia": "Slovensko",
}

# Country aliases
COUNTRY_ALIASES = {
    "česko": "CZ",
    "česká republika": "CZ",
    "czech": "CZ",
    "czechia": "CZ",
    "slovensko": "SK",
    "slovakia": "SK",
}


def normalize_region(text: str) -> Optional[str]:
    """
    Normalize region name from user input.

    Args:
        text: User input (e.g., "moravě", "v čechách")

    Returns:
        Canonical region name or None if not recognized
    """
    if not text:
        return None

    text_lower = text.lower().strip()

    # Direct match
    if text_lower in REGION_ALIASES:
        return REGION_ALIASES[text_lower]

    # Check if text contains a region keyword
    for alias, region in REGION_ALIASES.items():
        if alias in text_lower:
            return region

    return None


def normalize_country(text: str) -> Optional[str]:
    """
    Normalize country name from user input.

    Args:
        text: User input (e.g., "česko", "slovensko")

    Returns:
        Country code or None if not recognized
    """
    if not text:
        return None

    text_lower = text.lower().strip()

    for alias, code in COUNTRY_ALIASES.items():
        if alias in text_lower:
            return code

    return None


def extract_region_from_text(text: str) -> Optional[str]:
    """
    Try to extract region from user text.

    Args:
        text: User message

    Returns:
        Region name if found, None otherwise
    """
    return normalize_region(text)


def extract_country_from_text(text: str) -> Optional[str]:
    """
    Try to extract country from user text.

    Args:
        text: User message

    Returns:
        Country code if found, None otherwise
    """
    return normalize_country(text)


def normalize_location_list(locations: list[str]) -> Optional[str]:
    """
    Normalize a list of locations to find the primary region.

    Args:
        locations: List of location strings (e.g., ["Praha", "Brno"])

    Returns:
        Region name if found, None otherwise
    """
    if not locations:
        return None

    for location in locations:
        region = normalize_region(location)
        if region:
            return region

    return None
