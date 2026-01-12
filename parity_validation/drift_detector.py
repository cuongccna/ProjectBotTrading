"""
Drift Detection Engine.

============================================================
PURPOSE
============================================================
Detects and quantifies behavioral drift between live and backtest.

Drift types detected:
1. Parameter drift - Config/parameter changes over time
2. Behavior drift - Decision logic changes
3. Execution drift - Fill/slippage pattern changes
4. Risk tolerance drift - Risk assessment changes

============================================================
DRIFT DETECTION METHODOLOGY
============================================================

1. Collect historical parity comparisons
2. Calculate rolling statistics
3. Detect trend deviations
4. Quantify drift magnitude
5. Identify root cause hints

============================================================
"""

import logging
import statistics
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Deque, Dict, List, Optional, Tuple

from .models import (
    DriftType,
    DriftMetric,
    DriftReport,
    ParityComparisonResult,
    CycleParityReport,
    FieldMismatch,
    ParityDomain,
    MismatchSeverity,
)


logger = logging.getLogger(__name__)


# ============================================================
# DRIFT WINDOW
# ============================================================

@dataclass
class DriftWindow:
    """
    Sliding window for drift detection.
    
    Maintains historical data for statistical analysis.
    """
    max_size: int = 1000
    window_duration: timedelta = timedelta(hours=24)
    
    # Data storage
    _samples: Deque[Tuple[datetime, Decimal]] = field(
        default_factory=lambda: deque(maxlen=1000)
    )
    
    def add_sample(self, timestamp: datetime, value: Decimal) -> None:
        """Add a sample to the window."""
        self._samples.append((timestamp, value))
        self._prune_old()
    
    def _prune_old(self) -> None:
        """Remove samples older than window duration."""
        cutoff = datetime.utcnow() - self.window_duration
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()
    
    def get_samples(self) -> List[Tuple[datetime, Decimal]]:
        """Get all samples in window."""
        self._prune_old()
        return list(self._samples)
    
    def get_values(self) -> List[Decimal]:
        """Get just the values."""
        return [s[1] for s in self.get_samples()]
    
    def get_mean(self) -> Optional[Decimal]:
        """Calculate mean of samples."""
        values = self.get_values()
        if not values:
            return None
        return Decimal(str(statistics.mean([float(v) for v in values])))
    
    def get_stddev(self) -> Optional[Decimal]:
        """Calculate standard deviation."""
        values = self.get_values()
        if len(values) < 2:
            return None
        return Decimal(str(statistics.stdev([float(v) for v in values])))
    
    def get_trend(self) -> str:
        """Determine trend direction."""
        values = self.get_values()
        if len(values) < 10:
            return "insufficient_data"
        
        # Compare first half to second half
        mid = len(values) // 2
        first_half_mean = statistics.mean([float(v) for v in values[:mid]])
        second_half_mean = statistics.mean([float(v) for v in values[mid:]])
        
        diff = second_half_mean - first_half_mean
        threshold = 0.05 * abs(first_half_mean) if first_half_mean != 0 else 0.05
        
        if diff > threshold:
            return "increasing"
        elif diff < -threshold:
            return "decreasing"
        return "stable"


# ============================================================
# DRIFT DETECTOR
# ============================================================

class DriftDetector:
    """
    Detects behavioral drift between live and backtest.
    
    Monitors multiple drift categories and maintains
    historical windows for statistical analysis.
    """
    
    # Significance thresholds (as percentage)
    PARAMETER_DRIFT_THRESHOLD = Decimal("5.0")
    BEHAVIOR_DRIFT_THRESHOLD = Decimal("10.0")
    EXECUTION_DRIFT_THRESHOLD = Decimal("15.0")
    RISK_TOLERANCE_DRIFT_THRESHOLD = Decimal("5.0")
    
    def __init__(
        self,
        window_duration: timedelta = timedelta(hours=24),
        min_samples: int = 10,
    ):
        self._window_duration = window_duration
        self._min_samples = min_samples
        
        # Drift windows by metric name
        self._parameter_windows: Dict[str, DriftWindow] = {}
        self._behavior_windows: Dict[str, DriftWindow] = {}
        self._execution_windows: Dict[str, DriftWindow] = {}
        self._risk_windows: Dict[str, DriftWindow] = {}
        
        # Baseline values (from initial calibration)
        self._baselines: Dict[str, Decimal] = {}
        
        # Detection history
        self._detected_drifts: List[DriftMetric] = []
    
    def set_baseline(self, metric_name: str, value: Decimal) -> None:
        """Set baseline value for a metric."""
        self._baselines[metric_name] = value
        logger.info(f"Set baseline for {metric_name}: {value}")
    
    def add_comparison_result(
        self,
        result: ParityComparisonResult,
    ) -> None:
        """Process a comparison result for drift detection."""
        timestamp = result.timestamp
        
        for mismatch in result.mismatches:
            if mismatch.deviation is None:
                continue
            
            # Categorize and store
            drift_type = self._categorize_field(mismatch.field_name, result.domain)
            self._add_to_window(drift_type, mismatch.field_name, timestamp, mismatch.deviation)
    
    def _categorize_field(self, field_name: str, domain: ParityDomain) -> DriftType:
        """Categorize a field into a drift type."""
        if domain == ParityDomain.DECISION:
            if "risk" in field_name.lower():
                return DriftType.RISK_TOLERANCE_DRIFT
            return DriftType.BEHAVIOR_DRIFT
        
        if domain == ParityDomain.EXECUTION:
            return DriftType.EXECUTION_DRIFT
        
        return DriftType.PARAMETER_DRIFT
    
    def _add_to_window(
        self,
        drift_type: DriftType,
        metric_name: str,
        timestamp: datetime,
        value: Decimal,
    ) -> None:
        """Add a value to the appropriate drift window."""
        windows = self._get_windows_for_type(drift_type)
        
        if metric_name not in windows:
            windows[metric_name] = DriftWindow(
                max_size=1000,
                window_duration=self._window_duration,
            )
        
        windows[metric_name].add_sample(timestamp, value)
    
    def _get_windows_for_type(self, drift_type: DriftType) -> Dict[str, DriftWindow]:
        """Get the window dict for a drift type."""
        if drift_type == DriftType.PARAMETER_DRIFT:
            return self._parameter_windows
        if drift_type == DriftType.BEHAVIOR_DRIFT:
            return self._behavior_windows
        if drift_type == DriftType.EXECUTION_DRIFT:
            return self._execution_windows
        return self._risk_windows
    
    def detect_drifts(self) -> List[DriftMetric]:
        """Run drift detection across all windows."""
        drifts = []
        
        # Check each drift type
        drifts.extend(self._detect_type_drifts(
            DriftType.PARAMETER_DRIFT,
            self._parameter_windows,
            self.PARAMETER_DRIFT_THRESHOLD,
        ))
        
        drifts.extend(self._detect_type_drifts(
            DriftType.BEHAVIOR_DRIFT,
            self._behavior_windows,
            self.BEHAVIOR_DRIFT_THRESHOLD,
        ))
        
        drifts.extend(self._detect_type_drifts(
            DriftType.EXECUTION_DRIFT,
            self._execution_windows,
            self.EXECUTION_DRIFT_THRESHOLD,
        ))
        
        drifts.extend(self._detect_type_drifts(
            DriftType.RISK_TOLERANCE_DRIFT,
            self._risk_windows,
            self.RISK_TOLERANCE_DRIFT_THRESHOLD,
        ))
        
        self._detected_drifts.extend(drifts)
        return drifts
    
    def _detect_type_drifts(
        self,
        drift_type: DriftType,
        windows: Dict[str, DriftWindow],
        threshold: Decimal,
    ) -> List[DriftMetric]:
        """Detect drifts for a specific type."""
        drifts = []
        
        for metric_name, window in windows.items():
            samples = window.get_samples()
            if len(samples) < self._min_samples:
                continue
            
            mean = window.get_mean()
            if mean is None:
                continue
            
            # Get baseline (use first samples if not set)
            baseline = self._baselines.get(metric_name)
            if baseline is None:
                # Use first 10% of samples as baseline
                baseline_count = max(1, len(samples) // 10)
                baseline_values = [s[1] for s in samples[:baseline_count]]
                baseline = Decimal(str(statistics.mean([float(v) for v in baseline_values])))
            
            # Calculate deviation
            if baseline != 0:
                deviation_pct = abs((mean - baseline) / baseline) * 100
            else:
                deviation_pct = abs(mean) * 100 if mean != 0 else Decimal("0")
            
            # Check significance
            is_significant = deviation_pct > threshold
            
            if is_significant:
                drift = DriftMetric(
                    drift_id=f"drift_{uuid.uuid4().hex[:12]}",
                    drift_type=drift_type,
                    measured_at=datetime.utcnow(),
                    metric_name=metric_name,
                    current_value=mean,
                    baseline_value=baseline,
                    deviation=abs(mean - baseline),
                    deviation_pct=deviation_pct,
                    trend_direction=window.get_trend(),
                    measurement_window=str(self._window_duration),
                    sample_count=len(samples),
                    is_significant=is_significant,
                    significance_threshold=threshold,
                )
                drifts.append(drift)
        
        return drifts
    
    def generate_report(
        self,
        analysis_window_start: datetime,
        analysis_window_end: datetime,
    ) -> DriftReport:
        """Generate a comprehensive drift report."""
        drifts = self.detect_drifts()
        
        # Categorize drifts
        parameter_drifts = [d for d in drifts if d.drift_type == DriftType.PARAMETER_DRIFT]
        behavior_drifts = [d for d in drifts if d.drift_type == DriftType.BEHAVIOR_DRIFT]
        execution_drifts = [d for d in drifts if d.drift_type == DriftType.EXECUTION_DRIFT]
        risk_drifts = [d for d in drifts if d.drift_type == DriftType.RISK_TOLERANCE_DRIFT]
        
        # Generate root cause hints
        hints = self._generate_root_cause_hints(drifts)
        
        return DriftReport(
            report_id=f"drift_report_{uuid.uuid4().hex[:12]}",
            generated_at=datetime.utcnow(),
            analysis_window_start=analysis_window_start,
            analysis_window_end=analysis_window_end,
            parameter_drifts=parameter_drifts,
            behavior_drifts=behavior_drifts,
            execution_drifts=execution_drifts,
            risk_tolerance_drifts=risk_drifts,
            total_drift_count=len(drifts),
            significant_drift_count=sum(1 for d in drifts if d.is_significant),
            root_cause_hints=hints,
        )
    
    def _generate_root_cause_hints(self, drifts: List[DriftMetric]) -> List[str]:
        """Generate root cause hints based on detected drifts."""
        hints = []
        
        # Parameter drifts
        param_drifts = [d for d in drifts if d.drift_type == DriftType.PARAMETER_DRIFT]
        if param_drifts:
            hints.append(
                f"Parameter drift detected in {len(param_drifts)} metrics. "
                "Check for configuration changes or data source modifications."
            )
        
        # Behavior drifts
        behavior_drifts = [d for d in drifts if d.drift_type == DriftType.BEHAVIOR_DRIFT]
        if behavior_drifts:
            hints.append(
                f"Behavior drift in {len(behavior_drifts)} decision metrics. "
                "Review Trade Guard logic and entry permission rules."
            )
        
        # Execution drifts
        exec_drifts = [d for d in drifts if d.drift_type == DriftType.EXECUTION_DRIFT]
        if exec_drifts:
            # Check if slippage is drifting
            slippage_drift = any("slippage" in d.metric_name.lower() for d in exec_drifts)
            if slippage_drift:
                hints.append(
                    "Slippage drift detected. Market liquidity may have changed "
                    "or backtest slippage model may need recalibration."
                )
            else:
                hints.append(
                    f"Execution drift in {len(exec_drifts)} metrics. "
                    "Review order execution logic and fill assumptions."
                )
        
        # Risk tolerance drifts
        risk_drifts = [d for d in drifts if d.drift_type == DriftType.RISK_TOLERANCE_DRIFT]
        if risk_drifts:
            hints.append(
                f"Risk tolerance drift in {len(risk_drifts)} metrics. "
                "Risk assessment may have diverged between live and backtest."
            )
        
        # Cross-category patterns
        if len(drifts) > 5:
            hints.append(
                "Multiple drift types detected. Consider full system recalibration "
                "or backtest model update."
            )
        
        return hints
    
    def get_drift_history(
        self,
        since: datetime,
    ) -> List[DriftMetric]:
        """Get drift detection history since timestamp."""
        return [d for d in self._detected_drifts if d.measured_at >= since]
    
    def clear_history(self) -> None:
        """Clear drift detection history."""
        self._detected_drifts.clear()
    
    def reset_windows(self) -> None:
        """Reset all drift windows."""
        self._parameter_windows.clear()
        self._behavior_windows.clear()
        self._execution_windows.clear()
        self._risk_windows.clear()


# ============================================================
# CONTINUOUS DRIFT MONITOR
# ============================================================

class ContinuousDriftMonitor:
    """
    Continuously monitors for drift in real-time.
    
    Maintains rolling statistics and triggers alerts
    when drift exceeds thresholds.
    """
    
    def __init__(
        self,
        detector: DriftDetector,
        check_interval_seconds: float = 60.0,
        alert_callback: Optional[callable] = None,
    ):
        self._detector = detector
        self._check_interval = check_interval_seconds
        self._alert_callback = alert_callback
        self._is_running = False
        self._last_check = datetime.utcnow()
    
    def process_cycle_report(
        self,
        report: CycleParityReport,
    ) -> List[DriftMetric]:
        """
        Process a cycle parity report for drift.
        
        Returns any newly detected significant drifts.
        """
        # Add all comparison results to detector
        for comparison in [
            report.data_parity,
            report.feature_parity,
            report.decision_parity,
            report.execution_parity,
            report.accounting_parity,
        ]:
            if comparison:
                self._detector.add_comparison_result(comparison)
        
        # Check for drifts
        now = datetime.utcnow()
        if (now - self._last_check).total_seconds() >= self._check_interval:
            self._last_check = now
            return self._check_and_alert()
        
        return []
    
    def _check_and_alert(self) -> List[DriftMetric]:
        """Check for drifts and alert if found."""
        drifts = self._detector.detect_drifts()
        significant = [d for d in drifts if d.is_significant]
        
        if significant and self._alert_callback:
            for drift in significant:
                try:
                    self._alert_callback(drift)
                except Exception as e:
                    logger.error(f"Alert callback failed: {e}")
        
        return significant
    
    def get_current_drift_summary(self) -> Dict[str, Any]:
        """Get current drift status summary."""
        now = datetime.utcnow()
        recent_drifts = self._detector.get_drift_history(
            since=now - timedelta(hours=1)
        )
        
        return {
            "total_drifts_detected": len(recent_drifts),
            "significant_drifts": sum(1 for d in recent_drifts if d.is_significant),
            "drift_types": list(set(d.drift_type.value for d in recent_drifts)),
            "last_check": self._last_check.isoformat(),
        }


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_drift_detector(
    window_duration: timedelta = timedelta(hours=24),
    min_samples: int = 10,
) -> DriftDetector:
    """Create a DriftDetector."""
    return DriftDetector(
        window_duration=window_duration,
        min_samples=min_samples,
    )


def create_drift_monitor(
    detector: Optional[DriftDetector] = None,
    check_interval_seconds: float = 60.0,
    alert_callback: Optional[callable] = None,
) -> ContinuousDriftMonitor:
    """Create a ContinuousDriftMonitor."""
    detector = detector or create_drift_detector()
    return ContinuousDriftMonitor(
        detector=detector,
        check_interval_seconds=check_interval_seconds,
        alert_callback=alert_callback,
    )
