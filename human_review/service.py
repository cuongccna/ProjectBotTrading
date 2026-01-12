"""
Human-in-the-Loop Review Service.

This service handles:
- Creating review events when triggers are met
- Processing human decisions
- Applying parameter changes
- Audit logging
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from database.models_review import (
    ReviewEvent, HumanDecision, ParameterChange, 
    Annotation, OutcomeEvaluation,
    ReviewStatus, ReviewTriggerType, DecisionType
)
from database.models import RiskState, EntryDecision, SystemMonitoring
from database.engine import transaction_scope, get_session

from .schemas import (
    ReviewEventCreate, HumanDecisionCreate, 
    ParameterChangeCreate, AnnotationCreate,
    OutcomeEvaluationCreate, ALLOWED_ACTIONS,
    DecisionTypeEnum
)

logger = logging.getLogger(__name__)


# =============================================================
# TRIGGER CONDITIONS
# =============================================================

class TriggerConditions:
    """Configuration for review triggers."""
    
    # Trade Guard block duration (hours) before triggering review
    TRADE_GUARD_BLOCK_HOURS = 2
    
    # Drawdown thresholds
    DRAWDOWN_SOFT_THRESHOLD = 0.05  # 5%
    DRAWDOWN_HARD_THRESHOLD = 0.10  # 10%
    
    # Consecutive losses
    MAX_CONSECUTIVE_LOSSES = 5
    
    # Risk oscillation (standard deviations)
    RISK_OSCILLATION_STD = 2.0
    
    # Data source health minimum
    DATA_SOURCE_HEALTH_MIN = 0.5
    
    # Backtest divergence threshold
    BACKTEST_DIVERGENCE_THRESHOLD = 0.15  # 15%


# =============================================================
# REVIEW SERVICE
# =============================================================

class ReviewService:
    """Service for managing human review workflow."""
    
    def __init__(self, session: Session):
        self.session = session
    
    # ---------------------------------------------------------
    # CREATE REVIEW EVENTS
    # ---------------------------------------------------------
    
    def create_review_event(self, data: ReviewEventCreate, notify_telegram: bool = True) -> ReviewEvent:
        """
        Create a new review event.
        
        This is called when a trigger condition is met.
        """
        event = ReviewEvent(
            correlation_id=data.correlation_id,
            trigger_type=data.trigger_type.value,
            trigger_reason=data.trigger_reason,
            trigger_value=data.trigger_value,
            trigger_threshold=data.trigger_threshold,
            status=ReviewStatus.PENDING.value,
            priority=data.priority.value,
            market_context=data.market_context,
            risk_state_snapshot=data.risk_state_snapshot,
            sentiment_summary=data.sentiment_summary,
            flow_context=data.flow_context,
            smart_money_context=data.smart_money_context,
            strategy_decision=data.strategy_decision,
            trade_guard_rules=data.trade_guard_rules,
            execution_outcome=data.execution_outcome,
            entry_decision_id=data.entry_decision_id,
            risk_state_id=data.risk_state_id,
            expires_at=datetime.utcnow() + timedelta(hours=24),  # 24h expiry
        )
        
        self.session.add(event)
        self.session.flush()
        
        logger.info(f"Created review event: id={event.id} trigger={data.trigger_type.value}")
        
        # Log to system monitoring
        self._log_audit_event(
            event_type="review_event_created",
            module_name="human_review",
            message=f"Review event created: {data.trigger_reason}",
            details={"review_event_id": event.id, "trigger_type": data.trigger_type.value}
        )
        
        return event
    
    def create_trade_guard_block_review(
        self,
        correlation_id: str,
        blocked_hours: float,
        risk_state: Dict[str, Any],
        trade_guard_rules: List[Dict[str, Any]],
    ) -> ReviewEvent:
        """Create review for prolonged trade guard block."""
        from .schemas import ReviewEventCreate, TriggerTypeEnum, PriorityEnum
        
        priority = PriorityEnum.HIGH if blocked_hours > 4 else PriorityEnum.NORMAL
        
        data = ReviewEventCreate(
            correlation_id=correlation_id,
            trigger_type=TriggerTypeEnum.TRADE_GUARD_BLOCK,
            trigger_reason=f"Trade Guard has blocked trading for {blocked_hours:.1f} hours",
            trigger_value=blocked_hours,
            trigger_threshold=TriggerConditions.TRADE_GUARD_BLOCK_HOURS,
            priority=priority,
            risk_state_snapshot=risk_state,
            trade_guard_rules=trade_guard_rules,
        )
        
        return self.create_review_event(data)
    
    def create_drawdown_review(
        self,
        correlation_id: str,
        current_drawdown: float,
        market_context: Dict[str, Any],
    ) -> ReviewEvent:
        """Create review for drawdown threshold breach."""
        from .schemas import ReviewEventCreate, TriggerTypeEnum, PriorityEnum
        
        priority = PriorityEnum.CRITICAL if current_drawdown > TriggerConditions.DRAWDOWN_HARD_THRESHOLD else PriorityEnum.HIGH
        
        data = ReviewEventCreate(
            correlation_id=correlation_id,
            trigger_type=TriggerTypeEnum.DRAWDOWN_THRESHOLD,
            trigger_reason=f"Drawdown at {current_drawdown*100:.1f}% exceeds soft threshold",
            trigger_value=current_drawdown,
            trigger_threshold=TriggerConditions.DRAWDOWN_SOFT_THRESHOLD,
            priority=priority,
            market_context=market_context,
        )
        
        return self.create_review_event(data)
    
    def create_consecutive_losses_review(
        self,
        correlation_id: str,
        loss_count: int,
        recent_trades: List[Dict[str, Any]],
    ) -> ReviewEvent:
        """Create review for consecutive losses."""
        from .schemas import ReviewEventCreate, TriggerTypeEnum, PriorityEnum
        
        data = ReviewEventCreate(
            correlation_id=correlation_id,
            trigger_type=TriggerTypeEnum.CONSECUTIVE_LOSSES,
            trigger_reason=f"Consecutive losing trades: {loss_count}",
            trigger_value=loss_count,
            trigger_threshold=TriggerConditions.MAX_CONSECUTIVE_LOSSES,
            priority=PriorityEnum.HIGH,
            execution_outcome={"recent_trades": recent_trades},
        )
        
        return self.create_review_event(data)
    
    # ---------------------------------------------------------
    # PROCESS HUMAN DECISIONS
    # ---------------------------------------------------------
    
    def submit_decision(
        self,
        data: HumanDecisionCreate,
        user_id: str,
        user_role: str,
    ) -> Tuple[HumanDecision, Optional[ParameterChange]]:
        """
        Submit a human decision on a review event.
        
        Validates the action is allowed and applies changes if applicable.
        """
        # Get the review event
        event = self.session.query(ReviewEvent).filter(ReviewEvent.id == data.review_event_id).first()
        if not event:
            raise ValueError(f"Review event {data.review_event_id} not found")
        
        if event.status == ReviewStatus.RESOLVED.value:
            raise ValueError("Review event already resolved")
        
        # Validate action is allowed
        action_config = ALLOWED_ACTIONS.get(data.decision_type)
        if not action_config:
            raise ValueError(f"Unknown decision type: {data.decision_type}")
        
        # Validate parameter bounds if applicable
        if data.parameter_after:
            self._validate_parameter_bounds(data.decision_type, data.parameter_after)
        
        # Create the decision record
        decision = HumanDecision(
            review_event_id=data.review_event_id,
            decision_type=data.decision_type.value,
            reason_code=data.reason_code,
            confidence_level=data.confidence_level.value,
            comment=data.comment,
            user_id=user_id,
            user_role=user_role,
            parameter_before=data.parameter_before,
            parameter_after=data.parameter_after,
            requires_approval=action_config.get("requires_approval", False),
        )
        
        self.session.add(decision)
        self.session.flush()
        
        # Update review event status
        event.status = ReviewStatus.RESOLVED.value
        event.reviewed_at = datetime.utcnow()
        event.resolved_at = datetime.utcnow()
        
        # Create parameter change record if applicable
        param_change = None
        if data.parameter_after and data.decision_type in [
            DecisionTypeEnum.ADJUST_RISK_THRESHOLD,
            DecisionTypeEnum.REDUCE_POSITION_LIMIT,
            DecisionTypeEnum.PAUSE_STRATEGY,
        ]:
            param_change = self._create_parameter_change(decision, data, user_id)
        
        # Audit log
        self._log_audit_event(
            event_type="human_decision_submitted",
            module_name="human_review",
            message=f"Decision: {data.decision_type.value} by {user_id}",
            details={
                "review_event_id": event.id,
                "decision_id": decision.id,
                "decision_type": data.decision_type.value,
                "reason_code": data.reason_code,
            }
        )
        
        logger.info(f"Human decision submitted: id={decision.id} type={data.decision_type.value}")
        
        return decision, param_change
    
    def _validate_parameter_bounds(self, decision_type: DecisionTypeEnum, params: Dict[str, Any]) -> None:
        """Validate parameter values are within allowed bounds."""
        action_config = ALLOWED_ACTIONS.get(decision_type, {})
        bounds = action_config.get("bounds", {})
        
        for param_name, value in params.items():
            if param_name in bounds:
                min_val = bounds[param_name].get("min")
                max_val = bounds[param_name].get("max")
                
                if min_val is not None and value < min_val:
                    raise ValueError(f"{param_name} value {value} below minimum {min_val}")
                if max_val is not None and value > max_val:
                    raise ValueError(f"{param_name} value {value} above maximum {max_val}")
    
    def _create_parameter_change(
        self,
        decision: HumanDecision,
        data: HumanDecisionCreate,
        user_id: str,
    ) -> ParameterChange:
        """Create a parameter change record."""
        # Extract parameter info from the decision
        param_after = data.parameter_after or {}
        param_before = data.parameter_before or {}
        
        change = ParameterChange(
            human_decision_id=decision.id,
            parameter_category=data.decision_type.value.split("_")[0],  # e.g., "adjust" -> "risk"
            parameter_name=list(param_after.keys())[0] if param_after else "unknown",
            old_value=param_before,
            new_value=param_after,
            changed_by=user_id,
            change_reason=data.comment,
        )
        
        self.session.add(change)
        self.session.flush()
        
        return change
    
    # ---------------------------------------------------------
    # QUERY METHODS
    # ---------------------------------------------------------
    
    def get_pending_reviews(self, status: Optional[ReviewStatus] = None, limit: int = 50) -> List[ReviewEvent]:
        """Get pending review events, optionally filtered by status."""
        query = self.session.query(ReviewEvent)
        
        if status is not None:
            # Filter by specific status
            query = query.filter(ReviewEvent.status == status.value)
        else:
            # Default: show pending and in-progress
            query = query.filter(ReviewEvent.status.in_([
                ReviewStatus.PENDING.value,
                ReviewStatus.IN_PROGRESS.value
            ]))
        
        return (
            query.order_by(
                desc(ReviewEvent.priority == "critical"),
                desc(ReviewEvent.priority == "high"),
                desc(ReviewEvent.created_at)
            )
            .limit(limit)
            .all()
        )
    
    def get_review_event(self, event_id: int) -> Optional[ReviewEvent]:
        """Get a single review event with all details."""
        return self.session.query(ReviewEvent).filter(ReviewEvent.id == event_id).first()
    
    def get_decisions_for_event(self, event_id: int) -> List[HumanDecision]:
        """Get all decisions for a review event."""
        return (
            self.session.query(HumanDecision)
            .filter(HumanDecision.review_event_id == event_id)
            .order_by(desc(HumanDecision.created_at))
            .all()
        )
    
    def get_recent_decisions(self, limit: int = 50) -> List[HumanDecision]:
        """Get recent human decisions."""
        return (
            self.session.query(HumanDecision)
            .order_by(desc(HumanDecision.created_at))
            .limit(limit)
            .all()
        )
    
    def get_parameter_history(self, category: str = None, limit: int = 50) -> List[ParameterChange]:
        """Get parameter change history."""
        query = self.session.query(ParameterChange)
        if category:
            query = query.filter(ParameterChange.parameter_category == category)
        return query.order_by(desc(ParameterChange.created_at)).limit(limit).all()
    
    # ---------------------------------------------------------
    # ANNOTATIONS
    # ---------------------------------------------------------
    
    def add_annotation(self, data: AnnotationCreate, user_id: str) -> Annotation:
        """Add an annotation to a review event."""
        annotation = Annotation(
            review_event_id=data.review_event_id,
            correlation_id=data.correlation_id,
            annotation_type=data.annotation_type,
            tag=data.tag,
            content=data.content,
            tags=data.tags,
            created_by=user_id,
        )
        
        self.session.add(annotation)
        self.session.flush()
        
        logger.info(f"Annotation added: id={annotation.id} type={data.annotation_type}")
        
        return annotation
    
    # ---------------------------------------------------------
    # OUTCOME EVALUATION
    # ---------------------------------------------------------
    
    def evaluate_outcome(self, data: OutcomeEvaluationCreate, evaluator_id: str) -> OutcomeEvaluation:
        """Record outcome evaluation for learning."""
        evaluation = OutcomeEvaluation(
            review_event_id=data.review_event_id,
            human_decision_id=data.human_decision_id,
            verdict=data.verdict,
            pnl_impact=data.pnl_impact,
            risk_impact=data.risk_impact,
            actual_outcome=data.actual_outcome,
            expected_outcome=data.expected_outcome,
            evaluation_window_hours=data.evaluation_window_hours,
            evaluator_id=evaluator_id,
            evaluation_notes=data.evaluation_notes,
        )
        
        self.session.add(evaluation)
        self.session.flush()
        
        # Audit log
        self._log_audit_event(
            event_type="outcome_evaluated",
            module_name="human_review",
            message=f"Outcome evaluated: {data.verdict}",
            details={
                "review_event_id": data.review_event_id,
                "verdict": data.verdict,
                "pnl_impact": data.pnl_impact,
            }
        )
        
        return evaluation
    
    # ---------------------------------------------------------
    # STATISTICS
    # ---------------------------------------------------------
    
    def get_review_statistics(self) -> Dict[str, Any]:
        """Get review queue statistics."""
        pending = self.session.query(func.count(ReviewEvent.id)).filter(
            ReviewEvent.status == ReviewStatus.PENDING.value
        ).scalar()
        
        in_progress = self.session.query(func.count(ReviewEvent.id)).filter(
            ReviewEvent.status == ReviewStatus.IN_PROGRESS.value
        ).scalar()
        
        resolved_24h = self.session.query(func.count(ReviewEvent.id)).filter(
            ReviewEvent.status == ReviewStatus.RESOLVED.value,
            ReviewEvent.resolved_at >= datetime.utcnow() - timedelta(hours=24)
        ).scalar()
        
        # Decision type distribution
        decision_counts = (
            self.session.query(
                HumanDecision.decision_type,
                func.count(HumanDecision.id)
            )
            .filter(HumanDecision.created_at >= datetime.utcnow() - timedelta(days=7))
            .group_by(HumanDecision.decision_type)
            .all()
        )
        
        return {
            "pending_count": pending,
            "in_progress_count": in_progress,
            "resolved_24h": resolved_24h,
            "decision_distribution": {dt: count for dt, count in decision_counts},
        }
    
    # ---------------------------------------------------------
    # AUDIT LOGGING
    # ---------------------------------------------------------
    
    def _log_audit_event(
        self,
        event_type: str,
        module_name: str,
        message: str,
        details: Dict[str, Any] = None,
    ) -> None:
        """Log to system monitoring for audit trail."""
        try:
            audit_record = SystemMonitoring(
                event_type=event_type,
                severity="info",
                module_name=module_name,
                message=message,
                details=details,
                source_module="human_review",
            )
            self.session.add(audit_record)
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")


# =============================================================
# TRIGGER DETECTOR
# =============================================================

class TriggerDetector:
    """Detects conditions that require human review."""
    
    def __init__(self, session: Session):
        self.session = session
        self.review_service = ReviewService(session)
    
    def check_all_triggers(self, context: Dict[str, Any]) -> List[ReviewEvent]:
        """
        Check all trigger conditions and create review events as needed.
        
        Args:
            context: Current system state including risk, market, positions
            
        Returns:
            List of created review events
        """
        events = []
        correlation_id = context.get("correlation_id", str(uuid.uuid4()))
        
        # Check trade guard block duration
        if context.get("trade_guard_blocked"):
            blocked_hours = context.get("blocked_hours", 0)
            if blocked_hours >= TriggerConditions.TRADE_GUARD_BLOCK_HOURS:
                event = self.review_service.create_trade_guard_block_review(
                    correlation_id=correlation_id,
                    blocked_hours=blocked_hours,
                    risk_state=context.get("risk_state", {}),
                    trade_guard_rules=context.get("trade_guard_rules", []),
                )
                events.append(event)
        
        # Check drawdown
        drawdown = context.get("current_drawdown", 0)
        if drawdown >= TriggerConditions.DRAWDOWN_SOFT_THRESHOLD:
            event = self.review_service.create_drawdown_review(
                correlation_id=correlation_id,
                current_drawdown=drawdown,
                market_context=context.get("market_context", {}),
            )
            events.append(event)
        
        # Check consecutive losses
        consecutive_losses = context.get("consecutive_losses", 0)
        if consecutive_losses >= TriggerConditions.MAX_CONSECUTIVE_LOSSES:
            event = self.review_service.create_consecutive_losses_review(
                correlation_id=correlation_id,
                loss_count=consecutive_losses,
                recent_trades=context.get("recent_trades", []),
            )
            events.append(event)
        
        return events
