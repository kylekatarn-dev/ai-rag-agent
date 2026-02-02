"""
Quality metrics and analytics for AI agent monitoring.

Features:
- Track conversation quality
- Detect potential issues (hallucinations, repeated questions)
- Aggregate metrics for admin dashboard
- Support continuous improvement
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from app.utils import get_logger

logger = get_logger(__name__)

# Storage for metrics
METRICS_FILE = Path("data/agent_metrics.json")


@dataclass
class ConversationMetrics:
    """Metrics for a single conversation."""
    session_id: str
    timestamp: str
    message_count: int
    user_messages: int
    assistant_messages: int
    tool_calls: int
    properties_shown: int
    lead_score: int
    lead_converted: bool
    quality_issues: list[str]
    response_times_ms: list[int]
    avg_response_time_ms: float


class QualityMetrics:
    """
    Tracks and aggregates quality metrics for the AI agent.

    Metrics tracked:
    - Response times
    - Conversation length
    - Lead conversion rate
    - Quality issues (repeated questions, hallucinations)
    - Property match quality
    """

    def __init__(self, metrics_file: Path = METRICS_FILE):
        self.metrics_file = metrics_file
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load_data()

    def _load_data(self) -> dict:
        """Load metrics data from file."""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading metrics: {e}")
        return {
            "conversations": [],
            "daily_stats": {},
            "quality_issues": [],
        }

    def _save_data(self):
        """Save metrics data to file."""
        try:
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving metrics: {e}")

    def record_conversation(self, metrics: ConversationMetrics):
        """Record metrics for a completed conversation."""
        self._data["conversations"].append(asdict(metrics))

        # Update daily stats
        date_key = datetime.now().strftime("%Y-%m-%d")
        if date_key not in self._data["daily_stats"]:
            self._data["daily_stats"][date_key] = {
                "total_conversations": 0,
                "total_messages": 0,
                "leads_converted": 0,
                "quality_issues": 0,
                "avg_lead_score": 0,
                "total_lead_score": 0,
            }

        stats = self._data["daily_stats"][date_key]
        stats["total_conversations"] += 1
        stats["total_messages"] += metrics.message_count
        stats["leads_converted"] += 1 if metrics.lead_converted else 0
        stats["quality_issues"] += len(metrics.quality_issues)
        stats["total_lead_score"] += metrics.lead_score
        stats["avg_lead_score"] = (
            stats["total_lead_score"] / stats["total_conversations"]
        )

        # Track quality issues
        for issue in metrics.quality_issues:
            self._data["quality_issues"].append({
                "session_id": metrics.session_id,
                "timestamp": metrics.timestamp,
                "issue": issue,
            })

        self._save_data()

    def get_dashboard_stats(self, days: int = 7) -> dict:
        """Get aggregated stats for admin dashboard."""
        cutoff = datetime.now() - timedelta(days=days)

        # Filter recent conversations
        recent = [
            c for c in self._data["conversations"]
            if datetime.fromisoformat(c["timestamp"]) > cutoff
        ]

        if not recent:
            return {
                "period_days": days,
                "total_conversations": 0,
                "avg_messages_per_conversation": 0,
                "lead_conversion_rate": 0,
                "avg_lead_score": 0,
                "quality_issue_rate": 0,
                "avg_response_time_ms": 0,
                "top_issues": [],
            }

        # Calculate aggregates
        total_convs = len(recent)
        total_messages = sum(c["message_count"] for c in recent)
        converted = sum(1 for c in recent if c["lead_converted"])
        total_score = sum(c["lead_score"] for c in recent)
        total_issues = sum(len(c["quality_issues"]) for c in recent)

        # Response times
        all_times = []
        for c in recent:
            all_times.extend(c.get("response_times_ms", []))
        avg_response = sum(all_times) / len(all_times) if all_times else 0

        # Top issues
        issue_counts: dict[str, int] = {}
        for c in recent:
            for issue in c["quality_issues"]:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1
        top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "period_days": days,
            "total_conversations": total_convs,
            "avg_messages_per_conversation": total_messages / total_convs,
            "lead_conversion_rate": converted / total_convs * 100,
            "avg_lead_score": total_score / total_convs,
            "quality_issue_rate": total_issues / total_convs * 100,
            "avg_response_time_ms": avg_response,
            "top_issues": top_issues,
        }

    def get_quality_report(self) -> str:
        """Generate a quality report for admin review."""
        stats = self.get_dashboard_stats(7)

        report = f"""
# AI Agent Quality Report
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Last 7 Days Summary

- **Total Conversations:** {stats['total_conversations']}
- **Avg Messages/Conversation:** {stats['avg_messages_per_conversation']:.1f}
- **Lead Conversion Rate:** {stats['lead_conversion_rate']:.1f}%
- **Avg Lead Score:** {stats['avg_lead_score']:.0f}/100
- **Quality Issue Rate:** {stats['quality_issue_rate']:.1f}%
- **Avg Response Time:** {stats['avg_response_time_ms']:.0f}ms

## Top Quality Issues
"""
        for issue, count in stats["top_issues"]:
            report += f"- {issue}: {count} occurrences\n"

        if not stats["top_issues"]:
            report += "- No issues detected\n"

        report += """
## Recommendations

"""
        if stats["quality_issue_rate"] > 20:
            report += "- HIGH: Quality issues in >20% of conversations. Review prompts.\n"
        if stats["avg_lead_score"] < 40:
            report += "- MEDIUM: Low average lead score. Review conversation flow.\n"
        if stats["lead_conversion_rate"] < 10:
            report += "- LOW: Conversion rate below 10%. Analyze drop-off points.\n"

        return report

    def cleanup_old_data(self, days: int = 90):
        """Remove metrics older than specified days."""
        cutoff = datetime.now() - timedelta(days=days)

        self._data["conversations"] = [
            c for c in self._data["conversations"]
            if datetime.fromisoformat(c["timestamp"]) > cutoff
        ]

        self._data["quality_issues"] = [
            q for q in self._data["quality_issues"]
            if datetime.fromisoformat(q["timestamp"]) > cutoff
        ]

        # Keep daily stats for 1 year
        year_ago = datetime.now() - timedelta(days=365)
        self._data["daily_stats"] = {
            k: v for k, v in self._data["daily_stats"].items()
            if datetime.strptime(k, "%Y-%m-%d") > year_ago
        }

        self._save_data()


# Singleton instance
_quality_metrics: Optional[QualityMetrics] = None


def get_quality_metrics() -> QualityMetrics:
    """Get singleton QualityMetrics instance."""
    global _quality_metrics
    if _quality_metrics is None:
        _quality_metrics = QualityMetrics()
    return _quality_metrics
