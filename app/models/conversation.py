from datetime import datetime
from typing import Literal, Optional, TYPE_CHECKING, Any
from pydantic import BaseModel, Field

from .lead import Lead

if TYPE_CHECKING:
    from .property import Property


# Token estimation constants (rough approximations)
CHARS_PER_TOKEN = 4  # Average characters per token for Czech/English mix
MAX_CONTEXT_TOKENS = 8000  # Safe limit for gpt-4o-mini (128k context, but we want headroom)
SYSTEM_PROMPT_TOKENS = 2000  # Estimated tokens for system prompt
RESPONSE_TOKENS = 2000  # Reserved for response generation


class Message(BaseModel):
    """Chat message model."""

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Optional metadata
    properties_mentioned: list[int] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)

    @property
    def estimated_tokens(self) -> int:
        """Estimate token count for this message."""
        return len(self.content) // CHARS_PER_TOKEN + 4  # +4 for role/formatting


class ConversationState(BaseModel):
    """Tracks the state of a conversation with a lead."""

    lead: Lead = Field(default_factory=Lead)
    messages: list[Message] = Field(default_factory=list)

    current_phase: Literal[
        "greeting",
        "needs_discovery",
        "property_search",
        "recommendation",
        "objection_handling",
        "contact_capture",
        "handoff"
    ] = "greeting"

    properties_shown: list[int] = Field(default_factory=list)
    last_shown_properties: list[Any] = Field(default_factory=list)  # Stores Property objects
    questions_asked: list[str] = Field(default_factory=list)
    info_gathered: dict = Field(default_factory=dict)

    # Tracking
    search_performed: bool = False
    recommendations_made: bool = False
    contact_requested: bool = False
    summary_generated: bool = False

    # Memory management settings
    max_history_tokens: int = MAX_CONTEXT_TOKENS - SYSTEM_PROMPT_TOKENS - RESPONSE_TOKENS
    keep_first_n_messages: int = 2  # Keep initial greeting exchange

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation."""
        self.messages.append(Message(role=role, content=content))

    def get_messages_for_llm(self, include_summary: bool = True) -> list[dict]:
        """
        Get messages in format for LLM API with memory management.

        Implements a sliding window approach:
        1. Always keep the first N messages (greeting context)
        2. If too long, create a summary of trimmed messages
        3. Keep most recent messages that fit in token budget

        Args:
            include_summary: Whether to include summary of trimmed messages

        Returns:
            List of message dicts for LLM API
        """
        non_system_messages = [
            msg for msg in self.messages if msg.role != "system"
        ]

        if not non_system_messages:
            return []

        total_tokens = sum(msg.estimated_tokens for msg in non_system_messages)

        # If within limits, return all messages
        if total_tokens <= self.max_history_tokens:
            return [
                {"role": msg.role, "content": msg.content}
                for msg in non_system_messages
            ]

        # Need to trim - keep first N and most recent messages
        first_messages = non_system_messages[:self.keep_first_n_messages]
        remaining_messages = non_system_messages[self.keep_first_n_messages:]

        # Calculate tokens used by first messages
        first_tokens = sum(msg.estimated_tokens for msg in first_messages)
        available_tokens = self.max_history_tokens - first_tokens

        # Add messages from the end until we run out of tokens
        kept_messages = []
        current_tokens = 0

        for msg in reversed(remaining_messages):
            if current_tokens + msg.estimated_tokens > available_tokens:
                break
            kept_messages.insert(0, msg)
            current_tokens += msg.estimated_tokens

        # Build result with optional summary
        result = [{"role": msg.role, "content": msg.content} for msg in first_messages]

        # Add summary of trimmed messages if there are any
        trimmed_count = len(remaining_messages) - len(kept_messages)
        if include_summary and trimmed_count > 0:
            trimmed_messages = remaining_messages[:trimmed_count]
            summary = self._create_conversation_summary(trimmed_messages)
            result.append({
                "role": "system",
                "content": f"[Shrnuti predchozi konverzace: {summary}]"
            })

        # Add kept recent messages
        result.extend([
            {"role": msg.role, "content": msg.content}
            for msg in kept_messages
        ])

        return result

    def _create_conversation_summary(self, messages: list[Message]) -> str:
        """
        Create a brief summary of trimmed messages.

        Args:
            messages: Messages to summarize

        Returns:
            Brief summary string
        """
        # Extract key information from messages
        user_messages = [m.content for m in messages if m.role == "user"]
        properties_mentioned = set()

        for msg in messages:
            properties_mentioned.update(msg.properties_mentioned)

        summary_parts = []

        if user_messages:
            # Get first user message topic
            first_topic = user_messages[0][:100]
            summary_parts.append(f"Klient zacal dotazem: '{first_topic}...'")

        if properties_mentioned:
            summary_parts.append(
                f"Byly zobrazeny nemovitosti ID: {', '.join(map(str, properties_mentioned))}"
            )

        summary_parts.append(f"Celkem {len(messages)} zprav bylo shrnuto.")

        return " ".join(summary_parts)

    def get_context_usage(self) -> dict:
        """
        Get context window usage statistics.

        Returns:
            Dict with usage statistics
        """
        total_tokens = sum(msg.estimated_tokens for msg in self.messages)
        return {
            "total_messages": len(self.messages),
            "estimated_tokens": total_tokens,
            "max_tokens": self.max_history_tokens,
            "usage_percent": f"{(total_tokens / self.max_history_tokens) * 100:.1f}%",
            "messages_would_trim": self._count_messages_to_trim(),
        }

    def _count_messages_to_trim(self) -> int:
        """Count how many messages would be trimmed."""
        non_system = [m for m in self.messages if m.role != "system"]
        total_tokens = sum(m.estimated_tokens for m in non_system)

        if total_tokens <= self.max_history_tokens:
            return 0

        first_tokens = sum(
            m.estimated_tokens for m in non_system[:self.keep_first_n_messages]
        )
        available = self.max_history_tokens - first_tokens

        # Count from end
        kept = 0
        current = 0
        for msg in reversed(non_system[self.keep_first_n_messages:]):
            if current + msg.estimated_tokens > available:
                break
            kept += 1
            current += msg.estimated_tokens

        return len(non_system) - self.keep_first_n_messages - kept

    @property
    def message_count(self) -> int:
        """Count of user messages."""
        return sum(1 for msg in self.messages if msg.role == "user")

    @property
    def has_enough_info_for_search(self) -> bool:
        """Check if we have minimum info to search properties."""
        lead = self.lead
        return (
            lead.property_type is not None and
            (lead.min_area_sqm is not None or lead.max_area_sqm is not None or
             len(lead.preferred_locations) > 0)
        )

    def clear_history(self, keep_last: int = 0) -> int:
        """
        Clear conversation history.

        Args:
            keep_last: Number of recent messages to keep

        Returns:
            Number of messages removed
        """
        if keep_last <= 0:
            removed = len(self.messages)
            self.messages.clear()
            return removed

        if keep_last >= len(self.messages):
            return 0

        removed = len(self.messages) - keep_last
        self.messages = self.messages[-keep_last:]
        return removed
