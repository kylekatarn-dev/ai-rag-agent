from datetime import date
from typing import Optional

from app.data.loader import load_properties, get_property_by_id
from app.models.property import Property
from .vectorstore import PropertyVectorStore
from .hybrid_search import HybridSearch
from .query_expansion import QueryExpander
from .reranker import LLMReranker


class PropertyRetriever:
    """
    High-level property retrieval with business logic.

    Features:
    - Hybrid search (vector + BM25)
    - Query expansion
    - Multi-query retrieval
    - LLM-based re-ranking
    """

    def __init__(self, use_reranking: bool = True):
        self.vectorstore = PropertyVectorStore()
        self.hybrid_search = HybridSearch()
        self.query_expander = QueryExpander()
        self.reranker = LLMReranker() if use_reranking else None
        self.use_reranking = use_reranking
        self._ensure_indexed()

    def _ensure_indexed(self):
        """Ensure properties are indexed."""
        if not self.vectorstore.is_indexed():
            self.vectorstore.index_properties()

    def search_properties(
        self,
        query: str = "",
        property_type: str | None = None,
        locations: list[str] | None = None,
        min_area: int | None = None,
        max_area: int | None = None,
        max_price: int | None = None,
        available_by: date | None = None,
        top_k: int = 5,
        use_hybrid: bool = True,
        use_expansion: bool = True,
        use_reranking: bool = None,
    ) -> list[Property]:
        """
        Search for properties based on criteria using enhanced RAG.

        Features:
        - Hybrid search (vector + BM25 keyword matching)
        - Query expansion (synonyms, related locations)
        - Multi-query retrieval
        - Optional LLM re-ranking

        Returns Property objects sorted by relevance and business priority.
        """
        # Use instance setting if not specified
        if use_reranking is None:
            use_reranking = self.use_reranking and self.reranker is not None

        # Expand query if enabled
        expanded = None
        if use_expansion and query:
            expanded = self.query_expander.expand_query(query)
            # Use inferred filters if not explicitly provided
            inferred = expanded.get("inferred_filters", {})
            if not property_type and "property_type" in inferred:
                property_type = inferred["property_type"]
            if not min_area and "min_area" in inferred:
                min_area = inferred["min_area"]
            if not max_area and "max_area" in inferred:
                max_area = inferred["max_area"]
            if not max_price and "max_price" in inferred:
                max_price = inferred["max_price"]
            if not locations and "locations" in inferred:
                locations = inferred["locations"]

        # Get region from query expansion (e.g., "morava" -> "Morava")
        location_region = None
        if expanded and expanded.get("region"):
            location_region = expanded["region"]

        # Build search query if not provided
        if not query:
            parts = []
            if property_type:
                parts.append("sklad" if property_type == "warehouse" else "kancelář")
            if locations:
                parts.append(" ".join(locations))
            if min_area or max_area:
                area_str = f"{min_area or '?'}-{max_area or '?'} m²"
                parts.append(area_str)
            query = " ".join(parts) if parts else "komerční nemovitost"

        # Check if we need immediate availability
        available_now = None
        if available_by:
            from datetime import datetime
            days_until = (available_by - datetime.now().date()).days
            if days_until <= 14:
                available_now = True

        # Multi-query retrieval: search with multiple query variants
        all_vector_results = []
        search_queries = [query]

        if use_expansion and expanded:
            search_queries = expanded.get("queries", [query])[:3]

        # Search with each query variant
        for search_query in search_queries:
            results = self.vectorstore.search(
                query=search_query,
                property_type=property_type,
                location_region=location_region,
                min_area=min_area,
                max_area=max_area,
                max_price=max_price,
                available_now=available_now,
                top_k=top_k * 2,
            )
            all_vector_results.extend(results)

        # Deduplicate by ID, keeping highest similarity
        seen_ids = {}
        for result in all_vector_results:
            pid = result["id"]
            if pid not in seen_ids or result.get("similarity", 0) > seen_ids[pid].get("similarity", 0):
                seen_ids[pid] = result

        vector_results = list(seen_ids.values())

        # Apply hybrid search if enabled
        if use_hybrid and vector_results:
            vector_results = self.hybrid_search.search_hybrid(
                query=query,
                vector_results=vector_results,
                bm25_weight=0.3,
                vector_weight=0.7,
                top_k=top_k * 2,
            )

        # Get full property objects
        properties = []
        for result in vector_results:
            prop = get_property_by_id(result["id"])
            if prop:
                # Additional filtering for availability date
                if available_by and prop.availability_date:
                    if prop.availability_date > available_by:
                        continue

                properties.append(prop)

        # Apply LLM re-ranking if enabled and we have enough results
        if use_reranking and self.reranker and len(properties) > 1:
            user_requirements = {
                "property_type": property_type,
                "min_area": min_area,
                "max_price": max_price,
                "locations": locations,
            }
            reranked = self.reranker.rerank(
                query=query,
                properties=properties[:top_k * 2],
                top_k=top_k,
                user_requirements=user_requirements,
            )
            properties = [p for p, score, reason in reranked]

        return properties[:top_k]

    def get_recommendations(
        self,
        property_type: str | None = None,
        locations: list[str] | None = None,
        min_area: int | None = None,
        max_area: int | None = None,
        max_price: int | None = None,
        available_by: date | None = None,
    ) -> dict:
        """
        Get property recommendations with context.

        Returns dict with matches, alternatives, and market info.
        """
        # Search for exact matches
        exact_matches = self.search_properties(
            property_type=property_type,
            locations=locations,
            min_area=min_area,
            max_area=max_area,
            max_price=max_price,
            available_by=available_by,
            top_k=5,
        )

        # If no exact matches, try relaxed search
        alternatives = []
        relaxed_criteria = []

        if not exact_matches:
            # Try without price filter
            if max_price:
                alternatives = self.search_properties(
                    property_type=property_type,
                    locations=locations,
                    min_area=min_area,
                    max_area=max_area,
                    max_price=None,  # Relaxed
                    available_by=available_by,
                    top_k=3,
                )
                if alternatives:
                    relaxed_criteria.append("rozpočet")

            # Try without location filter
            if not alternatives and locations:
                alternatives = self.search_properties(
                    property_type=property_type,
                    locations=None,  # Relaxed
                    min_area=min_area,
                    max_area=max_area,
                    max_price=max_price,
                    available_by=available_by,
                    top_k=3,
                )
                if alternatives:
                    relaxed_criteria.append("lokalita")

            # Try with smaller area
            if not alternatives and min_area and min_area > 100:
                alternatives = self.search_properties(
                    property_type=property_type,
                    locations=locations,
                    min_area=min_area // 2,  # Relaxed
                    max_area=max_area,
                    max_price=max_price,
                    available_by=available_by,
                    top_k=3,
                )
                if alternatives:
                    relaxed_criteria.append("plocha")

        # Get market stats for context
        from app.data.loader import get_market_stats
        market_stats = get_market_stats()

        return {
            "exact_matches": exact_matches,
            "alternatives": alternatives,
            "relaxed_criteria": relaxed_criteria,
            "market_stats": market_stats,
            "total_available": len(load_properties()),
        }

    def find_best_match(
        self,
        property_type: str | None = None,
        locations: list[str] | None = None,
        min_area: int | None = None,
        max_price: int | None = None,
    ) -> Property | None:
        """Find the single best matching property."""
        matches = self.search_properties(
            property_type=property_type,
            locations=locations,
            min_area=min_area,
            max_price=max_price,
            top_k=1,
        )
        return matches[0] if matches else None

    def reindex(self) -> int:
        """Force reindex all properties."""
        return self.vectorstore.index_properties()
