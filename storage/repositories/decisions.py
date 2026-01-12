"""
Decision & Risk Repositories.

============================================================
PURPOSE
============================================================
Repositories for trading decisions and risk events. These
handle the decision-making audit trail and risk management
records.

============================================================
DATA LIFECYCLE
============================================================
- Stage: DECISION
- Mutability: APPEND-ONLY for decisions, state transitions tracked
- Full audit trail required for compliance

============================================================
REPOSITORIES
============================================================
- TradeDecisionRepository: Trading decisions and eligibility
- RiskEventRepository: Risk events and system halts

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import select, and_, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from storage.models.decisions import (
    TradingDecision,
    TradeEligibilityEvaluation,
    VetoEvent,
    DecisionStateTransition,
)
from storage.models.risk_management import (
    SystemHalt,
    StrategyPause,
    DrawdownEvent,
    RiskThresholdBreach,
    RiskConfigurationAudit,
)
from storage.repositories.base import BaseRepository
from storage.repositories.exceptions import (
    RecordNotFoundError,
    RepositoryException,
    ImmutableRecordError,
)


class TradeDecisionRepository(BaseRepository[TradingDecision]):
    """
    Repository for trading decisions.
    
    ============================================================
    SCOPE
    ============================================================
    Manages TradingDecision, TradeEligibilityEvaluation,
    VetoEvent, and DecisionStateTransition records. Complete
    audit trail for all trading decisions.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - TradingDecision: Core trading decisions
    - TradeEligibilityEvaluation: Eligibility checks
    - VetoEvent: Decision vetoes
    - DecisionStateTransition: State change audit
    
    ============================================================
    IMMUTABILITY
    ============================================================
    Trading decisions are APPEND-ONLY. State changes are tracked
    via DecisionStateTransition records, not updates.
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, TradingDecision, "TradeDecisionRepository")
    
    # =========================================================
    # TRADING DECISION OPERATIONS
    # =========================================================
    
    def create_trading_decision(
        self,
        symbol: str,
        decision_timestamp: datetime,
        decision_type: str,
        direction: str,
        strategy_id: str,
        strategy_version: str,
        signal_strength: Decimal,
        confidence: Decimal,
        recommended_size: Decimal,
        recommended_entry: Decimal,
        recommended_stop_loss: Decimal,
        recommended_take_profit: Decimal,
        reasoning: Dict[str, Any],
        input_scores: Dict[str, Decimal],
        state: str = "pending",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TradingDecision:
        """
        Create a trading decision.
        
        Args:
            symbol: Trading symbol
            decision_timestamp: Decision timestamp
            decision_type: Decision type (entry, exit, scale)
            direction: Trade direction (long, short)
            strategy_id: Strategy identifier
            strategy_version: Strategy version
            signal_strength: Signal strength
            confidence: Decision confidence
            recommended_size: Recommended position size
            recommended_entry: Recommended entry price
            recommended_stop_loss: Recommended stop loss
            recommended_take_profit: Recommended take profit
            reasoning: Decision reasoning details
            input_scores: Input scores used
            state: Initial state
            metadata: Additional metadata
            
        Returns:
            Created TradingDecision record
        """
        entity = TradingDecision(
            symbol=symbol,
            decision_timestamp=decision_timestamp,
            decision_type=decision_type,
            direction=direction,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            signal_strength=signal_strength,
            confidence=confidence,
            recommended_size=recommended_size,
            recommended_entry=recommended_entry,
            recommended_stop_loss=recommended_stop_loss,
            recommended_take_profit=recommended_take_profit,
            reasoning=reasoning,
            input_scores=input_scores,
            state=state,
            metadata=metadata or {},
        )
        return self._add(entity)
    
    def get_decision_by_id(
        self,
        decision_id: UUID
    ) -> Optional[TradingDecision]:
        """Get trading decision by ID."""
        return self._get_by_id(decision_id)
    
    def get_decision_by_id_or_raise(
        self,
        decision_id: UUID
    ) -> TradingDecision:
        """Get trading decision by ID, raising if not found."""
        return self._get_by_id_or_raise(decision_id, "decision_id")
    
    def list_decisions_by_symbol(
        self,
        symbol: str,
        state: Optional[str] = None,
        limit: int = 100
    ) -> List[TradingDecision]:
        """
        List trading decisions by symbol.
        
        Args:
            symbol: Trading symbol
            state: Optional state filter
            limit: Maximum records to return
            
        Returns:
            List of TradingDecision
        """
        conditions = [TradingDecision.symbol == symbol]
        if state:
            conditions.append(TradingDecision.state == state)
        
        stmt = (
            select(TradingDecision)
            .where(and_(*conditions))
            .order_by(desc(TradingDecision.decision_timestamp))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_decisions_by_strategy(
        self,
        strategy_id: str,
        limit: int = 100
    ) -> List[TradingDecision]:
        """
        List trading decisions by strategy.
        
        Args:
            strategy_id: Strategy identifier
            limit: Maximum records to return
            
        Returns:
            List of TradingDecision
        """
        stmt = (
            select(TradingDecision)
            .where(TradingDecision.strategy_id == strategy_id)
            .order_by(desc(TradingDecision.decision_timestamp))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_decisions_by_state(
        self,
        state: str,
        limit: int = 100
    ) -> List[TradingDecision]:
        """
        List trading decisions by state.
        
        Args:
            state: Decision state
            limit: Maximum records to return
            
        Returns:
            List of TradingDecision
        """
        stmt = (
            select(TradingDecision)
            .where(TradingDecision.state == state)
            .order_by(desc(TradingDecision.decision_timestamp))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_decisions_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None,
        limit: int = 1000
    ) -> List[TradingDecision]:
        """
        List trading decisions within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            symbol: Optional symbol filter
            limit: Maximum records to return
            
        Returns:
            List of TradingDecision
        """
        conditions = [
            TradingDecision.decision_timestamp >= start_time,
            TradingDecision.decision_timestamp < end_time,
        ]
        if symbol:
            conditions.append(TradingDecision.symbol == symbol)
        
        stmt = (
            select(TradingDecision)
            .where(and_(*conditions))
            .order_by(TradingDecision.decision_timestamp)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_pending_decisions(
        self,
        limit: int = 100
    ) -> List[TradingDecision]:
        """
        List pending trading decisions.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            List of pending TradingDecision records
        """
        return self.list_decisions_by_state("pending", limit)
    
    # =========================================================
    # DECISION STATE TRANSITION OPERATIONS
    # =========================================================
    
    def record_state_transition(
        self,
        decision_id: UUID,
        from_state: str,
        to_state: str,
        transitioned_at: datetime,
        reason: str,
        triggered_by: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DecisionStateTransition:
        """
        Record a decision state transition.
        
        Args:
            decision_id: Reference to trading decision
            from_state: Previous state
            to_state: New state
            transitioned_at: Transition timestamp
            reason: Transition reason
            triggered_by: What triggered the transition
            metadata: Additional metadata
            
        Returns:
            Created DecisionStateTransition record
        """
        entity = DecisionStateTransition(
            decision_id=decision_id,
            from_state=from_state,
            to_state=to_state,
            transitioned_at=transitioned_at,
            reason=reason,
            triggered_by=triggered_by,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.info(
                f"Decision {decision_id}: {from_state} -> {to_state}"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_state_transition", {
                "decision_id": str(decision_id),
                "transition": f"{from_state} -> {to_state}"
            })
            raise
    
    def list_state_transitions_by_decision(
        self,
        decision_id: UUID
    ) -> List[DecisionStateTransition]:
        """
        List all state transitions for a decision.
        
        Args:
            decision_id: The decision UUID
            
        Returns:
            List of DecisionStateTransition
        """
        stmt = (
            select(DecisionStateTransition)
            .where(DecisionStateTransition.decision_id == decision_id)
            .order_by(DecisionStateTransition.transitioned_at)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_state_transitions_by_decision", {
                "decision_id": str(decision_id)
            })
            raise
    
    # =========================================================
    # ELIGIBILITY EVALUATION OPERATIONS
    # =========================================================
    
    def create_eligibility_evaluation(
        self,
        decision_id: UUID,
        evaluated_at: datetime,
        is_eligible: bool,
        evaluator_version: str,
        checks_passed: List[str],
        checks_failed: List[str],
        details: Dict[str, Any],
    ) -> TradeEligibilityEvaluation:
        """
        Create an eligibility evaluation record.
        
        Args:
            decision_id: Reference to trading decision
            evaluated_at: Evaluation timestamp
            is_eligible: Whether trade is eligible
            evaluator_version: Evaluator version
            checks_passed: List of passed checks
            checks_failed: List of failed checks
            details: Detailed evaluation results
            
        Returns:
            Created TradeEligibilityEvaluation record
        """
        entity = TradeEligibilityEvaluation(
            decision_id=decision_id,
            evaluated_at=evaluated_at,
            is_eligible=is_eligible,
            evaluator_version=evaluator_version,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            details=details,
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.debug(
                f"Eligibility evaluation for decision {decision_id}: {is_eligible}"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "create_eligibility_evaluation", {
                "decision_id": str(decision_id)
            })
            raise
    
    def get_eligibility_by_decision(
        self,
        decision_id: UUID
    ) -> Optional[TradeEligibilityEvaluation]:
        """
        Get eligibility evaluation for a decision.
        
        Args:
            decision_id: The decision UUID
            
        Returns:
            TradeEligibilityEvaluation or None
        """
        stmt = select(TradeEligibilityEvaluation).where(
            TradeEligibilityEvaluation.decision_id == decision_id
        )
        try:
            result = self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            self._handle_db_error(e, "get_eligibility_by_decision", {
                "decision_id": str(decision_id)
            })
            raise
    
    # =========================================================
    # VETO EVENT OPERATIONS
    # =========================================================
    
    def record_veto_event(
        self,
        decision_id: UUID,
        vetoed_at: datetime,
        veto_reason: str,
        veto_source: str,
        veto_type: str,
        details: Dict[str, Any],
    ) -> VetoEvent:
        """
        Record a veto event for a decision.
        
        Args:
            decision_id: Reference to trading decision
            vetoed_at: Veto timestamp
            veto_reason: Reason for veto
            veto_source: What vetoed the decision
            veto_type: Veto type (risk, manual, system)
            details: Detailed veto information
            
        Returns:
            Created VetoEvent record
        """
        entity = VetoEvent(
            decision_id=decision_id,
            vetoed_at=vetoed_at,
            veto_reason=veto_reason,
            veto_source=veto_source,
            veto_type=veto_type,
            details=details,
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.warning(
                f"Decision {decision_id} vetoed: {veto_reason}"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_veto_event", {
                "decision_id": str(decision_id)
            })
            raise
    
    def list_veto_events_by_decision(
        self,
        decision_id: UUID
    ) -> List[VetoEvent]:
        """
        List all veto events for a decision.
        
        Args:
            decision_id: The decision UUID
            
        Returns:
            List of VetoEvent
        """
        stmt = (
            select(VetoEvent)
            .where(VetoEvent.decision_id == decision_id)
            .order_by(VetoEvent.vetoed_at)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_veto_events_by_decision", {
                "decision_id": str(decision_id)
            })
            raise
    
    def list_veto_events_by_type(
        self,
        veto_type: str,
        limit: int = 100
    ) -> List[VetoEvent]:
        """
        List veto events by type.
        
        Args:
            veto_type: Veto type
            limit: Maximum records to return
            
        Returns:
            List of VetoEvent
        """
        stmt = (
            select(VetoEvent)
            .where(VetoEvent.veto_type == veto_type)
            .order_by(desc(VetoEvent.vetoed_at))
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_veto_events_by_type", {
                "veto_type": veto_type
            })
            raise


class RiskEventRepository(BaseRepository[SystemHalt]):
    """
    Repository for risk events.
    
    ============================================================
    SCOPE
    ============================================================
    Manages SystemHalt, StrategyPause, DrawdownEvent,
    RiskThresholdBreach, and RiskConfigurationAudit records.
    Complete audit trail for all risk management events.
    
    ============================================================
    MODELS MANAGED
    ============================================================
    - SystemHalt: System-wide trading halts
    - StrategyPause: Strategy-specific pauses
    - DrawdownEvent: Drawdown tracking
    - RiskThresholdBreach: Risk limit violations
    - RiskConfigurationAudit: Risk config changes
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, SystemHalt, "RiskEventRepository")
    
    # =========================================================
    # SYSTEM HALT OPERATIONS
    # =========================================================
    
    def record_system_halt(
        self,
        halted_at: datetime,
        reason: str,
        halt_type: str,
        triggered_by: str,
        severity: str,
        affected_symbols: List[str],
        details: Dict[str, Any],
        expected_duration_minutes: Optional[int] = None,
    ) -> SystemHalt:
        """
        Record a system halt.
        
        Args:
            halted_at: Halt timestamp
            reason: Halt reason
            halt_type: Halt type (emergency, scheduled, risk)
            triggered_by: What triggered the halt
            severity: Severity level
            affected_symbols: Affected trading symbols
            details: Detailed halt information
            expected_duration_minutes: Expected duration
            
        Returns:
            Created SystemHalt record
        """
        entity = SystemHalt(
            halted_at=halted_at,
            reason=reason,
            halt_type=halt_type,
            triggered_by=triggered_by,
            severity=severity,
            affected_symbols=affected_symbols,
            details=details,
            expected_duration_minutes=expected_duration_minutes,
            is_active=True,
        )
        return self._add(entity)
    
    def get_system_halt_by_id(
        self,
        halt_id: UUID
    ) -> Optional[SystemHalt]:
        """Get system halt by ID."""
        return self._get_by_id(halt_id)
    
    def get_active_system_halt(self) -> Optional[SystemHalt]:
        """
        Get the currently active system halt.
        
        Returns:
            Active SystemHalt or None
        """
        stmt = (
            select(SystemHalt)
            .where(SystemHalt.is_active == True)
            .order_by(desc(SystemHalt.halted_at))
            .limit(1)
        )
        return self._execute_scalar(stmt)
    
    def list_system_halts(
        self,
        include_resolved: bool = True,
        limit: int = 100
    ) -> List[SystemHalt]:
        """
        List system halts.
        
        Args:
            include_resolved: Whether to include resolved halts
            limit: Maximum records to return
            
        Returns:
            List of SystemHalt
        """
        if include_resolved:
            stmt = (
                select(SystemHalt)
                .order_by(desc(SystemHalt.halted_at))
                .limit(limit)
            )
        else:
            stmt = (
                select(SystemHalt)
                .where(SystemHalt.is_active == True)
                .order_by(desc(SystemHalt.halted_at))
                .limit(limit)
            )
        return self._execute_query(stmt)
    
    # =========================================================
    # STRATEGY PAUSE OPERATIONS
    # =========================================================
    
    def record_strategy_pause(
        self,
        strategy_id: str,
        paused_at: datetime,
        reason: str,
        pause_type: str,
        triggered_by: str,
        affected_symbols: List[str],
        details: Dict[str, Any],
    ) -> StrategyPause:
        """
        Record a strategy pause.
        
        Args:
            strategy_id: Strategy identifier
            paused_at: Pause timestamp
            reason: Pause reason
            pause_type: Pause type
            triggered_by: What triggered the pause
            affected_symbols: Affected symbols
            details: Detailed pause information
            
        Returns:
            Created StrategyPause record
        """
        entity = StrategyPause(
            strategy_id=strategy_id,
            paused_at=paused_at,
            reason=reason,
            pause_type=pause_type,
            triggered_by=triggered_by,
            affected_symbols=affected_symbols,
            details=details,
            is_active=True,
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.warning(
                f"Strategy {strategy_id} paused: {reason}"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_strategy_pause", {
                "strategy_id": strategy_id
            })
            raise
    
    def get_active_strategy_pause(
        self,
        strategy_id: str
    ) -> Optional[StrategyPause]:
        """
        Get active pause for a strategy.
        
        Args:
            strategy_id: Strategy identifier
            
        Returns:
            Active StrategyPause or None
        """
        stmt = (
            select(StrategyPause)
            .where(and_(
                StrategyPause.strategy_id == strategy_id,
                StrategyPause.is_active == True,
            ))
            .order_by(desc(StrategyPause.paused_at))
            .limit(1)
        )
        try:
            result = self._session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            self._handle_db_error(e, "get_active_strategy_pause", {
                "strategy_id": strategy_id
            })
            raise
    
    def list_strategy_pauses(
        self,
        strategy_id: Optional[str] = None,
        include_resolved: bool = True,
        limit: int = 100
    ) -> List[StrategyPause]:
        """
        List strategy pauses.
        
        Args:
            strategy_id: Optional strategy filter
            include_resolved: Whether to include resolved pauses
            limit: Maximum records to return
            
        Returns:
            List of StrategyPause
        """
        conditions = []
        if strategy_id:
            conditions.append(StrategyPause.strategy_id == strategy_id)
        if not include_resolved:
            conditions.append(StrategyPause.is_active == True)
        
        if conditions:
            stmt = (
                select(StrategyPause)
                .where(and_(*conditions))
                .order_by(desc(StrategyPause.paused_at))
                .limit(limit)
            )
        else:
            stmt = (
                select(StrategyPause)
                .order_by(desc(StrategyPause.paused_at))
                .limit(limit)
            )
        
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_strategy_pauses", {
                "strategy_id": strategy_id
            })
            raise
    
    # =========================================================
    # DRAWDOWN EVENT OPERATIONS
    # =========================================================
    
    def record_drawdown_event(
        self,
        recorded_at: datetime,
        drawdown_type: str,
        drawdown_percent: Decimal,
        peak_value: Decimal,
        current_value: Decimal,
        duration_minutes: int,
        affected_strategies: List[str],
        details: Dict[str, Any],
    ) -> DrawdownEvent:
        """
        Record a drawdown event.
        
        Args:
            recorded_at: Event timestamp
            drawdown_type: Drawdown type (daily, weekly, total)
            drawdown_percent: Drawdown percentage
            peak_value: Peak portfolio value
            current_value: Current portfolio value
            duration_minutes: Duration of drawdown
            affected_strategies: Affected strategies
            details: Detailed drawdown information
            
        Returns:
            Created DrawdownEvent record
        """
        entity = DrawdownEvent(
            recorded_at=recorded_at,
            drawdown_type=drawdown_type,
            drawdown_percent=drawdown_percent,
            peak_value=peak_value,
            current_value=current_value,
            duration_minutes=duration_minutes,
            affected_strategies=affected_strategies,
            details=details,
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.warning(
                f"Drawdown event: {drawdown_percent}% ({drawdown_type})"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_drawdown_event", {
                "drawdown_percent": str(drawdown_percent)
            })
            raise
    
    def list_drawdown_events(
        self,
        drawdown_type: Optional[str] = None,
        min_percent: Optional[Decimal] = None,
        limit: int = 100
    ) -> List[DrawdownEvent]:
        """
        List drawdown events.
        
        Args:
            drawdown_type: Optional drawdown type filter
            min_percent: Optional minimum percentage filter
            limit: Maximum records to return
            
        Returns:
            List of DrawdownEvent
        """
        conditions = []
        if drawdown_type:
            conditions.append(DrawdownEvent.drawdown_type == drawdown_type)
        if min_percent is not None:
            conditions.append(DrawdownEvent.drawdown_percent >= min_percent)
        
        if conditions:
            stmt = (
                select(DrawdownEvent)
                .where(and_(*conditions))
                .order_by(desc(DrawdownEvent.recorded_at))
                .limit(limit)
            )
        else:
            stmt = (
                select(DrawdownEvent)
                .order_by(desc(DrawdownEvent.recorded_at))
                .limit(limit)
            )
        
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_drawdown_events", {})
            raise
    
    # =========================================================
    # RISK THRESHOLD BREACH OPERATIONS
    # =========================================================
    
    def record_threshold_breach(
        self,
        breached_at: datetime,
        threshold_name: str,
        threshold_value: Decimal,
        actual_value: Decimal,
        breach_type: str,
        severity: str,
        affected_entity: str,
        details: Dict[str, Any],
    ) -> RiskThresholdBreach:
        """
        Record a risk threshold breach.
        
        Args:
            breached_at: Breach timestamp
            threshold_name: Name of breached threshold
            threshold_value: Threshold limit value
            actual_value: Actual value that breached
            breach_type: Breach type
            severity: Breach severity
            affected_entity: What was affected
            details: Detailed breach information
            
        Returns:
            Created RiskThresholdBreach record
        """
        entity = RiskThresholdBreach(
            breached_at=breached_at,
            threshold_name=threshold_name,
            threshold_value=threshold_value,
            actual_value=actual_value,
            breach_type=breach_type,
            severity=severity,
            affected_entity=affected_entity,
            details=details,
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.error(
                f"Threshold breach: {threshold_name} "
                f"(limit: {threshold_value}, actual: {actual_value})"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_threshold_breach", {
                "threshold_name": threshold_name
            })
            raise
    
    def list_threshold_breaches(
        self,
        severity: Optional[str] = None,
        threshold_name: Optional[str] = None,
        limit: int = 100
    ) -> List[RiskThresholdBreach]:
        """
        List risk threshold breaches.
        
        Args:
            severity: Optional severity filter
            threshold_name: Optional threshold name filter
            limit: Maximum records to return
            
        Returns:
            List of RiskThresholdBreach
        """
        conditions = []
        if severity:
            conditions.append(RiskThresholdBreach.severity == severity)
        if threshold_name:
            conditions.append(RiskThresholdBreach.threshold_name == threshold_name)
        
        if conditions:
            stmt = (
                select(RiskThresholdBreach)
                .where(and_(*conditions))
                .order_by(desc(RiskThresholdBreach.breached_at))
                .limit(limit)
            )
        else:
            stmt = (
                select(RiskThresholdBreach)
                .order_by(desc(RiskThresholdBreach.breached_at))
                .limit(limit)
            )
        
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_threshold_breaches", {})
            raise
    
    def list_threshold_breaches_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000
    ) -> List[RiskThresholdBreach]:
        """
        List threshold breaches within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            limit: Maximum records to return
            
        Returns:
            List of RiskThresholdBreach
        """
        stmt = (
            select(RiskThresholdBreach)
            .where(and_(
                RiskThresholdBreach.breached_at >= start_time,
                RiskThresholdBreach.breached_at < end_time,
            ))
            .order_by(RiskThresholdBreach.breached_at)
            .limit(limit)
        )
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_threshold_breaches_by_time_range", {
                "start": str(start_time),
                "end": str(end_time)
            })
            raise
    
    # =========================================================
    # RISK CONFIGURATION AUDIT OPERATIONS
    # =========================================================
    
    def record_config_change(
        self,
        changed_at: datetime,
        config_key: str,
        old_value: str,
        new_value: str,
        changed_by: str,
        change_reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RiskConfigurationAudit:
        """
        Record a risk configuration change.
        
        Args:
            changed_at: Change timestamp
            config_key: Configuration key
            old_value: Previous value
            new_value: New value
            changed_by: Who made the change
            change_reason: Reason for change
            metadata: Additional metadata
            
        Returns:
            Created RiskConfigurationAudit record
        """
        entity = RiskConfigurationAudit(
            changed_at=changed_at,
            config_key=config_key,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            change_reason=change_reason,
            metadata=metadata or {},
        )
        try:
            self._session.add(entity)
            self._session.flush()
            self._logger.info(
                f"Config change: {config_key} = {new_value} (was: {old_value})"
            )
            return entity
        except SQLAlchemyError as e:
            self._handle_db_error(e, "record_config_change", {
                "config_key": config_key
            })
            raise
    
    def list_config_changes(
        self,
        config_key: Optional[str] = None,
        limit: int = 100
    ) -> List[RiskConfigurationAudit]:
        """
        List risk configuration changes.
        
        Args:
            config_key: Optional config key filter
            limit: Maximum records to return
            
        Returns:
            List of RiskConfigurationAudit
        """
        if config_key:
            stmt = (
                select(RiskConfigurationAudit)
                .where(RiskConfigurationAudit.config_key == config_key)
                .order_by(desc(RiskConfigurationAudit.changed_at))
                .limit(limit)
            )
        else:
            stmt = (
                select(RiskConfigurationAudit)
                .order_by(desc(RiskConfigurationAudit.changed_at))
                .limit(limit)
            )
        
        try:
            result = self._session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self._handle_db_error(e, "list_config_changes", {
                "config_key": config_key
            })
            raise
