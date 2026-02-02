"""
Property view/query tracking for dynamic HOT badge.

Tracks how often properties are shown/queried to determine popularity.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from collections import defaultdict

from app.utils import get_logger

logger = get_logger(__name__)

# Storage file for tracking data
TRACKING_FILE = Path("data/property_tracking.json")

# Time window for HOT calculation (7 days)
HOT_WINDOW_DAYS = 7

# Minimum views to be considered HOT (relative to average)
HOT_THRESHOLD_MULTIPLIER = 2.0


class PropertyTracker:
    """
    Tracks property views/queries for popularity-based HOT badge.

    Features:
    - Track each time a property is shown
    - Calculate rolling view counts
    - Determine HOT properties based on relative popularity
    """

    def __init__(self, tracking_file: Path = TRACKING_FILE):
        self.tracking_file = tracking_file
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load_data()

    def _load_data(self) -> dict:
        """Load tracking data from file."""
        if self.tracking_file.exists():
            try:
                with open(self.tracking_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading tracking data: {e}")
        return {"views": {}, "queries": {}}

    def _save_data(self):
        """Save tracking data to file."""
        try:
            with open(self.tracking_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving tracking data: {e}")

    def track_view(self, property_id: int):
        """Track a property being shown to a user."""
        pid = str(property_id)
        timestamp = datetime.now().isoformat()

        if pid not in self._data["views"]:
            self._data["views"][pid] = []

        self._data["views"][pid].append(timestamp)
        self._save_data()

    def track_query(self, property_id: int, query: str):
        """Track a property being queried/searched."""
        pid = str(property_id)
        timestamp = datetime.now().isoformat()

        if pid not in self._data["queries"]:
            self._data["queries"][pid] = []

        self._data["queries"][pid].append({
            "timestamp": timestamp,
            "query": query[:100]  # Truncate long queries
        })
        self._save_data()

    def get_view_count(self, property_id: int, days: int = HOT_WINDOW_DAYS) -> int:
        """Get view count for a property within the time window."""
        pid = str(property_id)
        if pid not in self._data["views"]:
            return 0

        cutoff = datetime.now() - timedelta(days=days)
        count = 0

        for ts in self._data["views"][pid]:
            try:
                view_time = datetime.fromisoformat(ts)
                if view_time > cutoff:
                    count += 1
            except ValueError:
                continue

        return count

    def get_hot_properties(self, property_type: Optional[str] = None) -> list[int]:
        """
        Get list of HOT property IDs based on relative popularity.

        A property is HOT if its view count is significantly above average.
        """
        # Calculate view counts for all properties
        view_counts: dict[int, int] = {}

        for pid in self._data["views"]:
            count = self.get_view_count(int(pid))
            if count > 0:
                view_counts[int(pid)] = count

        if not view_counts:
            return []

        # Calculate average and threshold
        avg_views = sum(view_counts.values()) / len(view_counts)
        hot_threshold = avg_views * HOT_THRESHOLD_MULTIPLIER

        # Get HOT properties (above threshold, minimum 3 views)
        hot_ids = [
            pid for pid, count in view_counts.items()
            if count >= hot_threshold and count >= 3
        ]

        return hot_ids

    def is_hot(self, property_id: int) -> bool:
        """Check if a property is currently HOT."""
        return property_id in self.get_hot_properties()

    def get_popularity_score(self, property_id: int) -> int:
        """
        Get popularity score (0-100) based on view count.

        Normalized relative to the most viewed property.
        """
        view_count = self.get_view_count(property_id)

        if view_count == 0:
            return 0

        # Get max views across all properties
        max_views = max(
            self.get_view_count(int(pid))
            for pid in self._data["views"]
        ) or 1

        # Normalize to 0-100
        return min(100, int((view_count / max_views) * 100))

    def get_analytics(self) -> dict:
        """Get overall analytics summary."""
        total_views = sum(
            len(views) for views in self._data["views"].values()
        )

        # Views in last 24h
        cutoff_24h = datetime.now() - timedelta(hours=24)
        views_24h = 0
        for views in self._data["views"].values():
            for ts in views:
                try:
                    if datetime.fromisoformat(ts) > cutoff_24h:
                        views_24h += 1
                except ValueError:
                    continue

        # Top properties
        property_views = {
            int(pid): self.get_view_count(int(pid))
            for pid in self._data["views"]
        }
        top_properties = sorted(
            property_views.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            "total_views": total_views,
            "views_24h": views_24h,
            "unique_properties_viewed": len(self._data["views"]),
            "hot_properties": self.get_hot_properties(),
            "top_properties": top_properties,
        }

    def cleanup_old_data(self, days: int = 30):
        """Remove tracking data older than specified days."""
        cutoff = datetime.now() - timedelta(days=days)

        for pid in list(self._data["views"].keys()):
            self._data["views"][pid] = [
                ts for ts in self._data["views"][pid]
                if datetime.fromisoformat(ts) > cutoff
            ]
            if not self._data["views"][pid]:
                del self._data["views"][pid]

        for pid in list(self._data["queries"].keys()):
            self._data["queries"][pid] = [
                q for q in self._data["queries"][pid]
                if datetime.fromisoformat(q["timestamp"]) > cutoff
            ]
            if not self._data["queries"][pid]:
                del self._data["queries"][pid]

        self._save_data()
        logger.info(f"Cleaned up tracking data older than {days} days")


# Singleton instance
_property_tracker: Optional[PropertyTracker] = None


def get_property_tracker() -> PropertyTracker:
    """Get singleton PropertyTracker instance."""
    global _property_tracker
    if _property_tracker is None:
        _property_tracker = PropertyTracker()
    return _property_tracker
