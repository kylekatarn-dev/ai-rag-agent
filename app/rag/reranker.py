"""
Hybrid Reranking Module.

Combines fast local scoring with optional LLM reranking for best results.
"""

import json
from typing import Optional

from openai import OpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.models.property import Property
from app.utils import get_logger

logger = get_logger(__name__)


class LocalScorer:
    """
    Fast local scoring based on criteria matching.

    No LLM calls - instant results for initial filtering.
    """

    def score(
        self,
        prop: Property,
        user_requirements: Optional[dict] = None,
    ) -> tuple[float, list[str]]:
        """
        Score a property against user requirements.

        Args:
            prop: Property to score
            user_requirements: Dict with property_type, min_area, max_price, locations

        Returns:
            Tuple of (score 0-100, list of match reasons)
        """
        if not user_requirements:
            # Default scoring based on property attributes
            score = 50
            if prop.is_hot:
                score += 20
            if prop.is_featured:
                score += 15
            if prop.is_available_now:
                score += 10
            score += min(prop.priority_score / 10, 5)
            return score, ["Doporucena nabidka"]

        score = 0
        reasons = []

        # Type match (25 points)
        req_type = user_requirements.get("property_type")
        if req_type:
            if prop.property_type == req_type:
                score += 25
                reasons.append("Spravny typ nemovitosti")
            else:
                score -= 10  # Penalty for wrong type

        # Location match (25 points)
        locations = user_requirements.get("locations", [])
        if locations:
            prop_location_lower = prop.location.lower()
            prop_region_lower = prop.location_region.lower()

            for loc in locations:
                loc_lower = loc.lower()
                if loc_lower in prop_location_lower or loc_lower in prop_region_lower:
                    score += 25
                    reasons.append(f"Lokalita: {prop.location}")
                    break
            else:
                # Check for region match
                for loc in locations:
                    if loc.lower() in prop_region_lower:
                        score += 15  # Partial match for region
                        reasons.append(f"Region: {prop.location_region}")
                        break

        # Area match (20 points)
        min_area = user_requirements.get("min_area")
        max_area = user_requirements.get("max_area")

        if min_area or max_area:
            area_match = True
            if min_area and prop.area_sqm < min_area:
                # Penalty proportional to how much smaller
                ratio = prop.area_sqm / min_area
                if ratio >= 0.8:
                    score += 10  # Close enough
                    reasons.append(f"Plocha blizko pozadavku ({prop.area_sqm}m²)")
                else:
                    score -= 5
                    area_match = False
            elif max_area and prop.area_sqm > max_area:
                ratio = max_area / prop.area_sqm
                if ratio >= 0.7:
                    score += 10
                    reasons.append(f"Plocha mirne vetsi ({prop.area_sqm}m²)")
                else:
                    score -= 5
                    area_match = False
            else:
                score += 20
                reasons.append(f"Plocha vyhovuje ({prop.area_sqm}m²)")

        # Price match (20 points)
        max_price = user_requirements.get("max_price")
        if max_price:
            if prop.price_czk_sqm <= max_price:
                score += 20
                reasons.append(f"Cena v rozpočtu ({prop.price_czk_sqm} Kč/m²)")
            elif prop.price_czk_sqm <= max_price * 1.2:
                score += 10  # Within 20% over budget
                reasons.append(f"Cena mírně nad rozpočet ({prop.price_czk_sqm} Kč/m²)")
            else:
                score -= 10
                reasons.append(f"Nad rozpočet ({prop.price_czk_sqm} Kč/m²)")

        # Availability bonus (10 points)
        if prop.is_available_now:
            score += 10
            reasons.append("Ihned k dispozici")

        # Business priority bonus
        if prop.is_hot:
            score += 5
            reasons.append("HOT nabidka")
        elif prop.is_featured:
            score += 3
            reasons.append("Doporuceno")

        # Priority score contribution
        score += min(prop.priority_score / 20, 5)

        # Normalize to 0-100
        score = max(0, min(100, score))

        return score, reasons


class LLMReranker:
    """
    Uses LLM to re-rank search results based on relevance to user query.

    More accurate than embedding similarity for complex queries.
    """

    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL

    def rerank(
        self,
        query: str,
        properties: list[Property],
        top_k: int = 5,
        user_requirements: Optional[dict] = None,
    ) -> list[tuple[Property, float, str]]:
        """
        Re-rank properties using LLM judgment.

        Args:
            query: User's search query
            properties: List of candidate properties
            top_k: Number of results to return
            user_requirements: Optional dict of explicit requirements

        Returns:
            List of (Property, relevance_score, reasoning) tuples
        """
        if not properties:
            return []

        # For small lists, just rank them all
        if len(properties) <= top_k:
            candidates = properties
        else:
            candidates = properties[:top_k * 2]  # Consider 2x candidates

        # Build property descriptions for LLM
        property_descs = []
        for i, prop in enumerate(candidates):
            prop_title = f"{prop.property_type_cz.upper()} - {prop.location}"
            hot_badge = " [HOT]" if prop.is_hot else ""
            featured_badge = " [Doporučeno]" if prop.is_featured else ""

            desc = f"""[{i+1}] {prop_title}{hot_badge}{featured_badge}
- Typ: {"Sklad" if prop.property_type == "warehouse" else "Kancelář"}
- Lokalita: {prop.location} ({prop.location_region})
- Plocha: {prop.area_sqm} m²
- Cena: {prop.price_czk_sqm} Kč/m²/měsíc ({prop.total_monthly_rent:,} Kč celkem)
- Dostupnost: {"Ihned" if prop.is_available_now else f"Od {prop.availability}"}
- Vybavení: {prop.amenities_cz if prop.amenities else "Základní"}"""
            property_descs.append(desc)

        properties_text = "\n\n".join(property_descs)

        # Build requirements context
        requirements_text = ""
        if user_requirements:
            req_parts = []
            if user_requirements.get("property_type"):
                ptype = "sklad" if user_requirements["property_type"] == "warehouse" else "kancelář"
                req_parts.append(f"Typ: {ptype}")
            if user_requirements.get("min_area"):
                req_parts.append(f"Min. plocha: {user_requirements['min_area']} m²")
            if user_requirements.get("max_area"):
                req_parts.append(f"Max. plocha: {user_requirements['max_area']} m²")
            if user_requirements.get("max_price"):
                req_parts.append(f"Max. cena: {user_requirements['max_price']} Kč/m²")
            if user_requirements.get("locations"):
                req_parts.append(f"Lokality: {', '.join(user_requirements['locations'])}")
            if req_parts:
                requirements_text = f"\n\nExplicitní požadavky klienta:\n" + "\n".join(req_parts)

        prompt = f"""Jsi expert na komerční nemovitosti. Ohodnoť následující nemovitosti podle relevance pro klienta.

DOTAZ KLIENTA: "{query}"{requirements_text}

KANDIDÁTNÍ NEMOVITOSTI:
{properties_text}

Pro každou nemovitost urči skóre relevance (1-10) a stručné zdůvodnění.

FAKTORY (váhy):
- Shoda typu nemovitosti: 25%
- Vhodnost lokality: 25%
- Adekvátnost velikosti: 20%
- Cenová dostupnost: 20%
- Aktuální dostupnost: 10%

BONUS faktory:
- HOT/Doporučeno: +0.5 bodu
- Přesná shoda všech kritérií: +1 bod

Odpověz POUZE jako JSON objekt s polem "rankings":
{{"rankings": [{{"index": 1, "score": 8.5, "reason": "Přesná shoda lokality a ceny"}}]}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            result = json.loads(response.choices[0].message.content)

            # Handle different response formats
            if isinstance(result, list):
                rankings = result
            else:
                rankings = result.get("rankings") or result.get("results") or result.get("properties") or []

            # Map back to properties
            scored = []
            for ranking in rankings:
                idx = ranking.get("index", 0)
                if isinstance(idx, int) and 1 <= idx <= len(candidates):
                    prop = candidates[idx - 1]
                    score = float(ranking.get("score", 5)) / 10  # Normalize to 0-1
                    reason = ranking.get("reason", "")
                    scored.append((prop, score, reason))

            # Sort by score
            scored.sort(key=lambda x: x[1], reverse=True)

            return scored[:top_k]

        except Exception as e:
            logger.error(f"LLM reranking failed: {e}")
            # Fallback: return original order with default scores
            return [(p, 0.5, "") for p in candidates[:top_k]]

    def score_single(
        self,
        query: str,
        prop: Property,
        user_requirements: Optional[dict] = None,
    ) -> tuple[float, str]:
        """
        Score a single property against a query.

        Returns (score 0-1, reasoning).
        """
        results = self.rerank(query, [prop], top_k=1, user_requirements=user_requirements)
        if results:
            return results[0][1], results[0][2]
        return 0.5, ""


class HybridReranker:
    """
    Combines fast local scoring with LLM reranking.

    Strategy:
    1. Apply local scoring to all candidates
    2. Only use LLM for top candidates when scores are close
    3. Fall back to local scoring if LLM fails
    """

    def __init__(self, llm_threshold: float = 0.15, min_candidates_for_llm: int = 3):
        """
        Initialize hybrid reranker.

        Args:
            llm_threshold: Score difference threshold to trigger LLM reranking
            min_candidates_for_llm: Minimum candidates needed to use LLM
        """
        self.local_scorer = LocalScorer()
        self.llm_reranker = LLMReranker()
        self.llm_threshold = llm_threshold
        self.min_candidates_for_llm = min_candidates_for_llm

    def rerank(
        self,
        query: str,
        properties: list[Property],
        top_k: int = 5,
        user_requirements: Optional[dict] = None,
        force_llm: bool = False,
    ) -> list[tuple[Property, float, str]]:
        """
        Rerank properties using hybrid approach.

        Args:
            query: User's search query
            properties: List of candidate properties
            top_k: Number of results to return
            user_requirements: Optional dict of explicit requirements
            force_llm: Force LLM reranking regardless of scores

        Returns:
            List of (Property, score, reasoning) tuples
        """
        if not properties:
            return []

        logger.debug(f"Hybrid reranking {len(properties)} properties")

        # Step 1: Local scoring
        local_scores = []
        for prop in properties:
            score, reasons = self.local_scorer.score(prop, user_requirements)
            local_scores.append((prop, score / 100, "; ".join(reasons)))

        # Sort by local score
        local_scores.sort(key=lambda x: x[1], reverse=True)

        # Step 2: Determine if LLM reranking is needed
        use_llm = force_llm

        if not use_llm and len(local_scores) >= self.min_candidates_for_llm:
            # Check if top scores are close
            top_scores = [s[1] for s in local_scores[:top_k + 2]]
            if len(top_scores) >= 2:
                score_diff = top_scores[0] - top_scores[-1]
                if score_diff < self.llm_threshold:
                    use_llm = True
                    logger.debug(f"Scores close ({score_diff:.2f}), using LLM reranking")

        # Step 3: LLM reranking if needed
        if use_llm:
            # Only send top candidates to LLM
            candidates = [p for p, s, r in local_scores[:top_k * 2]]
            try:
                llm_results = self.llm_reranker.rerank(
                    query=query,
                    properties=candidates,
                    top_k=top_k,
                    user_requirements=user_requirements,
                )

                if llm_results:
                    logger.debug(f"LLM reranking returned {len(llm_results)} results")
                    return llm_results

            except Exception as e:
                logger.warning(f"LLM reranking failed, falling back to local: {e}")

        # Return local scores
        return local_scores[:top_k]

    def quick_score(
        self,
        prop: Property,
        user_requirements: Optional[dict] = None,
    ) -> tuple[float, list[str]]:
        """
        Quick local scoring without LLM.

        Args:
            prop: Property to score
            user_requirements: Optional requirements dict

        Returns:
            Tuple of (score 0-1, list of reasons)
        """
        score, reasons = self.local_scorer.score(prop, user_requirements)
        return score / 100, reasons


# Singleton instances
_local_scorer: LocalScorer | None = None
_hybrid_reranker: HybridReranker | None = None


def get_local_scorer() -> LocalScorer:
    """Get singleton local scorer instance."""
    global _local_scorer
    if _local_scorer is None:
        _local_scorer = LocalScorer()
    return _local_scorer


def get_hybrid_reranker() -> HybridReranker:
    """Get singleton hybrid reranker instance."""
    global _hybrid_reranker
    if _hybrid_reranker is None:
        _hybrid_reranker = HybridReranker()
    return _hybrid_reranker
