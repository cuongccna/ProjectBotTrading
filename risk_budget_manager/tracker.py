"""
Risk Budget Manager - Risk Tracker.

============================================================
PURPOSE
============================================================
Real-time tracking of risk consumption across all dimensions.

The Risk Tracker maintains the current state of:
- Daily cumulative risk used
- Open position risk held
- Current drawdown from peak

Risk budget is HELD when positions open and RELEASED when closed.

============================================================
CRITICAL INVARIANTS
============================================================
1. Risk is consumed when trade is OPENED (not executed)
2. Risk is released ONLY when position is FULLY closed
3. Partial closes release proportional risk
4. Stop loss updates may increase or decrease held risk

============================================================
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, Optional, List
import threading
from uuid import uuid4

from .types import (
    OpenPositionRisk,
    DailyRiskUsage,
    RiskBudgetSnapshot,
    EquityUpdate,
    PositionStatus,
    RiskBudgetError,
    EquityDataError,
    PositionStateError,
)
from .config import RiskBudgetConfig


@dataclass
class TrackerState:
    """
    Internal state of the risk tracker.
    
    This is the source of truth for all risk calculations.
    """
    
    # Equity State
    current_equity: float = 0.0
    """Current account equity."""
    
    peak_equity: float = 0.0
    """Historical peak equity."""
    
    last_equity_update: Optional[datetime] = None
    """When equity was last updated."""
    
    # Position Tracking
    open_positions: Dict[str, OpenPositionRisk] = field(default_factory=dict)
    """Map of position_id to OpenPositionRisk."""
    
    # Daily Tracking
    current_daily_usage: Optional[DailyRiskUsage] = None
    """Current day's risk usage."""
    
    daily_history: Dict[str, DailyRiskUsage] = field(default_factory=dict)
    """Historical daily usage by date string."""
    
    # Consecutive Loss Tracking
    consecutive_losses: int = 0
    """Number of consecutive losing trades."""
    
    # System State
    is_halted: bool = False
    """Whether trading is halted."""
    
    halt_reason: Optional[str] = None
    """Reason for halt if applicable."""
    
    halted_at: Optional[datetime] = None
    """When trading was halted."""


class RiskTracker:
    """
    Real-time risk consumption tracker.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    1. Track equity updates from Account Monitor
    2. Track open position risk
    3. Track daily cumulative risk
    4. Calculate current drawdown
    5. Provide risk budget availability
    
    ============================================================
    THREAD SAFETY
    ============================================================
    All state modifications are protected by a lock.
    This allows concurrent queries and updates.
    
    ============================================================
    """
    
    def __init__(self, config: RiskBudgetConfig):
        """
        Initialize the risk tracker.
        
        Args:
            config: Risk budget configuration
        """
        self._config = config
        self._state = TrackerState()
        self._lock = threading.RLock()
    
    # --------------------------------------------------------
    # EQUITY UPDATES
    # --------------------------------------------------------
    
    def update_equity(self, update: EquityUpdate) -> None:
        """
        Process an equity update from Account Monitor.
        
        This MUST be called regularly for the system to function.
        Stale equity data will cause all trades to be rejected.
        
        Args:
            update: Equity update from Account Monitor
        """
        with self._lock:
            self._state.current_equity = update.account_equity
            self._state.last_equity_update = update.timestamp
            
            # Track peak equity for drawdown calculation
            if update.account_equity > self._state.peak_equity:
                self._state.peak_equity = update.account_equity
            
            # Check if we've recovered from drawdown
            self._check_drawdown_recovery()
    
    def get_current_equity(self) -> float:
        """Get current account equity."""
        with self._lock:
            return self._state.current_equity
    
    def get_peak_equity(self) -> float:
        """Get peak account equity."""
        with self._lock:
            return self._state.peak_equity
    
    def is_equity_stale(self) -> bool:
        """
        Check if equity data is stale.
        
        Returns:
            True if equity data is missing or too old
        """
        with self._lock:
            if self._state.last_equity_update is None:
                return True
            
            age = (datetime.utcnow() - self._state.last_equity_update).total_seconds()
            return age > self._config.equity_tracking.max_staleness_seconds
    
    def set_peak_equity(self, peak: float) -> None:
        """
        Set peak equity (for initialization from persisted state).
        
        Args:
            peak: Peak equity value
        """
        with self._lock:
            self._state.peak_equity = max(peak, self._state.current_equity)
    
    # --------------------------------------------------------
    # POSITION TRACKING
    # --------------------------------------------------------
    
    def register_position(
        self,
        position_id: str,
        symbol: str,
        exchange: str,
        direction: str,
        entry_price: float,
        stop_loss_price: float,
        position_size: float,
    ) -> OpenPositionRisk:
        """
        Register a new open position and consume risk budget.
        
        Args:
            position_id: Unique position identifier
            symbol: Trading pair
            exchange: Exchange identifier
            direction: 'LONG' or 'SHORT'
            entry_price: Entry price
            stop_loss_price: Stop loss price
            position_size: Position size
        
        Returns:
            Created OpenPositionRisk
        
        Raises:
            PositionStateError: If position already exists
        """
        with self._lock:
            if position_id in self._state.open_positions:
                raise PositionStateError(
                    f"Position {position_id} already registered"
                )
            
            # Calculate risk
            if direction == "LONG":
                risk_per_unit = entry_price - stop_loss_price
            else:
                risk_per_unit = stop_loss_price - entry_price
            
            risk_amount = abs(risk_per_unit * position_size)
            risk_pct = (risk_amount / self._state.current_equity) * 100 if self._state.current_equity > 0 else 0
            
            position = OpenPositionRisk(
                position_id=position_id,
                symbol=symbol,
                exchange=exchange,
                direction=direction,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                position_size=position_size,
                risk_amount=risk_amount,
                risk_percentage=risk_pct,
                equity_at_entry=self._state.current_equity,
                status=PositionStatus.OPEN,
                opened_at=datetime.utcnow(),
            )
            
            self._state.open_positions[position_id] = position
            
            # Update daily risk usage
            self._consume_daily_risk(risk_pct)
            
            return position
    
    def close_position(
        self,
        position_id: str,
        realized_pnl: float,
    ) -> OpenPositionRisk:
        """
        Close a position and release risk budget.
        
        Args:
            position_id: Position identifier
            realized_pnl: Realized P&L from the trade
        
        Returns:
            Closed OpenPositionRisk
        
        Raises:
            PositionStateError: If position not found
        """
        with self._lock:
            if position_id not in self._state.open_positions:
                raise PositionStateError(
                    f"Position {position_id} not found"
                )
            
            position = self._state.open_positions.pop(position_id)
            position.status = PositionStatus.CLOSED
            position.closed_at = datetime.utcnow()
            position.realized_pnl = realized_pnl
            
            # Update consecutive loss tracking
            if realized_pnl < 0:
                self._state.consecutive_losses += 1
            else:
                self._state.consecutive_losses = 0
            
            # Update daily realized P&L
            if self._state.current_daily_usage:
                self._state.current_daily_usage.realized_pnl += realized_pnl
            
            return position
    
    def partial_close_position(
        self,
        position_id: str,
        closed_size: float,
        realized_pnl: float,
    ) -> OpenPositionRisk:
        """
        Partially close a position.
        
        Args:
            position_id: Position identifier
            closed_size: Size being closed
            realized_pnl: Realized P&L from partial close
        
        Returns:
            Updated OpenPositionRisk
        
        Raises:
            PositionStateError: If position not found or invalid size
        """
        with self._lock:
            if position_id not in self._state.open_positions:
                raise PositionStateError(
                    f"Position {position_id} not found"
                )
            
            position = self._state.open_positions[position_id]
            
            if closed_size >= position.position_size:
                raise PositionStateError(
                    f"Closed size {closed_size} >= position size {position.position_size}"
                )
            
            # Calculate proportional risk release
            close_ratio = closed_size / position.position_size
            released_risk = position.risk_percentage * close_ratio
            
            # Update position
            position.position_size -= closed_size
            position.risk_amount *= (1 - close_ratio)
            position.risk_percentage *= (1 - close_ratio)
            position.status = PositionStatus.PARTIALLY_CLOSED
            
            # Update daily realized P&L
            if self._state.current_daily_usage:
                self._state.current_daily_usage.realized_pnl += realized_pnl
            
            return position
    
    def update_stop_loss(
        self,
        position_id: str,
        new_stop_loss: float,
    ) -> OpenPositionRisk:
        """
        Update stop loss for a position (recalculates risk).
        
        Moving stop loss to break-even or profit releases risk.
        Widening stop loss increases held risk.
        
        Args:
            position_id: Position identifier
            new_stop_loss: New stop loss price
        
        Returns:
            Updated OpenPositionRisk
        
        Raises:
            PositionStateError: If position not found
        """
        with self._lock:
            if position_id not in self._state.open_positions:
                raise PositionStateError(
                    f"Position {position_id} not found"
                )
            
            position = self._state.open_positions[position_id]
            old_risk_pct = position.risk_percentage
            
            # Update position with new stop loss
            position.update_stop_loss(
                new_stop_loss,
                self._state.current_equity,
            )
            
            # If risk increased, consume additional daily budget
            risk_diff = position.risk_percentage - old_risk_pct
            if risk_diff > 0:
                self._consume_daily_risk(risk_diff)
            
            return position
    
    def get_open_positions(self) -> List[OpenPositionRisk]:
        """Get all open positions."""
        with self._lock:
            return list(self._state.open_positions.values())
    
    def get_position(self, position_id: str) -> Optional[OpenPositionRisk]:
        """Get a specific position."""
        with self._lock:
            return self._state.open_positions.get(position_id)
    
    def has_position_for_symbol(self, symbol: str) -> bool:
        """Check if there's an open position for a symbol."""
        with self._lock:
            for position in self._state.open_positions.values():
                if position.symbol == symbol:
                    return True
            return False
    
    # --------------------------------------------------------
    # RISK BUDGET CALCULATIONS
    # --------------------------------------------------------
    
    def get_total_open_risk_pct(self) -> float:
        """
        Get total risk across all open positions.
        
        Returns:
            Total open risk as percentage of equity
        """
        with self._lock:
            total = 0.0
            for position in self._state.open_positions.values():
                total += position.risk_percentage
            return total
    
    def get_daily_risk_used_pct(self) -> float:
        """
        Get cumulative daily risk used.
        
        Returns:
            Daily risk used as percentage
        """
        with self._lock:
            self._ensure_daily_usage()
            return self._state.current_daily_usage.risk_consumed
    
    def get_daily_risk_remaining_pct(self, equity: float) -> float:
        """
        Get remaining daily risk budget.
        
        Args:
            equity: Current equity for tier lookup
        
        Returns:
            Remaining daily risk as percentage
        """
        with self._lock:
            daily_config = self._config.get_daily_config(equity)
            used = self.get_daily_risk_used_pct()
            return max(0.0, daily_config.max_risk_pct - used)
    
    def get_open_risk_remaining_pct(self, equity: float) -> float:
        """
        Get remaining open position risk budget.
        
        Args:
            equity: Current equity for tier lookup
        
        Returns:
            Remaining open risk as percentage
        """
        with self._lock:
            open_config = self._config.get_open_position_config(equity)
            used = self.get_total_open_risk_pct()
            return max(0.0, open_config.max_risk_pct - used)
    
    def get_current_drawdown_pct(self) -> float:
        """
        Get current drawdown from peak.
        
        Returns:
            Drawdown as percentage
        """
        with self._lock:
            if self._state.peak_equity <= 0:
                return 0.0
            
            drawdown = (
                (self._state.peak_equity - self._state.current_equity) 
                / self._state.peak_equity
            ) * 100
            
            return max(0.0, drawdown)
    
    def get_consecutive_losses(self) -> int:
        """Get number of consecutive losing trades."""
        with self._lock:
            return self._state.consecutive_losses
    
    def get_open_position_count(self) -> int:
        """Get number of open positions."""
        with self._lock:
            return len(self._state.open_positions)
    
    # --------------------------------------------------------
    # HALT MANAGEMENT
    # --------------------------------------------------------
    
    def is_halted(self) -> bool:
        """Check if trading is halted."""
        with self._lock:
            return self._state.is_halted
    
    def get_halt_reason(self) -> Optional[str]:
        """Get reason for halt."""
        with self._lock:
            return self._state.halt_reason
    
    def halt_trading(self, reason: str) -> None:
        """
        Halt all trading.
        
        Args:
            reason: Reason for halt
        """
        with self._lock:
            self._state.is_halted = True
            self._state.halt_reason = reason
            self._state.halted_at = datetime.utcnow()
    
    def resume_trading(self) -> None:
        """Resume trading after halt."""
        with self._lock:
            self._state.is_halted = False
            self._state.halt_reason = None
            self._state.halted_at = None
    
    # --------------------------------------------------------
    # DAILY BUDGET MANAGEMENT
    # --------------------------------------------------------
    
    def reset_daily_budget(self) -> DailyRiskUsage:
        """
        Reset daily budget (called at configured reset time).
        
        Returns:
            The previous day's usage (for persistence)
        """
        with self._lock:
            previous = self._state.current_daily_usage
            
            # Archive previous day if exists
            if previous:
                self._state.daily_history[previous.date] = previous
            
            # Create new daily usage
            today = date.today().isoformat()
            daily_config = self._config.get_daily_config(self._state.current_equity)
            
            self._state.current_daily_usage = DailyRiskUsage(
                date=today,
                risk_budget_limit=daily_config.max_risk_pct,
                risk_consumed=0.0,
                trades_taken=0,
                trades_rejected=0,
            )
            
            # Reset consecutive losses on new day
            self._state.consecutive_losses = 0
            
            return previous
    
    def record_trade_rejection(self) -> None:
        """Record a trade rejection in daily stats."""
        with self._lock:
            self._ensure_daily_usage()
            self._state.current_daily_usage.trades_rejected += 1
    
    # --------------------------------------------------------
    # SNAPSHOT
    # --------------------------------------------------------
    
    def get_snapshot(self) -> RiskBudgetSnapshot:
        """
        Get a complete snapshot of current risk state.
        
        Returns:
            RiskBudgetSnapshot with all current values
        """
        with self._lock:
            equity = self._state.current_equity
            
            # Get configs for current equity level
            per_trade_config = self._config.get_per_trade_config(equity)
            daily_config = self._config.get_daily_config(equity)
            open_config = self._config.get_open_position_config(equity)
            drawdown_config = self._config.get_drawdown_config(equity)
            
            daily_used = self.get_daily_risk_used_pct()
            open_used = self.get_total_open_risk_pct()
            
            return RiskBudgetSnapshot(
                account_equity=equity,
                peak_equity=self._state.peak_equity,
                current_drawdown_pct=self.get_current_drawdown_pct(),
                per_trade_limit_pct=per_trade_config.max_risk_pct,
                daily_limit_pct=daily_config.max_risk_pct,
                daily_used_pct=daily_used,
                daily_remaining_pct=max(0, daily_config.max_risk_pct - daily_used),
                open_limit_pct=open_config.max_risk_pct,
                open_used_pct=open_used,
                open_remaining_pct=max(0, open_config.max_risk_pct - open_used),
                drawdown_limit_pct=drawdown_config.max_drawdown_pct,
                open_positions=len(self._state.open_positions),
                max_positions=open_config.max_positions,
                is_trading_allowed=not self._state.is_halted,
                halt_reason=self._state.halt_reason,
                timestamp=datetime.utcnow(),
            )
    
    # --------------------------------------------------------
    # INTERNAL HELPERS
    # --------------------------------------------------------
    
    def _ensure_daily_usage(self) -> None:
        """Ensure daily usage record exists for today."""
        today = date.today().isoformat()
        
        if (
            self._state.current_daily_usage is None
            or self._state.current_daily_usage.date != today
        ):
            # New day, reset
            self.reset_daily_budget()
    
    def _consume_daily_risk(self, risk_pct: float) -> None:
        """
        Consume daily risk budget.
        
        Args:
            risk_pct: Risk percentage to consume
        """
        self._ensure_daily_usage()
        self._state.current_daily_usage.risk_consumed += risk_pct
        self._state.current_daily_usage.trades_taken += 1
        self._state.current_daily_usage.updated_at = datetime.utcnow()
        
        # Track peak open risk
        current_open = self.get_total_open_risk_pct()
        if current_open > self._state.current_daily_usage.peak_open_risk:
            self._state.current_daily_usage.peak_open_risk = current_open
    
    def _check_drawdown_recovery(self) -> None:
        """Check if drawdown has recovered sufficiently."""
        if not self._state.is_halted:
            return
        
        if self._state.halt_reason != "DRAWDOWN_LIMIT_BREACHED":
            return
        
        drawdown_config = self._config.get_drawdown_config(self._state.current_equity)
        current_dd = self.get_current_drawdown_pct()
        
        # Only auto-resume if manual resume not required
        if not drawdown_config.require_manual_resume:
            if current_dd <= drawdown_config.recovery_threshold_pct:
                self.resume_trading()
