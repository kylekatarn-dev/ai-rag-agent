"""
Property Data Loader.

Loads properties from SQLite database.
Run scripts/init_database.py to initialize the database with properties.
"""

from typing import Optional

from app.models.property import Property
from app.utils import get_logger

logger = get_logger(__name__)

# In-memory cache for fast access
_properties_cache: list[Property] | None = None
_properties_by_id: dict[int, Property] = {}


def _get_repository():
    """Get property repository (lazy import to avoid circular deps)."""
    from app.persistence import get_property_repository
    return get_property_repository()


def _ensure_database_populated() -> bool:
    """
    Ensure database has properties.

    Returns:
        True if database is populated
    """
    repo = _get_repository()

    # Check if database has properties
    if repo.get_count() > 0:
        return True

    logger.warning(
        "Database is empty! Run 'python scripts/init_database.py' to initialize."
    )
    return False


def load_properties(force_reload: bool = False) -> list[Property]:
    """
    Load properties from database.

    Args:
        force_reload: Force reload from database (bypass cache)

    Returns:
        List of Property models
    """
    global _properties_cache, _properties_by_id

    if _properties_cache is not None and not force_reload:
        return _properties_cache

    # Ensure database has data
    _ensure_database_populated()

    # Load from database
    repo = _get_repository()
    _properties_cache = repo.get_all(use_cache=not force_reload)

    # Build ID lookup
    _properties_by_id = {p.id: p for p in _properties_cache}

    logger.debug(f"Loaded {len(_properties_cache)} properties from database")
    return _properties_cache


def get_property_by_id(property_id: int) -> Property | None:
    """
    Get a property by its ID.

    Args:
        property_id: Property ID to look up

    Returns:
        Property if found, None otherwise
    """
    # Check cache first
    if property_id in _properties_by_id:
        return _properties_by_id[property_id]

    # Load if cache is empty
    if not _properties_cache:
        load_properties()
        return _properties_by_id.get(property_id)

    # Try database directly
    repo = _get_repository()
    prop = repo.get_by_id(property_id)

    if prop:
        _properties_by_id[property_id] = prop

    return prop


def get_properties_by_type(property_type: str) -> list[Property]:
    """Get all properties of a specific type."""
    properties = load_properties()
    return [p for p in properties if p.property_type == property_type]


def get_properties_by_region(region: str) -> list[Property]:
    """Get all properties in a specific region."""
    properties = load_properties()
    region_lower = region.lower()
    return [p for p in properties if region_lower in p.location_region.lower()]


def get_available_now() -> list[Property]:
    """Get all immediately available properties."""
    properties = load_properties()
    return [p for p in properties if p.is_available_now]


def get_featured_properties() -> list[Property]:
    """Get all featured properties."""
    properties = load_properties()
    return sorted(
        [p for p in properties if p.is_featured],
        key=lambda p: p.priority_score,
        reverse=True
    )


def get_hot_properties() -> list[Property]:
    """Get all hot/urgent properties."""
    properties = load_properties()
    return sorted(
        [p for p in properties if p.is_hot],
        key=lambda p: p.priority_score,
        reverse=True
    )


def get_market_stats() -> dict:
    """Get market statistics for reference."""
    repo = _get_repository()
    return repo.get_market_stats()


def get_properties_by_region_name(region: str) -> list[Property]:
    """Get all properties in a specific region by exact name."""
    properties = load_properties()
    return [p for p in properties if p.region == region]


def create_property(prop: Property) -> int:
    """
    Create a new property in the database.

    Args:
        prop: Property to create

    Returns:
        Property ID
    """
    global _properties_cache, _properties_by_id

    repo = _get_repository()
    prop_id = repo.create(prop)

    # Invalidate cache
    _properties_cache = None
    _properties_by_id = {}

    return prop_id


def update_property(prop: Property) -> bool:
    """
    Update a property in the database.

    Args:
        prop: Property with updated data

    Returns:
        True if updated
    """
    global _properties_cache, _properties_by_id

    repo = _get_repository()
    success = repo.update(prop)

    if success:
        # Invalidate cache
        _properties_cache = None
        _properties_by_id = {}

    return success


def delete_property(property_id: int) -> bool:
    """
    Delete a property from the database.

    Args:
        property_id: ID of property to delete

    Returns:
        True if deleted
    """
    global _properties_cache, _properties_by_id

    repo = _get_repository()
    success = repo.delete(property_id)

    if success:
        # Invalidate cache
        _properties_cache = None
        _properties_by_id.pop(property_id, None)

    return success
