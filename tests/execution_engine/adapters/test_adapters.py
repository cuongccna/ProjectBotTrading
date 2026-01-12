"""
Exchange Adapter Tests.

============================================================
PURPOSE
============================================================
Unit and integration tests for exchange adapters.

TEST CATEGORIES:
- Factory tests: Adapter creation
- Error mapping tests: Error code translation
- Metrics tests: Metrics collection
- Logging tests: Credential masking

============================================================
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import time

from execution_engine.adapters import (
    # Factory
    AdapterFactory,
    AdapterConfig,
    AdapterPool,
    create_adapter,
    # Base
    ExchangeAdapter,
    SubmitOrderRequest,
    SubmitOrderResponse,
    QueryOrderRequest,
    CancelOrderRequest,
    # Errors
    ErrorCategory,
    RetryEligibility,
    map_binance_error,
    map_okx_error,
    map_bybit_error,
    map_exchange_error,
    create_network_error,
    create_timeout_error,
    # Metrics
    AdapterMetrics,
    MetricType,
    get_global_aggregator,
    # Logging
    AdapterLogger,
    mask_value,
    mask_headers,
    mask_params,
    get_audit_log,
    # Mock
    MockExchangeAdapter,
    MockConfig,
)


# ============================================================
# FACTORY TESTS
# ============================================================

class TestAdapterFactory:
    """Tests for AdapterFactory."""
    
    def test_list_supported_exchanges(self):
        """Test listing supported exchanges."""
        supported = AdapterFactory.list_supported()
        
        assert "binance" in supported
        assert "okx" in supported
        assert "bybit" in supported
        assert "mock" in supported
    
    def test_create_mock_adapter(self):
        """Test creating mock adapter."""
        adapter = AdapterFactory.create("mock")
        
        assert adapter is not None
        assert adapter.exchange_id == "mock"
    
    def test_create_with_config(self):
        """Test creating adapter with config."""
        config = AdapterConfig(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )
        
        adapter = AdapterFactory.create("mock", config=config)
        
        assert adapter is not None
    
    def test_create_convenience_function(self):
        """Test create_adapter convenience function."""
        adapter = create_adapter("mock", testnet=True)
        
        assert adapter is not None
        assert adapter.exchange_id == "mock"
    
    def test_create_unsupported_raises(self):
        """Test that unsupported exchange raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported exchange"):
            AdapterFactory.create("unsupported_exchange")
    
    def test_create_all_adapters(self):
        """Test creating multiple adapters."""
        adapters = AdapterFactory.create_all(["mock", "mock"])
        
        assert len(adapters) == 2
        assert "mock" in adapters


class TestAdapterPool:
    """Tests for AdapterPool."""
    
    @pytest.mark.asyncio
    async def test_add_adapter(self):
        """Test adding adapter to pool."""
        pool = AdapterPool()
        
        adapter = MockExchangeAdapter()
        await pool.add("mock", adapter=adapter, auto_connect=False)
        
        assert "mock" in pool
        assert pool.get("mock") is adapter
    
    @pytest.mark.asyncio
    async def test_remove_adapter(self):
        """Test removing adapter from pool."""
        pool = AdapterPool()
        
        adapter = MockExchangeAdapter()
        await pool.add("mock", adapter=adapter, auto_connect=False)
        await pool.remove("mock")
        
        assert "mock" not in pool
    
    @pytest.mark.asyncio
    async def test_list_exchanges(self):
        """Test listing exchanges in pool."""
        pool = AdapterPool()
        
        await pool.add("mock1", adapter=MockExchangeAdapter(), auto_connect=False)
        await pool.add("mock2", adapter=MockExchangeAdapter(), auto_connect=False)
        
        exchanges = pool.list_exchanges()
        
        assert "mock1" in exchanges
        assert "mock2" in exchanges
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test pool as async context manager."""
        async with AdapterPool() as pool:
            await pool.add("mock", adapter=MockExchangeAdapter(), auto_connect=False)
            assert "mock" in pool


# ============================================================
# ERROR MAPPING TESTS
# ============================================================

class TestBinanceErrorMapping:
    """Tests for Binance error mapping."""
    
    def test_rate_limit_error(self):
        """Test rate limit error mapping."""
        error = map_binance_error(-1003, "Too many requests", 429)
        
        assert error.category == ErrorCategory.RATE_LIMIT
        assert error.retry_eligible == RetryEligibility.BACKOFF
        assert error.exchange_id == "binance"
    
    def test_auth_error(self):
        """Test authentication error mapping."""
        error = map_binance_error(-2015, "Invalid API key", 401)
        
        assert error.category == ErrorCategory.AUTHENTICATION
        assert error.retry_eligible == RetryEligibility.NO_RETRY
    
    def test_insufficient_funds(self):
        """Test insufficient funds error."""
        error = map_binance_error(-2010, "Insufficient balance", 400)
        
        assert error.category == ErrorCategory.INSUFFICIENT_FUNDS
        assert error.is_retryable() is False
    
    def test_invalid_quantity(self):
        """Test invalid quantity error."""
        error = map_binance_error(-1111, "Invalid quantity", 400)
        
        assert error.category == ErrorCategory.INVALID_QUANTITY
    
    def test_order_not_found(self):
        """Test order not found error."""
        error = map_binance_error(-2013, "Order does not exist", 400)
        
        assert error.category == ErrorCategory.ORDER_NOT_FOUND


class TestOKXErrorMapping:
    """Tests for OKX error mapping."""
    
    def test_rate_limit_error(self):
        """Test rate limit error mapping."""
        error = map_okx_error("50011", "Rate limit exceeded", 429)
        
        assert error.category == ErrorCategory.RATE_LIMIT
        assert error.retry_eligible == RetryEligibility.BACKOFF
    
    def test_auth_error(self):
        """Test authentication error."""
        error = map_okx_error("50101", "Invalid API key", 401)
        
        assert error.category == ErrorCategory.AUTHENTICATION
    
    def test_insufficient_margin(self):
        """Test insufficient margin error."""
        error = map_okx_error("51119", "Insufficient margin", 400)
        
        assert error.category == ErrorCategory.INSUFFICIENT_MARGIN


class TestBybitErrorMapping:
    """Tests for Bybit error mapping."""
    
    def test_rate_limit_error(self):
        """Test rate limit error mapping."""
        error = map_bybit_error(10006, "Rate limit exceeded", 429)
        
        assert error.category == ErrorCategory.RATE_LIMIT
        assert error.retry_eligible == RetryEligibility.BACKOFF
    
    def test_order_not_found(self):
        """Test order not found error."""
        error = map_bybit_error(110001, "Order not found", 400)
        
        assert error.category == ErrorCategory.ORDER_NOT_FOUND


class TestExchangeErrorFactory:
    """Tests for exchange error factory function."""
    
    def test_route_to_binance(self):
        """Test routing to Binance mapper."""
        error = map_exchange_error("binance", -1003, "Rate limit", 429)
        
        assert error.code == "BINANCE_-1003"
        assert error.category == ErrorCategory.RATE_LIMIT
    
    def test_route_to_okx(self):
        """Test routing to OKX mapper."""
        error = map_exchange_error("okx", "50011", "Rate limit", 429)
        
        assert error.code == "OKX_50011"
    
    def test_route_to_bybit(self):
        """Test routing to Bybit mapper."""
        error = map_exchange_error("bybit", 10006, "Rate limit", 429)
        
        assert error.code == "BYBIT_10006"
    
    def test_unknown_exchange(self):
        """Test handling unknown exchange."""
        error = map_exchange_error("unknown", "123", "Error", 400)
        
        assert error.category == ErrorCategory.UNKNOWN
        assert error.code == "UNKNOWN_123"


class TestErrorHelpers:
    """Tests for error helper functions."""
    
    def test_create_network_error(self):
        """Test creating network error."""
        error = create_network_error("binance", "Connection refused")
        
        assert error.category == ErrorCategory.NETWORK
        assert error.is_retryable() is True
    
    def test_create_timeout_error(self):
        """Test creating timeout error."""
        error = create_timeout_error("okx", 30000)
        
        assert error.category == ErrorCategory.TIMEOUT
        assert "30000" in error.message


# ============================================================
# METRICS TESTS
# ============================================================

class TestAdapterMetrics:
    """Tests for AdapterMetrics."""
    
    def test_record_request(self):
        """Test recording request."""
        metrics = AdapterMetrics("test")
        
        metrics.record_request(
            endpoint="/v1/order",
            latency_ms=150.0,
            success=True,
            status_code=200,
        )
        
        summary = metrics.get_summary()
        
        assert summary["requests"]["total"] == 1
        assert summary["requests"]["success"] == 1
        assert summary["latency"]["avg_ms"] == 150.0
    
    def test_record_failure(self):
        """Test recording failed request."""
        metrics = AdapterMetrics("test")
        
        metrics.record_request(
            endpoint="/v1/order",
            latency_ms=100.0,
            success=False,
            error_code="RATE_LIMIT",
        )
        
        summary = metrics.get_summary()
        
        assert summary["requests"]["failure"] == 1
        assert summary["errors"]["rate_limit_hits"] == 1
    
    def test_record_orders(self):
        """Test recording order metrics."""
        metrics = AdapterMetrics("test")
        
        metrics.record_order_submitted()
        metrics.record_order_filled()
        metrics.record_order_rejected("INVALID_QTY")
        metrics.record_order_canceled()
        
        summary = metrics.get_summary()
        
        assert summary["orders"]["submitted"] == 1
        assert summary["orders"]["filled"] == 1
        assert summary["orders"]["rejected"] == 1
        assert summary["orders"]["canceled"] == 1
    
    def test_latency_by_endpoint(self):
        """Test latency tracking by endpoint."""
        metrics = AdapterMetrics("test")
        
        metrics.record_request("/v1/order", 100, True)
        metrics.record_request("/v1/order", 200, True)
        metrics.record_request("/v1/balance", 50, True)
        
        latency = metrics.get_latency_by_endpoint()
        
        assert "/v1/order" in latency
        assert latency["/v1/order"]["count"] == 2
        assert latency["/v1/order"]["avg_ms"] == 150.0
    
    def test_recent_requests(self):
        """Test recent requests tracking."""
        metrics = AdapterMetrics("test")
        
        for i in range(5):
            metrics.record_request(f"/endpoint{i}", 100, True)
        
        recent = metrics.get_recent_requests(limit=3)
        
        assert len(recent) == 3
    
    def test_reset_metrics(self):
        """Test resetting metrics."""
        metrics = AdapterMetrics("test")
        
        metrics.record_request("/v1/order", 100, True)
        metrics.reset()
        
        summary = metrics.get_summary()
        
        assert summary["requests"]["total"] == 0


class TestMetricsAggregator:
    """Tests for MetricsAggregator."""
    
    def test_register_adapter(self):
        """Test registering adapter metrics."""
        aggregator = get_global_aggregator()
        metrics = AdapterMetrics("test_exchange")
        
        aggregator.register("test_exchange", metrics)
        
        summaries = aggregator.get_all_summaries()
        assert "test_exchange" in summaries
        
        aggregator.unregister("test_exchange")


# ============================================================
# LOGGING TESTS
# ============================================================

class TestCredentialMasking:
    """Tests for credential masking."""
    
    def test_mask_value(self):
        """Test masking sensitive value."""
        api_key = "abc123def456ghi789"
        masked = mask_value(api_key, show_chars=4)
        
        assert masked == "abc1...***"
        assert "def456" not in masked
    
    def test_mask_short_value(self):
        """Test masking short value."""
        short = "abc"
        masked = mask_value(short, show_chars=4)
        
        assert masked == "***"
    
    def test_mask_headers(self):
        """Test masking sensitive headers."""
        headers = {
            "Content-Type": "application/json",
            "X-MBX-APIKEY": "secret_api_key_12345",
            "Authorization": "Bearer token123",
        }
        
        masked = mask_headers(headers)
        
        assert masked["Content-Type"] == "application/json"
        assert "secret_api_key" not in masked["X-MBX-APIKEY"]
        assert "token123" not in masked["Authorization"]
    
    def test_mask_params(self):
        """Test masking sensitive parameters."""
        params = {
            "symbol": "BTCUSDT",
            "signature": "hmac_signature_abc123def456",
            "apiKey": "my_secret_key_xyz",
            "quantity": "1.5",
        }
        
        masked = mask_params(params)
        
        assert masked["symbol"] == "BTCUSDT"
        assert masked["quantity"] == "1.5"
        assert "hmac_signature" not in str(masked["signature"])
        assert "my_secret_key" not in str(masked["apiKey"])


class TestAdapterLogger:
    """Tests for AdapterLogger."""
    
    def test_log_request(self):
        """Test logging request."""
        logger = AdapterLogger("test")
        
        request_id = logger.log_request(
            operation="submit_order",
            method="POST",
            endpoint="/v1/order",
            headers={"X-API-KEY": "secret123"},
            params={"symbol": "BTCUSDT"},
        )
        
        assert request_id is not None
        assert "test-" in request_id
    
    def test_log_order(self):
        """Test logging order."""
        logger = AdapterLogger("test")
        
        # Should not raise
        logger.log_order(
            operation="submit",
            client_order_id="test123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="1.0",
            price="50000",
        )


class TestAuditLog:
    """Tests for AuditLog."""
    
    def test_record_entry(self):
        """Test recording audit entry."""
        audit = get_audit_log()
        audit.clear()
        
        audit.record(
            exchange_id="binance",
            operation="submit_order",
            request={"symbol": "BTCUSDT"},
            response={"orderId": "123"},
            latency_ms=150.0,
            success=True,
        )
        
        entries = audit.get_entries()
        
        assert len(entries) == 1
        assert entries[0]["exchange_id"] == "binance"
    
    def test_filter_entries(self):
        """Test filtering audit entries."""
        audit = get_audit_log()
        audit.clear()
        
        audit.record("binance", "submit", {}, {}, 100, True)
        audit.record("okx", "submit", {}, {}, 100, True)
        audit.record("binance", "cancel", {}, {}, 100, True)
        
        binance_entries = audit.get_entries(exchange_id="binance")
        submit_entries = audit.get_entries(operation="submit")
        
        assert len(binance_entries) == 2
        assert len(submit_entries) == 2


# ============================================================
# MOCK ADAPTER TESTS
# ============================================================

class TestMockAdapter:
    """Tests for MockExchangeAdapter."""
    
    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        """Test connection lifecycle."""
        adapter = MockExchangeAdapter()
        
        assert not adapter.is_connected
        
        await adapter.connect()
        assert adapter.is_connected
        
        await adapter.disconnect()
        assert not adapter.is_connected
    
    @pytest.mark.asyncio
    async def test_submit_order(self):
        """Test order submission."""
        adapter = MockExchangeAdapter()
        await adapter.connect()
        
        request = SubmitOrderRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("0.1"),
        )
        
        response = await adapter.submit_order(request)
        
        assert response.success
        assert response.exchange_order_id is not None
        
        await adapter.disconnect()
    
    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test balance query."""
        adapter = MockExchangeAdapter()
        await adapter.connect()
        
        balance = await adapter.get_balance("USDT")
        
        assert balance.asset == "USDT"
        assert balance.total > 0
        
        await adapter.disconnect()
    
    @pytest.mark.asyncio
    async def test_get_current_price(self):
        """Test price query."""
        adapter = MockExchangeAdapter()
        await adapter.connect()
        
        price = await adapter.get_current_price("BTCUSDT")
        
        assert price > 0
        
        await adapter.disconnect()


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
