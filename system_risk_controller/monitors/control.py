"""
System Risk Controller - Control Monitor.

============================================================
PURPOSE
============================================================
Monitors risk limits and control thresholds.

HALT TRIGGERS:
- CT_RISK_LIMIT_VIOLATED: Risk limits violated
- CT_LEVERAGE_EXCEEDED: Unexpected leverage exposure
- CT_DRAWDOWN_EXCEEDED: Drawdown beyond threshold
- CT_STRATEGY_DEVIATION: Strategy behavior deviation
- CT_LOSS_LIMIT_BREACHED: Loss limits breached
- CT_EXPOSURE_LIMIT_BREACHED: Exposure limits breached

============================================================
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from ..types import (
    HaltTrigger,
    HaltLevel,
    TriggerCategory,
    MonitorResult,
)
from ..config import ControlConfig
from .base import (
    BaseMonitor,
    MonitorMeta,
    create_healthy_result,
    create_halt_result,
)


# ============================================================
# CONTROL STATE SNAPSHOT
# ============================================================

@dataclass
class ControlStateSnapshot:
    """
    Snapshot of current control/risk state.
    """
    
    # Capital
    total_equity: float = 0.0
    """Total account equity."""
    
    available_balance: float = 0.0
    """Available balance for trading."""
    
    peak_equity: float = 0.0
    """Peak equity (for drawdown calculation)."""
    
    # Drawdown
    current_drawdown_pct: float = 0.0
    """Current drawdown from peak (percentage)."""
    
    daily_drawdown_pct: float = 0.0
    """Drawdown today (percentage)."""
    
    # P&L
    daily_pnl: float = 0.0
    """Today's P&L in USD."""
    
    hourly_pnl: float = 0.0
    """Current hour's P&L in USD."""
    
    unrealized_pnl: float = 0.0
    """Unrealized P&L."""
    
    # Leverage
    current_leverage: float = 0.0
    """Current leverage."""
    
    max_leverage_used_today: float = 0.0
    """Maximum leverage used today."""
    
    # Exposure
    total_exposure_pct: float = 0.0
    """Total portfolio exposure as percentage."""
    
    largest_position_pct: float = 0.0
    """Largest single position as percentage."""
    
    position_count: int = 0
    """Number of open positions."""
    
    # Strategy Metrics (for deviation detection)
    actual_win_rate: Optional[float] = None
    """Actual win rate."""
    
    expected_win_rate: Optional[float] = None
    """Expected win rate from backtest."""
    
    trades_today: int = 0
    """Number of trades today."""
    
    # Risk Score
    current_risk_score: float = 0.0
    """Current risk score (0-1)."""
    
    risk_level: Optional[str] = None
    """Current risk level (LOW, MEDIUM, HIGH, CRITICAL)."""


# ============================================================
# CONTROL MONITOR
# ============================================================

class ControlMonitor(BaseMonitor):
    """
    Monitors risk limits and controls.
    
    Checks:
    1. Drawdown limits
    2. Loss limits
    3. Leverage limits
    4. Exposure limits
    5. Risk score
    6. Strategy deviation
    """
    
    def __init__(
        self,
        config: ControlConfig,
    ):
        """
        Initialize monitor.
        
        Args:
            config: Control configuration
        """
        self._config = config
        self._last_control_state: Optional[ControlStateSnapshot] = None
    
    @property
    def meta(self) -> MonitorMeta:
        return MonitorMeta(
            name="ControlMonitor",
            category=TriggerCategory.CONTROL,
            description="Monitors risk limits and controls",
            is_critical=True,
        )
    
    def update_state(self, state: ControlStateSnapshot) -> None:
        """
        Update the control state for monitoring.
        
        Args:
            state: Current control state
        """
        self._last_control_state = state
    
    def _check(self) -> MonitorResult:
        """
        Perform control/risk checks.
        """
        if self._last_control_state is None:
            return create_healthy_result(
                monitor_name=self.meta.name,
                metrics={"warning": "No control state provided"},
            )
        
        state = self._last_control_state
        
        # Check 1: Total Drawdown (EMERGENCY)
        result = self._check_total_drawdown(state)
        if result is not None:
            return result
        
        # Check 2: Daily Drawdown
        result = self._check_daily_drawdown(state)
        if result is not None:
            return result
        
        # Check 3: Leverage (EMERGENCY if exceeded)
        result = self._check_leverage(state)
        if result is not None:
            return result
        
        # Check 4: Loss Limits
        result = self._check_loss_limits(state)
        if result is not None:
            return result
        
        # Check 5: Exposure Limits
        result = self._check_exposure_limits(state)
        if result is not None:
            return result
        
        # Check 6: Strategy Deviation
        result = self._check_strategy_deviation(state)
        if result is not None:
            return result
        
        # All checks passed
        return create_healthy_result(
            monitor_name=self.meta.name,
            metrics={
                "current_drawdown_pct": state.current_drawdown_pct,
                "daily_drawdown_pct": state.daily_drawdown_pct,
                "current_leverage": state.current_leverage,
                "daily_pnl": state.daily_pnl,
                "total_exposure_pct": state.total_exposure_pct,
                "risk_score": state.current_risk_score,
            },
        )
    
    def _check_total_drawdown(
        self,
        state: ControlStateSnapshot,
    ) -> Optional[MonitorResult]:
        """
        Check total drawdown from peak.
        
        THIS IS CRITICAL - exceeding total drawdown = EMERGENCY.
        """
        if state.current_drawdown_pct >= self._config.max_total_drawdown_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_DRAWDOWN_EXCEEDED,
                halt_level=HaltLevel.EMERGENCY,
                message=f"TOTAL DRAWDOWN LIMIT BREACHED: {state.current_drawdown_pct:.2f}%",
                details={
                    "current_drawdown_pct": state.current_drawdown_pct,
                    "limit_pct": self._config.max_total_drawdown_pct,
                    "peak_equity": state.peak_equity,
                    "current_equity": state.total_equity,
                },
            )
        
        return None
    
    def _check_daily_drawdown(
        self,
        state: ControlStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check daily drawdown."""
        # Emergency threshold
        if state.daily_drawdown_pct >= self._config.max_daily_drawdown_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_DRAWDOWN_EXCEEDED,
                halt_level=HaltLevel.HARD,
                message=f"Daily drawdown limit breached: {state.daily_drawdown_pct:.2f}%",
                details={
                    "daily_drawdown_pct": state.daily_drawdown_pct,
                    "limit_pct": self._config.max_daily_drawdown_pct,
                },
            )
        
        # Warning threshold
        if state.daily_drawdown_pct >= self._config.drawdown_warning_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_DRAWDOWN_EXCEEDED,
                halt_level=HaltLevel.SOFT,
                message=f"Daily drawdown warning: {state.daily_drawdown_pct:.2f}%",
                details={
                    "daily_drawdown_pct": state.daily_drawdown_pct,
                    "warning_pct": self._config.drawdown_warning_pct,
                },
            )
        
        return None
    
    def _check_leverage(
        self,
        state: ControlStateSnapshot,
    ) -> Optional[MonitorResult]:
        """
        Check leverage limits.
        
        Exceeding max leverage = EMERGENCY (unexpected exposure).
        """
        if state.current_leverage > self._config.max_leverage:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_LEVERAGE_EXCEEDED,
                halt_level=HaltLevel.EMERGENCY,
                message=f"LEVERAGE LIMIT EXCEEDED: {state.current_leverage:.1f}x (max: {self._config.max_leverage}x)",
                details={
                    "current_leverage": state.current_leverage,
                    "max_leverage": self._config.max_leverage,
                },
            )
        
        # Warning threshold
        if state.current_leverage > self._config.leverage_warning_threshold:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_LEVERAGE_EXCEEDED,
                halt_level=HaltLevel.SOFT,
                message=f"Leverage warning: {state.current_leverage:.1f}x",
                details={
                    "current_leverage": state.current_leverage,
                    "warning_threshold": self._config.leverage_warning_threshold,
                },
            )
        
        return None
    
    def _check_loss_limits(
        self,
        state: ControlStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check loss limits."""
        # Daily loss limit
        if state.daily_pnl < 0 and abs(state.daily_pnl) >= self._config.max_daily_loss_usd:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_LOSS_LIMIT_BREACHED,
                halt_level=HaltLevel.HARD,
                message=f"Daily loss limit breached: ${abs(state.daily_pnl):.2f}",
                details={
                    "daily_pnl": state.daily_pnl,
                    "limit_usd": self._config.max_daily_loss_usd,
                },
            )
        
        # Hourly loss limit
        if state.hourly_pnl < 0 and abs(state.hourly_pnl) >= self._config.max_hourly_loss_usd:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_LOSS_LIMIT_BREACHED,
                halt_level=HaltLevel.SOFT,
                message=f"Hourly loss limit breached: ${abs(state.hourly_pnl):.2f}",
                details={
                    "hourly_pnl": state.hourly_pnl,
                    "limit_usd": self._config.max_hourly_loss_usd,
                },
            )
        
        return None
    
    def _check_exposure_limits(
        self,
        state: ControlStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check exposure limits."""
        # Total exposure
        if state.total_exposure_pct > self._config.max_total_exposure_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_EXPOSURE_LIMIT_BREACHED,
                halt_level=HaltLevel.HARD,
                message=f"Total exposure limit breached: {state.total_exposure_pct:.1f}%",
                details={
                    "exposure_pct": state.total_exposure_pct,
                    "limit_pct": self._config.max_total_exposure_pct,
                },
            )
        
        # Single position exposure
        if state.largest_position_pct > self._config.max_single_position_pct:
            return create_halt_result(
                monitor_name=self.meta.name,
                trigger=HaltTrigger.CT_EXPOSURE_LIMIT_BREACHED,
                halt_level=HaltLevel.SOFT,
                message=f"Single position exposure limit: {state.largest_position_pct:.1f}%",
                details={
                    "largest_position_pct": state.largest_position_pct,
                    "limit_pct": self._config.max_single_position_pct,
                },
            )
        
        return None
    
    def _check_strategy_deviation(
        self,
        state: ControlStateSnapshot,
    ) -> Optional[MonitorResult]:
        """Check for strategy deviation from expected behavior."""
        if not self._config.check_strategy_deviation:
            return None
        
        # Need enough trades to make a judgment
        if state.trades_today < 5:
            return None
        
        # Check win rate deviation
        if (state.actual_win_rate is not None and 
            state.expected_win_rate is not None):
            
            deviation = abs(state.actual_win_rate - state.expected_win_rate) * 100
            
            if deviation > self._config.max_win_rate_deviation_pct:
                return create_halt_result(
                    monitor_name=self.meta.name,
                    trigger=HaltTrigger.CT_STRATEGY_DEVIATION,
                    halt_level=HaltLevel.SOFT,
                    message=f"Strategy win rate deviation: {deviation:.1f}%",
                    details={
                        "actual_win_rate": state.actual_win_rate,
                        "expected_win_rate": state.expected_win_rate,
                        "deviation_pct": deviation,
                        "trades_today": state.trades_today,
                    },
                )
        
        return None
