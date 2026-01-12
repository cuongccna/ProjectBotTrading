"""
Alert Rules and Definitions.

============================================================
PURPOSE
============================================================
Deterministic alert rules with explicit triggers.

PRINCIPLES:
- All thresholds are explicit and configurable
- NO derived or predictive alerts
- Simple condition evaluation
- Human-readable rule descriptions

============================================================
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, Any, Optional, List, Callable

from ..models import (
    Alert,
    AlertTier,
    SystemMode,
    ModuleStatus,
    DataFreshness,
    SystemStateSnapshot,
    RiskExposureSnapshot,
    ModuleHealth,
    DataSourceStatus,
)


logger = logging.getLogger(__name__)


# ============================================================
# ALERT CATEGORY
# ============================================================

class AlertCategory(Enum):
    """Alert categories."""
    SYSTEM = "system"          # System-level alerts
    RISK = "risk"              # Risk/exposure alerts
    EXECUTION = "execution"    # Order/execution alerts
    DATA = "data"              # Data pipeline alerts
    MODULE = "module"          # Module health alerts
    POSITION = "position"      # Position alerts


# ============================================================
# ALERT RULE BASE
# ============================================================

@dataclass
class AlertRuleConfig:
    """Configuration for an alert rule."""
    rule_id: str
    rule_name: str
    category: AlertCategory
    tier: AlertTier
    description: str
    enabled: bool = True
    cooldown_seconds: int = 60  # Minimum time between alerts
    auto_resolve: bool = True   # Auto-resolve when condition clears


class AlertRule(ABC):
    """
    Base class for alert rules.
    
    All rules MUST be deterministic.
    NO predictions, NO derived assumptions.
    """
    
    def __init__(self, config: AlertRuleConfig):
        """Initialize rule."""
        self.config = config
        self._last_triggered: Optional[datetime] = None
        self._active_alert: Optional[Alert] = None
    
    @property
    def rule_id(self) -> str:
        """Rule ID."""
        return self.config.rule_id
    
    @property
    def is_active(self) -> bool:
        """Whether this rule has an active (unresolved) alert."""
        return self._active_alert is not None
    
    @abstractmethod
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """
        Evaluate the rule against current context.
        
        Returns Alert if triggered, None otherwise.
        
        MUST be deterministic.
        MUST NOT make assumptions.
        """
        pass
    
    def check_cooldown(self) -> bool:
        """Check if cooldown period has passed."""
        if self._last_triggered is None:
            return True
        
        elapsed = (datetime.utcnow() - self._last_triggered).total_seconds()
        return elapsed >= self.config.cooldown_seconds
    
    def trigger(
        self,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """Create and register an alert."""
        self._last_triggered = datetime.utcnow()
        
        alert = Alert(
            alert_id=f"{self.rule_id}_{int(datetime.utcnow().timestamp())}",
            tier=self.config.tier,
            category=self.config.category.value,
            title=title,
            message=message,
            triggered_at=datetime.utcnow(),
            triggered_by_rule=self.rule_id,
            data=data or {},
            acknowledged=False,
            acknowledged_at=None,
            acknowledged_by=None,
            resolved=False,
            resolved_at=None,
        )
        
        self._active_alert = alert
        return alert
    
    def resolve(self) -> Optional[Alert]:
        """Resolve active alert."""
        if self._active_alert is None:
            return None
        
        alert = self._active_alert
        alert.resolved = True
        alert.resolved_at = datetime.utcnow()
        
        self._active_alert = None
        return alert


# ============================================================
# SYSTEM ALERT RULES
# ============================================================

class SystemModeChangeRule(AlertRule):
    """Alert when system mode changes."""
    
    def __init__(self):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="system_mode_change",
            rule_name="System Mode Change",
            category=AlertCategory.SYSTEM,
            tier=AlertTier.WARNING,
            description="Alerts when system mode changes",
            cooldown_seconds=0,  # Always alert on mode change
        ))
        self._last_mode: Optional[SystemMode] = None
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        system_state: Optional[SystemStateSnapshot] = context.get("system_state")
        if system_state is None:
            return None
        
        current_mode = system_state.mode
        
        # Check for mode change
        if self._last_mode is not None and current_mode != self._last_mode:
            # Determine tier based on new mode
            tier = AlertTier.INFO
            if current_mode in [SystemMode.HALTED_SYSTEM, SystemMode.PAUSED_RISK]:
                tier = AlertTier.CRITICAL
            elif current_mode == SystemMode.DEGRADED:
                tier = AlertTier.WARNING
            
            self.config.tier = tier
            
            alert = self.trigger(
                title=f"System Mode: {current_mode.value}",
                message=f"System mode changed from {self._last_mode.value} to {current_mode.value}. "
                        f"Reason: {system_state.mode_reason}",
                data={
                    "previous_mode": self._last_mode.value,
                    "new_mode": current_mode.value,
                    "changed_by": system_state.mode_changed_by,
                    "reason": system_state.mode_reason,
                },
            )
            
            self._last_mode = current_mode
            return alert
        
        self._last_mode = current_mode
        return None


class TradingHaltedRule(AlertRule):
    """Alert when trading is halted."""
    
    def __init__(self):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="trading_halted",
            rule_name="Trading Halted",
            category=AlertCategory.SYSTEM,
            tier=AlertTier.CRITICAL,
            description="Alerts when trading is halted",
            cooldown_seconds=300,
        ))
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        system_state: Optional[SystemStateSnapshot] = context.get("system_state")
        if system_state is None:
            return None
        
        is_halted = system_state.mode in [
            SystemMode.HALTED_SYSTEM,
            SystemMode.PAUSED_RISK,
        ]
        
        if is_halted and not self.is_active:
            if self.check_cooldown():
                return self.trigger(
                    title="Trading Halted",
                    message=f"Trading has been halted. Mode: {system_state.mode.value}. "
                            f"Reason: {system_state.mode_reason}",
                    data={
                        "mode": system_state.mode.value,
                        "reason": system_state.mode_reason,
                        "changed_by": system_state.mode_changed_by,
                    },
                )
        elif not is_halted and self.is_active:
            self.resolve()
        
        return None


# ============================================================
# RISK ALERT RULES
# ============================================================

class DrawdownThresholdRule(AlertRule):
    """Alert when drawdown exceeds threshold."""
    
    def __init__(
        self,
        warning_threshold: Decimal = Decimal("0.05"),   # 5%
        critical_threshold: Decimal = Decimal("0.10"),  # 10%
    ):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="drawdown_threshold",
            rule_name="Drawdown Threshold",
            category=AlertCategory.RISK,
            tier=AlertTier.WARNING,
            description="Alerts when drawdown exceeds configured thresholds",
            cooldown_seconds=60,
        ))
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        risk: Optional[RiskExposureSnapshot] = context.get("risk_exposure")
        if risk is None or risk.current_drawdown is None:
            return None
        
        drawdown = abs(risk.current_drawdown)
        
        # Check thresholds
        if drawdown >= self.critical_threshold:
            if not self.is_active or self.config.tier != AlertTier.CRITICAL:
                self.config.tier = AlertTier.CRITICAL
                if self.check_cooldown():
                    return self.trigger(
                        title="Critical Drawdown",
                        message=f"Drawdown of {drawdown*100:.2f}% exceeds "
                                f"critical threshold ({self.critical_threshold*100:.1f}%)",
                        data={
                            "drawdown_pct": float(drawdown * 100),
                            "threshold_pct": float(self.critical_threshold * 100),
                            "daily_pnl": float(risk.daily_pnl) if risk.daily_pnl else None,
                        },
                    )
        elif drawdown >= self.warning_threshold:
            if not self.is_active:
                self.config.tier = AlertTier.WARNING
                if self.check_cooldown():
                    return self.trigger(
                        title="Elevated Drawdown",
                        message=f"Drawdown of {drawdown*100:.2f}% exceeds "
                                f"warning threshold ({self.warning_threshold*100:.1f}%)",
                        data={
                            "drawdown_pct": float(drawdown * 100),
                            "threshold_pct": float(self.warning_threshold * 100),
                        },
                    )
        elif self.is_active and self.config.auto_resolve:
            self.resolve()
        
        return None


class ExposureLimitRule(AlertRule):
    """Alert when exposure approaches limits."""
    
    def __init__(
        self,
        max_exposure_ratio: Decimal = Decimal("0.80"),
    ):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="exposure_limit",
            rule_name="Exposure Limit",
            category=AlertCategory.RISK,
            tier=AlertTier.WARNING,
            description="Alerts when exposure ratio approaches maximum",
            cooldown_seconds=120,
        ))
        self.max_exposure_ratio = max_exposure_ratio
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        risk: Optional[RiskExposureSnapshot] = context.get("risk_exposure")
        if risk is None or risk.exposure_ratio is None:
            return None
        
        if risk.exposure_ratio >= self.max_exposure_ratio:
            if not self.is_active and self.check_cooldown():
                return self.trigger(
                    title="High Exposure",
                    message=f"Exposure ratio of {risk.exposure_ratio*100:.1f}% "
                            f"exceeds threshold ({self.max_exposure_ratio*100:.1f}%)",
                    data={
                        "exposure_ratio": float(risk.exposure_ratio),
                        "total_exposure": float(risk.total_exposure) if risk.total_exposure else None,
                        "total_equity": float(risk.total_equity) if risk.total_equity else None,
                    },
                )
        elif self.is_active and self.config.auto_resolve:
            self.resolve()
        
        return None


class MarginWarningRule(AlertRule):
    """Alert when margin usage is high."""
    
    def __init__(
        self,
        warning_threshold: Decimal = Decimal("0.70"),
        critical_threshold: Decimal = Decimal("0.85"),
    ):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="margin_warning",
            rule_name="Margin Warning",
            category=AlertCategory.RISK,
            tier=AlertTier.WARNING,
            description="Alerts when margin usage is high",
            cooldown_seconds=60,
        ))
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        risk: Optional[RiskExposureSnapshot] = context.get("risk_exposure")
        if risk is None or risk.margin_ratio is None:
            return None
        
        if risk.margin_ratio >= self.critical_threshold:
            self.config.tier = AlertTier.CRITICAL
            if not self.is_active and self.check_cooldown():
                return self.trigger(
                    title="Critical Margin Usage",
                    message=f"Margin usage at {risk.margin_ratio*100:.1f}% - "
                            f"Liquidation risk!",
                    data={
                        "margin_ratio": float(risk.margin_ratio),
                        "margin_used": float(risk.margin_used) if risk.margin_used else None,
                    },
                )
        elif risk.margin_ratio >= self.warning_threshold:
            self.config.tier = AlertTier.WARNING
            if not self.is_active and self.check_cooldown():
                return self.trigger(
                    title="High Margin Usage",
                    message=f"Margin usage at {risk.margin_ratio*100:.1f}%",
                    data={
                        "margin_ratio": float(risk.margin_ratio),
                    },
                )
        elif self.is_active and self.config.auto_resolve:
            self.resolve()
        
        return None


# ============================================================
# MODULE HEALTH RULES
# ============================================================

class ModuleUnhealthyRule(AlertRule):
    """Alert when a module becomes unhealthy."""
    
    def __init__(self):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="module_unhealthy",
            rule_name="Module Unhealthy",
            category=AlertCategory.MODULE,
            tier=AlertTier.CRITICAL,
            description="Alerts when a module becomes unhealthy",
            cooldown_seconds=60,
        ))
        self._unhealthy_modules: set = set()
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        modules: Dict[str, ModuleHealth] = context.get("module_health", {})
        
        current_unhealthy = set()
        for name, health in modules.items():
            if health.status == ModuleStatus.UNHEALTHY:
                current_unhealthy.add(name)
        
        # Check for newly unhealthy modules
        newly_unhealthy = current_unhealthy - self._unhealthy_modules
        
        if newly_unhealthy and self.check_cooldown():
            self._unhealthy_modules = current_unhealthy
            
            return self.trigger(
                title="Module(s) Unhealthy",
                message=f"The following modules are unhealthy: {', '.join(newly_unhealthy)}",
                data={
                    "unhealthy_modules": list(newly_unhealthy),
                    "all_unhealthy": list(current_unhealthy),
                },
            )
        
        # Update tracking
        self._unhealthy_modules = current_unhealthy
        
        if not current_unhealthy and self.is_active:
            self.resolve()
        
        return None


class HeartbeatMissedRule(AlertRule):
    """Alert when module heartbeat is missed."""
    
    def __init__(self):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="heartbeat_missed",
            rule_name="Heartbeat Missed",
            category=AlertCategory.MODULE,
            tier=AlertTier.WARNING,
            description="Alerts when module heartbeat is missed",
            cooldown_seconds=30,
        ))
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        modules: Dict[str, ModuleHealth] = context.get("module_health", {})
        
        missed = []
        for name, health in modules.items():
            if health.heartbeat_missed:
                missed.append(name)
        
        if missed and not self.is_active and self.check_cooldown():
            return self.trigger(
                title="Heartbeat Missed",
                message=f"Heartbeat missed for: {', '.join(missed)}",
                data={
                    "modules": missed,
                },
            )
        
        if not missed and self.is_active:
            self.resolve()
        
        return None


# ============================================================
# DATA PIPELINE RULES
# ============================================================

class DataStaleRule(AlertRule):
    """Alert when data source becomes stale."""
    
    def __init__(self):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="data_stale",
            rule_name="Data Stale",
            category=AlertCategory.DATA,
            tier=AlertTier.WARNING,
            description="Alerts when data source becomes stale",
            cooldown_seconds=60,
        ))
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        sources: List[DataSourceStatus] = context.get("data_sources", [])
        
        stale = []
        for source in sources:
            if source.freshness in [DataFreshness.STALE, DataFreshness.MISSING]:
                stale.append(source.source_name)
        
        if stale and not self.is_active and self.check_cooldown():
            return self.trigger(
                title="Data Source Stale",
                message=f"Data sources are stale: {', '.join(stale)}",
                data={
                    "stale_sources": stale,
                },
            )
        
        if not stale and self.is_active:
            self.resolve()
        
        return None


class DataErrorRateRule(AlertRule):
    """Alert when data source error rate is high."""
    
    def __init__(self, error_threshold: int = 5):
        """Initialize rule."""
        super().__init__(AlertRuleConfig(
            rule_id="data_error_rate",
            rule_name="Data Error Rate",
            category=AlertCategory.DATA,
            tier=AlertTier.WARNING,
            description="Alerts when data source error rate is high",
            cooldown_seconds=60,
        ))
        self.error_threshold = error_threshold
    
    def evaluate(self, context: Dict[str, Any]) -> Optional[Alert]:
        """Evaluate rule."""
        sources: List[DataSourceStatus] = context.get("data_sources", [])
        
        high_error = []
        for source in sources:
            if source.error_count_5m >= self.error_threshold:
                high_error.append({
                    "name": source.source_name,
                    "errors": source.error_count_5m,
                })
        
        if high_error and not self.is_active and self.check_cooldown():
            names = [e["name"] for e in high_error]
            return self.trigger(
                title="High Data Error Rate",
                message=f"High error rate on: {', '.join(names)}",
                data={
                    "sources": high_error,
                },
            )
        
        if not high_error and self.is_active:
            self.resolve()
        
        return None


# ============================================================
# RULE REGISTRY
# ============================================================

def get_default_rules() -> List[AlertRule]:
    """Get default set of alert rules."""
    return [
        # System rules
        SystemModeChangeRule(),
        TradingHaltedRule(),
        
        # Risk rules
        DrawdownThresholdRule(),
        ExposureLimitRule(),
        MarginWarningRule(),
        
        # Module rules
        ModuleUnhealthyRule(),
        HeartbeatMissedRule(),
        
        # Data rules
        DataStaleRule(),
        DataErrorRateRule(),
    ]
