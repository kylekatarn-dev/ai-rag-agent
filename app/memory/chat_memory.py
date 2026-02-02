"""
RAG-based Chat Memory.

Provides semantic search over conversation history instead of
sending full history with every request.
"""

import re
import time
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import chromadb
from chromadb.config import Settings

from app.config import CHROMA_DIR
from app.rag.embeddings import get_embeddings
from app.utils import get_logger

logger = get_logger(__name__)

# Collection name for chat memory
CHAT_MEMORY_COLLECTION = "chat_memory"

# How many recent turns to always include (not retrieved, just kept)
RECENT_BUFFER_SIZE = 3

# How many relevant turns to retrieve from history
RETRIEVAL_TOP_K = 5


@dataclass
class ChatTurn:
    """A single conversation turn."""
    user_message: str
    assistant_response: str
    turn_number: int
    timestamp: float
    image_refs: list[str] = field(default_factory=list)
    extracted_info: dict = field(default_factory=dict)


class ChatMemory:
    """
    RAG-based chat memory for conversation history.

    Instead of sending full history, this:
    1. Keeps last N turns in a buffer (always sent)
    2. Embeds and stores all turns in ChromaDB
    3. Retrieves semantically relevant older turns for context

    Benefits:
    - Fixed context window regardless of conversation length
    - Semantically relevant history (not just recent)
    - Handles long conversations without truncation
    """

    def __init__(
        self,
        session_id: str,
        recent_buffer_size: int = RECENT_BUFFER_SIZE,
        retrieval_top_k: int = RETRIEVAL_TOP_K,
    ):
        """
        Initialize chat memory for a session.

        Args:
            session_id: Unique session identifier
            recent_buffer_size: Number of recent turns to always include
            retrieval_top_k: Number of relevant turns to retrieve
        """
        self.session_id = session_id
        self.recent_buffer_size = recent_buffer_size
        self.retrieval_top_k = retrieval_top_k

        self.embeddings = get_embeddings()
        self.client = self._get_client()
        self.collection = self._get_or_create_collection()

        # Recent turns buffer (always included)
        self.recent_buffer: list[ChatTurn] = []

        # Current turn counter
        self.turn_count = 0

        # Cached extracted requirements from conversation
        self.extracted_requirements: dict = {}

        logger.info(f"ChatMemory initialized for session {session_id}")

    def _get_client(self) -> chromadb.Client:
        """Get ChromaDB client."""
        persist_dir = Path(CHROMA_DIR) / "chat_memory"
        persist_dir.mkdir(parents=True, exist_ok=True)

        return chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False)
        )

    def _get_or_create_collection(self):
        """Get or create chat memory collection."""
        return self.client.get_or_create_collection(
            name=CHAT_MEMORY_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )

    def _extract_image_refs(self, text: str) -> list[str]:
        """
        Extract image references from text.

        Finds URLs and image filenames, returns just references
        (not base64 data).
        """
        refs = []

        # Find image URLs (http/https with image extensions)
        url_pattern = r'https?://[^\s]+\.(?:jpg|jpeg|png|gif|webp)'
        refs.extend(re.findall(url_pattern, text, re.IGNORECASE))

        # Find placehold.co URLs (our property images)
        placeholder_pattern = r'https?://placehold\.co/[^\s\)]+'
        refs.extend(re.findall(placeholder_pattern, text, re.IGNORECASE))

        # Find image filenames
        filename_pattern = r'\b[\w-]+\.(?:jpg|jpeg|png|gif|webp)\b'
        refs.extend(re.findall(filename_pattern, text, re.IGNORECASE))

        return list(set(refs))  # Deduplicate

    def _create_embedding_text(self, turn: ChatTurn) -> str:
        """
        Create text for embedding a conversation turn.

        Focuses on semantic content, strips image data.
        """
        # Clean user message (remove image base64 if present)
        user_clean = re.sub(r'data:image/[^;]+;base64,[^\s]+', '[IMAGE]', turn.user_message)

        # Clean assistant response (remove large image URLs)
        assistant_clean = re.sub(
            r'!\[.*?\]\(https?://[^\)]+\)',
            '[PROPERTY_IMAGE]',
            turn.assistant_response
        )

        # Create embedding text
        parts = [
            f"User: {user_clean[:500]}",  # Limit length
            f"Assistant: {assistant_clean[:1000]}",
        ]

        # Add extracted info if available
        if turn.extracted_info:
            info_parts = []
            for key, value in turn.extracted_info.items():
                if value:
                    info_parts.append(f"{key}: {value}")
            if info_parts:
                parts.append(f"Requirements: {', '.join(info_parts)}")

        return "\n".join(parts)

    def add_turn(
        self,
        user_message: str,
        assistant_response: str,
        extracted_info: Optional[dict] = None,
    ):
        """
        Add a conversation turn to memory.

        Args:
            user_message: The user's message
            assistant_response: The assistant's response
            extracted_info: Optional extracted requirements from this turn
        """
        self.turn_count += 1

        # Extract image references (but don't store full images)
        image_refs = self._extract_image_refs(user_message + assistant_response)

        # Create turn object
        turn = ChatTurn(
            user_message=user_message,
            assistant_response=assistant_response,
            turn_number=self.turn_count,
            timestamp=time.time(),
            image_refs=image_refs,
            extracted_info=extracted_info or {},
        )

        # Update extracted requirements
        if extracted_info:
            self.extracted_requirements.update(
                {k: v for k, v in extracted_info.items() if v}
            )

        # Add to recent buffer
        self.recent_buffer.append(turn)

        # If buffer is full, embed and store the oldest turn
        if len(self.recent_buffer) > self.recent_buffer_size:
            old_turn = self.recent_buffer.pop(0)
            self._store_turn(old_turn)

        logger.debug(f"Added turn {self.turn_count} to memory (buffer: {len(self.recent_buffer)})")

    def _store_turn(self, turn: ChatTurn):
        """Store a turn in ChromaDB for later retrieval."""
        embedding_text = self._create_embedding_text(turn)

        try:
            embedding = self.embeddings.embed_query(embedding_text)

            turn_id = f"{self.session_id}_turn_{turn.turn_number}"

            self.collection.add(
                ids=[turn_id],
                embeddings=[embedding],
                documents=[embedding_text],
                metadatas=[{
                    "session_id": self.session_id,
                    "turn_number": turn.turn_number,
                    "timestamp": turn.timestamp,
                    "has_images": len(turn.image_refs) > 0,
                    "image_count": len(turn.image_refs),
                }]
            )

            logger.debug(f"Stored turn {turn.turn_number} in ChromaDB")

        except Exception as e:
            logger.error(f"Failed to store turn in ChromaDB: {e}")

    def get_relevant_context(self, current_query: str) -> str:
        """
        Get relevant conversation context for a new query.

        Returns formatted context including:
        1. Retrieved relevant older turns
        2. Current extracted requirements
        3. Recent conversation buffer

        Args:
            current_query: The current user query

        Returns:
            Formatted context string
        """
        context_parts = []

        # 1. Retrieve relevant older turns from ChromaDB
        retrieved = self._retrieve_relevant_turns(current_query)
        if retrieved:
            context_parts.append("=== Relevantni historie ===")
            for doc, meta in retrieved:
                context_parts.append(f"[Tura {meta['turn_number']}]\n{doc}")
            context_parts.append("")

        # 2. Add extracted requirements summary
        if self.extracted_requirements:
            context_parts.append("=== Zname pozadavky klienta ===")
            for key, value in self.extracted_requirements.items():
                if value:
                    context_parts.append(f"- {key}: {value}")
            context_parts.append("")

        # 3. Add recent buffer (always included)
        if self.recent_buffer:
            context_parts.append("=== Posledni zpravy ===")
            for turn in self.recent_buffer:
                # Strip images from display
                user_clean = re.sub(r'data:image/[^;]+;base64,[^\s]+', '[IMAGE]', turn.user_message)
                context_parts.append(f"Klient: {user_clean[:300]}")
                context_parts.append(f"Asistent: {turn.assistant_response[:500]}")
                context_parts.append("")

        return "\n".join(context_parts)

    def _retrieve_relevant_turns(
        self,
        query: str,
    ) -> list[tuple[str, dict]]:
        """
        Retrieve relevant turns from ChromaDB.

        Args:
            query: Current query to find relevant history for

        Returns:
            List of (document, metadata) tuples
        """
        try:
            # Check if we have any stored turns
            count = self.collection.count()
            if count == 0:
                return []

            # Embed query
            query_embedding = self.embeddings.embed_query(query)

            # Search for relevant turns (only from this session)
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(self.retrieval_top_k, count),
                where={"session_id": self.session_id},
                include=["documents", "metadatas", "distances"]
            )

            if not results["ids"] or not results["ids"][0]:
                return []

            # Filter by relevance (similarity > 0.5)
            relevant = []
            for i, doc in enumerate(results["documents"][0]):
                distance = results["distances"][0][i]
                similarity = 1 - distance

                if similarity > 0.5:  # Only include if reasonably relevant
                    relevant.append((doc, results["metadatas"][0][i]))

            # Sort by turn number (chronological order)
            relevant.sort(key=lambda x: x[1]["turn_number"])

            logger.debug(f"Retrieved {len(relevant)} relevant turns from history")
            return relevant

        except Exception as e:
            logger.error(f"Failed to retrieve from ChromaDB: {e}")
            return []

    def get_full_history(self) -> list[dict]:
        """
        Get full conversation history (for logging/export).

        Returns list of all turns in chronological order.
        """
        history = []

        # Get stored turns from ChromaDB
        try:
            results = self.collection.get(
                where={"session_id": self.session_id},
                include=["documents", "metadatas"]
            )

            if results["ids"]:
                for i, doc in enumerate(results["documents"]):
                    meta = results["metadatas"][i]
                    history.append({
                        "turn": meta["turn_number"],
                        "content": doc,
                        "timestamp": meta.get("timestamp"),
                    })
        except Exception as e:
            logger.error(f"Failed to get history from ChromaDB: {e}")

        # Add recent buffer
        for turn in self.recent_buffer:
            history.append({
                "turn": turn.turn_number,
                "content": f"User: {turn.user_message}\nAssistant: {turn.assistant_response}",
                "timestamp": turn.timestamp,
            })

        # Sort by turn number
        history.sort(key=lambda x: x["turn"])

        return history

    def clear_session(self):
        """Clear all memory for this session."""
        try:
            # Get all IDs for this session
            results = self.collection.get(
                where={"session_id": self.session_id}
            )

            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info(f"Cleared {len(results['ids'])} turns from session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")

        # Clear buffer
        self.recent_buffer.clear()
        self.turn_count = 0
        self.extracted_requirements.clear()

    def get_stats(self) -> dict:
        """Get memory statistics."""
        try:
            results = self.collection.get(
                where={"session_id": self.session_id}
            )
            stored_count = len(results["ids"]) if results["ids"] else 0
        except:
            stored_count = 0

        return {
            "session_id": self.session_id,
            "total_turns": self.turn_count,
            "buffer_size": len(self.recent_buffer),
            "stored_turns": stored_count,
            "extracted_requirements": self.extracted_requirements,
        }


# Session memory cache
_memory_cache: dict[str, ChatMemory] = {}


def get_chat_memory(session_id: str) -> ChatMemory:
    """
    Get or create ChatMemory for a session.

    Args:
        session_id: Session identifier

    Returns:
        ChatMemory instance for the session
    """
    if session_id not in _memory_cache:
        _memory_cache[session_id] = ChatMemory(session_id)
    return _memory_cache[session_id]


def clear_memory_cache():
    """Clear all cached memory instances."""
    global _memory_cache
    _memory_cache.clear()
