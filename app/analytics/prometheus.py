"""
Prometheus Metrics Module.

Provides Prometheus-compatible metrics export for monitoring.
"""

import time
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict
import threading

from app.utils import get_logger

logger = get_logger(__name__)


@dataclass
class Counter:
    """Prometheus-style counter metric."""
    name: str
    help: str
    value: float = 0
    labels: dict = field(default_factory=dict)

    def inc(self, value: float = 1) -> None:
        self.value += value

    def get(self) -> float:
        return self.value


@dataclass
class Gauge:
    """Prometheus-style gauge metric."""
    name: str
    help: str
    value: float = 0

    def set(self, value: float) -> None:
        self.value = value

    def inc(self, value: float = 1) -> None:
        self.value += value

    def dec(self, value: float = 1) -> None:
        self.value -= value

    def get(self) -> float:
        return self.value


@dataclass
class Histogram:
    """Prometheus-style histogram metric."""
    name: str
    help: str
    buckets: list = field(default_factory=lambda: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10])
    observations: list = field(default_factory=list)
    bucket_counts: dict = field(default_factory=dict)
    sum: float = 0
    count: int = 0

    def __post_init__(self):
        self.bucket_counts = {b: 0 for b in self.buckets}
        self.bucket_counts[float('inf')] = 0

    def observe(self, value: float) -> None:
        self.observations.append(value)
        self.sum += value
        self.count += 1

        for bucket in self.buckets:
            if value <= bucket:
                self.bucket_counts[bucket] += 1
        self.bucket_counts[float('inf')] += 1

    def get_percentile(self, p: float) -> float:
        if not self.observations:
            return 0
        sorted_obs = sorted(self.observations)
        idx = int(len(sorted_obs) * p / 100)
        return sorted_obs[min(idx, len(sorted_obs) - 1)]


class PrometheusMetrics:
    """
    Prometheus-compatible metrics collector.

    Features:
    - Counters, Gauges, Histograms
    - Labels support
    - Thread-safe operations
    - Prometheus text format export
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = datetime.utcnow()

        # Pre-defined metrics
        self._counters: dict[str, dict[str, Counter]] = defaultdict(dict)
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}

        # Initialize standard metrics
        self._init_standard_metrics()

        logger.info("Prometheus metrics initialized")

    def _init_standard_metrics(self) -> None:
        """Initialize standard application metrics."""
        # Request counters
        self.register_counter(
            "requests_total",
            "Total number of requests",
        )
        self.register_counter(
            "requests_errors_total",
            "Total number of request errors",
        )

        # LLM metrics
        self.register_counter(
            "llm_calls_total",
            "Total number of LLM API calls",
        )
        self.register_counter(
            "llm_tokens_total",
            "Total tokens used in LLM calls",
        )
        self.register_counter(
            "llm_errors_total",
            "Total number of LLM API errors",
        )

        # Lead metrics
        self.register_counter(
            "leads_created_total",
            "Total number of leads created",
        )
        self.register_counter(
            "leads_qualified_total",
            "Total number of qualified leads",
        )
        self.register_counter(
            "leads_converted_total",
            "Total number of converted leads",
        )

        # Search metrics
        self.register_counter(
            "searches_total",
            "Total number of property searches",
        )
        self.register_counter(
            "search_no_results_total",
            "Total number of searches with no results",
        )

        # Cache metrics
        self.register_counter(
            "cache_hits_total",
            "Total number of cache hits",
        )
        self.register_counter(
            "cache_misses_total",
            "Total number of cache misses",
        )

        # Gauges
        self.register_gauge(
            "active_sessions",
            "Number of active sessions",
        )
        self.register_gauge(
            "active_conversations",
            "Number of active conversations",
        )

        # Histograms
        self.register_histogram(
            "request_duration_seconds",
            "Request duration in seconds",
            buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10],
        )
        self.register_histogram(
            "llm_response_time_seconds",
            "LLM API response time in seconds",
            buckets=[0.5, 1, 2, 3, 5, 10, 30],
        )
        self.register_histogram(
            "search_duration_seconds",
            "Property search duration in seconds",
            buckets=[0.05, 0.1, 0.25, 0.5, 1, 2],
        )

    def register_counter(self, name: str, help: str) -> None:
        """Register a new counter metric."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = {}

    def register_gauge(self, name: str, help: str) -> None:
        """Register a new gauge metric."""
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name=name, help=help)

    def register_histogram(
        self,
        name: str,
        help: str,
        buckets: Optional[list] = None,
    ) -> None:
        """Register a new histogram metric."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(
                    name=name,
                    help=help,
                    buckets=buckets or [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
                )

    def counter_inc(self, name: str, value: float = 1, labels: Optional[dict] = None) -> None:
        """Increment a counter."""
        with self._lock:
            label_key = self._labels_to_key(labels)
            if name in self._counters:
                if label_key not in self._counters[name]:
                    self._counters[name][label_key] = Counter(
                        name=name,
                        help="",
                        labels=labels or {},
                    )
                self._counters[name][label_key].inc(value)

    def gauge_set(self, name: str, value: float) -> None:
        """Set a gauge value."""
        with self._lock:
            if name in self._gauges:
                self._gauges[name].set(value)

    def gauge_inc(self, name: str, value: float = 1) -> None:
        """Increment a gauge."""
        with self._lock:
            if name in self._gauges:
                self._gauges[name].inc(value)

    def gauge_dec(self, name: str, value: float = 1) -> None:
        """Decrement a gauge."""
        with self._lock:
            if name in self._gauges:
                self._gauges[name].dec(value)

    def histogram_observe(self, name: str, value: float) -> None:
        """Record a histogram observation."""
        with self._lock:
            if name in self._histograms:
                self._histograms[name].observe(value)

    def _labels_to_key(self, labels: Optional[dict]) -> str:
        """Convert labels dict to string key."""
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))

    def _format_labels(self, labels: Optional[dict]) -> str:
        """Format labels for Prometheus output."""
        if not labels:
            return ""
        return "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items())) + "}"

    def export_metrics(self) -> str:
        """
        Export metrics in Prometheus text format.

        Returns:
            Prometheus-compatible metrics string
        """
        with self._lock:
            lines = []

            # Process info
            uptime = (datetime.utcnow() - self._start_time).total_seconds()
            lines.append("# HELP prochazka_uptime_seconds Time since application start")
            lines.append("# TYPE prochazka_uptime_seconds gauge")
            lines.append(f"prochazka_uptime_seconds {uptime:.2f}")
            lines.append("")

            # Counters
            for name, label_counters in self._counters.items():
                if label_counters:
                    first_counter = next(iter(label_counters.values()))
                    lines.append(f"# HELP prochazka_{name} {first_counter.help or name}")
                    lines.append(f"# TYPE prochazka_{name} counter")
                    for label_key, counter in label_counters.items():
                        labels = self._format_labels(counter.labels)
                        lines.append(f"prochazka_{name}{labels} {counter.value}")
                    lines.append("")

            # Gauges
            for name, gauge in self._gauges.items():
                lines.append(f"# HELP prochazka_{name} {gauge.help}")
                lines.append(f"# TYPE prochazka_{name} gauge")
                lines.append(f"prochazka_{name} {gauge.value}")
                lines.append("")

            # Histograms
            for name, hist in self._histograms.items():
                lines.append(f"# HELP prochazka_{name} {hist.help}")
                lines.append(f"# TYPE prochazka_{name} histogram")

                # Bucket counts
                cumulative = 0
                for bucket in sorted(hist.buckets):
                    cumulative += hist.bucket_counts.get(bucket, 0)
                    lines.append(f'prochazka_{name}_bucket{{le="{bucket}"}} {cumulative}')
                lines.append(f'prochazka_{name}_bucket{{le="+Inf"}} {hist.count}')

                # Sum and count
                lines.append(f"prochazka_{name}_sum {hist.sum:.6f}")
                lines.append(f"prochazka_{name}_count {hist.count}")
                lines.append("")

            return "\n".join(lines)

    def get_summary(self) -> dict:
        """Get metrics summary as dictionary."""
        with self._lock:
            summary = {
                "uptime_seconds": (datetime.utcnow() - self._start_time).total_seconds(),
                "counters": {},
                "gauges": {},
                "histograms": {},
            }

            for name, label_counters in self._counters.items():
                total = sum(c.value for c in label_counters.values())
                summary["counters"][name] = total

            for name, gauge in self._gauges.items():
                summary["gauges"][name] = gauge.value

            for name, hist in self._histograms.items():
                summary["histograms"][name] = {
                    "count": hist.count,
                    "sum": hist.sum,
                    "avg": hist.sum / hist.count if hist.count > 0 else 0,
                    "p50": hist.get_percentile(50),
                    "p95": hist.get_percentile(95),
                    "p99": hist.get_percentile(99),
                }

            return summary

    def timer(self, histogram_name: str):
        """Context manager for timing operations."""
        return MetricsTimer(self, histogram_name)


class MetricsTimer:
    """Context manager for timing operations and recording to histogram."""

    def __init__(self, metrics: PrometheusMetrics, histogram_name: str):
        self.metrics = metrics
        self.histogram_name = histogram_name
        self.start_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.perf_counter() - self.start_time
            self.metrics.histogram_observe(self.histogram_name, duration)
        return False


# Singleton instance
_prometheus_metrics: PrometheusMetrics | None = None


def get_prometheus_metrics() -> PrometheusMetrics:
    """Get singleton Prometheus metrics instance."""
    global _prometheus_metrics
    if _prometheus_metrics is None:
        _prometheus_metrics = PrometheusMetrics()
    return _prometheus_metrics


# Convenience functions
def inc_counter(name: str, value: float = 1, **labels) -> None:
    """Increment a counter metric."""
    get_prometheus_metrics().counter_inc(name, value, labels if labels else None)


def set_gauge(name: str, value: float) -> None:
    """Set a gauge metric."""
    get_prometheus_metrics().gauge_set(name, value)


def observe_histogram(name: str, value: float) -> None:
    """Record a histogram observation."""
    get_prometheus_metrics().histogram_observe(name, value)


def get_metrics_text() -> str:
    """Get metrics in Prometheus text format."""
    return get_prometheus_metrics().export_metrics()
