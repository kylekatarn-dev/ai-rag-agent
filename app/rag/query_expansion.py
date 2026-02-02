"""Query expansion for better search coverage."""

from typing import Optional
import re


# Location synonyms (simple spelling variants only, no region-to-city expansion)
LOCATION_EXPANSIONS = {
    # Prague variants
    "praha": ["praha", "prague"],
    "prague": ["praha", "prague"],
    # Brno variants
    "brno": ["brno"],
    # Ostrava variants
    "ostrava": ["ostrava"],
    # Plzeň variants
    "plzeň": ["plzeň", "plzen", "pilsen"],
    "plzen": ["plzeň", "plzen"],
    # Other cities
    "olomouc": ["olomouc"],
    "liberec": ["liberec"],
    "hradec králové": ["hradec králové", "hradec kralove"],
    "kladno": ["kladno"],
}

# Region name aliases (for query detection - actual filtering uses database region field)
REGION_TERMS = ["morava", "moravě", "moravia", "čechy", "čechách", "bohemia", "slezsko", "slovensko"]

# Property type synonyms
PROPERTY_TYPE_EXPANSIONS = {
    "sklad": ["sklad", "skladové prostory", "skladový prostor", "warehouse", "logistický areál", "hala"],
    "warehouse": ["warehouse", "sklad", "skladové prostory"],
    "kancelář": ["kancelář", "kancelářské prostory", "kancelářský prostor", "office", "administrativní budova"],
    "office": ["office", "kancelář", "kancelářské prostory"],
}

# Size-related terms
SIZE_KEYWORDS = {
    "malý": {"max_area": 200},
    "střední": {"min_area": 200, "max_area": 500},
    "velký": {"min_area": 500, "max_area": 2000},
    "velmi velký": {"min_area": 2000},
    "obrovský": {"min_area": 5000},
    "logistický": {"min_area": 2000},  # Logistics usually needs larger space
}

# Price-related terms
PRICE_KEYWORDS = {
    "levný": {"max_price": 80},
    "cenově dostupný": {"max_price": 100},
    "prémiový": {"min_price": 150},
    "luxusní": {"min_price": 200},
}


class QueryExpander:
    """
    Expands user queries to improve search coverage.

    Handles:
    - Location synonyms and related areas
    - Property type synonyms
    - Size and price inference from descriptive terms
    """

    def expand_query(self, query: str) -> dict:
        """
        Expand a query into multiple search variants.

        Args:
            query: Original search query

        Returns:
            Dict with:
            - queries: List of expanded query strings
            - inferred_filters: Dict of inferred filter values
            - locations: List of expanded locations
            - region: Detected region name (e.g., "Morava", "Čechy")
        """
        query_lower = query.lower()

        result = {
            "queries": [query],  # Always include original
            "inferred_filters": {},
            "locations": [],
            "property_types": [],
            "region": None,  # Detected region for database filtering
        }

        # Detect region terms and set region filter (don't expand to cities)
        from app.utils.regions import normalize_region
        detected_region = normalize_region(query_lower)
        if detected_region:
            result["region"] = detected_region
            result["inferred_filters"]["region"] = detected_region

        # Expand locations (only simple spelling variants)
        for location, expansions in LOCATION_EXPANSIONS.items():
            if location in query_lower:
                result["locations"].extend(expansions)
                # Add queries with location variants
                for exp in expansions:
                    if exp != location:
                        result["queries"].append(query_lower.replace(location, exp))

        # Expand property types
        for ptype, expansions in PROPERTY_TYPE_EXPANSIONS.items():
            if ptype in query_lower:
                result["property_types"].extend(expansions)
                # Add queries with type variants
                for exp in expansions[:2]:  # Limit to avoid too many
                    if exp != ptype:
                        result["queries"].append(query_lower.replace(ptype, exp))

        # Infer size from keywords
        for keyword, filters in SIZE_KEYWORDS.items():
            if keyword in query_lower:
                result["inferred_filters"].update(filters)
                break  # Only use first match

        # Infer price from keywords
        for keyword, filters in PRICE_KEYWORDS.items():
            if keyword in query_lower:
                result["inferred_filters"].update(filters)
                break

        # Extract explicit numbers for area
        area_match = re.search(r'(\d+)\s*m[²2]?', query_lower)
        if area_match:
            area = int(area_match.group(1))
            # Assume it's a minimum if large number
            if area >= 100:
                result["inferred_filters"]["min_area"] = area

        # Extract explicit price
        price_match = re.search(r'(\d+)\s*(?:kč|czk|korun)', query_lower)
        if price_match:
            price = int(price_match.group(1))
            result["inferred_filters"]["max_price"] = price

        # Deduplicate
        result["queries"] = list(dict.fromkeys(result["queries"]))
        result["locations"] = list(dict.fromkeys(result["locations"]))
        result["property_types"] = list(dict.fromkeys(result["property_types"]))

        return result

    def generate_search_queries(self, query: str, count: int = 3) -> list[str]:
        """
        Generate multiple search query variants.

        Args:
            query: Original query
            count: Number of variants to generate

        Returns:
            List of query variants
        """
        expansion = self.expand_query(query)
        queries = expansion["queries"][:count]

        # Ensure we have enough queries
        if len(queries) < count:
            # Add simplified versions
            words = query.lower().split()
            if len(words) > 2:
                # Try without first word
                queries.append(" ".join(words[1:]))
            if len(words) > 3:
                # Try key terms only
                key_terms = [w for w in words if len(w) > 3]
                if key_terms:
                    queries.append(" ".join(key_terms[:3]))

        return queries[:count]

    def extract_filters_from_query(self, query: str) -> dict:
        """
        Extract structured filters from natural language query.

        Args:
            query: Natural language query

        Returns:
            Dict of filter parameters
        """
        expansion = self.expand_query(query)
        filters = expansion["inferred_filters"].copy()

        # Add property type if detected
        if expansion["property_types"]:
            ptype = expansion["property_types"][0]
            if ptype in ["sklad", "warehouse", "skladové prostory", "hala", "logistický areál"]:
                filters["property_type"] = "warehouse"
            elif ptype in ["kancelář", "office", "kancelářské prostory"]:
                filters["property_type"] = "office"

        # Add locations if detected
        if expansion["locations"]:
            filters["locations"] = expansion["locations"]

        return filters
