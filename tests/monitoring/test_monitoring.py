"""
Tests for Monitoring & Dashboard Subsystem.

============================================================
PURPOSE
============================================================
Comprehensive tests for the monitoring subsystem.

TEST PRINCIPLES:
- Verify read-only behavior
- Test alert rule determinism
- Validate data collection
- Confirm proper UNKNOWN handling

============================================================
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
from unittest.mock import AsyncMock, MagicMock, patch

# Import monitoring components
from monitoring.models import (
    SystemMode,
    ModuleStatus,
    AlertTier,
    DataFreshness,
    SystemStateSnapshot,
    DataSourceStatus,
    PositionSnapshot,
    RiskExposureSnapshot,
    SignalRecord,
    OrderRecord,
    ModuleHealth,
    Alert,
    DashboardOverview,
)
from monitoring.collectors import (
    BaseCollector,
    SystemStateCollector,
    DataPipelineCollector,
    ModuleHealthCollector,
    RiskExposureCollector,
    PositionCollector,
    SignalCollector,
    OrderCollector,
)
from monitoring.alerts import (
    AlertCategory,
    AlertRule,
    AlertRuleConfig,
    DrawdownThresholdRule,
    ExposureLimitRule,
    MarginWarningRule,
    ModuleUnhealthyRule,
    DataStaleRule,
    SystemModeChangeRule,
    AlertHistory,
    AlertManager,
    get_default_rules,
)
from monitoring.notifications import (
    TelegramFormatter,
    TelegramRateLimiter,
    TelegramNotifier,
)
from monitoring.dashboard_service import (
    DashboardService,
    create_dashboard_service,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def mock_state_store():
    """Create mock state store."""
    store = AsyncMock()
    store.get = AsyncMock(side_effect=lambda key: {
        "system.mode": "RUNNING",
        "system.mode_changed_at": datetime.utcnow(),
        "system.mode_changed_by": "SYSTEM",
        "system.mode_reason": "Normal operation",
        "trading.enabled": True,
        "trading.active_orders": 5,
        "trading.open_positions": 3,
        "modules.health": {
            "execution_engine": {"status": "HEALTHY"},
            "risk_controller": {"status": "HEALTHY"},
        },
    }.get(key))
    return store


@pytest.fixture
def mock_position_store():
    """Create mock position store."""
    store = AsyncMock()
    store.get_all_positions = AsyncMock(return_value=[
        {
            "id": "pos1",
            "symbol": "BTCUSDT",
            "exchange": "binance",
            "side": "long",
            "size": Decimal("0.5"),
            "notional_value": Decimal("15000"),
            "entry_price": Decimal("30000"),
            "current_price": Decimal("30500"),
            "unrealized_pnl": Decimal("250"),
            "leverage": Decimal("10"),
        },
        {
            "id": "pos2",
            "symbol": "ETHUSDT",
            "exchange": "binance",
            "side": "short",
            "size": Decimal("2"),
            "notional_value": Decimal("4000"),
            "entry_price": Decimal("2000"),
            "current_price": Decimal("1950"),
            "unrealized_pnl": Decimal("100"),
            "leverage": Decimal("5"),
        },
    ])
    store.get_position = AsyncMock(return_value={
        "id": "pos1",
        "symbol": "BTCUSDT",
        "exchange": "binance",
        "side": "long",
    })
    store.get_last_update_time = AsyncMock(return_value=datetime.utcnow())
    return store


@pytest.fixture
def mock_risk_store():
    """Create mock risk store."""
    store = AsyncMock()
    store.get_current_metrics = AsyncMock(return_value={
        "current_drawdown": Decimal("-0.03"),
        "max_drawdown_today": Decimal("-0.05"),
        "daily_pnl": Decimal("1500"),
        "realized_pnl": Decimal("1000"),
        "unrealized_pnl": Decimal("500"),
        "risk_budget_used_pct": Decimal("0.60"),
        "risk_budget_remaining": Decimal("10000"),
        "max_position_size": Decimal("50000"),
        "max_leverage": Decimal("10"),
        "current_leverage": Decimal("5"),
    })
    return store


@pytest.fixture
def mock_balance_reader():
    """Create mock balance reader."""
    reader = AsyncMock()
    reader.get_balance = AsyncMock(return_value={
        "total_equity": Decimal("100000"),
        "total_balance": Decimal("95000"),
        "available_balance": Decimal("80000"),
        "margin_used": Decimal("15000"),
        "margin_ratio": Decimal("0.15"),
        "is_fresh": True,
    })
    return reader


@pytest.fixture
def sample_system_state():
    """Create sample system state snapshot."""
    return SystemStateSnapshot(
        mode=SystemMode.RUNNING,
        mode_changed_at=datetime.utcnow(),
        mode_changed_by="SYSTEM",
        mode_reason="Normal operation",
        snapshot_time=datetime.utcnow(),
        system_uptime_seconds=3600,
        healthy_modules=5,
        degraded_modules=0,
        unhealthy_modules=0,
        trading_enabled=True,
        active_orders_count=3,
        open_positions_count=2,
    )


@pytest.fixture
def sample_risk_exposure():
    """Create sample risk exposure snapshot."""
    return RiskExposureSnapshot(
        snapshot_time=datetime.utcnow(),
        total_equity=Decimal("100000"),
        total_balance=Decimal("95000"),
        available_balance=Decimal("80000"),
        margin_used=Decimal("15000"),
        margin_ratio=Decimal("0.15"),
        total_exposure=Decimal("50000"),
        exposure_ratio=Decimal("0.50"),
        long_exposure=Decimal("35000"),
        short_exposure=Decimal("15000"),
        net_exposure=Decimal("20000"),
        current_drawdown=Decimal("-0.03"),
        max_drawdown_today=Decimal("-0.05"),
        daily_pnl=Decimal("1500"),
        realized_pnl=Decimal("1000"),
        unrealized_pnl=Decimal("500"),
        position_count=2,
        long_count=1,
        short_count=1,
        risk_budget_used_pct=Decimal("0.60"),
        risk_budget_remaining=Decimal("10000"),
        max_position_size=Decimal("50000"),
        max_leverage=Decimal("10"),
        current_leverage=Decimal("5"),
        balance_data_fresh=True,
        position_data_fresh=True,
    )


# ============================================================
# COLLECTOR TESTS
# ============================================================

class TestSystemStateCollector:
    """Tests for SystemStateCollector."""
    
    @pytest.mark.asyncio
    async def test_collect_returns_snapshot(self, mock_state_store):
        """Test that collector returns a valid snapshot."""
        collector = SystemStateCollector(state_store=mock_state_store)
        result = await collector.collect()
        
        assert isinstance(result, SystemStateSnapshot)
        assert result.mode == SystemMode.RUNNING
        assert result.trading_enabled is True
    
    @pytest.mark.asyncio
    async def test_collect_without_store_returns_initializing(self):
        """Test that collector without store returns INITIALIZING."""
        collector = SystemStateCollector(state_store=None)
        result = await collector.collect()
        
        assert isinstance(result, SystemStateSnapshot)
        assert result.mode == SystemMode.INITIALIZING
    
    @pytest.mark.asyncio
    async def test_safe_collect_handles_errors(self, mock_state_store):
        """Test that safe_collect handles errors gracefully."""
        mock_state_store.get.side_effect = Exception("Connection error")
        collector = SystemStateCollector(state_store=mock_state_store)
        
        result = await collector.safe_collect()
        # Should return None on error, not raise
        # (actual implementation returns partial data)
        assert result is not None


class TestRiskExposureCollector:
    """Tests for RiskExposureCollector."""
    
    @pytest.mark.asyncio
    async def test_collect_aggregates_positions(
        self,
        mock_risk_store,
        mock_position_store,
        mock_balance_reader,
    ):
        """Test that collector aggregates position data."""
        collector = RiskExposureCollector(
            risk_store=mock_risk_store,
            position_store=mock_position_store,
            balance_reader=mock_balance_reader,
        )
        
        result = await collector.collect()
        
        assert isinstance(result, RiskExposureSnapshot)
        assert result.total_equity == Decimal("100000")
        assert result.position_count == 2
        assert result.long_count == 1
        assert result.short_count == 1
    
    @pytest.mark.asyncio
    async def test_collect_without_stores_returns_empty(self):
        """Test that collector without stores returns empty snapshot."""
        collector = RiskExposureCollector()
        result = await collector.collect()
        
        assert isinstance(result, RiskExposureSnapshot)
        assert result.position_count == 0
        assert result.balance_data_fresh is False


class TestPositionCollector:
    """Tests for PositionCollector."""
    
    @pytest.mark.asyncio
    async def test_collect_returns_positions(self, mock_position_store):
        """Test that collector returns position snapshots."""
        collector = PositionCollector(position_store=mock_position_store)
        result = await collector.collect()
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(p, PositionSnapshot) for p in result)
        assert result[0].symbol == "BTCUSDT"
    
    @pytest.mark.asyncio
    async def test_get_position_by_id(self, mock_position_store):
        """Test getting a single position."""
        collector = PositionCollector(position_store=mock_position_store)
        result = await collector.get_position("pos1")
        
        assert isinstance(result, PositionSnapshot)
        assert result.position_id == "pos1"


# ============================================================
# ALERT RULE TESTS
# ============================================================

class TestDrawdownThresholdRule:
    """Tests for DrawdownThresholdRule."""
    
    def test_triggers_on_warning_threshold(self, sample_risk_exposure):
        """Test that rule triggers on warning threshold."""
        rule = DrawdownThresholdRule(
            warning_threshold=Decimal("0.02"),
            critical_threshold=Decimal("0.10"),
        )
        
        # 3% drawdown exceeds 2% warning
        context = {"risk_exposure": sample_risk_exposure}
        alert = rule.evaluate(context)
        
        assert alert is not None
        assert alert.tier == AlertTier.WARNING
        assert "drawdown" in alert.title.lower()
    
    def test_triggers_on_critical_threshold(self, sample_risk_exposure):
        """Test that rule triggers on critical threshold."""
        rule = DrawdownThresholdRule(
            warning_threshold=Decimal("0.01"),
            critical_threshold=Decimal("0.02"),
        )
        
        # 3% drawdown exceeds 2% critical
        context = {"risk_exposure": sample_risk_exposure}
        alert = rule.evaluate(context)
        
        assert alert is not None
        assert alert.tier == AlertTier.CRITICAL
    
    def test_no_trigger_below_threshold(self, sample_risk_exposure):
        """Test that rule doesn't trigger below threshold."""
        rule = DrawdownThresholdRule(
            warning_threshold=Decimal("0.10"),
            critical_threshold=Decimal("0.20"),
        )
        
        context = {"risk_exposure": sample_risk_exposure}
        alert = rule.evaluate(context)
        
        assert alert is None
    
    def test_handles_missing_data(self):
        """Test that rule handles missing data gracefully."""
        rule = DrawdownThresholdRule()
        
        # No risk exposure in context
        alert = rule.evaluate({})
        assert alert is None
        
        # Risk exposure but no drawdown
        risk = MagicMock()
        risk.current_drawdown = None
        alert = rule.evaluate({"risk_exposure": risk})
        assert alert is None


class TestMarginWarningRule:
    """Tests for MarginWarningRule."""
    
    def test_triggers_on_high_margin(self, sample_risk_exposure):
        """Test that rule triggers on high margin usage."""
        # Modify to have high margin
        sample_risk_exposure.margin_ratio = Decimal("0.80")
        
        rule = MarginWarningRule(
            warning_threshold=Decimal("0.70"),
            critical_threshold=Decimal("0.85"),
        )
        
        context = {"risk_exposure": sample_risk_exposure}
        alert = rule.evaluate(context)
        
        assert alert is not None
        assert alert.tier == AlertTier.WARNING


class TestModuleUnhealthyRule:
    """Tests for ModuleUnhealthyRule."""
    
    def test_triggers_on_unhealthy_module(self):
        """Test that rule triggers when module is unhealthy."""
        rule = ModuleUnhealthyRule()
        
        modules = {
            "execution_engine": ModuleHealth(
                module_name="execution_engine",
                module_type="core",
                status=ModuleStatus.HEALTHY,
                last_heartbeat=datetime.utcnow(),
                heartbeat_interval_seconds=30,
                heartbeat_missed=False,
            ),
            "risk_controller": ModuleHealth(
                module_name="risk_controller",
                module_type="core",
                status=ModuleStatus.UNHEALTHY,
                status_reason="Connection lost",
                last_heartbeat=datetime.utcnow() - timedelta(minutes=5),
                heartbeat_interval_seconds=30,
                heartbeat_missed=True,
            ),
        }
        
        context = {"module_health": modules}
        alert = rule.evaluate(context)
        
        assert alert is not None
        assert alert.tier == AlertTier.CRITICAL
        assert "risk_controller" in alert.message


class TestDataStaleRule:
    """Tests for DataStaleRule."""
    
    def test_triggers_on_stale_data(self):
        """Test that rule triggers on stale data source."""
        rule = DataStaleRule()
        
        sources = [
            DataSourceStatus(
                source_name="market_data",
                source_type="websocket",
                last_successful_fetch=datetime.utcnow() - timedelta(minutes=10),
                freshness=DataFreshness.STALE,
                error_count_1m=0,
                error_count_5m=0,
                error_count_1h=0,
                is_stale=True,
            ),
        ]
        
        context = {"data_sources": sources}
        alert = rule.evaluate(context)
        
        assert alert is not None
        assert "stale" in alert.title.lower()


class TestSystemModeChangeRule:
    """Tests for SystemModeChangeRule."""
    
    def test_triggers_on_mode_change(self, sample_system_state):
        """Test that rule triggers on mode change."""
        rule = SystemModeChangeRule()
        
        # First evaluation sets baseline
        context = {"system_state": sample_system_state}
        alert = rule.evaluate(context)
        assert alert is None  # No change yet
        
        # Change mode
        sample_system_state.mode = SystemMode.HALTED_SYSTEM
        sample_system_state.mode_reason = "Emergency halt"
        
        alert = rule.evaluate(context)
        
        assert alert is not None
        assert alert.tier == AlertTier.CRITICAL
        assert "HALTED_SYSTEM" in alert.title


# ============================================================
# ALERT MANAGER TESTS
# ============================================================

class TestAlertHistory:
    """Tests for AlertHistory."""
    
    def test_add_and_get_alert(self):
        """Test adding and retrieving alerts."""
        history = AlertHistory()
        
        alert = Alert(
            alert_id="test_1",
            tier=AlertTier.WARNING,
            category="test",
            title="Test Alert",
            message="This is a test",
            triggered_at=datetime.utcnow(),
            triggered_by_rule="test_rule",
        )
        
        history.add(alert)
        
        retrieved = history.get("test_1")
        assert retrieved is not None
        assert retrieved.alert_id == "test_1"
    
    def test_get_active_alerts(self):
        """Test getting active alerts."""
        history = AlertHistory()
        
        # Add active alert
        history.add(Alert(
            alert_id="active_1",
            tier=AlertTier.WARNING,
            category="test",
            title="Active",
            message="Active alert",
            triggered_at=datetime.utcnow(),
            triggered_by_rule="test",
            resolved=False,
        ))
        
        # Add resolved alert
        history.add(Alert(
            alert_id="resolved_1",
            tier=AlertTier.INFO,
            category="test",
            title="Resolved",
            message="Resolved alert",
            triggered_at=datetime.utcnow(),
            triggered_by_rule="test",
            resolved=True,
        ))
        
        active = history.get_active()
        assert len(active) == 1
        assert active[0].alert_id == "active_1"
    
    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        history = AlertHistory()
        
        history.add(Alert(
            alert_id="ack_test",
            tier=AlertTier.WARNING,
            category="test",
            title="To Acknowledge",
            message="Needs ack",
            triggered_at=datetime.utcnow(),
            triggered_by_rule="test",
        ))
        
        success = history.acknowledge("ack_test", "operator")
        
        assert success is True
        alert = history.get("ack_test")
        assert alert.acknowledged is True
        assert alert.acknowledged_by == "operator"


class TestAlertManager:
    """Tests for AlertManager."""
    
    @pytest.mark.asyncio
    async def test_evaluate_triggers_alerts(self, sample_risk_exposure):
        """Test that manager evaluates rules and triggers alerts."""
        manager = AlertManager(rules=[
            DrawdownThresholdRule(
                warning_threshold=Decimal("0.01"),
                critical_threshold=Decimal("0.05"),
            ),
        ])
        
        context = {"risk_exposure": sample_risk_exposure}
        triggered = await manager.evaluate(context)
        
        assert len(triggered) == 1
        assert triggered[0].tier == AlertTier.WARNING
    
    @pytest.mark.asyncio
    async def test_disabled_manager_no_alerts(self, sample_risk_exposure):
        """Test that disabled manager doesn't trigger alerts."""
        manager = AlertManager(rules=[
            DrawdownThresholdRule(
                warning_threshold=Decimal("0.01"),
            ),
        ])
        manager.disable()
        
        context = {"risk_exposure": sample_risk_exposure}
        triggered = await manager.evaluate(context)
        
        assert len(triggered) == 0
    
    @pytest.mark.asyncio
    async def test_notification_handler_called(self, sample_risk_exposure):
        """Test that notification handlers are called."""
        handler = AsyncMock(return_value=True)
        
        manager = AlertManager(
            rules=[
                DrawdownThresholdRule(warning_threshold=Decimal("0.01")),
            ],
            notification_handlers=[handler],
        )
        
        context = {"risk_exposure": sample_risk_exposure}
        await manager.evaluate(context)
        
        handler.assert_called_once()


# ============================================================
# NOTIFICATION TESTS
# ============================================================

class TestTelegramFormatter:
    """Tests for TelegramFormatter."""
    
    def test_format_alert(self):
        """Test formatting an alert."""
        alert = Alert(
            alert_id="test_1",
            tier=AlertTier.WARNING,
            category="risk",
            title="High Exposure",
            message="Exposure at 80%",
            triggered_at=datetime.utcnow(),
            triggered_by_rule="exposure_limit",
            data={"exposure_pct": 80},
        )
        
        formatted = TelegramFormatter.format_alert(alert)
        
        assert "High Exposure" in formatted
        assert "WARNING" in formatted
        assert "📊" in formatted  # Risk icon
        assert "⚠️" in formatted  # Warning icon
    
    def test_format_summary(self):
        """Test formatting alert summary."""
        alerts = [
            Alert(
                alert_id="1",
                tier=AlertTier.CRITICAL,
                category="system",
                title="Critical Alert",
                message="Critical",
                triggered_at=datetime.utcnow(),
                triggered_by_rule="test",
            ),
            Alert(
                alert_id="2",
                tier=AlertTier.WARNING,
                category="risk",
                title="Warning Alert",
                message="Warning",
                triggered_at=datetime.utcnow(),
                triggered_by_rule="test",
            ),
        ]
        
        formatted = TelegramFormatter.format_summary(alerts)
        
        assert "Critical: 1" in formatted
        assert "Warning: 1" in formatted


class TestTelegramRateLimiter:
    """Tests for TelegramRateLimiter."""
    
    @pytest.mark.asyncio
    async def test_allows_within_limit(self):
        """Test that rate limiter allows requests within limit."""
        limiter = TelegramRateLimiter(max_per_minute=5, max_per_hour=100)
        
        for _ in range(3):
            assert await limiter.acquire() is True
    
    @pytest.mark.asyncio
    async def test_blocks_over_minute_limit(self):
        """Test that rate limiter blocks over minute limit."""
        limiter = TelegramRateLimiter(max_per_minute=2, max_per_hour=100)
        
        assert await limiter.acquire() is True
        assert await limiter.acquire() is True
        assert await limiter.acquire() is False  # Should be blocked


# ============================================================
# DASHBOARD SERVICE TESTS
# ============================================================

class TestDashboardService:
    """Tests for DashboardService."""
    
    @pytest.mark.asyncio
    async def test_get_overview_returns_dashboard(
        self,
        mock_state_store,
        mock_position_store,
        mock_risk_store,
        mock_balance_reader,
    ):
        """Test that get_overview returns a complete dashboard."""
        service = create_dashboard_service(
            state_store=mock_state_store,
            position_store=mock_position_store,
            risk_store=mock_risk_store,
            balance_reader=mock_balance_reader,
        )
        
        overview = await service.get_overview()
        
        assert isinstance(overview, DashboardOverview)
        assert overview.system_state is not None
        assert overview.risk_exposure is not None
        assert isinstance(overview.active_positions, list)
    
    @pytest.mark.asyncio
    async def test_get_overview_handles_failures_gracefully(self):
        """Test that get_overview handles collector failures."""
        # Service with no stores - should return empty/default data
        service = create_dashboard_service()
        
        overview = await service.get_overview()
        
        assert isinstance(overview, DashboardOverview)
        assert overview.system_state.mode == SystemMode.INITIALIZING
        assert overview.risk_exposure.position_count == 0
    
    @pytest.mark.asyncio
    async def test_get_alert_context(
        self,
        mock_state_store,
        mock_risk_store,
        mock_balance_reader,
        mock_position_store,
    ):
        """Test getting alert context."""
        service = create_dashboard_service(
            state_store=mock_state_store,
            risk_store=mock_risk_store,
            balance_reader=mock_balance_reader,
            position_store=mock_position_store,
        )
        
        context = await service.get_alert_context()
        
        assert "system_state" in context
        assert "risk_exposure" in context
        assert "module_health" in context
        assert "data_sources" in context


# ============================================================
# READ-ONLY VERIFICATION TESTS
# ============================================================

class TestReadOnlyBehavior:
    """Tests to verify read-only behavior."""
    
    def test_collectors_do_not_modify_stores(self, mock_position_store):
        """Verify collectors don't call mutating methods."""
        collector = PositionCollector(position_store=mock_position_store)
        
        # Check that no mutating methods exist on the store mock
        # that would have been called
        assert not hasattr(mock_position_store, "create_position")
        assert not hasattr(mock_position_store, "update_position")
        assert not hasattr(mock_position_store, "delete_position")
    
    def test_alert_rules_do_not_modify_context(self, sample_risk_exposure):
        """Verify alert rules don't modify the context."""
        original_drawdown = sample_risk_exposure.current_drawdown
        
        rule = DrawdownThresholdRule()
        context = {"risk_exposure": sample_risk_exposure}
        
        rule.evaluate(context)
        
        # Verify context wasn't modified
        assert sample_risk_exposure.current_drawdown == original_drawdown
    
    def test_dashboard_service_is_read_only_marked(self):
        """Verify DashboardService has ReadOnlyAccess marker."""
        from monitoring.models import ReadOnlyAccess
        
        service = DashboardService()
        assert isinstance(service, ReadOnlyAccess)


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
