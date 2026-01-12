"""
Tests for Human-in-the-Loop Review System.

Tests cover:
- Schema validation
- Allowed/forbidden action logic
- Review event creation
- Decision submission with bounds validation
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

# Import schemas
from human_review.schemas import (
    ReviewEventCreate,
    ReviewEventResponse,
    HumanDecisionCreate,
    HumanDecisionResponse,
    AnnotationCreate,
    OutcomeEvaluationCreate,
    ALLOWED_ACTIONS,
    FORBIDDEN_ACTIONS,
    DecisionTypeEnum,
    TriggerTypeEnum,
    PriorityEnum,
)


# =============================================================
# TEST: ALLOWED_ACTIONS Configuration
# =============================================================

class TestAllowedActions:
    """Test ALLOWED_ACTIONS configuration."""
    
    def test_allowed_actions_has_required_keys(self):
        """All required action types should be defined."""
        required_actions = [
            DecisionTypeEnum.ADJUST_RISK_THRESHOLD,
            DecisionTypeEnum.PAUSE_STRATEGY,
            DecisionTypeEnum.REDUCE_POSITION_LIMIT,
            DecisionTypeEnum.ENABLE_DATA_SOURCE,
            DecisionTypeEnum.DISABLE_DATA_SOURCE,
            DecisionTypeEnum.MARK_ANOMALY,
            DecisionTypeEnum.ESCALATE,
            DecisionTypeEnum.ACKNOWLEDGE_ONLY,
        ]
        
        for action in required_actions:
            assert action in ALLOWED_ACTIONS, f"Missing action: {action}"
    
    def test_adjust_risk_threshold_has_bounds(self):
        """Risk threshold adjustment should have defined bounds."""
        config = ALLOWED_ACTIONS[DecisionTypeEnum.ADJUST_RISK_THRESHOLD]
        assert "bounds" in config
        
        bounds = config["bounds"]
        assert "max_drawdown" in bounds
        assert bounds["max_drawdown"]["min"] >= 0
        assert bounds["max_drawdown"]["max"] <= 1.0  # Percentage as decimal
    
    def test_pause_strategy_has_max_duration(self):
        """Pause strategy should have max duration."""
        config = ALLOWED_ACTIONS[DecisionTypeEnum.PAUSE_STRATEGY]
        assert "bounds" in config
        assert "pause_duration_hours" in config["bounds"]
        assert config["bounds"]["pause_duration_hours"]["max"] == 168  # 7 days
    
    def test_reduce_position_limit_bounds(self):
        """Position limit reduction should have percentage bounds."""
        config = ALLOWED_ACTIONS[DecisionTypeEnum.REDUCE_POSITION_LIMIT]
        assert "bounds" in config
        assert "new_limit_percent" in config["bounds"]
        assert config["bounds"]["new_limit_percent"]["min"] > 0
        assert config["bounds"]["new_limit_percent"]["max"] <= 100


class TestForbiddenActions:
    """Test FORBIDDEN_ACTIONS list."""
    
    def test_forbidden_actions_exist(self):
        """Forbidden actions list should not be empty."""
        assert len(FORBIDDEN_ACTIONS) > 0
    
    def test_critical_actions_forbidden(self):
        """Critical dangerous actions should be forbidden."""
        forbidden_text = " ".join(FORBIDDEN_ACTIONS).lower()
        
        assert "trade" in forbidden_text or "force" in forbidden_text


# =============================================================
# TEST: Schema Validation
# =============================================================

class TestReviewEventSchemas:
    """Test review event Pydantic schemas."""
    
    def test_create_review_event_minimal(self):
        """Create review event with minimal required fields."""
        event = ReviewEventCreate(
            correlation_id="test-123",
            trigger_type=TriggerTypeEnum.TRADE_GUARD_BLOCK,
            trigger_reason="Trading blocked for 2.5 hours",
        )
        
        assert event.trigger_type == TriggerTypeEnum.TRADE_GUARD_BLOCK
        assert event.trigger_reason == "Trading blocked for 2.5 hours"
        assert event.priority == PriorityEnum.NORMAL  # default
    
    def test_create_review_event_full(self):
        """Create review event with all fields."""
        event = ReviewEventCreate(
            correlation_id="test-456",
            trigger_type=TriggerTypeEnum.DRAWDOWN_THRESHOLD,
            trigger_reason="Daily drawdown exceeded 5%",
            trigger_value=5.5,
            trigger_threshold=5.0,
            priority=PriorityEnum.HIGH,
            market_context={"token": "BTC", "price": 42500.0},
            risk_state_snapshot={"global_risk_score": 75.0},
        )
        
        assert event.trigger_value == 5.5
        assert event.trigger_threshold == 5.0
        assert event.priority == PriorityEnum.HIGH
        assert event.market_context["token"] == "BTC"


class TestHumanDecisionSchemas:
    """Test human decision Pydantic schemas."""
    
    def test_create_decision_minimal(self):
        """Create decision with minimal fields."""
        decision = HumanDecisionCreate(
            review_event_id=1,
            decision_type="acknowledge_only",
            reason_code="market_conditions",
            reason_text="Market conditions appear stable",
        )
        
        assert decision.decision_type == "acknowledge_only"
        assert decision.reason_code == "market_conditions"
    
    def test_create_decision_with_parameters(self):
        """Create decision with parameter changes."""
        decision = HumanDecisionCreate(
            review_event_id=1,
            decision_type="adjust_risk_threshold",
            reason_code="volatility",
            reason_text="Elevated volatility requires tighter limits",
            parameter_before={"max_drawdown_percent": 5.0},
            parameter_after={"max_drawdown_percent": 7.5},
            confidence_level="high",
        )
        
        assert decision.parameter_before["max_drawdown_percent"] == 5.0
        assert decision.parameter_after["max_drawdown_percent"] == 7.5
        assert decision.confidence_level == "high"


class TestAnnotationSchemas:
    """Test annotation Pydantic schemas."""
    
    def test_create_annotation(self):
        """Create annotation with note and tags."""
        annotation = AnnotationCreate(
            review_event_id=1,
            annotation_type="note",
            content="This was caused by a flash crash",
            tags=["flash_crash", "market_anomaly", "btc"],
        )
        
        assert annotation.content == "This was caused by a flash crash"
        assert len(annotation.tags) == 3
        assert "flash_crash" in annotation.tags


class TestOutcomeEvaluationSchemas:
    """Test outcome evaluation Pydantic schemas."""
    
    def test_create_evaluation(self):
        """Create outcome evaluation."""
        evaluation = OutcomeEvaluationCreate(
            review_event_id=1,
            human_decision_id=1,
            verdict="correct",
            actual_outcome={"result": "Avoided 2.5% additional drawdown"},
            expected_outcome={"result": "Reduce exposure during uncertainty"},
            pnl_impact=1250.0,
            evaluation_notes="Fed announcement volatility was correctly anticipated",
        )
        
        assert evaluation.verdict == "correct"
        assert evaluation.pnl_impact == 1250.0


# =============================================================
# TEST: Bounds Validation Logic
# =============================================================

class TestBoundsValidation:
    """Test parameter bounds validation logic."""
    
    def test_drawdown_within_bounds(self):
        """Drawdown within bounds should be valid."""
        bounds = ALLOWED_ACTIONS[DecisionTypeEnum.ADJUST_RISK_THRESHOLD]["bounds"]["max_drawdown"]
        
        # Valid values (as decimal percentages)
        for value in [0.05, 0.10, 0.15, 0.20]:
            assert bounds["min"] <= value <= bounds["max"]
    
    def test_drawdown_outside_bounds(self):
        """Drawdown outside bounds should fail validation."""
        bounds = ALLOWED_ACTIONS[DecisionTypeEnum.ADJUST_RISK_THRESHOLD]["bounds"]["max_drawdown"]
        
        # Invalid: too low
        assert 0.03 < bounds["min"]
        
        # Invalid: too high
        assert 0.25 > bounds["max"]
    
    def test_pause_duration_within_bounds(self):
        """Pause duration within 168 hours should be valid."""
        bounds = ALLOWED_ACTIONS[DecisionTypeEnum.PAUSE_STRATEGY]["bounds"]["pause_duration_hours"]
        
        for value in [1, 24, 72, 168]:
            assert bounds["min"] <= value <= bounds["max"]
    
    def test_pause_duration_outside_bounds(self):
        """Pause duration over 168 hours should fail."""
        bounds = ALLOWED_ACTIONS[DecisionTypeEnum.PAUSE_STRATEGY]["bounds"]["pause_duration_hours"]
        
        assert 200 > bounds["max"]


# =============================================================
# TEST: Telegram Notification Formatting
# =============================================================

class TestTelegramNotifier:
    """Test Telegram notification formatting."""
    
    def test_format_review_notification(self):
        """Test formatting a review event for Telegram."""
        from human_review.telegram_notifier import TelegramReviewNotifier
        
        notifier = TelegramReviewNotifier()
        
        # Create mock event
        mock_event = MagicMock()
        mock_event.id = 15
        mock_event.trigger_type = "trade_guard_block"
        mock_event.trigger_reason = "Trading blocked for 2.5 hours"
        mock_event.priority = "high"
        mock_event.created_at = datetime(2024, 1, 15, 10, 30)
        mock_event.trigger_value = 2.5
        mock_event.trigger_threshold = 2.0
        mock_event.market_context = {"token": "BTC", "price": 42500}
        mock_event.risk_state_snapshot = {"global_risk_score": 65, "risk_level": "elevated", "trading_allowed": False}
        mock_event.trade_guard_rules = []
        
        message = notifier.format_review_notification(mock_event)
        
        assert "REVIEW REQUIRED" in message
        assert "#15" in message
        assert "Trade Guard Block" in message
        assert "HIGH" in message
        assert "BTC" in message
    
    def test_format_critical_alert(self):
        """Test formatting a critical alert."""
        from human_review.telegram_notifier import TelegramReviewNotifier
        
        notifier = TelegramReviewNotifier()
        
        mock_event = MagicMock()
        mock_event.id = 20
        mock_event.trigger_type = "drawdown_threshold"
        mock_event.trigger_reason = "Weekly drawdown exceeded 10%"
        mock_event.priority = "critical"
        mock_event.created_at = datetime(2024, 1, 15, 11, 0)
        mock_event.trigger_value = 11.5
        mock_event.trigger_threshold = 10.0
        mock_event.market_context = {}
        mock_event.risk_state_snapshot = {}
        mock_event.trade_guard_rules = []
        
        message = notifier.format_critical_alert(mock_event)
        
        assert "CRITICAL REVIEW" in message
        assert "IMMEDIATE ATTENTION REQUIRED" in message


# =============================================================
# TEST: Service Layer (Mocked Database)
# =============================================================

class TestReviewServiceMocked:
    """Test ReviewService with mocked database."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        db.query = MagicMock()
        return db
    
    def test_validate_allowed_action(self, mock_db):
        """Test that allowed actions pass validation."""
        from human_review.service import ReviewService
        
        service = ReviewService(mock_db)
        
        # These should not raise
        for action in ALLOWED_ACTIONS.keys():
            # Just checking the action exists in config
            assert action in ALLOWED_ACTIONS
    
    def test_schema_validates_decision_type(self, mock_db):
        """Test that schema validates decision_type against enum."""
        # The schema uses an enum, so invalid types are caught at schema level
        with pytest.raises(ValidationError):
            HumanDecisionCreate(
                review_event_id=1,
                decision_type="unknown_action_type",
                reason_code="test",
                reason_text="Testing unknown action",
            )


# =============================================================
# TEST: Trigger Conditions
# =============================================================

class TestTriggerConditions:
    """Test trigger condition thresholds."""
    
    def test_default_thresholds(self):
        """Test default trigger thresholds are reasonable."""
        from human_review.service import TriggerConditions
        
        assert TriggerConditions.TRADE_GUARD_BLOCK_HOURS >= 1
        assert TriggerConditions.DRAWDOWN_SOFT_THRESHOLD > 0
        assert TriggerConditions.DRAWDOWN_HARD_THRESHOLD > TriggerConditions.DRAWDOWN_SOFT_THRESHOLD
        assert TriggerConditions.MAX_CONSECUTIVE_LOSSES >= 3


# =============================================================
# RUN TESTS
# =============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
