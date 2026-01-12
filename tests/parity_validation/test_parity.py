"""
Tests for Parity Validation Module.

============================================================
PURPOSE
============================================================
Comprehensive tests for the Live vs Backtest Parity Validation
module, covering:
1. Tolerance configuration validation
2. Domain comparators
3. Drift detection
4. Reaction handling
5. Integration scenarios

============================================================
"""

import asyncio
import pytest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def tolerance_config():
    """Create a default tolerance configuration."""
    from parity_validation.models import ToleranceConfig
    return ToleranceConfig.default()


@pytest.fixture
def strict_tolerance():
    """Create a strict tolerance configuration."""
    from parity_validation.models import ToleranceConfig
    return ToleranceConfig.strict()


@pytest.fixture
def loose_tolerance():
    """Create a loose tolerance configuration."""
    from parity_validation.models import ToleranceConfig
    return ToleranceConfig.loose()


@pytest.fixture
def market_snapshot():
    """Create a sample market snapshot."""
    from parity_validation.models import OHLCVData, MarketSnapshot
    
    ohlcv = OHLCVData(
        open=Decimal("50000.00"),
        high=Decimal("50500.00"),
        low=Decimal("49500.00"),
        close=Decimal("50100.00"),
        volume=Decimal("1000.50"),
        timestamp=datetime.utcnow(),
    )
    
    return MarketSnapshot(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        ohlcv=ohlcv,
        bid_price=Decimal("50095.00"),
        ask_price=Decimal("50105.00"),
        spread=Decimal("10.00"),
        volume_24h=Decimal("50000000.00"),
        current_risk_level="normal",
        exchange="binance",
        raw_data={"test": True},
    )


@pytest.fixture
def feature_snapshot():
    """Create a sample feature snapshot."""
    from parity_validation.models import FeatureSnapshot
    
    return FeatureSnapshot(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        features={
            "rsi_14": Decimal("55.5"),
            "macd": Decimal("100.25"),
            "bb_upper": Decimal("51000.00"),
            "bb_lower": Decimal("49000.00"),
            "atr_14": Decimal("500.00"),
        },
        feature_version="1.0.0",
        calculation_time_ms=Decimal("5.5"),
    )


@pytest.fixture
def decision_snapshot():
    """Create a sample decision snapshot."""
    from parity_validation.models import DecisionSnapshot
    
    return DecisionSnapshot(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        trade_guard_decision="approved",
        entry_permission_granted=True,
        position_size=Decimal("0.1"),
        risk_level="normal",
        stop_loss_price=Decimal("49500.00"),
        take_profit_price=Decimal("51000.00"),
        entry_price=Decimal("50100.00"),
        position_risk_pct=Decimal("1.0"),
        account_risk_pct=Decimal("0.5"),
        decision_reasons=["RSI favorable", "Trend confirmed"],
        rejection_reasons=[],
    )


@pytest.fixture
def execution_snapshot():
    """Create a sample execution snapshot."""
    from parity_validation.models import ExecutionSnapshot
    
    return ExecutionSnapshot(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        order_id="order_123",
        order_type="limit",
        side="buy",
        requested_size=Decimal("0.1"),
        filled_size=Decimal("0.1"),
        requested_price=Decimal("50100.00"),
        filled_price=Decimal("50102.50"),
        slippage=Decimal("2.50"),
        slippage_pct=Decimal("0.005"),
        fees=Decimal("5.01"),
        execution_time_ms=Decimal("150.5"),
        partial_fills=[],
    )


# ============================================================
# TOLERANCE CONFIGURATION TESTS
# ============================================================

class TestToleranceConfig:
    """Tests for ToleranceConfig."""
    
    def test_default_config_creation(self, tolerance_config):
        """Test default configuration creation."""
        assert tolerance_config.price_tolerance_absolute == Decimal("0.0001")
        assert tolerance_config.price_tolerance_relative_pct == Decimal("0.1")
        assert tolerance_config.timing_tolerance_seconds == Decimal("1.0")
    
    def test_strict_config_creation(self, strict_tolerance):
        """Test strict configuration has tighter tolerances."""
        default = ToleranceConfig.default()
        
        assert strict_tolerance.price_tolerance_relative_pct < default.price_tolerance_relative_pct
        assert strict_tolerance.slippage_tolerance_pct < default.slippage_tolerance_pct
    
    def test_loose_config_creation(self, loose_tolerance):
        """Test loose configuration has relaxed tolerances."""
        default = ToleranceConfig.default()
        
        assert loose_tolerance.price_tolerance_relative_pct > default.price_tolerance_relative_pct
        assert loose_tolerance.slippage_tolerance_pct > default.slippage_tolerance_pct
    
    def test_price_within_tolerance(self, tolerance_config):
        """Test price tolerance checking."""
        base_price = Decimal("50000.00")
        
        # Within tolerance
        assert tolerance_config.is_price_within_tolerance(
            Decimal("50000.00"),  # live
            Decimal("50000.00"),  # backtest
        )
        
        # Small deviation - within relative tolerance
        assert tolerance_config.is_price_within_tolerance(
            Decimal("50000.00"),
            Decimal("50010.00"),  # 0.02% deviation
        )
    
    def test_price_outside_tolerance(self, tolerance_config):
        """Test price outside tolerance."""
        # Large deviation - outside relative tolerance
        assert not tolerance_config.is_price_within_tolerance(
            Decimal("50000.00"),
            Decimal("50100.00"),  # 0.2% deviation (> 0.1% tolerance)
        )
    
    def test_size_within_tolerance(self, tolerance_config):
        """Test size tolerance checking."""
        assert tolerance_config.is_size_within_tolerance(
            Decimal("0.1"),
            Decimal("0.1"),
        )
        
        assert tolerance_config.is_size_within_tolerance(
            Decimal("0.1"),
            Decimal("0.1005"),  # 0.5% deviation
        )
    
    def test_size_outside_tolerance(self, tolerance_config):
        """Test size outside tolerance."""
        assert not tolerance_config.is_size_within_tolerance(
            Decimal("0.1"),
            Decimal("0.12"),  # 20% deviation
        )
    
    def test_feature_within_tolerance(self, tolerance_config):
        """Test feature tolerance checking."""
        assert tolerance_config.is_feature_within_tolerance(
            Decimal("55.5"),
            Decimal("55.5"),
        )
        
        # 0.05% deviation (within 0.1% tolerance)
        assert tolerance_config.is_feature_within_tolerance(
            Decimal("100.0"),
            Decimal("100.05"),
        )
    
    def test_zero_division_protection(self, tolerance_config):
        """Test that zero values don't cause division errors."""
        # Zero backtest value uses absolute comparison
        assert tolerance_config.is_price_within_tolerance(
            Decimal("0.00001"),
            Decimal("0"),
        )
        
        assert tolerance_config.is_size_within_tolerance(
            Decimal("0"),
            Decimal("0"),
        )


# ============================================================
# DATA COMPARATOR TESTS
# ============================================================

class TestDataComparator:
    """Tests for DataComparator."""
    
    @pytest.fixture
    def comparator(self, tolerance_config):
        """Create a data comparator."""
        from parity_validation.comparators import DataComparator
        return DataComparator(tolerance_config)
    
    def test_matching_ohlcv(self, comparator, market_snapshot):
        """Test OHLCV data that matches."""
        result = comparator.compare(market_snapshot, market_snapshot)
        
        assert result.is_match
        assert len(result.mismatches) == 0
    
    def test_mismatching_price(self, comparator, market_snapshot):
        """Test mismatching close price."""
        from parity_validation.models import OHLCVData, MarketSnapshot
        
        live = market_snapshot
        
        # Create backtest with different close
        bt_ohlcv = OHLCVData(
            open=live.ohlcv.open,
            high=live.ohlcv.high,
            low=live.ohlcv.low,
            close=Decimal("50200.00"),  # Different close
            volume=live.ohlcv.volume,
            timestamp=live.ohlcv.timestamp,
        )
        backtest = MarketSnapshot(
            symbol=live.symbol,
            timestamp=live.timestamp,
            ohlcv=bt_ohlcv,
            bid_price=live.bid_price,
            ask_price=live.ask_price,
            spread=live.spread,
            volume_24h=live.volume_24h,
            current_risk_level=live.current_risk_level,
            exchange=live.exchange,
            raw_data=live.raw_data,
        )
        
        result = comparator.compare(live, backtest)
        
        assert not result.is_match
        assert any(m.field_name == "close_price" for m in result.mismatches)
    
    def test_none_snapshots(self, comparator):
        """Test handling of None snapshots."""
        result = comparator.compare(None, None)
        
        assert result.is_match  # Both None is technically a match


# ============================================================
# FEATURE COMPARATOR TESTS
# ============================================================

class TestFeatureComparator:
    """Tests for FeatureComparator."""
    
    @pytest.fixture
    def comparator(self, tolerance_config):
        """Create a feature comparator."""
        from parity_validation.comparators import FeatureComparator
        return FeatureComparator(tolerance_config)
    
    def test_matching_features(self, comparator, feature_snapshot):
        """Test matching feature snapshots."""
        result = comparator.compare(feature_snapshot, feature_snapshot)
        
        assert result.is_match
        assert len(result.mismatches) == 0
    
    def test_mismatching_feature(self, comparator, feature_snapshot):
        """Test mismatching feature value."""
        from parity_validation.models import FeatureSnapshot
        
        live = feature_snapshot
        
        # Create backtest with different RSI
        bt_features = dict(live.features)
        bt_features["rsi_14"] = Decimal("65.0")  # Different RSI
        
        backtest = FeatureSnapshot(
            symbol=live.symbol,
            timestamp=live.timestamp,
            features=bt_features,
            feature_version=live.feature_version,
            calculation_time_ms=live.calculation_time_ms,
        )
        
        result = comparator.compare(live, backtest)
        
        assert not result.is_match
        assert any(m.field_name == "feature.rsi_14" for m in result.mismatches)
    
    def test_missing_feature(self, comparator, feature_snapshot):
        """Test missing feature in one snapshot."""
        from parity_validation.models import FeatureSnapshot
        
        live = feature_snapshot
        
        # Create backtest missing a feature
        bt_features = dict(live.features)
        del bt_features["macd"]
        
        backtest = FeatureSnapshot(
            symbol=live.symbol,
            timestamp=live.timestamp,
            features=bt_features,
            feature_version=live.feature_version,
            calculation_time_ms=live.calculation_time_ms,
        )
        
        result = comparator.compare(live, backtest)
        
        assert not result.is_match
    
    def test_version_mismatch(self, comparator, feature_snapshot):
        """Test feature version mismatch."""
        from parity_validation.models import FeatureSnapshot
        
        live = feature_snapshot
        
        backtest = FeatureSnapshot(
            symbol=live.symbol,
            timestamp=live.timestamp,
            features=live.features,
            feature_version="2.0.0",  # Different version
            calculation_time_ms=live.calculation_time_ms,
        )
        
        result = comparator.compare(live, backtest)
        
        # Version mismatch should be noted
        assert any("version" in m.field_name.lower() for m in result.mismatches)


# ============================================================
# DECISION COMPARATOR TESTS
# ============================================================

class TestDecisionComparator:
    """Tests for DecisionComparator."""
    
    @pytest.fixture
    def comparator(self, tolerance_config):
        """Create a decision comparator."""
        from parity_validation.comparators import DecisionComparator
        return DecisionComparator(tolerance_config)
    
    def test_matching_decisions(self, comparator, decision_snapshot):
        """Test matching decision snapshots."""
        result = comparator.compare(decision_snapshot, decision_snapshot)
        
        assert result.is_match
    
    def test_conflicting_trade_guard(self, comparator, decision_snapshot):
        """Test conflicting Trade Guard decisions."""
        from parity_validation.models import DecisionSnapshot, FailureCondition
        
        live = decision_snapshot
        
        backtest = DecisionSnapshot(
            symbol=live.symbol,
            timestamp=live.timestamp,
            trade_guard_decision="rejected",  # Different decision
            entry_permission_granted=False,
            position_size=Decimal("0"),
            risk_level=live.risk_level,
            stop_loss_price=live.stop_loss_price,
            take_profit_price=live.take_profit_price,
            entry_price=live.entry_price,
            position_risk_pct=live.position_risk_pct,
            account_risk_pct=live.account_risk_pct,
            decision_reasons=[],
            rejection_reasons=["Risk too high"],
        )
        
        result = comparator.compare(live, backtest)
        
        assert not result.is_match
        # Should detect trade allowed in live but blocked in backtest
        assert FailureCondition.TRADE_ALLOWED_LIVE_BLOCKED_BACKTEST in result.failure_conditions
    
    def test_position_size_deviation(self, comparator, decision_snapshot):
        """Test position size deviation."""
        from parity_validation.models import DecisionSnapshot
        
        live = decision_snapshot
        
        backtest = DecisionSnapshot(
            symbol=live.symbol,
            timestamp=live.timestamp,
            trade_guard_decision=live.trade_guard_decision,
            entry_permission_granted=live.entry_permission_granted,
            position_size=Decimal("0.15"),  # 50% larger
            risk_level=live.risk_level,
            stop_loss_price=live.stop_loss_price,
            take_profit_price=live.take_profit_price,
            entry_price=live.entry_price,
            position_risk_pct=live.position_risk_pct,
            account_risk_pct=live.account_risk_pct,
            decision_reasons=live.decision_reasons,
            rejection_reasons=live.rejection_reasons,
        )
        
        result = comparator.compare(live, backtest)
        
        assert not result.is_match
        assert any(m.field_name == "position_size" for m in result.mismatches)


# ============================================================
# EXECUTION COMPARATOR TESTS
# ============================================================

class TestExecutionComparator:
    """Tests for ExecutionComparator."""
    
    @pytest.fixture
    def comparator(self, tolerance_config):
        """Create an execution comparator."""
        from parity_validation.comparators import ExecutionComparator
        return ExecutionComparator(tolerance_config)
    
    def test_matching_execution(self, comparator, execution_snapshot):
        """Test matching execution snapshots."""
        result = comparator.compare(execution_snapshot, execution_snapshot)
        
        assert result.is_match
    
    def test_slippage_exceeds_tolerance(self, comparator, execution_snapshot):
        """Test slippage exceeding tolerance."""
        from parity_validation.models import ExecutionSnapshot, FailureCondition
        
        live = execution_snapshot
        
        backtest = ExecutionSnapshot(
            symbol=live.symbol,
            timestamp=live.timestamp,
            order_id=live.order_id,
            order_type=live.order_type,
            side=live.side,
            requested_size=live.requested_size,
            filled_size=live.filled_size,
            requested_price=live.requested_price,
            filled_price=Decimal("50000.00"),  # No slippage in backtest
            slippage=Decimal("0"),
            slippage_pct=Decimal("0"),
            fees=live.fees,
            execution_time_ms=live.execution_time_ms,
            partial_fills=live.partial_fills,
        )
        
        result = comparator.compare(live, backtest)
        
        # Live has slippage, backtest doesn't
        assert any(m.field_name == "slippage" for m in result.mismatches)


# ============================================================
# DRIFT DETECTOR TESTS
# ============================================================

class TestDriftDetector:
    """Tests for DriftDetector."""
    
    @pytest.fixture
    def detector(self):
        """Create a drift detector."""
        from parity_validation.drift_detector import create_drift_detector
        return create_drift_detector(window_size=10)
    
    def test_no_drift_with_stable_values(self, detector):
        """Test no drift detection with stable values."""
        from parity_validation.models import MismatchSeverity
        
        # Add stable mismatches
        for i in range(10):
            mismatch = MagicMock()
            mismatch.field_name = "close_price"
            mismatch.deviation_pct = Decimal("0.05")  # Consistent 0.05%
            mismatch.severity = MismatchSeverity.INFO
            detector.add_mismatch(mismatch)
        
        report = detector.generate_report()
        
        # Stable values shouldn't trigger significant drift
        assert report.significant_drift_count == 0
    
    def test_drift_with_increasing_values(self, detector):
        """Test drift detection with increasing deviation."""
        from parity_validation.models import MismatchSeverity
        
        # Add increasing mismatches
        for i in range(10):
            mismatch = MagicMock()
            mismatch.field_name = "close_price"
            mismatch.deviation_pct = Decimal(str(i * 2))  # 0%, 2%, 4%...
            mismatch.severity = MismatchSeverity.WARNING
            detector.add_mismatch(mismatch)
        
        report = detector.generate_report()
        
        # Should detect parameter drift due to increasing trend
        assert report.total_drift_count > 0


# ============================================================
# DRIFT MONITOR TESTS
# ============================================================

class TestDriftMonitor:
    """Tests for ContinuousDriftMonitor."""
    
    @pytest.fixture
    def monitor(self):
        """Create a drift monitor."""
        from parity_validation.drift_detector import create_drift_monitor
        return create_drift_monitor(window_size=5)
    
    @pytest.mark.asyncio
    async def test_monitor_processes_reports(self, monitor, tolerance_config):
        """Test that monitor processes cycle reports."""
        from parity_validation.models import (
            CycleParityReport,
            ParityComparisonResult,
            ParityDomain,
            MismatchSeverity,
            SystemReaction,
            ValidationMode,
        )
        
        # Create a mock report
        report = CycleParityReport(
            report_id=str(uuid.uuid4()),
            cycle_id="cycle_1",
            timestamp=datetime.utcnow(),
            validation_mode=ValidationMode.SHADOW_MODE,
            overall_match=True,
            highest_severity=MismatchSeverity.INFO,
            failure_conditions=[],
            recommended_reaction=SystemReaction.LOG_ONLY,
            data_parity=ParityComparisonResult(
                comparison_id=str(uuid.uuid4()),
                domain=ParityDomain.DATA,
                is_match=True,
                severity=MismatchSeverity.INFO,
                mismatches=[],
                failure_conditions=[],
            ),
            feature_parity=None,
            decision_parity=None,
            execution_parity=None,
            accounting_parity=None,
            code_version="1.0.0",
            config_version="1.0.0",
        )
        
        # Process should not raise
        await monitor.process_cycle_report(report)
        
        drift_report = monitor.get_current_drift()
        assert drift_report is not None


# ============================================================
# REACTION HANDLER TESTS
# ============================================================

class TestReactionHandler:
    """Tests for ReactionHandler."""
    
    @pytest.fixture
    def handler(self):
        """Create a reaction handler."""
        from parity_validation.validator import ReactionHandler
        return ReactionHandler()
    
    def test_determine_reaction_info(self, handler):
        """Test reaction for INFO severity."""
        from parity_validation.models import (
            CycleParityReport,
            MismatchSeverity,
            SystemReaction,
            ValidationMode,
        )
        
        report = MagicMock(spec=CycleParityReport)
        report.overall_match = True
        report.highest_severity = MismatchSeverity.INFO
        report.failure_conditions = []
        
        reaction = handler.determine_reaction(report)
        
        assert reaction == SystemReaction.LOG_ONLY
    
    def test_determine_reaction_warning(self, handler):
        """Test reaction for WARNING severity."""
        from parity_validation.models import (
            CycleParityReport,
            MismatchSeverity,
            SystemReaction,
            ValidationMode,
        )
        
        report = MagicMock(spec=CycleParityReport)
        report.overall_match = False
        report.highest_severity = MismatchSeverity.WARNING
        report.failure_conditions = []
        
        reaction = handler.determine_reaction(report)
        
        assert reaction == SystemReaction.ESCALATE_RISK
    
    def test_determine_reaction_critical(self, handler):
        """Test reaction for CRITICAL severity."""
        from parity_validation.models import (
            CycleParityReport,
            MismatchSeverity,
            SystemReaction,
            ValidationMode,
        )
        
        report = MagicMock(spec=CycleParityReport)
        report.overall_match = False
        report.highest_severity = MismatchSeverity.CRITICAL
        report.failure_conditions = []
        
        reaction = handler.determine_reaction(report)
        
        assert reaction == SystemReaction.NOTIFY_TRADE_GUARD
    
    def test_determine_reaction_fatal(self, handler):
        """Test reaction for FATAL severity."""
        from parity_validation.models import (
            CycleParityReport,
            MismatchSeverity,
            SystemReaction,
            ValidationMode,
        )
        
        report = MagicMock(spec=CycleParityReport)
        report.overall_match = False
        report.highest_severity = MismatchSeverity.FATAL
        report.failure_conditions = []
        
        reaction = handler.determine_reaction(report)
        
        assert reaction == SystemReaction.BLOCK_TRADING


# ============================================================
# NOTIFICATION TESTS
# ============================================================

class TestNotificationRateLimiter:
    """Tests for NotificationRateLimiter."""
    
    def test_allows_first_notification(self):
        """Test that first notification is allowed."""
        from parity_validation.notifications import (
            NotificationRateLimiter,
            NotificationType,
        )
        
        limiter = NotificationRateLimiter()
        
        assert limiter.should_send(NotificationType.PARITY_MISMATCH)
    
    def test_limits_rapid_notifications(self):
        """Test that rapid notifications are limited."""
        from parity_validation.notifications import (
            NotificationRateLimiter,
            NotificationType,
        )
        
        # Create limiter with very low limit
        limiter = NotificationRateLimiter({
            NotificationType.PARITY_MISMATCH: (2, timedelta(minutes=5)),
        })
        
        # First two should be allowed
        assert limiter.should_send(NotificationType.PARITY_MISMATCH)
        assert limiter.should_send(NotificationType.PARITY_MISMATCH)
        
        # Third should be blocked
        assert not limiter.should_send(NotificationType.PARITY_MISMATCH)
    
    def test_reset_clears_limits(self):
        """Test that reset clears rate limits."""
        from parity_validation.notifications import (
            NotificationRateLimiter,
            NotificationType,
        )
        
        limiter = NotificationRateLimiter({
            NotificationType.PARITY_MISMATCH: (1, timedelta(minutes=5)),
        })
        
        assert limiter.should_send(NotificationType.PARITY_MISMATCH)
        assert not limiter.should_send(NotificationType.PARITY_MISMATCH)
        
        limiter.reset()
        
        assert limiter.should_send(NotificationType.PARITY_MISMATCH)


# ============================================================
# REPORT FORMATTER TESTS
# ============================================================

class TestReportFormatter:
    """Tests for ReportFormatter."""
    
    @pytest.fixture
    def formatter(self):
        """Create a report formatter."""
        from parity_validation.reporter import ReportFormatter
        return ReportFormatter()
    
    def test_format_cycle_report(self, formatter):
        """Test formatting a cycle report."""
        from parity_validation.models import (
            CycleParityReport,
            MismatchSeverity,
            SystemReaction,
            ValidationMode,
        )
        
        report = CycleParityReport(
            report_id="report_123",
            cycle_id="cycle_456",
            timestamp=datetime.utcnow(),
            validation_mode=ValidationMode.SHADOW_MODE,
            overall_match=True,
            highest_severity=MismatchSeverity.INFO,
            failure_conditions=[],
            recommended_reaction=SystemReaction.LOG_ONLY,
            data_parity=None,
            feature_parity=None,
            decision_parity=None,
            execution_parity=None,
            accounting_parity=None,
            code_version="1.0.0",
            config_version="1.0.0",
        )
        
        formatted = formatter.format_cycle_report(report)
        
        assert formatted["report_id"] == "report_123"
        assert formatted["cycle_id"] == "cycle_456"
        assert formatted["overall_match"] is True
        assert formatted["validation_mode"] == "shadow_mode"
    
    def test_format_text_summary(self, formatter):
        """Test formatting text summary."""
        from parity_validation.models import (
            CycleParityReport,
            MismatchSeverity,
            SystemReaction,
            ValidationMode,
        )
        
        report = CycleParityReport(
            report_id="report_123",
            cycle_id="cycle_456",
            timestamp=datetime.utcnow(),
            validation_mode=ValidationMode.SHADOW_MODE,
            overall_match=False,
            highest_severity=MismatchSeverity.WARNING,
            failure_conditions=[],
            recommended_reaction=SystemReaction.ESCALATE_RISK,
            data_parity=None,
            feature_parity=None,
            decision_parity=None,
            execution_parity=None,
            accounting_parity=None,
            code_version="1.0.0",
            config_version="1.0.0",
        )
        
        text = formatter.format_text_summary(report)
        
        assert "cycle_456" in text
        assert "✗" in text  # Not matching
        assert "WARNING" in text


# ============================================================
# INTEGRATION TESTS
# ============================================================

class TestParityValidationIntegration:
    """Integration tests for parity validation."""
    
    @pytest.fixture
    def mock_services(self):
        """Create mock services."""
        return {
            "data_service": AsyncMock(),
            "feature_service": AsyncMock(),
            "trade_guard": AsyncMock(),
            "execution_engine": AsyncMock(),
            "backtest_engine": AsyncMock(),
        }
    
    @pytest.mark.asyncio
    async def test_full_validation_cycle(self, mock_services, market_snapshot, feature_snapshot, decision_snapshot):
        """Test a complete validation cycle."""
        from parity_validation.models import ValidationMode, ToleranceConfig
        from parity_validation.collectors import SynchronizedCollector
        from parity_validation.comparators import create_comparators
        from parity_validation.drift_detector import create_drift_detector
        
        # Setup mock returns
        mock_services["data_service"].get_market_snapshot = AsyncMock(return_value=market_snapshot)
        mock_services["feature_service"].calculate_features = AsyncMock(return_value=feature_snapshot)
        mock_services["trade_guard"].evaluate = AsyncMock(return_value=decision_snapshot)
        
        # Create components
        tolerance = ToleranceConfig.default()
        comparators = create_comparators(tolerance)
        detector = create_drift_detector()
        
        # Comparators should be created
        assert "data" in comparators
        assert "feature" in comparators
        assert "decision" in comparators
        assert "execution" in comparators
        assert "accounting" in comparators
    
    @pytest.mark.asyncio
    async def test_tolerance_violation_detection(self, tolerance_config, market_snapshot):
        """Test that tolerance violations are detected."""
        from parity_validation.models import OHLCVData, MarketSnapshot
        from parity_validation.comparators import DataComparator
        
        comparator = DataComparator(tolerance_config)
        
        # Create backtest with significant price deviation
        bt_ohlcv = OHLCVData(
            open=market_snapshot.ohlcv.open,
            high=market_snapshot.ohlcv.high,
            low=market_snapshot.ohlcv.low,
            close=Decimal("51000.00"),  # 1.8% deviation
            volume=market_snapshot.ohlcv.volume,
            timestamp=market_snapshot.ohlcv.timestamp,
        )
        backtest = MarketSnapshot(
            symbol=market_snapshot.symbol,
            timestamp=market_snapshot.timestamp,
            ohlcv=bt_ohlcv,
            bid_price=market_snapshot.bid_price,
            ask_price=market_snapshot.ask_price,
            spread=market_snapshot.spread,
            volume_24h=market_snapshot.volume_24h,
            current_risk_level=market_snapshot.current_risk_level,
            exchange=market_snapshot.exchange,
            raw_data=market_snapshot.raw_data,
        )
        
        result = comparator.compare(market_snapshot, backtest)
        
        # Should detect mismatch
        assert not result.is_match
        
        # Should have mismatch for close price
        close_mismatch = next(
            (m for m in result.mismatches if m.field_name == "close_price"),
            None
        )
        assert close_mismatch is not None
        assert not close_mismatch.within_tolerance


# ============================================================
# EDGE CASE TESTS
# ============================================================

class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_decimal_precision(self, tolerance_config):
        """Test decimal precision handling."""
        # Very small differences should be within absolute tolerance
        assert tolerance_config.is_price_within_tolerance(
            Decimal("0.00001234567890"),
            Decimal("0.00001234567891"),
        )
    
    def test_very_large_numbers(self, tolerance_config):
        """Test handling of very large numbers."""
        # Large numbers should use relative tolerance
        result = tolerance_config.is_price_within_tolerance(
            Decimal("1000000000.00"),
            Decimal("1000000100.00"),  # 0.00001% deviation
        )
        assert result
    
    def test_negative_values(self, tolerance_config):
        """Test handling of negative values (e.g., PnL)."""
        # Both negative, small difference
        assert tolerance_config.is_feature_within_tolerance(
            Decimal("-100.00"),
            Decimal("-100.05"),
        )
    
    def test_mixed_signs(self, tolerance_config):
        """Test handling when signs differ."""
        # One positive, one negative - should be significant
        assert not tolerance_config.is_feature_within_tolerance(
            Decimal("100.00"),
            Decimal("-100.00"),
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
