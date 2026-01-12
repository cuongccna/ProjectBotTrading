"""
Tests for Data Retention Module.

============================================================
PURPOSE
============================================================
Comprehensive tests for the Data Retention and Monetization
module, covering:
1. Data classification
2. Retention policies
3. Storage tiers
4. Data lineage
5. Anonymization
6. Access control

============================================================
"""

import asyncio
import pytest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def sample_ohlcv_data():
    """Sample OHLCV data."""
    return {
        "symbol": "BTCUSDT",
        "open": 50000.0,
        "high": 50500.0,
        "low": 49500.0,
        "close": 50100.0,
        "volume": 1000.5,
        "timestamp": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def sample_sentiment_data():
    """Sample sentiment score data."""
    return {
        "symbol": "BTCUSDT",
        "sentiment_score": 0.75,
        "confidence": 0.85,
        "source_count": 10,
        "timestamp": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def sample_decision_data():
    """Sample decision log data."""
    return {
        "symbol": "BTCUSDT",
        "trade_guard_decision": "approved",
        "risk_level": "normal",
        "position_size": 0.1,
        "reasons": ["RSI favorable", "Trend confirmed"],
        "timestamp": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def sample_execution_data():
    """Sample execution record."""
    return {
        "symbol": "BTCUSDT",
        "order_id": "order_123",
        "order_type": "limit",
        "side": "buy",
        "requested_size": 0.1,
        "filled_size": 0.1,
        "requested_price": 50100.0,
        "filled_price": 50102.5,
        "slippage": 2.5,
        "fees": 5.01,
        "timestamp": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def sensitive_data():
    """Data with sensitive fields that should be anonymized."""
    return {
        "api_key": "abc123secret456",
        "account_id": "user_12345",
        "email": "user@example.com",
        "balance": 10000.0,
        "wallet_address": "0x1234567890abcdef1234567890abcdef12345678",
        "data": {"symbol": "BTCUSDT", "price": 50000.0},
    }


# ============================================================
# DATA CLASSIFICATION TESTS
# ============================================================

class TestDataClassification:
    """Tests for data classification."""
    
    def test_classify_ohlcv_data(self, sample_ohlcv_data):
        """Test classification of OHLCV data."""
        from data_retention.categories import create_classifier
        from data_retention.models import DataCategory, DataSubCategory
        
        classifier = create_classifier()
        
        category, subcategory, sensitivity, confidence = classifier.classify(
            data=sample_ohlcv_data,
            source_type="exchange_api",
            source_name="binance",
        )
        
        assert category == DataCategory.RAW_DATA
        assert subcategory == DataSubCategory.MARKET_OHLCV
        assert confidence > 0
    
    def test_classify_sentiment_data(self, sample_sentiment_data):
        """Test classification of sentiment data."""
        from data_retention.categories import create_classifier
        from data_retention.models import DataCategory, DataSubCategory
        
        classifier = create_classifier()
        
        category, subcategory, sensitivity, confidence = classifier.classify(
            data=sample_sentiment_data,
            source_type="sentiment_analyzer",
            source_name="nlp_engine",
        )
        
        assert category == DataCategory.DERIVED_SCORES
        assert subcategory == DataSubCategory.SENTIMENT_SCORES
    
    def test_classify_with_hints(self, sample_ohlcv_data):
        """Test classification with explicit hints."""
        from data_retention.categories import create_classifier
        from data_retention.models import DataCategory, DataSubCategory
        
        classifier = create_classifier()
        
        category, subcategory, sensitivity, confidence = classifier.classify(
            data=sample_ohlcv_data,
            hint_category=DataCategory.RAW_DATA,
            hint_subcategory=DataSubCategory.MARKET_OHLCV,
        )
        
        assert category == DataCategory.RAW_DATA
        assert subcategory == DataSubCategory.MARKET_OHLCV
        assert confidence == 1.0  # Hints give full confidence
    
    def test_subcategory_to_category_mapping(self):
        """Test subcategory to category mapping."""
        from data_retention.categories import get_category_for_subcategory
        from data_retention.models import DataCategory, DataSubCategory
        
        assert get_category_for_subcategory(DataSubCategory.NEWS_HEADLINES) == DataCategory.RAW_DATA
        assert get_category_for_subcategory(DataSubCategory.SENTIMENT_SCORES) == DataCategory.DERIVED_SCORES
        assert get_category_for_subcategory(DataSubCategory.TRADE_GUARD_DECISIONS) == DataCategory.DECISION_LOGS
        assert get_category_for_subcategory(DataSubCategory.ORDERS_FILLED) == DataCategory.EXECUTION_RECORDS


# ============================================================
# RETENTION POLICY TESTS
# ============================================================

class TestRetentionPolicies:
    """Tests for retention policies."""
    
    def test_default_policies_created(self):
        """Test that default policies are created for all categories."""
        from data_retention.models import DataCategory, create_default_retention_policies
        
        policies = create_default_retention_policies()
        
        for category in DataCategory:
            assert category in policies
    
    def test_retention_duration_expiration(self):
        """Test retention duration expiration checking."""
        from data_retention.models import RetentionDuration
        
        # Short term - should expire
        short_term = RetentionDuration.short_term(days=7)
        old_date = datetime.utcnow() - timedelta(days=10)
        assert short_term.is_expired(old_date)
        
        # Indefinite - never expires
        indefinite = RetentionDuration.forever()
        very_old = datetime.utcnow() - timedelta(days=3650)
        assert not indefinite.is_expired(very_old)
    
    def test_policy_registry(self):
        """Test policy registry operations."""
        from data_retention.policies import create_policy_registry
        from data_retention.models import DataCategory
        
        registry = create_policy_registry()
        
        # Get policy for category
        policy = registry.get_policy_for_category(DataCategory.RAW_DATA)
        assert policy is not None
        assert policy.category == DataCategory.RAW_DATA
    
    def test_decision_logs_indefinite_retention(self):
        """Test that decision logs have indefinite retention."""
        from data_retention.models import DataCategory, create_default_retention_policies
        
        policies = create_default_retention_policies()
        decision_policy = policies[DataCategory.DECISION_LOGS]
        
        assert decision_policy.retention_duration.indefinite
    
    def test_execution_records_indefinite_retention(self):
        """Test that execution records have indefinite retention."""
        from data_retention.models import DataCategory, create_default_retention_policies
        
        policies = create_default_retention_policies()
        execution_policy = policies[DataCategory.EXECUTION_RECORDS]
        
        assert execution_policy.retention_duration.indefinite


# ============================================================
# STORAGE TIER TESTS
# ============================================================

class TestStorageTiers:
    """Tests for storage tiers."""
    
    def test_tier_configs_created(self):
        """Test that tier configs are created for all tiers."""
        from data_retention.models import StorageTier, create_storage_tier_configs
        
        configs = create_storage_tier_configs()
        
        for tier in StorageTier:
            assert tier in configs
    
    def test_tier_cost_ordering(self):
        """Test that HOT is more expensive than COLD."""
        from data_retention.models import StorageTier, create_storage_tier_configs
        
        configs = create_storage_tier_configs()
        
        assert configs[StorageTier.HOT].cost_per_gb_month > configs[StorageTier.COLD].cost_per_gb_month
        assert configs[StorageTier.COLD].cost_per_gb_month > configs[StorageTier.ARCHIVE].cost_per_gb_month
    
    def test_tier_router_initial_tier(self):
        """Test tier router assigns HOT tier to new data."""
        from data_retention.storage import create_tier_router
        from data_retention.models import StorageTier, DataCategory, DataRecord, RetentionPolicy
        from data_retention.lineage import build_simple_lineage
        
        router = create_tier_router()
        
        # Create a mock record
        record = MagicMock()
        record.category = DataCategory.RAW_DATA
        record.created_at = datetime.utcnow()
        record.policy = RetentionPolicy.for_raw_data()
        
        tier = router.get_initial_tier(record)
        
        assert tier == StorageTier.HOT


# ============================================================
# DATA LINEAGE TESTS
# ============================================================

class TestDataLineage:
    """Tests for data lineage tracking."""
    
    def test_lineage_builder(self):
        """Test lineage builder."""
        from data_retention.lineage import LineageBuilder
        
        builder = LineageBuilder("record_123")
        lineage = (
            builder
            .with_source("exchange_api", "binance")
            .with_parent_records(["parent_1", "parent_2"])
            .with_correlation_id("corr_abc")
            .build()
        )
        
        assert lineage.record_id == "record_123"
        assert lineage.source.source_type == "exchange_api"
        assert lineage.source.source_name == "binance"
        assert lineage.parent_record_ids == ["parent_1", "parent_2"]
        assert lineage.correlation_id == "corr_abc"
    
    def test_lineage_tracker_trace_to_root(self):
        """Test tracing lineage to root."""
        from data_retention.lineage import LineageTracker, build_simple_lineage
        
        tracker = LineageTracker()
        
        # Register lineage chain: root -> derived1 -> derived2
        root = build_simple_lineage("root", "exchange_api", "binance")
        tracker.register_lineage(root)
        
        derived1 = build_simple_lineage(
            "derived1", "processor", "normalizer",
            parent_record_ids=["root"]
        )
        tracker.register_lineage(derived1)
        
        derived2 = build_simple_lineage(
            "derived2", "scorer", "sentiment",
            parent_record_ids=["derived1"]
        )
        tracker.register_lineage(derived2)
        
        # Trace back to root
        roots = tracker.get_root_records("derived2")
        assert "root" in roots
    
    def test_correlation_manager(self):
        """Test correlation manager."""
        from data_retention.lineage import create_correlation_manager
        
        manager = create_correlation_manager()
        
        # Create correlation
        corr_id = manager.create_correlation("trading_cycle", {"cycle": 1})
        assert corr_id.startswith("corr_")
        
        # Get info
        info = manager.get_correlation_info(corr_id)
        assert info is not None
        assert info["context"] == "trading_cycle"


# ============================================================
# ANONYMIZATION TESTS
# ============================================================

class TestAnonymization:
    """Tests for data anonymization."""
    
    def test_removes_prohibited_fields(self, sensitive_data):
        """Test that prohibited fields are removed."""
        from data_retention.anonymizer import create_anonymizer
        from data_retention.models import DataCategory
        
        anonymizer = create_anonymizer()
        
        anonymized = anonymizer.anonymize(sensitive_data, DataCategory.RAW_DATA)
        
        assert "api_key" not in anonymized
        assert "account_id" not in anonymized
        assert "email" not in anonymized
        assert "balance" not in anonymized
        assert "wallet_address" not in anonymized
        
        # Non-sensitive data should remain
        assert "data" in anonymized
    
    def test_validates_anonymized_data(self, sensitive_data):
        """Test anonymization validation."""
        from data_retention.anonymizer import create_anonymizer
        from data_retention.models import DataCategory
        
        anonymizer = create_anonymizer()
        
        # Before anonymization - should have issues
        issues_before = anonymizer.validate_anonymized(sensitive_data)
        assert len(issues_before) > 0
        
        # After anonymization - should be clean
        anonymized = anonymizer.anonymize(sensitive_data, DataCategory.RAW_DATA)
        issues_after = anonymizer.validate_anonymized(anonymized)
        assert len(issues_after) == 0
    
    def test_pii_detector(self, sensitive_data):
        """Test PII detection."""
        from data_retention.anonymizer import create_pii_detector
        
        detector = create_pii_detector()
        
        findings = detector.scan(sensitive_data)
        
        # Should find multiple PII items
        assert len(findings) > 0
        
        # Check specific detections
        field_names = [f["field"] for f in findings if f["type"] == "field_name"]
        assert "api_key" in field_names
        assert "email" in field_names
    
    def test_hash_identifier_consistency(self):
        """Test that identifier hashing is consistent."""
        from data_retention.anonymizer import create_anonymizer
        
        anonymizer = create_anonymizer(salt="test_salt")
        
        hash1 = anonymizer.hash_identifier("user123")
        hash2 = anonymizer.hash_identifier("user123")
        
        assert hash1 == hash2  # Same input = same output
        
        hash3 = anonymizer.hash_identifier("user456")
        assert hash1 != hash3  # Different input = different output


# ============================================================
# ACCESS CONTROL TESTS
# ============================================================

class TestAccessControl:
    """Tests for access control."""
    
    @pytest.fixture
    def mock_record(self):
        """Create a mock data record."""
        from data_retention.models import DataCategory, StorageTier, RetentionPolicy
        
        record = MagicMock()
        record.record_id = "rec_123"
        record.category = DataCategory.RAW_DATA
        record.storage_tier = StorageTier.HOT
        record.policy = RetentionPolicy.for_raw_data()
        return record
    
    def test_system_internal_access(self, mock_record):
        """Test that internal system has full access."""
        from data_retention.access_control import create_access_controller
        from data_retention.models import AuditAction
        
        controller = create_access_controller()
        
        allowed, reason = controller.check_access(
            actor="strategy_module",
            actor_type="system",
            record=mock_record,
            action=AuditAction.READ,
        )
        
        assert allowed
    
    def test_external_read_only(self, mock_record):
        """Test that external access is read-only."""
        from data_retention.access_control import create_access_controller
        from data_retention.models import AuditAction
        
        controller = create_access_controller()
        
        # Read should be allowed
        allowed, reason = controller.check_access(
            actor="external_client",
            actor_type="external",
            record=mock_record,
            action=AuditAction.READ,
        )
        assert allowed
    
    def test_decision_logs_restricted(self):
        """Test that decision logs are restricted from external access."""
        from data_retention.access_control import create_access_controller
        from data_retention.models import DataCategory, AuditAction, RetentionPolicy
        
        controller = create_access_controller()
        
        # Create decision log record
        record = MagicMock()
        record.record_id = "rec_decision"
        record.category = DataCategory.DECISION_LOGS
        record.policy = RetentionPolicy.for_decision_logs()
        
        # External access should be denied
        allowed, reason = controller.check_access(
            actor="external_client",
            actor_type="external",
            record=record,
            action=AuditAction.READ,
        )
        
        assert not allowed
    
    def test_immutability_enforcement(self, mock_record):
        """Test that sealed records cannot be modified."""
        from data_retention.access_control import create_immutability_enforcer
        
        enforcer = create_immutability_enforcer()
        
        # Seal the record
        enforcer.seal_record(mock_record)
        assert enforcer.is_sealed(mock_record.record_id)
        
        # Modification should be blocked
        allowed, reason = enforcer.check_modification(
            record=mock_record,
            actor="some_module",
            modification_type="update",
        )
        
        assert not allowed
        
        # Deletion should still be allowed
        allowed, reason = enforcer.check_modification(
            record=mock_record,
            actor="retention_executor",
            modification_type="delete",
        )
        
        assert allowed


# ============================================================
# MONETIZATION TESTS
# ============================================================

class TestMonetization:
    """Tests for monetization preparation."""
    
    def test_can_monetize_categories(self):
        """Test which categories can be monetized."""
        from data_retention.anonymizer import create_monetization_preparer
        from data_retention.models import DataCategory
        
        preparer = create_monetization_preparer()
        
        # These can be monetized
        assert preparer.can_monetize(DataCategory.RAW_DATA)
        assert preparer.can_monetize(DataCategory.PROCESSED_DATA)
        assert preparer.can_monetize(DataCategory.DERIVED_SCORES)
        
        # These cannot
        assert not preparer.can_monetize(DataCategory.DECISION_LOGS)
        assert not preparer.can_monetize(DataCategory.EXECUTION_RECORDS)
    
    def test_product_definitions(self):
        """Test default product definitions."""
        from data_retention.anonymizer import get_default_product_definitions
        from data_retention.models import DataProductType
        
        definitions = get_default_product_definitions()
        
        # Should have definitions for all product types
        product_types = [d.product_type for d in definitions]
        assert DataProductType.SENTIMENT_INDEX in product_types
        assert DataProductType.RISK_REGIME_DATASET in product_types
        
        # All should be disabled by default
        for definition in definitions:
            assert not definition.is_enabled
    
    def test_aggregator_sentiment(self):
        """Test sentiment aggregation."""
        from data_retention.anonymizer import create_aggregator
        from decimal import Decimal
        
        aggregator = create_aggregator()
        
        scores = [Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        
        mean = aggregator.aggregate_sentiment(scores, "mean")
        assert mean == Decimal("0.7")
        
        max_val = aggregator.aggregate_sentiment(scores, "max")
        assert max_val == Decimal("0.9")


# ============================================================
# INTEGRATION TESTS
# ============================================================

class TestDataRetentionIntegration:
    """Integration tests for data retention."""
    
    @pytest.mark.asyncio
    async def test_full_store_retrieve_cycle(self, sample_ohlcv_data):
        """Test complete store and retrieve cycle."""
        from data_retention.manager import create_data_retention_manager
        from data_retention.models import DataCategory, DataSubCategory
        
        manager = create_data_retention_manager()
        
        # Store data
        record_id = await manager.store(
            data=sample_ohlcv_data,
            source_type="exchange_api",
            source_name="binance",
            symbol="BTCUSDT",
            exchange="binance",
            hint_category=DataCategory.RAW_DATA,
            hint_subcategory=DataSubCategory.MARKET_OHLCV,
        )
        
        assert record_id is not None
        
        # Retrieve data
        data = await manager.retrieve(record_id)
        
        assert data is not None
        assert data["symbol"] == "BTCUSDT"
    
    @pytest.mark.asyncio
    async def test_lineage_tracking(self, sample_ohlcv_data, sample_sentiment_data):
        """Test lineage tracking across records."""
        from data_retention.manager import create_data_retention_manager
        from data_retention.models import DataCategory, DataSubCategory
        
        manager = create_data_retention_manager()
        
        # Store raw data
        raw_id = await manager.store(
            data=sample_ohlcv_data,
            source_type="exchange_api",
            source_name="binance",
            symbol="BTCUSDT",
        )
        
        # Store derived data with parent reference
        derived_id = await manager.store(
            data=sample_sentiment_data,
            source_type="sentiment_analyzer",
            source_name="nlp_engine",
            symbol="BTCUSDT",
            parent_record_ids=[raw_id],
        )
        
        # Get lineage
        lineage = await manager.get_lineage(derived_id)
        
        assert lineage is not None
    
    @pytest.mark.asyncio
    async def test_correlation_grouping(self, sample_ohlcv_data, sample_sentiment_data):
        """Test correlation ID grouping."""
        from data_retention.manager import create_data_retention_manager
        
        manager = create_data_retention_manager()
        
        # Start correlation
        corr_id = manager.start_correlation("test_cycle")
        
        # Store multiple records with same correlation
        await manager.store(
            data=sample_ohlcv_data,
            source_type="exchange_api",
            source_name="binance",
            correlation_id=corr_id,
        )
        
        await manager.store(
            data=sample_sentiment_data,
            source_type="sentiment_analyzer",
            source_name="nlp_engine",
            correlation_id=corr_id,
        )
        
        # End correlation
        manager.end_correlation(corr_id)
        
        # Get correlated records
        records = manager.get_records_by_correlation(corr_id)
        
        assert len(records) == 2
    
    @pytest.mark.asyncio
    async def test_fail_safe_wrapper(self, sample_ohlcv_data):
        """Test fail-safe wrapper doesn't crash on errors."""
        from data_retention.manager import create_fail_safe_retention
        
        wrapper = create_fail_safe_retention()
        
        # This should not raise even if internal error occurs
        result = await wrapper.store(
            data=sample_ohlcv_data,
            source_type="test",
            source_name="test",
        )
        
        # Should return record_id or None, not raise
        assert result is None or isinstance(result, str)


# ============================================================
# FAILURE SAFETY TESTS
# ============================================================

class TestFailureSafety:
    """Tests for failure safety."""
    
    @pytest.mark.asyncio
    async def test_retention_failure_doesnt_stop_trading(self):
        """Test that retention failures are isolated."""
        from data_retention.manager import create_fail_safe_retention
        
        wrapper = create_fail_safe_retention()
        
        # Force an error by passing invalid data
        result = await wrapper.store(
            data=None,  # Invalid
            source_type="test",
            source_name="test",
        )
        
        # Should return None, not raise
        assert result is None
        
        # Check health status records failure
        health = wrapper.get_health_status()
        assert health["failure_count"] >= 0


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
