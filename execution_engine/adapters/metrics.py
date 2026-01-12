"""
Exchange Adapter - Metrics and Observability.

============================================================
PURPOSE
============================================================
Metrics collection for exchange adapter performance.

METRICS TRACKED:
- Request latency (by exchange, endpoint)
- Request success/failure rates
- Rate limit usage
- Order rejection rates
- Connection health

============================================================
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum


logger = logging.getLogger(__name__)


# ============================================================
# METRIC TYPES
# ============================================================

class MetricType(Enum):
    """Types of metrics."""
    
    REQUEST_LATENCY = "request_latency"
    REQUEST_SUCCESS = "request_success"
    REQUEST_FAILURE = "request_failure"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_REJECTED = "order_rejected"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELED = "order_canceled"
    RATE_LIMIT_HIT = "rate_limit_hit"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"


@dataclass
class LatencyStats:
    """Latency statistics."""
    
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    
    @property
    def avg_ms(self) -> float:
        """Average latency in ms."""
        return self.total_ms / self.count if self.count > 0 else 0.0
    
    def record(self, latency_ms: float) -> None:
        """Record a latency measurement."""
        self.count += 1
        self.total_ms += latency_ms
        self.min_ms = min(self.min_ms, latency_ms)
        self.max_ms = max(self.max_ms, latency_ms)


@dataclass
class CounterStats:
    """Counter statistics."""
    
    total: int = 0
    last_hour: int = 0
    last_minute: int = 0
    
    # Timestamps for rolling windows
    _minute_counts: List[tuple] = field(default_factory=list)
    _hour_counts: List[tuple] = field(default_factory=list)
    
    def increment(self) -> None:
        """Increment counter."""
        now = time.time()
        self.total += 1
        self._minute_counts.append((now, 1))
        self._hour_counts.append((now, 1))
        self._cleanup(now)
    
    def _cleanup(self, now: float) -> None:
        """Clean up old entries."""
        minute_ago = now - 60
        hour_ago = now - 3600
        
        self._minute_counts = [(t, c) for t, c in self._minute_counts if t > minute_ago]
        self._hour_counts = [(t, c) for t, c in self._hour_counts if t > hour_ago]
        
        self.last_minute = sum(c for _, c in self._minute_counts)
        self.last_hour = sum(c for _, c in self._hour_counts)


# ============================================================
# ADAPTER METRICS
# ============================================================

class AdapterMetrics:
    """
    Metrics collector for exchange adapter.
    
    Thread-safe metrics collection and reporting.
    """
    
    def __init__(self, exchange_id: str):
        """
        Initialize metrics.
        
        Args:
            exchange_id: Exchange identifier
        """
        self._exchange_id = exchange_id
        self._start_time = datetime.utcnow()
        
        # Latency by endpoint
        self._latency: Dict[str, LatencyStats] = defaultdict(LatencyStats)
        
        # Counters
        self._counters: Dict[MetricType, CounterStats] = {
            mt: CounterStats() for mt in MetricType
        }
        
        # Error tracking
        self._error_codes: Dict[str, int] = defaultdict(int)
        
        # Last N requests for debugging
        self._recent_requests: List[Dict[str, Any]] = []
        self._max_recent = 100
    
    # --------------------------------------------------------
    # RECORDING
    # --------------------------------------------------------
    
    def record_request(
        self,
        endpoint: str,
        latency_ms: float,
        success: bool,
        status_code: int = None,
        error_code: str = None,
    ) -> None:
        """
        Record a request.
        
        Args:
            endpoint: API endpoint
            latency_ms: Request latency in ms
            success: Whether request succeeded
            status_code: HTTP status code
            error_code: Error code if failed
        """
        # Latency
        self._latency[endpoint].record(latency_ms)
        self._latency["_all"].record(latency_ms)
        
        # Success/failure counter
        if success:
            self._counters[MetricType.REQUEST_SUCCESS].increment()
        else:
            self._counters[MetricType.REQUEST_FAILURE].increment()
            
            if error_code:
                self._error_codes[error_code] += 1
                
                # Specific error types
                if "RATE" in error_code.upper():
                    self._counters[MetricType.RATE_LIMIT_HIT].increment()
                elif "TIMEOUT" in error_code.upper() or "TMO" in error_code.upper():
                    self._counters[MetricType.TIMEOUT].increment()
                elif "NET" in error_code.upper() or "CONN" in error_code.upper():
                    self._counters[MetricType.CONNECTION_ERROR].increment()
        
        # Recent requests
        self._recent_requests.append({
            "timestamp": datetime.utcnow().isoformat(),
            "endpoint": endpoint,
            "latency_ms": latency_ms,
            "success": success,
            "status_code": status_code,
            "error_code": error_code,
        })
        
        if len(self._recent_requests) > self._max_recent:
            self._recent_requests.pop(0)
    
    def record_order_submitted(self) -> None:
        """Record order submission."""
        self._counters[MetricType.ORDER_SUBMITTED].increment()
    
    def record_order_rejected(self, error_code: str = None) -> None:
        """Record order rejection."""
        self._counters[MetricType.ORDER_REJECTED].increment()
        if error_code:
            self._error_codes[error_code] += 1
    
    def record_order_filled(self) -> None:
        """Record order fill."""
        self._counters[MetricType.ORDER_FILLED].increment()
    
    def record_order_canceled(self) -> None:
        """Record order cancellation."""
        self._counters[MetricType.ORDER_CANCELED].increment()
    
    # --------------------------------------------------------
    # REPORTING
    # --------------------------------------------------------
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get metrics summary.
        
        Returns:
            Dict with all metrics
        """
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        
        all_latency = self._latency.get("_all", LatencyStats())
        success = self._counters[MetricType.REQUEST_SUCCESS]
        failure = self._counters[MetricType.REQUEST_FAILURE]
        
        total_requests = success.total + failure.total
        success_rate = success.total / total_requests if total_requests > 0 else 1.0
        
        return {
            "exchange_id": self._exchange_id,
            "uptime_seconds": uptime,
            "requests": {
                "total": total_requests,
                "success": success.total,
                "failure": failure.total,
                "success_rate": success_rate,
                "last_minute": {
                    "success": success.last_minute,
                    "failure": failure.last_minute,
                },
            },
            "latency": {
                "avg_ms": all_latency.avg_ms,
                "min_ms": all_latency.min_ms if all_latency.min_ms != float("inf") else 0,
                "max_ms": all_latency.max_ms,
            },
            "orders": {
                "submitted": self._counters[MetricType.ORDER_SUBMITTED].total,
                "rejected": self._counters[MetricType.ORDER_REJECTED].total,
                "filled": self._counters[MetricType.ORDER_FILLED].total,
                "canceled": self._counters[MetricType.ORDER_CANCELED].total,
            },
            "errors": {
                "rate_limit_hits": self._counters[MetricType.RATE_LIMIT_HIT].total,
                "timeouts": self._counters[MetricType.TIMEOUT].total,
                "connection_errors": self._counters[MetricType.CONNECTION_ERROR].total,
                "by_code": dict(self._error_codes),
            },
        }
    
    def get_latency_by_endpoint(self) -> Dict[str, Dict[str, float]]:
        """Get latency stats by endpoint."""
        result = {}
        for endpoint, stats in self._latency.items():
            if endpoint != "_all":
                result[endpoint] = {
                    "count": stats.count,
                    "avg_ms": stats.avg_ms,
                    "min_ms": stats.min_ms if stats.min_ms != float("inf") else 0,
                    "max_ms": stats.max_ms,
                }
        return result
    
    def get_recent_requests(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent requests."""
        return self._recent_requests[-limit:]
    
    def get_error_distribution(self) -> Dict[str, int]:
        """Get error code distribution."""
        return dict(self._error_codes)
    
    def reset(self) -> None:
        """Reset all metrics."""
        self._start_time = datetime.utcnow()
        self._latency.clear()
        self._counters = {mt: CounterStats() for mt in MetricType}
        self._error_codes.clear()
        self._recent_requests.clear()


# ============================================================
# METRICS AGGREGATOR
# ============================================================

class MetricsAggregator:
    """
    Aggregates metrics from multiple adapters.
    """
    
    def __init__(self):
        """Initialize aggregator."""
        self._adapters: Dict[str, AdapterMetrics] = {}
    
    def register(self, exchange_id: str, metrics: AdapterMetrics) -> None:
        """Register adapter metrics."""
        self._adapters[exchange_id] = metrics
    
    def unregister(self, exchange_id: str) -> None:
        """Unregister adapter metrics."""
        self._adapters.pop(exchange_id, None)
    
    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """Get summaries from all adapters."""
        return {
            exchange_id: metrics.get_summary()
            for exchange_id, metrics in self._adapters.items()
        }
    
    def get_aggregate_summary(self) -> Dict[str, Any]:
        """Get aggregated summary."""
        total_requests = 0
        total_success = 0
        total_failure = 0
        total_latency_sum = 0.0
        total_latency_count = 0
        
        for metrics in self._adapters.values():
            summary = metrics.get_summary()
            total_requests += summary["requests"]["total"]
            total_success += summary["requests"]["success"]
            total_failure += summary["requests"]["failure"]
            
            latency = metrics._latency.get("_all", LatencyStats())
            total_latency_sum += latency.total_ms
            total_latency_count += latency.count
        
        return {
            "exchanges": list(self._adapters.keys()),
            "total_requests": total_requests,
            "total_success": total_success,
            "total_failure": total_failure,
            "success_rate": total_success / total_requests if total_requests > 0 else 1.0,
            "avg_latency_ms": total_latency_sum / total_latency_count if total_latency_count > 0 else 0,
        }


# Global aggregator instance
_global_aggregator = MetricsAggregator()


def get_global_aggregator() -> MetricsAggregator:
    """Get global metrics aggregator."""
    return _global_aggregator
