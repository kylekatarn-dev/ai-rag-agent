"""
Embedding utilities with caching support.

Provides cached embeddings to reduce API costs and improve response time.
"""

import hashlib
import time
from functools import lru_cache
from typing import Optional
from dataclasses import dataclass, field

from langchain_openai import OpenAIEmbeddings

from app.config import OPENAI_EMBEDDING_MODEL, get_secret
from app.utils import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with TTL support."""
    embedding: list[float]
    created_at: float
    hits: int = 0


class EmbeddingCache:
    """
    LRU cache for embeddings with TTL support.

    Reduces API costs by caching frequently used query embeddings.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """
        Initialize embedding cache.

        Args:
            max_size: Maximum number of cached embeddings
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []

        # Statistics
        self.hits = 0
        self.misses = 0

    def _hash_text(self, text: str) -> str:
        """Create a hash key for the text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry has expired."""
        return time.time() - entry.created_at > self.ttl_seconds

    def _evict_if_needed(self):
        """Evict oldest entries if cache is full."""
        while len(self._cache) >= self.max_size and self._access_order:
            oldest_key = self._access_order.pop(0)
            if oldest_key in self._cache:
                del self._cache[oldest_key]
                logger.debug(f"Evicted cache entry: {oldest_key}")

    def get(self, text: str) -> Optional[list[float]]:
        """
        Get embedding from cache.

        Args:
            text: The text to look up

        Returns:
            Cached embedding or None if not found/expired
        """
        key = self._hash_text(text)

        if key in self._cache:
            entry = self._cache[key]

            # Check TTL
            if self._is_expired(entry):
                del self._cache[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                self.misses += 1
                return None

            # Update access order (move to end)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            # Update hit count
            entry.hits += 1
            self.hits += 1

            logger.debug(f"Cache hit for: {text[:50]}...")
            return entry.embedding

        self.misses += 1
        return None

    def set(self, text: str, embedding: list[float]):
        """
        Store embedding in cache.

        Args:
            text: The text that was embedded
            embedding: The embedding vector
        """
        key = self._hash_text(text)

        self._evict_if_needed()

        self._cache[key] = CacheEntry(
            embedding=embedding,
            created_at=time.time(),
        )
        self._access_order.append(key)

        logger.debug(f"Cached embedding for: {text[:50]}...")

    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
        self._access_order.clear()
        logger.info("Embedding cache cleared")

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_requests = self.hits + self.misses
        hit_rate = self.hits / total_requests if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1%}",
            "ttl_seconds": self.ttl_seconds,
        }


class CachedOpenAIEmbeddings:
    """
    OpenAI Embeddings wrapper with caching support.

    Caches query embeddings to reduce API costs for repeated searches.
    Document embeddings are not cached (they're typically only computed once).
    """

    def __init__(
        self,
        model: str = None,
        api_key: str = None,
        cache_max_size: int = 1000,
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize cached embeddings.

        Args:
            model: OpenAI embedding model name
            api_key: OpenAI API key
            cache_max_size: Maximum cached query embeddings
            cache_ttl_seconds: Cache TTL in seconds
        """
        # Get secrets at runtime (important for Streamlit Cloud)
        if api_key is None:
            api_key = get_secret("OPENAI_API_KEY")
        if model is None:
            model = get_secret("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL)

        self._embeddings = OpenAIEmbeddings(
            model=model,
            openai_api_key=api_key,
        )
        self._cache = EmbeddingCache(
            max_size=cache_max_size,
            ttl_seconds=cache_ttl_seconds,
        )
        logger.info(f"Initialized CachedOpenAIEmbeddings with {model}")

    def embed_query(self, text: str) -> list[float]:
        """
        Embed a query string with caching.

        Args:
            text: Query text to embed

        Returns:
            Embedding vector
        """
        # Check cache first
        cached = self._cache.get(text)
        if cached is not None:
            return cached

        # Generate embedding
        logger.debug(f"Generating embedding for query: {text[:50]}...")
        embedding = self._embeddings.embed_query(text)

        # Cache the result
        self._cache.set(text, embedding)

        return embedding

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple documents (not cached - typically one-time operation).

        Args:
            texts: List of document texts

        Returns:
            List of embedding vectors
        """
        logger.info(f"Embedding {len(texts)} documents (batch)")
        return self._embeddings.embed_documents(texts)

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return self._cache.get_stats()

    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()


# Singleton instance
_cached_embeddings: CachedOpenAIEmbeddings | None = None


def get_embeddings() -> CachedOpenAIEmbeddings:
    """
    Get cached OpenAI embeddings instance (singleton).

    Returns:
        CachedOpenAIEmbeddings instance
    """
    global _cached_embeddings
    if _cached_embeddings is None:
        _cached_embeddings = CachedOpenAIEmbeddings()
    return _cached_embeddings


def get_embedding_cache_stats() -> dict:
    """Get embedding cache statistics."""
    embeddings = get_embeddings()
    return embeddings.get_cache_stats()


def clear_embedding_cache():
    """Clear the embedding cache."""
    embeddings = get_embeddings()
    embeddings.clear_cache()
