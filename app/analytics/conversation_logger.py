"""
Conversation logging and storage for broker review and analytics.

Features:
- Save full conversation transcripts
- Generate AI summaries for broker
- Track quality metrics
- Enable human review
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from app.utils import get_logger

logger = get_logger(__name__)

# Default storage directory
CONVERSATIONS_DIR = Path("data/conversations")


@dataclass
class ConversationRecord:
    """Record of a single conversation."""
    session_id: str
    started_at: str
    ended_at: Optional[str]
    messages: list[dict]
    lead_data: dict
    lead_score: int
    lead_quality: str
    properties_shown: list[int]
    ai_summary: Optional[str]
    broker_notes: Optional[str]
    quality_flags: list[str]  # Issues detected
    outcome: Optional[str]  # "converted", "follow_up", "lost", etc.


class ConversationLogger:
    """
    Logs and stores conversations for review and analytics.

    Features:
    - Automatic saving of conversations
    - AI-generated summaries for broker
    - Quality tracking and flagging
    - JSON storage (can be extended to database)
    """

    def __init__(self, storage_dir: Path = CONVERSATIONS_DIR):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: Optional[str] = None
        self.messages: list[dict] = []
        self.properties_shown: list[int] = []
        self.quality_flags: list[str] = []
        self.started_at: Optional[datetime] = None

    def start_session(self, session_id: str):
        """Start a new conversation session."""
        self.current_session = session_id
        self.messages = []
        self.properties_shown = []
        self.quality_flags = []
        self.started_at = datetime.now()
        logger.info(f"Started conversation session: {session_id}")

    def log_message(self, role: str, content: str, metadata: Optional[dict] = None):
        """Log a message in the conversation."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.messages.append(msg)

        # Check for quality issues
        self._check_quality(role, content)

    def log_property_shown(self, property_id: int):
        """Track which properties were shown."""
        if property_id not in self.properties_shown:
            self.properties_shown.append(property_id)

    def flag_quality_issue(self, issue: str):
        """Flag a quality issue for review."""
        if issue not in self.quality_flags:
            self.quality_flags.append(issue)
            logger.warning(f"Quality issue flagged: {issue}")

    def _check_quality(self, role: str, content: str):
        """Automatically detect potential quality issues."""
        if role == "assistant":
            content_lower = content.lower()

            # Check for potential hallucinations
            if "10 000 m" in content or "10000 m" in content:
                # We don't have properties this big
                self.flag_quality_issue("mentioned_unavailable_size")

            # Check for repeated questions (simple heuristic)
            if len(self.messages) > 2:
                recent_assistant = [m for m in self.messages[-6:] if m["role"] == "assistant"]
                if len(recent_assistant) >= 2:
                    # Check if asking same question twice
                    last_questions = [m["content"] for m in recent_assistant if "?" in m["content"]]
                    if len(last_questions) >= 2:
                        # Simple duplicate detection
                        for i, q1 in enumerate(last_questions):
                            for q2 in last_questions[i+1:]:
                                if self._similar_questions(q1, q2):
                                    self.flag_quality_issue("repeated_question")

    def _similar_questions(self, q1: str, q2: str) -> bool:
        """Check if two questions are similar (simple keyword overlap)."""
        words1 = set(q1.lower().split())
        words2 = set(q2.lower().split())
        overlap = len(words1 & words2) / max(len(words1), len(words2), 1)
        return overlap > 0.7

    def save_conversation(
        self,
        lead_data: dict,
        lead_score: int,
        lead_quality: str,
        ai_summary: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> str:
        """
        Save the conversation to storage.

        Returns the filepath where conversation was saved.
        """
        if not self.current_session:
            logger.warning("No active session to save")
            return ""

        record = ConversationRecord(
            session_id=self.current_session,
            started_at=self.started_at.isoformat() if self.started_at else "",
            ended_at=datetime.now().isoformat(),
            messages=self.messages,
            lead_data=lead_data,
            lead_score=lead_score,
            lead_quality=lead_quality,
            properties_shown=self.properties_shown,
            ai_summary=ai_summary,
            broker_notes=None,
            quality_flags=self.quality_flags,
            outcome=outcome,
        )

        # Save to JSON file
        filename = f"{self.current_session}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.storage_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(record), f, ensure_ascii=False, indent=2)

        logger.info(f"Saved conversation to: {filepath}")
        return str(filepath)

    def get_broker_summary(self, lead_data: dict, ai_summary: str) -> str:
        """Generate a summary for the broker."""
        summary = f"""
## Souhrn konverzace pro makléře

**Klient:** {lead_data.get('name', 'Neznámý')}
**Email:** {lead_data.get('email', 'Neuveden')}
**Telefon:** {lead_data.get('phone', 'Neuveden')}

### Požadavky:
- Typ: {lead_data.get('property_type', 'Nespecifikován')}
- Plocha: {lead_data.get('min_area_sqm', '?')} - {lead_data.get('max_area_sqm', '?')} m²
- Lokalita: {', '.join(lead_data.get('preferred_locations', [])) or 'Nespecifikována'}
- Max cena: {lead_data.get('max_price_czk_sqm', 'Nespecifikována')} Kč/m²

### AI Shrnutí:
{ai_summary}

### Zobrazené nemovitosti:
{', '.join(str(p) for p in self.properties_shown) or 'Žádné'}

### Upozornění:
{', '.join(self.quality_flags) or 'Žádné problémy'}

### Plný přepis:
"""
        for msg in self.messages:
            role = "Klient" if msg["role"] == "user" else "Asistent"
            summary += f"\n**{role}:** {msg['content']}\n"

        return summary

    def list_conversations(self, limit: int = 50) -> list[dict]:
        """List recent conversations."""
        files = sorted(self.storage_dir.glob("*.json"), reverse=True)[:limit]
        conversations = []

        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    conversations.append({
                        "session_id": data.get("session_id"),
                        "started_at": data.get("started_at"),
                        "lead_name": data.get("lead_data", {}).get("name"),
                        "lead_score": data.get("lead_score"),
                        "quality_flags": data.get("quality_flags", []),
                        "filepath": str(f),
                    })
            except Exception as e:
                logger.error(f"Error reading {f}: {e}")

        return conversations


# Singleton instance
_conversation_logger: Optional[ConversationLogger] = None


def get_conversation_logger() -> ConversationLogger:
    """Get singleton ConversationLogger instance."""
    global _conversation_logger
    if _conversation_logger is None:
        _conversation_logger = ConversationLogger()
    return _conversation_logger
