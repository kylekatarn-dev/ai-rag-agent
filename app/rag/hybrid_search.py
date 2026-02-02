"""Hybrid search combining vector similarity with BM25 keyword matching."""

from typing import Optional

# Try to import BM25, fall back gracefully if not installed
try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    BM25Okapi = None

from app.models.property import Property
from app.data.loader import load_properties


class HybridSearch:
    """
    Combines vector similarity search with BM25 keyword matching
    for more robust property retrieval.
    """

    def __init__(self):
        self.properties: list[Property] = []
        self.bm25 = None
        self.corpus: list[list[str]] = []
        self.available = BM25_AVAILABLE
        self._initialize()

    def _initialize(self):
        """Load properties and build BM25 index."""
        self.properties = load_properties()
        if self.available:
            self._build_bm25_index()

    def _build_bm25_index(self):
        """Build BM25 index from property texts."""
        if not BM25_AVAILABLE:
            return

        self.corpus = []

        for prop in self.properties:
            # Create searchable text
            text = self._property_to_search_text(prop)
            # Tokenize (simple whitespace tokenization + lowercase)
            tokens = self._tokenize(text)
            self.corpus.append(tokens)

        if self.corpus and BM25Okapi:
            self.bm25 = BM25Okapi(self.corpus)

    def _property_to_search_text(self, prop: Property) -> str:
        """Convert property to searchable text."""
        parts = [
            prop.property_type,
            "sklad" if prop.property_type == "warehouse" else "kancelář",
            prop.location,
            prop.location_region,
            prop.description or "",
            f"{prop.area_sqm} m² metrů čtverečních",
            f"{prop.price_czk_sqm} korun kč cena",
        ]

        # Add amenities
        if prop.amenities:
            parts.extend(prop.amenities)

        # Add availability
        if prop.is_available_now:
            parts.append("ihned dostupné volné")

        return " ".join(filter(None, parts)).lower()

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization with Czech-aware processing."""
        # Remove punctuation and split
        import re
        text = re.sub(r'[^\w\sáčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]', ' ', text.lower())
        tokens = text.split()
        # Filter very short tokens
        return [t for t in tokens if len(t) > 1]

    def search_bm25(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[Property, float]]:
        """
        Search using BM25 keyword matching.

        Returns list of (Property, score) tuples.
        """
        if not self.available or not self.bm25 or not query:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        try:
            scores = self.bm25.get_scores(query_tokens)

            # Get top results
            scored_props = list(zip(self.properties, scores))
            scored_props.sort(key=lambda x: x[1], reverse=True)

            # Filter zero scores
            results = [(p, s) for p, s in scored_props[:top_k] if s > 0]

            return results
        except Exception:
            return []

    def search_hybrid(
        self,
        query: str,
        vector_results: list[dict],
        bm25_weight: float = 0.3,
        vector_weight: float = 0.7,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Combine BM25 and vector search results using reciprocal rank fusion.

        Args:
            query: Search query
            vector_results: Results from vector search (list of dicts with 'id', 'similarity')
            bm25_weight: Weight for BM25 scores (default 0.3)
            vector_weight: Weight for vector scores (default 0.7)
            top_k: Number of results to return

        Returns:
            Combined and re-ranked results
        """
        # Get BM25 results
        bm25_results = self.search_bm25(query, top_k=top_k * 2)

        # Build score maps
        # Vector scores (already normalized as similarity 0-1)
        vector_scores = {r['id']: r.get('similarity', 0.5) for r in vector_results}

        # BM25 scores (normalize to 0-1)
        max_bm25 = max((s for _, s in bm25_results), default=1) or 1
        bm25_scores = {p.id: s / max_bm25 for p, s in bm25_results}

        # Combine scores using weighted sum
        all_ids = set(vector_scores.keys()) | set(bm25_scores.keys())
        combined_scores = {}

        for prop_id in all_ids:
            v_score = vector_scores.get(prop_id, 0)
            b_score = bm25_scores.get(prop_id, 0)
            combined_scores[prop_id] = (v_score * vector_weight) + (b_score * bm25_weight)

        # Sort by combined score
        sorted_ids = sorted(combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True)

        # Rebuild results with combined scores
        results = []
        for prop_id in sorted_ids[:top_k]:
            # Find original result or create new one
            original = next((r for r in vector_results if r['id'] == prop_id), None)

            if original:
                result = original.copy()
            else:
                # Find property by id
                prop = next((p for p in self.properties if p.id == prop_id), None)
                if prop:
                    result = {
                        'id': prop_id,
                        'metadata': {
                            'id': prop_id,
                            'property_type': prop.property_type,
                            'location': prop.location,
                            'area_sqm': prop.area_sqm,
                            'price_czk_sqm': prop.price_czk_sqm,
                        }
                    }
                else:
                    continue

            result['combined_score'] = combined_scores[prop_id]
            result['vector_score'] = vector_scores.get(prop_id, 0)
            result['bm25_score'] = bm25_scores.get(prop_id, 0)
            results.append(result)

        return results

    def reindex(self):
        """Rebuild the BM25 index."""
        self.properties = load_properties()
        self._build_bm25_index()
