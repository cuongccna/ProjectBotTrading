"""
Risk Budget Manager - Decision Engine.

============================================================
PURPOSE
============================================================
The RiskBudgetManager is the MANDATORY GATEKEEPER between
Signal Engine and Execution Engine.

Every trade request MUST pass through this module before
execution. The module enforces capital preservation through
strict risk budget controls.

============================================================
DECISION LOGIC (PSEUDOCODE)
============================================================

def evaluate_trade_request(request):
    # STEP 1: Validate request
    if request is invalid:
        return REJECT_TRADE (INVALID_PARAMETERS)
    
    # STEP 2: Check system state
    if trading is halted:
        return REJECT_TRADE (TRADING_HALTED)
    
    if equity data is stale:
        return REJECT_TRADE (STALE_EQUITY_DATA)
    
    # STEP 3: Check drawdown
    if current_drawdown >= max_drawdown:
        halt_trading()
        return REJECT_TRADE (DRAWDOWN_LIMIT_BREACHED)
    
    # STEP 4: Calculate proposed risk
    proposed_risk_pct = calculate_risk_percentage(request)
    
    # STEP 5: Check per-trade limit
    if proposed_risk_pct > per_trade_limit:
        reduced_size = calculate_reduced_size(per_trade_limit)
        if reduced_size >= minimum_size:
            return REDUCE_SIZE (EXCEEDS_PER_TRADE_LIMIT)
        else:
            return REJECT_TRADE (EXCEEDS_PER_TRADE_LIMIT)
    
    # STEP 6: Check daily budget
    if daily_remaining < proposed_risk_pct:
        if daily_remaining > 0:
            return REDUCE_SIZE (EXCEEDS_REMAINING_DAILY)
        else:
            return REJECT_TRADE (DAILY_BUDGET_EXHAUSTED)
    
    # STEP 7: Check open position budget
    if open_remaining < proposed_risk_pct:
        if open_remaining > 0:
            return REDUCE_SIZE (EXCEEDS_REMAINING_OPEN)
        else:
            return REJECT_TRADE (OPEN_RISK_LIMIT_REACHED)
    
    # STEP 8: Check position count
    if open_positions >= max_positions:
        return REJECT_TRADE (MAX_POSITIONS_REACHED)
    
    # STEP 9: Check duplicate symbol
    if not allow_pyramiding and has_position(symbol):
        return REJECT_TRADE (DUPLICATE_SYMBOL_POSITION)
    
    # All checks passed
    return ALLOW_TRADE

============================================================
"""

import time
from datetime import datetime
from typing import Optional, List, Tuple
import logging

from .types import (
    TradeRiskRequest,
    TradeRiskResponse,
    TradeDecision,
    RejectReason,
    RiskBudgetDimension,
    BudgetCheckResult,
    EquityUpdate,
    RiskBudgetSnapshot,
    AlertSeverity,
    RiskBudgetError,
    EquityDataError,
    PositionStateError,
    BudgetCalculationError,
)
from .config import RiskBudgetConfig
from .tracker import RiskTracker


logger = logging.getLogger(__name__)


class RiskBudgetManager:
    """
    Risk Budget Manager - Mandatory Trade Gatekeeper.
    
    ============================================================
    INTERFACE FOR EXECUTION ENGINE
    ============================================================
    
    Primary method: evaluate_request(TradeRiskRequest) -> TradeRiskResponse
    
    The Execution Engine MUST call this before executing any trade.
    The response contains:
    - Decision: ALLOW_TRADE, REDUCE_SIZE, or REJECT_TRADE
    - Reason: Why the decision was made
    - Allowed size: Adjusted position size if REDUCE_SIZE
    
    ============================================================
    INTERFACE FOR ACCOUNT MONITOR
    ============================================================
    
    Method: update_equity(EquityUpdate)
    
    Account Monitor MUST call this regularly to provide
    current equity data. Stale data causes trade rejection.
    
    ============================================================
    FAILURE HANDLING
    ============================================================
    
    If any of the following occur:
    - Missing or stale equity data
    - Risk calculation error
    - Inconsistent position state
    
    The module will:
    1. Reject all new trades
    2. Emit a critical alert (via alerting callback)
    3. Log the error for debugging
    
    ============================================================
    """
    
    def __init__(
        self,
        config: RiskBudgetConfig,
        alert_callback: Optional[callable] = None,
    ):
        """
        Initialize the Risk Budget Manager.
        
        Args:
            config: Risk budget configuration
            alert_callback: Optional callback for alerts
                            Signature: (severity: str, title: str, message: str) -> None
        """
        self._config = config
        self._tracker = RiskTracker(config)
        self._alert_callback = alert_callback
        
        # Error tracking for escalation
        self._consecutive_errors = 0
        self._last_error_time: Optional[datetime] = None
        
        logger.info("RiskBudgetManager initialized")
    
    # --------------------------------------------------------
    # PRIMARY INTERFACE - TRADE EVALUATION
    # --------------------------------------------------------
    
    def evaluate_request(self, request: TradeRiskRequest) -> TradeRiskResponse:
        """
        Evaluate a trade request against risk budget.
        
        This is the PRIMARY interface for the Execution Engine.
        
        Args:
            request: Trade risk request to evaluate
        
        Returns:
            TradeRiskResponse with decision and details
        """
        start_time = time.perf_counter()
        
        try:
            # Run the evaluation
            response = self._do_evaluation(request)
            
            # Track rejection if applicable
            if response.is_rejected():
                self._tracker.record_trade_rejection()
                self._check_consecutive_rejections()
            
            # Reset error counter on success
            self._consecutive_errors = 0
            
            return response
            
        except Exception as e:
            # Handle unexpected errors
            return self._handle_evaluation_error(request, e, start_time)
    
    def _do_evaluation(self, request: TradeRiskRequest) -> TradeRiskResponse:
        """
        Internal evaluation logic.
        
        Args:
            request: Trade risk request
        
        Returns:
            TradeRiskResponse
        """
        start_time = time.perf_counter()
        budget_checks: List[BudgetCheckResult] = []
        
        # Get current equity
        equity = self._tracker.get_current_equity()
        
        # ============================================
        # STEP 1: Validate Request
        # ============================================
        validation_errors = request.validate()
        if validation_errors:
            logger.warning(f"Invalid request: {validation_errors}")
            return self._create_reject_response(
                request=request,
                reason=RejectReason.INVALID_PARAMETERS,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # ============================================
        # STEP 2: Check System State
        # ============================================
        
        # Check if trading is halted
        if self._tracker.is_halted():
            logger.info(f"Trade rejected: Trading halted - {self._tracker.get_halt_reason()}")
            return self._create_reject_response(
                request=request,
                reason=RejectReason.TRADING_HALTED,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # Check if equity data is stale
        if self._tracker.is_equity_stale():
            logger.warning("Trade rejected: Stale equity data")
            self._emit_alert(
                AlertSeverity.CRITICAL,
                "Stale Equity Data",
                "Equity data is stale - all trades rejected",
            )
            return self._create_reject_response(
                request=request,
                reason=RejectReason.STALE_EQUITY_DATA,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # Check minimum equity
        if equity < self._config.equity_tracking.min_equity_usd:
            logger.warning(f"Trade rejected: Equity {equity} below minimum")
            return self._create_reject_response(
                request=request,
                reason=RejectReason.TRADING_HALTED,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # ============================================
        # STEP 3: Check Drawdown
        # ============================================
        drawdown_result = self._check_drawdown(equity)
        budget_checks.append(drawdown_result)
        
        if not drawdown_result.passed:
            self._tracker.halt_trading("DRAWDOWN_LIMIT_BREACHED")
            self._emit_alert(
                AlertSeverity.EMERGENCY,
                "Drawdown Limit Breached",
                f"Drawdown {drawdown_result.budget_used:.1f}% exceeded limit. Trading halted.",
            )
            return self._create_reject_response(
                request=request,
                reason=RejectReason.DRAWDOWN_LIMIT_BREACHED,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # ============================================
        # STEP 4: Calculate Proposed Risk
        # ============================================
        proposed_risk_pct = request.calculate_risk_percentage(equity)
        
        logger.debug(
            f"Evaluating: {request.symbol} | "
            f"Size: {request.position_size} | "
            f"Risk: {proposed_risk_pct:.2f}%"
        )
        
        # ============================================
        # STEP 5: Check Per-Trade Limit
        # ============================================
        per_trade_result = self._check_per_trade(equity, proposed_risk_pct)
        budget_checks.append(per_trade_result)
        
        # ============================================
        # STEP 6: Check Daily Budget
        # ============================================
        daily_result = self._check_daily_budget(equity, proposed_risk_pct)
        budget_checks.append(daily_result)
        
        # ============================================
        # STEP 7: Check Open Position Budget
        # ============================================
        open_result = self._check_open_position_budget(equity, proposed_risk_pct)
        budget_checks.append(open_result)
        
        # ============================================
        # STEP 8: Check Position Count
        # ============================================
        position_count = self._tracker.get_open_position_count()
        open_config = self._config.get_open_position_config(equity)
        
        if position_count >= open_config.max_positions:
            logger.info(f"Trade rejected: Max positions reached ({position_count})")
            return self._create_reject_response(
                request=request,
                reason=RejectReason.MAX_POSITIONS_REACHED,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # ============================================
        # STEP 9: Check Duplicate Symbol
        # ============================================
        if not open_config.allow_pyramiding:
            if self._tracker.has_position_for_symbol(request.symbol):
                logger.info(f"Trade rejected: Duplicate position for {request.symbol}")
                return self._create_reject_response(
                    request=request,
                    reason=RejectReason.DUPLICATE_SYMBOL_POSITION,
                    budget_checks=budget_checks,
                    equity=equity,
                    start_time=start_time,
                )
        
        # ============================================
        # STEP 10: Check Consecutive Losses
        # ============================================
        daily_config = self._config.get_daily_config(equity)
        if self._tracker.get_consecutive_losses() >= daily_config.hard_stop_after_losses:
            logger.info("Trade rejected: Consecutive loss limit reached")
            return self._create_reject_response(
                request=request,
                reason=RejectReason.DAILY_BUDGET_EXHAUSTED,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # ============================================
        # STEP 11: Determine Decision
        # ============================================
        
        # Check if all passed at full size
        all_passed = all(check.passed for check in budget_checks)
        
        if all_passed:
            # ALLOW_TRADE at full size
            return self._create_allow_response(
                request=request,
                proposed_risk_pct=proposed_risk_pct,
                allowed_risk_pct=proposed_risk_pct,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # Check if we can reduce size
        max_allowable = self._calculate_max_allowable_risk(equity, budget_checks)
        
        if max_allowable <= 0:
            # No room for any trade
            primary_reason = self._get_primary_reject_reason(budget_checks)
            return self._create_reject_response(
                request=request,
                reason=primary_reason,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # Calculate reduced size
        size_ratio = max_allowable / proposed_risk_pct
        reduced_size = request.position_size * size_ratio
        
        # Check if reduced size meets minimum
        per_trade_config = self._config.get_per_trade_config(equity)
        min_risk = per_trade_config.min_risk_pct
        reduced_risk = (reduced_size / request.position_size) * proposed_risk_pct
        
        if reduced_risk < min_risk:
            # Reduced size too small
            primary_reason = self._get_primary_reject_reason(budget_checks)
            return self._create_reject_response(
                request=request,
                reason=primary_reason,
                budget_checks=budget_checks,
                equity=equity,
                start_time=start_time,
            )
        
        # REDUCE_SIZE
        primary_reason = self._get_primary_reject_reason(budget_checks)
        return self._create_reduce_response(
            request=request,
            proposed_risk_pct=proposed_risk_pct,
            allowed_risk_pct=max_allowable,
            reduced_size=reduced_size,
            reason=primary_reason,
            budget_checks=budget_checks,
            equity=equity,
            start_time=start_time,
        )
    
    # --------------------------------------------------------
    # BUDGET CHECKS
    # --------------------------------------------------------
    
    def _check_drawdown(self, equity: float) -> BudgetCheckResult:
        """Check current drawdown against limit."""
        drawdown_config = self._config.get_drawdown_config(equity)
        current_drawdown = self._tracker.get_current_drawdown_pct()
        
        passed = current_drawdown < drawdown_config.max_drawdown_pct
        
        return BudgetCheckResult(
            dimension=RiskBudgetDimension.DRAWDOWN,
            passed=passed,
            budget_limit=drawdown_config.max_drawdown_pct,
            budget_used=current_drawdown,
            budget_remaining=max(0, drawdown_config.max_drawdown_pct - current_drawdown),
            proposed_risk=0.0,  # Not applicable for drawdown
            reason=RejectReason.DRAWDOWN_LIMIT_BREACHED if not passed else None,
        )
    
    def _check_per_trade(
        self,
        equity: float,
        proposed_risk_pct: float,
    ) -> BudgetCheckResult:
        """Check proposed risk against per-trade limit."""
        per_trade_config = self._config.get_per_trade_config(equity)
        
        # Apply drawdown reduction if applicable
        drawdown = self._tracker.get_current_drawdown_pct()
        limit = per_trade_config.max_risk_pct
        
        if drawdown >= per_trade_config.reduce_when_drawdown_pct:
            limit *= per_trade_config.reduction_factor
        
        passed = proposed_risk_pct <= limit
        
        return BudgetCheckResult(
            dimension=RiskBudgetDimension.PER_TRADE,
            passed=passed,
            budget_limit=limit,
            budget_used=0.0,  # Per-trade is not cumulative
            budget_remaining=limit,
            proposed_risk=proposed_risk_pct,
            would_exceed_by=max(0, proposed_risk_pct - limit),
            max_allowable_risk=limit,
            reason=RejectReason.EXCEEDS_PER_TRADE_LIMIT if not passed else None,
        )
    
    def _check_daily_budget(
        self,
        equity: float,
        proposed_risk_pct: float,
    ) -> BudgetCheckResult:
        """Check proposed risk against remaining daily budget."""
        daily_config = self._config.get_daily_config(equity)
        daily_used = self._tracker.get_daily_risk_used_pct()
        daily_remaining = max(0, daily_config.max_risk_pct - daily_used)
        
        passed = proposed_risk_pct <= daily_remaining
        
        # Determine reason
        if not passed:
            if daily_remaining <= 0:
                reason = RejectReason.DAILY_BUDGET_EXHAUSTED
            else:
                reason = RejectReason.EXCEEDS_REMAINING_DAILY
        else:
            reason = None
        
        return BudgetCheckResult(
            dimension=RiskBudgetDimension.DAILY_CUMULATIVE,
            passed=passed,
            budget_limit=daily_config.max_risk_pct,
            budget_used=daily_used,
            budget_remaining=daily_remaining,
            proposed_risk=proposed_risk_pct,
            would_exceed_by=max(0, proposed_risk_pct - daily_remaining),
            max_allowable_risk=daily_remaining,
            reason=reason,
        )
    
    def _check_open_position_budget(
        self,
        equity: float,
        proposed_risk_pct: float,
    ) -> BudgetCheckResult:
        """Check proposed risk against remaining open position budget."""
        open_config = self._config.get_open_position_config(equity)
        open_used = self._tracker.get_total_open_risk_pct()
        open_remaining = max(0, open_config.max_risk_pct - open_used)
        
        passed = proposed_risk_pct <= open_remaining
        
        # Determine reason
        if not passed:
            if open_remaining <= 0:
                reason = RejectReason.OPEN_RISK_LIMIT_REACHED
            else:
                reason = RejectReason.EXCEEDS_REMAINING_OPEN
        else:
            reason = None
        
        return BudgetCheckResult(
            dimension=RiskBudgetDimension.OPEN_POSITION,
            passed=passed,
            budget_limit=open_config.max_risk_pct,
            budget_used=open_used,
            budget_remaining=open_remaining,
            proposed_risk=proposed_risk_pct,
            would_exceed_by=max(0, proposed_risk_pct - open_remaining),
            max_allowable_risk=open_remaining,
            reason=reason,
        )
    
    # --------------------------------------------------------
    # RESPONSE BUILDERS
    # --------------------------------------------------------
    
    def _create_allow_response(
        self,
        request: TradeRiskRequest,
        proposed_risk_pct: float,
        allowed_risk_pct: float,
        budget_checks: List[BudgetCheckResult],
        equity: float,
        start_time: float,
    ) -> TradeRiskResponse:
        """Create ALLOW_TRADE response."""
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        return TradeRiskResponse(
            decision=TradeDecision.ALLOW_TRADE,
            request_id=request.request_id,
            budget_checks=budget_checks,
            primary_reason=None,
            original_risk_pct=proposed_risk_pct,
            allowed_risk_pct=allowed_risk_pct,
            original_position_size=request.position_size,
            allowed_position_size=request.position_size,
            size_reduction_pct=0.0,
            account_equity=equity,
            daily_risk_used=self._tracker.get_daily_risk_used_pct(),
            open_risk_used=self._tracker.get_total_open_risk_pct(),
            current_drawdown=self._tracker.get_current_drawdown_pct(),
            timestamp=datetime.utcnow(),
            evaluation_duration_ms=duration_ms,
        )
    
    def _create_reduce_response(
        self,
        request: TradeRiskRequest,
        proposed_risk_pct: float,
        allowed_risk_pct: float,
        reduced_size: float,
        reason: RejectReason,
        budget_checks: List[BudgetCheckResult],
        equity: float,
        start_time: float,
    ) -> TradeRiskResponse:
        """Create REDUCE_SIZE response."""
        duration_ms = (time.perf_counter() - start_time) * 1000
        size_reduction = ((request.position_size - reduced_size) / request.position_size) * 100
        
        logger.info(
            f"Trade size reduced: {request.symbol} | "
            f"Original: {request.position_size:.4f} | "
            f"Reduced: {reduced_size:.4f} | "
            f"Reason: {reason.value}"
        )
        
        return TradeRiskResponse(
            decision=TradeDecision.REDUCE_SIZE,
            request_id=request.request_id,
            budget_checks=budget_checks,
            primary_reason=reason,
            original_risk_pct=proposed_risk_pct,
            allowed_risk_pct=allowed_risk_pct,
            original_position_size=request.position_size,
            allowed_position_size=reduced_size,
            size_reduction_pct=size_reduction,
            account_equity=equity,
            daily_risk_used=self._tracker.get_daily_risk_used_pct(),
            open_risk_used=self._tracker.get_total_open_risk_pct(),
            current_drawdown=self._tracker.get_current_drawdown_pct(),
            timestamp=datetime.utcnow(),
            evaluation_duration_ms=duration_ms,
        )
    
    def _create_reject_response(
        self,
        request: TradeRiskRequest,
        reason: RejectReason,
        budget_checks: List[BudgetCheckResult],
        equity: float,
        start_time: float,
    ) -> TradeRiskResponse:
        """Create REJECT_TRADE response."""
        duration_ms = (time.perf_counter() - start_time) * 1000
        proposed_risk = request.calculate_risk_percentage(equity) if equity > 0 else 0
        
        logger.info(f"Trade rejected: {request.symbol} | Reason: {reason.value}")
        
        return TradeRiskResponse(
            decision=TradeDecision.REJECT_TRADE,
            request_id=request.request_id,
            budget_checks=budget_checks,
            primary_reason=reason,
            original_risk_pct=proposed_risk,
            allowed_risk_pct=0.0,
            original_position_size=request.position_size,
            allowed_position_size=0.0,
            size_reduction_pct=100.0,
            account_equity=equity,
            daily_risk_used=self._tracker.get_daily_risk_used_pct(),
            open_risk_used=self._tracker.get_total_open_risk_pct(),
            current_drawdown=self._tracker.get_current_drawdown_pct(),
            timestamp=datetime.utcnow(),
            evaluation_duration_ms=duration_ms,
        )
    
    # --------------------------------------------------------
    # HELPER METHODS
    # --------------------------------------------------------
    
    def _calculate_max_allowable_risk(
        self,
        equity: float,
        budget_checks: List[BudgetCheckResult],
    ) -> float:
        """
        Calculate maximum allowable risk given budget constraints.
        
        Takes the minimum of all budget remaining values.
        """
        max_risk = float('inf')
        
        for check in budget_checks:
            if check.dimension == RiskBudgetDimension.DRAWDOWN:
                continue  # Drawdown doesn't have a per-trade limit
            
            if check.max_allowable_risk < max_risk:
                max_risk = check.max_allowable_risk
        
        return max_risk if max_risk != float('inf') else 0.0
    
    def _get_primary_reject_reason(
        self,
        budget_checks: List[BudgetCheckResult],
    ) -> RejectReason:
        """Get the primary reason for rejection from failed checks."""
        # Priority order
        priority = [
            RejectReason.DRAWDOWN_LIMIT_BREACHED,
            RejectReason.DAILY_BUDGET_EXHAUSTED,
            RejectReason.OPEN_RISK_LIMIT_REACHED,
            RejectReason.EXCEEDS_PER_TRADE_LIMIT,
            RejectReason.EXCEEDS_REMAINING_DAILY,
            RejectReason.EXCEEDS_REMAINING_OPEN,
        ]
        
        failed_reasons = [
            check.reason for check in budget_checks 
            if not check.passed and check.reason
        ]
        
        for reason in priority:
            if reason in failed_reasons:
                return reason
        
        return failed_reasons[0] if failed_reasons else RejectReason.CALCULATION_ERROR
    
    def _handle_evaluation_error(
        self,
        request: TradeRiskRequest,
        error: Exception,
        start_time: float,
    ) -> TradeRiskResponse:
        """Handle unexpected errors during evaluation."""
        self._consecutive_errors += 1
        self._last_error_time = datetime.utcnow()
        
        logger.error(f"Evaluation error: {error}", exc_info=True)
        
        # Emit critical alert
        self._emit_alert(
            AlertSeverity.CRITICAL,
            "Risk Calculation Error",
            f"Error evaluating trade: {error}. Rejecting all trades.",
        )
        
        # Escalate if too many errors
        if self._consecutive_errors >= 3:
            self._emit_alert(
                AlertSeverity.EMERGENCY,
                "System Risk Escalation",
                f"Multiple consecutive errors ({self._consecutive_errors}). "
                "Escalating to System Risk Controller.",
            )
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        return TradeRiskResponse(
            decision=TradeDecision.REJECT_TRADE,
            request_id=request.request_id,
            budget_checks=[],
            primary_reason=RejectReason.CALCULATION_ERROR,
            original_risk_pct=0.0,
            allowed_risk_pct=0.0,
            original_position_size=request.position_size,
            allowed_position_size=0.0,
            size_reduction_pct=100.0,
            account_equity=self._tracker.get_current_equity(),
            daily_risk_used=0.0,
            open_risk_used=0.0,
            current_drawdown=0.0,
            timestamp=datetime.utcnow(),
            evaluation_duration_ms=duration_ms,
        )
    
    def _check_consecutive_rejections(self) -> None:
        """Check for too many consecutive rejections."""
        # Implementation would track and alert
        pass
    
    def _emit_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
    ) -> None:
        """Emit an alert via the callback."""
        if self._alert_callback:
            try:
                self._alert_callback(severity.value, title, message)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")
    
    # --------------------------------------------------------
    # ACCOUNT MONITOR INTERFACE
    # --------------------------------------------------------
    
    def update_equity(self, update: EquityUpdate) -> None:
        """
        Update account equity from Account Monitor.
        
        This MUST be called regularly for the system to function.
        
        Args:
            update: Equity update from Account Monitor
        """
        self._tracker.update_equity(update)
        
        # Check for warning thresholds
        self._check_warning_thresholds()
    
    def _check_warning_thresholds(self) -> None:
        """Check and emit warnings for approaching limits."""
        equity = self._tracker.get_current_equity()
        
        # Check daily usage warning
        daily_config = self._config.get_daily_config(equity)
        daily_used = self._tracker.get_daily_risk_used_pct()
        daily_pct = (daily_used / daily_config.max_risk_pct) * 100 if daily_config.max_risk_pct > 0 else 0
        
        if daily_pct >= self._config.alerting.daily_usage_warning_pct:
            self._emit_alert(
                AlertSeverity.WARNING,
                "Daily Budget Warning",
                f"Daily risk budget {daily_pct:.0f}% used ({daily_used:.2f}%/{daily_config.max_risk_pct:.2f}%)",
            )
        
        # Check drawdown warning
        drawdown = self._tracker.get_current_drawdown_pct()
        if drawdown >= self._config.alerting.drawdown_warning_pct:
            self._emit_alert(
                AlertSeverity.WARNING,
                "Drawdown Warning",
                f"Current drawdown: {drawdown:.1f}%",
            )
    
    # --------------------------------------------------------
    # POSITION MANAGEMENT INTERFACE
    # --------------------------------------------------------
    
    def register_position_opened(
        self,
        position_id: str,
        symbol: str,
        exchange: str,
        direction: str,
        entry_price: float,
        stop_loss_price: float,
        position_size: float,
    ) -> None:
        """
        Register that a position was opened.
        
        Called by Execution Engine after trade executes.
        
        Args:
            position_id: Unique position identifier
            symbol: Trading pair
            exchange: Exchange identifier
            direction: 'LONG' or 'SHORT'
            entry_price: Actual entry price
            stop_loss_price: Stop loss price
            position_size: Actual position size
        """
        self._tracker.register_position(
            position_id=position_id,
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            position_size=position_size,
        )
        
        logger.info(
            f"Position registered: {position_id} | {symbol} | "
            f"{direction} | Size: {position_size}"
        )
    
    def register_position_closed(
        self,
        position_id: str,
        realized_pnl: float,
    ) -> None:
        """
        Register that a position was closed.
        
        Releases the held risk budget.
        
        Args:
            position_id: Position identifier
            realized_pnl: Realized P&L from the trade
        """
        position = self._tracker.close_position(position_id, realized_pnl)
        
        logger.info(
            f"Position closed: {position_id} | {position.symbol} | "
            f"P&L: {realized_pnl:.2f}"
        )
    
    def update_stop_loss(
        self,
        position_id: str,
        new_stop_loss: float,
    ) -> None:
        """
        Update stop loss for a position.
        
        Args:
            position_id: Position identifier
            new_stop_loss: New stop loss price
        """
        self._tracker.update_stop_loss(position_id, new_stop_loss)
    
    # --------------------------------------------------------
    # STATUS INTERFACE
    # --------------------------------------------------------
    
    def get_snapshot(self) -> RiskBudgetSnapshot:
        """
        Get current risk budget snapshot.
        
        Returns:
            Complete snapshot of current state
        """
        return self._tracker.get_snapshot()
    
    def halt_trading(self, reason: str) -> None:
        """
        Halt all trading.
        
        Args:
            reason: Reason for halt
        """
        self._tracker.halt_trading(reason)
        self._emit_alert(
            AlertSeverity.EMERGENCY,
            "Trading Halted",
            f"Reason: {reason}",
        )
    
    def resume_trading(self) -> None:
        """Resume trading after halt."""
        self._tracker.resume_trading()
        self._emit_alert(
            AlertSeverity.INFO,
            "Trading Resumed",
            "Trading has been resumed",
        )
    
    def reset_daily_budget(self) -> None:
        """Reset daily budget (called at configured reset time)."""
        previous = self._tracker.reset_daily_budget()
        
        if previous:
            logger.info(
                f"Daily budget reset | Previous day: {previous.date} | "
                f"Trades: {previous.trades_taken} | "
                f"Risk used: {previous.risk_consumed:.2f}%"
            )
