"""
Tests for Data Reality Guard.

============================================================
TEST SCENARIOS
============================================================
1. Fresh data + matching price → PASS
2. Stale data → FAIL (trigger halt)
3. Price deviation > 3% → FAIL (trigger halt)
4. No data in database → FAIL (trigger halt)
5. Live reference unavailable → FAIL (trigger halt)
6. Guard disabled → always PASS

============================================================
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from system_risk_controller.guards.data_reality import (
    DataRealityGuard,
    DataRealityGuardConfig,
    DataRealityCheckResult,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def config():
    """Default test configuration."""
    return DataRealityGuardConfig(
        reference_interval_seconds=3600,  # 1 hour
        max_intervals_stale=2,            # 2 hours max age
        max_price_deviation_pct=3.0,      # 3% max deviation
        reference_symbol="BTC",
        reference_pair="BTCUSDT",
        enabled=True,
        halt_on_failure=True,
    )


@pytest.fixture
def guard(config):
    """Create guard instance."""
    return DataRealityGuard(config=config)


def create_mock_market_data(timestamp: datetime, price: float):
    """Create a mock MarketData object."""
    mock = MagicMock()
    mock.candle_open_time = timestamp
    mock.close_price = Decimal(str(price))
    mock.symbol = "BTCUSDT"
    return mock


# ============================================================
# TEST: FRESHNESS CHECK
# ============================================================

class TestFreshnessCheck:
    """Tests for data freshness validation."""
    
    @pytest.mark.asyncio
    async def test_fresh_data_passes(self, guard, config):
        """Data within 2 intervals should pass."""
        # Data from 30 minutes ago (well within 2 hours)
        now = datetime.now(timezone.utc)
        data_timestamp = now - timedelta(minutes=30)
        mock_data = create_mock_market_data(data_timestamp, 50000.0)
        
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = mock_data
            
            with patch.object(guard, '_fetch_live_price') as mock_live:
                mock_live.return_value = 50000.0
                
                result = await guard.check()
                
                assert result.freshness_passed is True
                assert result.data_age_seconds < 3600 * 2  # Less than 2 hours
    
    @pytest.mark.asyncio
    async def test_stale_data_fails(self, guard, config):
        """Data older than 2 intervals should fail."""
        # Data from 3 hours ago (exceeds 2 hour limit)
        now = datetime.now(timezone.utc)
        data_timestamp = now - timedelta(hours=3)
        mock_data = create_mock_market_data(data_timestamp, 50000.0)
        
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = mock_data
            
            with patch.object(guard, '_fetch_live_price') as mock_live:
                mock_live.return_value = 50000.0
                
                result = await guard.check()
                
                assert result.passed is False
                assert result.freshness_passed is False
                assert result.halt_required is True
                assert "stale" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_exactly_at_threshold_passes(self, guard, config):
        """Data exactly at threshold should pass."""
        # Data from just under 2 hours ago
        now = datetime.now(timezone.utc)
        data_timestamp = now - timedelta(seconds=config.max_data_age_seconds - 60)
        mock_data = create_mock_market_data(data_timestamp, 50000.0)
        
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = mock_data
            
            with patch.object(guard, '_fetch_live_price') as mock_live:
                mock_live.return_value = 50000.0
                
                result = await guard.check()
                
                assert result.freshness_passed is True


# ============================================================
# TEST: PRICE DEVIATION CHECK
# ============================================================

class TestPriceDeviationCheck:
    """Tests for price deviation validation."""
    
    @pytest.mark.asyncio
    async def test_matching_price_passes(self, guard):
        """Price within 3% should pass."""
        now = datetime.now(timezone.utc)
        mock_data = create_mock_market_data(now - timedelta(minutes=5), 50000.0)
        
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = mock_data
            
            with patch.object(guard, '_fetch_live_price') as mock_live:
                # Live price is exactly the same
                mock_live.return_value = 50000.0
                
                result = await guard.check()
                
                assert result.deviation_passed is True
                assert result.deviation_pct == 0.0
    
    @pytest.mark.asyncio
    async def test_within_threshold_passes(self, guard):
        """Price deviation < 3% should pass."""
        now = datetime.now(timezone.utc)
        mock_data = create_mock_market_data(now - timedelta(minutes=5), 51000.0)  # 2% higher
        
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = mock_data
            
            with patch.object(guard, '_fetch_live_price') as mock_live:
                mock_live.return_value = 50000.0
                
                result = await guard.check()
                
                assert result.deviation_passed is True
                assert result.deviation_pct == pytest.approx(2.0, rel=0.01)
    
    @pytest.mark.asyncio
    async def test_exceeds_threshold_fails(self, guard):
        """Price deviation > 3% should fail."""
        now = datetime.now(timezone.utc)
        mock_data = create_mock_market_data(now - timedelta(minutes=5), 55000.0)  # 10% higher
        
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = mock_data
            
            with patch.object(guard, '_fetch_live_price') as mock_live:
                mock_live.return_value = 50000.0
                
                result = await guard.check()
                
                assert result.passed is False
                assert result.deviation_passed is False
                assert result.halt_required is True
                assert result.deviation_pct == pytest.approx(10.0, rel=0.01)
                assert "deviation" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_exactly_at_threshold_passes(self, guard):
        """Price deviation exactly at 3% should pass."""
        now = datetime.now(timezone.utc)
        mock_data = create_mock_market_data(now - timedelta(minutes=5), 51500.0)  # exactly 3%
        
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = mock_data
            
            with patch.object(guard, '_fetch_live_price') as mock_live:
                mock_live.return_value = 50000.0
                
                result = await guard.check()
                
                assert result.deviation_passed is True


# ============================================================
# TEST: NO DATA SCENARIOS
# ============================================================

class TestNoDataScenarios:
    """Tests for missing data scenarios."""
    
    @pytest.mark.asyncio
    async def test_no_market_data_fails(self, guard):
        """No data in database should fail."""
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = None
            
            result = await guard.check()
            
            assert result.passed is False
            assert result.halt_required is True
            assert "no market data" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_live_reference_unavailable_fails(self, guard):
        """Cannot reach live reference should fail."""
        now = datetime.now(timezone.utc)
        mock_data = create_mock_market_data(now - timedelta(minutes=5), 50000.0)
        
        with patch.object(guard, '_get_latest_market_data') as mock_get_data:
            mock_get_data.return_value = mock_data
            
            with patch.object(guard, '_fetch_live_price') as mock_live:
                mock_live.side_effect = Exception("Network error")
                
                result = await guard.check()
                
                assert result.passed is False
                assert result.halt_required is True
                assert "live" in result.error_message.lower() or "error" in result.error_message.lower()


# ============================================================
# TEST: GUARD DISABLED
# ============================================================

class TestGuardDisabled:
    """Tests for disabled guard."""
    
    @pytest.mark.asyncio
    async def test_disabled_guard_passes(self):
        """Disabled guard should always pass."""
        config = DataRealityGuardConfig(enabled=False)
        guard = DataRealityGuard(config=config)
        
        result = await guard.check()
        
        assert result.passed is True
        assert result.halt_required is False


# ============================================================
# TEST: CONFIGURATION
# ============================================================

class TestConfiguration:
    """Tests for configuration options."""
    
    def test_max_data_age_calculation(self):
        """Test max_data_age_seconds property."""
        config = DataRealityGuardConfig(
            reference_interval_seconds=3600,
            max_intervals_stale=2,
        )
        
        assert config.max_data_age_seconds == 7200  # 2 hours
    
    def test_custom_deviation_threshold(self):
        """Test custom deviation threshold."""
        config = DataRealityGuardConfig(
            max_price_deviation_pct=5.0,  # 5% instead of 3%
        )
        
        assert config.max_price_deviation_pct == 5.0
    
    def test_halt_on_failure_configurable(self):
        """Test halt_on_failure flag."""
        config = DataRealityGuardConfig(halt_on_failure=False)
        
        assert config.halt_on_failure is False


# ============================================================
# TEST: RESULT TO_DICT
# ============================================================

class TestResultSerialization:
    """Tests for result serialization."""
    
    def test_to_dict_contains_all_fields(self):
        """Test to_dict includes all important fields."""
        result = DataRealityCheckResult(
            passed=True,
            freshness_passed=True,
            deviation_passed=True,
            stored_price=50000.0,
            live_price=50000.0,
            deviation_pct=0.0,
            data_age_seconds=300.0,
        )
        
        d = result.to_dict()
        
        assert "passed" in d
        assert "timestamp" in d
        assert "freshness" in d
        assert "deviation" in d
        assert "halt_required" in d
        
        assert d["freshness"]["age_seconds"] == 300.0
        assert d["deviation"]["deviation_pct"] == 0.0


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
