"""
Analytics Tracking Module.

Tracks conversation events, lead quality, and conversion metrics.
"""

import json
from datetime import datetime, timedelta
from typing import Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from collections import defaultdict
import threading

from app.utils import get_logger

logger = get_logger(__name__)


class AnalyticsEvent(str, Enum):
    """Analytics event types."""
    # Conversation events
    CONVERSATION_STARTED = "conversation.started"
    CONVERSATION_ENDED = "conversation.ended"
    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"

    # Lead events
    LEAD_CREATED = "lead.created"
    LEAD_QUALIFIED = "lead.qualified"
    LEAD_SCORED = "lead.scored"
    LEAD_CONTACT_CAPTURED = "lead.contact_captured"

    # Search events
    SEARCH_PERFORMED = "search.performed"
    SEARCH_NO_RESULTS = "search.no_results"
    PROPERTY_VIEWED = "property.viewed"

    # Conversion events
    MEETING_SCHEDULED = "meeting.scheduled"
    ALERT_REGISTERED = "alert.registered"
    BROKER_HANDOFF = "broker.handoff"

    # Error events
    ERROR_OCCURRED = "error.occurred"
    VALIDATION_FAILED = "validation.failed"


@dataclass
class Event:
    """Analytics event."""
    event_type: str
    timestamp: datetime
    session_id: Optional[str] = None
    lead_id: Optional[str] = None
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


class AnalyticsTracker:
    """
    Tracks and stores analytics events.

    Features:
    - In-memory event storage
    - Session tracking
    - Aggregated metrics
    - Thread-safe operations
    """

    def __init__(self, max_events: int = 10000):
        """
        Initialize analytics tracker.

        Args:
            max_events: Maximum events to store in memory
        """
        self.max_events = max_events
        self._events: list[Event] = []
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

        # Aggregated counters
        self._counters: dict[str, int] = defaultdict(int)
        self._quality_distribution: dict[str, int] = defaultdict(int)

        logger.info("Analytics tracker initialized")

    def track(
        self,
        event_type: AnalyticsEvent,
        session_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        **properties
    ) -> None:
        """
        Track an analytics event.

        Args:
            event_type: Type of event
            session_id: Session identifier
            lead_id: Lead identifier
            **properties: Additional event properties
        """
        event = Event(
            event_type=event_type.value,
            timestamp=datetime.utcnow(),
            session_id=session_id,
            lead_id=lead_id,
            properties=properties,
        )

        with self._lock:
            # Store event
            self._events.append(event)

            # Trim if needed
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events:]

            # Update counters
            self._counters[event_type.value] += 1

            # Track quality distribution
            if event_type == AnalyticsEvent.LEAD_QUALIFIED:
                quality = properties.get("quality", "unknown")
                self._quality_distribution[quality] += 1

            # Update session
            if session_id:
                self._update_session(session_id, event)

        logger.debug(f"Tracked event: {event_type.value}")

    def _update_session(self, session_id: str, event: Event) -> None:
        """Update session tracking."""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "started_at": event.timestamp,
                "last_activity": event.timestamp,
                "event_count": 0,
                "messages": 0,
                "searches": 0,
            }

        session = self._sessions[session_id]
        session["last_activity"] = event.timestamp
        session["event_count"] += 1

        if event.event_type in [AnalyticsEvent.MESSAGE_SENT.value, AnalyticsEvent.MESSAGE_RECEIVED.value]:
            session["messages"] += 1
        elif event.event_type == AnalyticsEvent.SEARCH_PERFORMED.value:
            session["searches"] += 1

    def track_conversation_start(self, session_id: str) -> None:
        """Track conversation start."""
        self.track(AnalyticsEvent.CONVERSATION_STARTED, session_id=session_id)

    def track_message(
        self,
        session_id: str,
        direction: str,  # "sent" or "received"
        message_length: int,
    ) -> None:
        """Track message sent/received."""
        event = (
            AnalyticsEvent.MESSAGE_SENT
            if direction == "sent"
            else AnalyticsEvent.MESSAGE_RECEIVED
        )
        self.track(
            event,
            session_id=session_id,
            length=message_length,
        )

    def track_lead_qualified(
        self,
        session_id: str,
        lead_id: str,
        score: int,
        quality: str,
        customer_type: str,
    ) -> None:
        """Track lead qualification."""
        self.track(
            AnalyticsEvent.LEAD_QUALIFIED,
            session_id=session_id,
            lead_id=lead_id,
            score=score,
            quality=quality,
            customer_type=customer_type,
        )

    def track_search(
        self,
        session_id: str,
        query: str,
        results_count: int,
        filters: dict,
    ) -> None:
        """Track property search."""
        event = (
            AnalyticsEvent.SEARCH_PERFORMED
            if results_count > 0
            else AnalyticsEvent.SEARCH_NO_RESULTS
        )
        self.track(
            event,
            session_id=session_id,
            query=query[:100],
            results_count=results_count,
            filters=filters,
        )

    def track_conversion(
        self,
        session_id: str,
        lead_id: str,
        conversion_type: str,  # "meeting", "alert", "handoff"
    ) -> None:
        """Track conversion event."""
        event_map = {
            "meeting": AnalyticsEvent.MEETING_SCHEDULED,
            "alert": AnalyticsEvent.ALERT_REGISTERED,
            "handoff": AnalyticsEvent.BROKER_HANDOFF,
        }
        event = event_map.get(conversion_type, AnalyticsEvent.BROKER_HANDOFF)
        self.track(event, session_id=session_id, lead_id=lead_id)

    def track_error(
        self,
        error_type: str,
        error_message: str,
        session_id: Optional[str] = None,
    ) -> None:
        """Track error event."""
        self.track(
            AnalyticsEvent.ERROR_OCCURRED,
            session_id=session_id,
            error_type=error_type,
            message=error_message[:200],
        )

    def get_summary(self, hours: int = 24) -> dict:
        """
        Get analytics summary for time period.

        Args:
            hours: Number of hours to include

        Returns:
            Summary statistics
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        with self._lock:
            recent_events = [e for e in self._events if e.timestamp >= cutoff]

            # Count by type
            event_counts = defaultdict(int)
            for event in recent_events:
                event_counts[event.event_type] += 1

            # Session stats
            active_sessions = sum(
                1 for s in self._sessions.values()
                if s["last_activity"] >= cutoff
            )

            # Calculate averages
            messages = event_counts.get(AnalyticsEvent.MESSAGE_RECEIVED.value, 0)
            searches = event_counts.get(AnalyticsEvent.SEARCH_PERFORMED.value, 0)
            qualified = event_counts.get(AnalyticsEvent.LEAD_QUALIFIED.value, 0)
            conversions = (
                event_counts.get(AnalyticsEvent.MEETING_SCHEDULED.value, 0) +
                event_counts.get(AnalyticsEvent.ALERT_REGISTERED.value, 0)
            )

            return {
                "period_hours": hours,
                "total_events": len(recent_events),
                "active_sessions": active_sessions,
                "messages_received": messages,
                "searches_performed": searches,
                "leads_qualified": qualified,
                "conversions": conversions,
                "conversion_rate": f"{(conversions / qualified * 100):.1f}%" if qualified > 0 else "0%",
                "quality_distribution": dict(self._quality_distribution),
                "event_breakdown": dict(event_counts),
            }

    def get_recent_events(self, limit: int = 100) -> list[dict]:
        """Get recent events."""
        with self._lock:
            return [e.to_dict() for e in self._events[-limit:]]

    def get_session_stats(self, session_id: str) -> Optional[dict]:
        """Get stats for a specific session."""
        with self._lock:
            return self._sessions.get(session_id)

    def export_events(self, format: str = "json") -> str:
        """
        Export events for analysis.

        Args:
            format: Export format ("json" or "csv")

        Returns:
            Exported data as string
        """
        with self._lock:
            if format == "json":
                return json.dumps(
                    [e.to_dict() for e in self._events],
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                # CSV format
                lines = ["timestamp,event_type,session_id,lead_id,properties"]
                for event in self._events:
                    props = json.dumps(event.properties)
                    lines.append(
                        f"{event.timestamp.isoformat()},"
                        f"{event.event_type},"
                        f"{event.session_id or ''},"
                        f"{event.lead_id or ''},"
                        f'"{props}"'
                    )
                return "\n".join(lines)


# Singleton instance
_analytics_tracker: AnalyticsTracker | None = None


def get_analytics_tracker() -> AnalyticsTracker:
    """Get singleton analytics tracker instance."""
    global _analytics_tracker
    if _analytics_tracker is None:
        _analytics_tracker = AnalyticsTracker()
    return _analytics_tracker
