"""
Data Source Health - Metrics Collector.

============================================================
RAW METRICS COLLECTION
============================================================

Collects raw metrics from data source operations:
- Request metrics (latency, success, errors)
- Data metrics (freshness, completeness)
- Consistency metrics (value changes, deviations)

These metrics are used by dimension scorers to calculate
health scores.

============================================================
THREAD SAFETY
============================================================

This module uses thread-safe data structures for concurrent
access from multiple data sources.

============================================================
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, List, Optional, Tuple
import logging


logger = logging.getLogger(__name__)


# =============================================================
# METRIC DATA POINTS
# =============================================================


@dataclass
class RequestMetric:
    """Single request metric data point."""
    timestamp: datetime
    latency_ms: float
    success: bool
    error_type: Optional[str] = None
    is_timeout: bool = False
    is_retry: bool = False
    retry_count: int = 0
    http_status: Optional[int] = None


@dataclass
class DataMetric:
    """Single data metric data point."""
    timestamp: datetime
    data_timestamp: datetime  # When the data was generated
    fields_expected: int
    fields_received: int
    is_empty: bool = False
    is_partial: bool = False
    data_size_bytes: int = 0


@dataclass
class ValueMetric:
    """Single value metric for consistency tracking."""
    timestamp: datetime
    value: float
    field_name: str
    source_name: str  # For cross-source comparison


@dataclass
class ErrorMetric:
    """Single error metric data point."""
    timestamp: datetime
    error_type: str
    error_message: str
    is_recoverable: bool = True


# =============================================================
# SOURCE METRICS CONTAINER
# =============================================================


@dataclass
class SourceMetrics:
    """
    Container for all metrics of a single source.
    
    Maintains rolling windows of metrics for health scoring.
    """
    source_name: str
    max_samples: int = 1000
    window_seconds: int = 300  # 5 minutes default
    
    # Request metrics
    requests: Deque[RequestMetric] = field(default_factory=lambda: deque(maxlen=1000))
    
    # Data metrics
    data_points: Deque[DataMetric] = field(default_factory=lambda: deque(maxlen=1000))
    
    # Value metrics for consistency
    values: Dict[str, Deque[ValueMetric]] = field(default_factory=dict)
    
    # Error metrics
    errors: Deque[ErrorMetric] = field(default_factory=lambda: deque(maxlen=500))
    
    # Timestamps
    first_metric_at: Optional[datetime] = None
    last_metric_at: Optional[datetime] = None
    
    # Thread safety
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    
    def __post_init__(self) -> None:
        """Initialize deques with max length."""
        self.requests = deque(maxlen=self.max_samples)
        self.data_points = deque(maxlen=self.max_samples)
        self.errors = deque(maxlen=self.max_samples // 2)
    
    # =========================================================
    # RECORD METHODS
    # =========================================================
    
    def record_request(
        self,
        latency_ms: float,
        success: bool,
        error_type: Optional[str] = None,
        is_timeout: bool = False,
        is_retry: bool = False,
        retry_count: int = 0,
        http_status: Optional[int] = None,
    ) -> None:
        """Record a request metric."""
        with self._lock:
            now = datetime.utcnow()
            metric = RequestMetric(
                timestamp=now,
                latency_ms=latency_ms,
                success=success,
                error_type=error_type,
                is_timeout=is_timeout,
                is_retry=is_retry,
                retry_count=retry_count,
                http_status=http_status,
            )
            self.requests.append(metric)
            self._update_timestamps(now)
    
    def record_data(
        self,
        data_timestamp: datetime,
        fields_expected: int,
        fields_received: int,
        is_empty: bool = False,
        is_partial: bool = False,
        data_size_bytes: int = 0,
    ) -> None:
        """Record a data metric."""
        with self._lock:
            now = datetime.utcnow()
            metric = DataMetric(
                timestamp=now,
                data_timestamp=data_timestamp,
                fields_expected=fields_expected,
                fields_received=fields_received,
                is_empty=is_empty,
                is_partial=is_partial,
                data_size_bytes=data_size_bytes,
            )
            self.data_points.append(metric)
            self._update_timestamps(now)
    
    def record_value(
        self,
        field_name: str,
        value: float,
    ) -> None:
        """Record a value for consistency tracking."""
        with self._lock:
            now = datetime.utcnow()
            metric = ValueMetric(
                timestamp=now,
                value=value,
                field_name=field_name,
                source_name=self.source_name,
            )
            if field_name not in self.values:
                self.values[field_name] = deque(maxlen=self.max_samples)
            self.values[field_name].append(metric)
            self._update_timestamps(now)
    
    def record_error(
        self,
        error_type: str,
        error_message: str,
        is_recoverable: bool = True,
    ) -> None:
        """Record an error."""
        with self._lock:
            now = datetime.utcnow()
            metric = ErrorMetric(
                timestamp=now,
                error_type=error_type,
                error_message=error_message,
                is_recoverable=is_recoverable,
            )
            self.errors.append(metric)
            self._update_timestamps(now)
    
    def _update_timestamps(self, now: datetime) -> None:
        """Update first/last metric timestamps."""
        if self.first_metric_at is None:
            self.first_metric_at = now
        self.last_metric_at = now
    
    # =========================================================
    # QUERY METHODS
    # =========================================================
    
    def get_requests_in_window(
        self,
        window_seconds: Optional[int] = None,
    ) -> List[RequestMetric]:
        """Get requests within time window."""
        window = window_seconds or self.window_seconds
        cutoff = datetime.utcnow() - timedelta(seconds=window)
        
        with self._lock:
            return [r for r in self.requests if r.timestamp >= cutoff]
    
    def get_data_points_in_window(
        self,
        window_seconds: Optional[int] = None,
    ) -> List[DataMetric]:
        """Get data points within time window."""
        window = window_seconds or self.window_seconds
        cutoff = datetime.utcnow() - timedelta(seconds=window)
        
        with self._lock:
            return [d for d in self.data_points if d.timestamp >= cutoff]
    
    def get_values_in_window(
        self,
        field_name: str,
        window_seconds: Optional[int] = None,
    ) -> List[ValueMetric]:
        """Get values for a field within time window."""
        window = window_seconds or self.window_seconds
        cutoff = datetime.utcnow() - timedelta(seconds=window)
        
        with self._lock:
            if field_name not in self.values:
                return []
            return [v for v in self.values[field_name] if v.timestamp >= cutoff]
    
    def get_errors_in_window(
        self,
        window_seconds: Optional[int] = None,
    ) -> List[ErrorMetric]:
        """Get errors within time window."""
        window = window_seconds or self.window_seconds
        cutoff = datetime.utcnow() - timedelta(seconds=window)
        
        with self._lock:
            return [e for e in self.errors if e.timestamp >= cutoff]
    
    # =========================================================
    # COMPUTED METRICS
    # =========================================================
    
    def get_availability_metrics(
        self,
        window_seconds: Optional[int] = None,
    ) -> Dict[str, float]:
        """
        Calculate availability metrics.
        
        Returns:
            uptime_percent: Percentage of successful requests
            timeout_percent: Percentage of timeout requests
            retry_success_rate: Percentage of successful retries
            avg_latency_ms: Average request latency
        """
        requests = self.get_requests_in_window(window_seconds)
        
        if not requests:
            return {
                "uptime_percent": 100.0,  # Assume healthy if no data
                "timeout_percent": 0.0,
                "retry_success_rate": 100.0,
                "avg_latency_ms": 0.0,
                "sample_count": 0,
            }
        
        total = len(requests)
        successful = sum(1 for r in requests if r.success)
        timeouts = sum(1 for r in requests if r.is_timeout)
        retries = [r for r in requests if r.is_retry]
        retry_successes = sum(1 for r in retries if r.success)
        total_latency = sum(r.latency_ms for r in requests)
        
        return {
            "uptime_percent": (successful / total) * 100 if total > 0 else 100.0,
            "timeout_percent": (timeouts / total) * 100 if total > 0 else 0.0,
            "retry_success_rate": (retry_successes / len(retries)) * 100 if retries else 100.0,
            "avg_latency_ms": total_latency / total if total > 0 else 0.0,
            "sample_count": total,
        }
    
    def get_freshness_metrics(
        self,
        window_seconds: Optional[int] = None,
    ) -> Dict[str, float]:
        """
        Calculate freshness metrics.
        
        Returns:
            avg_delay_seconds: Average data delay
            max_delay_seconds: Maximum data delay
            stale_percent: Percentage of stale data points
            timestamp_drift_seconds: Average timestamp drift
        """
        data_points = self.get_data_points_in_window(window_seconds)
        
        if not data_points:
            return {
                "avg_delay_seconds": 0.0,
                "max_delay_seconds": 0.0,
                "stale_percent": 0.0,
                "timestamp_drift_seconds": 0.0,
                "sample_count": 0,
            }
        
        delays = []
        stale_threshold = 60  # 60 seconds = stale
        
        for dp in data_points:
            delay = (dp.timestamp - dp.data_timestamp).total_seconds()
            delays.append(abs(delay))
        
        stale_count = sum(1 for d in delays if d > stale_threshold)
        
        return {
            "avg_delay_seconds": sum(delays) / len(delays) if delays else 0.0,
            "max_delay_seconds": max(delays) if delays else 0.0,
            "stale_percent": (stale_count / len(delays)) * 100 if delays else 0.0,
            "timestamp_drift_seconds": sum(delays) / len(delays) if delays else 0.0,
            "sample_count": len(data_points),
        }
    
    def get_completeness_metrics(
        self,
        window_seconds: Optional[int] = None,
    ) -> Dict[str, float]:
        """
        Calculate completeness metrics.
        
        Returns:
            missing_fields_percent: Percentage of missing fields
            partial_record_percent: Percentage of partial records
            empty_response_percent: Percentage of empty responses
        """
        data_points = self.get_data_points_in_window(window_seconds)
        
        if not data_points:
            return {
                "missing_fields_percent": 0.0,
                "partial_record_percent": 0.0,
                "empty_response_percent": 0.0,
                "sample_count": 0,
            }
        
        total = len(data_points)
        
        # Calculate missing fields
        total_expected = sum(dp.fields_expected for dp in data_points)
        total_received = sum(dp.fields_received for dp in data_points)
        missing_percent = ((total_expected - total_received) / total_expected) * 100 if total_expected > 0 else 0.0
        
        # Count partial and empty
        partial_count = sum(1 for dp in data_points if dp.is_partial)
        empty_count = sum(1 for dp in data_points if dp.is_empty)
        
        return {
            "missing_fields_percent": missing_percent,
            "partial_record_percent": (partial_count / total) * 100 if total > 0 else 0.0,
            "empty_response_percent": (empty_count / total) * 100 if total > 0 else 0.0,
            "sample_count": total,
        }
    
    def get_consistency_metrics(
        self,
        field_name: str,
        window_seconds: Optional[int] = None,
    ) -> Dict[str, float]:
        """
        Calculate consistency metrics for a field.
        
        Returns:
            value_change_percent: Average percentage change between values
            max_jump_percent: Maximum percentage jump
            std_deviation: Standard deviation of values
        """
        values = self.get_values_in_window(field_name, window_seconds)
        
        if len(values) < 2:
            return {
                "value_change_percent": 0.0,
                "max_jump_percent": 0.0,
                "std_deviation": 0.0,
                "sample_count": len(values),
            }
        
        # Calculate changes
        sorted_values = sorted(values, key=lambda v: v.timestamp)
        changes = []
        
        for i in range(1, len(sorted_values)):
            prev_val = sorted_values[i-1].value
            curr_val = sorted_values[i].value
            if prev_val != 0:
                change_pct = abs((curr_val - prev_val) / prev_val) * 100
                changes.append(change_pct)
        
        # Calculate std deviation
        if values:
            mean_val = sum(v.value for v in values) / len(values)
            variance = sum((v.value - mean_val) ** 2 for v in values) / len(values)
            std_dev = variance ** 0.5
        else:
            std_dev = 0.0
        
        return {
            "value_change_percent": sum(changes) / len(changes) if changes else 0.0,
            "max_jump_percent": max(changes) if changes else 0.0,
            "std_deviation": std_dev,
            "sample_count": len(values),
        }
    
    def get_error_rate_metrics(
        self,
        window_seconds: Optional[int] = None,
    ) -> Dict[str, float]:
        """
        Calculate error rate metrics.
        
        Returns:
            error_rate_percent: Percentage of requests with errors
            http_error_rate: HTTP error rate
            parse_error_rate: Parsing error rate
            validation_error_rate: Validation error rate
        """
        requests = self.get_requests_in_window(window_seconds)
        errors = self.get_errors_in_window(window_seconds)
        
        total_requests = len(requests)
        total_errors = len(errors)
        
        if total_requests == 0:
            return {
                "error_rate_percent": 0.0,
                "http_error_rate": 0.0,
                "parse_error_rate": 0.0,
                "validation_error_rate": 0.0,
                "recoverable_error_rate": 0.0,
                "sample_count": 0,
            }
        
        # Count error types
        http_errors = sum(1 for e in errors if "http" in e.error_type.lower())
        parse_errors = sum(1 for e in errors if "parse" in e.error_type.lower())
        validation_errors = sum(1 for e in errors if "validation" in e.error_type.lower())
        recoverable_errors = sum(1 for e in errors if e.is_recoverable)
        
        return {
            "error_rate_percent": (total_errors / total_requests) * 100,
            "http_error_rate": (http_errors / total_requests) * 100,
            "parse_error_rate": (parse_errors / total_requests) * 100,
            "validation_error_rate": (validation_errors / total_requests) * 100,
            "recoverable_error_rate": (recoverable_errors / total_errors) * 100 if total_errors > 0 else 100.0,
            "sample_count": total_requests,
        }
    
    # =========================================================
    # UTILITY METHODS
    # =========================================================
    
    def get_total_sample_count(self) -> int:
        """Get total number of samples."""
        with self._lock:
            return len(self.requests) + len(self.data_points)
    
    def clear(self) -> None:
        """Clear all metrics."""
        with self._lock:
            self.requests.clear()
            self.data_points.clear()
            self.values.clear()
            self.errors.clear()
            self.first_metric_at = None
            self.last_metric_at = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "source_name": self.source_name,
            "total_requests": len(self.requests),
            "total_data_points": len(self.data_points),
            "total_errors": len(self.errors),
            "tracked_fields": list(self.values.keys()),
            "first_metric_at": self.first_metric_at.isoformat() if self.first_metric_at else None,
            "last_metric_at": self.last_metric_at.isoformat() if self.last_metric_at else None,
        }


# =============================================================
# METRICS COLLECTOR
# =============================================================


class MetricsCollector:
    """
    Central collector for all source metrics.
    
    Thread-safe storage and retrieval of metrics for all data sources.
    """
    
    def __init__(
        self,
        max_samples: int = 1000,
        window_seconds: int = 300,
    ) -> None:
        """
        Initialize metrics collector.
        
        Args:
            max_samples: Maximum samples per source
            window_seconds: Default time window for queries
        """
        self._max_samples = max_samples
        self._window_seconds = window_seconds
        self._sources: Dict[str, SourceMetrics] = {}
        self._lock = threading.RLock()
        
        logger.debug(f"MetricsCollector initialized (max_samples={max_samples}, window={window_seconds}s)")
    
    def get_or_create_source(self, source_name: str) -> SourceMetrics:
        """Get or create metrics for a source."""
        with self._lock:
            if source_name not in self._sources:
                self._sources[source_name] = SourceMetrics(
                    source_name=source_name,
                    max_samples=self._max_samples,
                    window_seconds=self._window_seconds,
                )
                logger.debug(f"Created metrics container for source: {source_name}")
            return self._sources[source_name]
    
    def get_source(self, source_name: str) -> Optional[SourceMetrics]:
        """Get metrics for a source (returns None if not exists)."""
        with self._lock:
            return self._sources.get(source_name)
    
    def record_request(
        self,
        source_name: str,
        latency_ms: float,
        success: bool,
        **kwargs,
    ) -> None:
        """Record a request metric for a source."""
        metrics = self.get_or_create_source(source_name)
        metrics.record_request(latency_ms, success, **kwargs)
    
    def record_data(
        self,
        source_name: str,
        data_timestamp: datetime,
        fields_expected: int,
        fields_received: int,
        **kwargs,
    ) -> None:
        """Record a data metric for a source."""
        metrics = self.get_or_create_source(source_name)
        metrics.record_data(data_timestamp, fields_expected, fields_received, **kwargs)
    
    def record_value(
        self,
        source_name: str,
        field_name: str,
        value: float,
    ) -> None:
        """Record a value for consistency tracking."""
        metrics = self.get_or_create_source(source_name)
        metrics.record_value(field_name, value)
    
    def record_error(
        self,
        source_name: str,
        error_type: str,
        error_message: str,
        is_recoverable: bool = True,
    ) -> None:
        """Record an error for a source."""
        metrics = self.get_or_create_source(source_name)
        metrics.record_error(error_type, error_message, is_recoverable)
    
    def get_all_sources(self) -> List[str]:
        """Get list of all tracked sources."""
        with self._lock:
            return list(self._sources.keys())
    
    def clear_source(self, source_name: str) -> None:
        """Clear metrics for a specific source."""
        with self._lock:
            if source_name in self._sources:
                self._sources[source_name].clear()
    
    def clear_all(self) -> None:
        """Clear all metrics."""
        with self._lock:
            for source in self._sources.values():
                source.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        with self._lock:
            return {
                "source_count": len(self._sources),
                "sources": {
                    name: metrics.to_dict()
                    for name, metrics in self._sources.items()
                },
            }
