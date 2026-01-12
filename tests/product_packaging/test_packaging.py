"""
Tests for Product Data Packaging Layer.

============================================================
PURPOSE
============================================================
Comprehensive tests for the Product Data Packaging layer:
1. Schema validation
2. Data extraction
3. Transformations
4. Safety checks
5. Formatting
6. Access control
7. Pipeline integration

============================================================
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def sample_sentiment_records():
    """Sample sentiment data records."""
    base_time = datetime(2025, 1, 10, 12, 0, 0)
    return [
        {
            "symbol": "BTC",
            "sentiment_score": 0.75,
            "sentiment_confidence": 0.85,
            "source_count": 15,
            "timestamp": base_time - timedelta(hours=i),
        }
        for i in range(10)
    ]


@pytest.fixture
def sample_flow_records():
    """Sample flow pressure data records."""
    base_time = datetime(2025, 1, 10, 12, 0, 0)
    return [
        {
            "symbol": "BTC",
            "net_flow_pressure": 0.25,
            "inflow_intensity": 0.6,
            "outflow_intensity": 0.35,
            "exchange_count": 5,
            "timestamp": base_time - timedelta(hours=i),
        }
        for i in range(10)
    ]


@pytest.fixture
def actionable_data():
    """Data containing actionable signals (should fail safety check)."""
    return {
        "symbol": "BTC",
        "buy_signal": True,
        "sell_target": 55000.0,
        "stop_loss": 45000.0,
        "recommendation": "buy now",
    }


@pytest.fixture
def safe_data():
    """Safe, non-actionable data."""
    return {
        "symbol": "BTC",
        "sentiment_score": 0.65,
        "sentiment_confidence": 0.80,
        "source_count": 12,
    }


# ============================================================
# SCHEMA TESTS
# ============================================================

class TestSchemas:
    """Tests for product schemas."""
    
    def test_schema_registry_creation(self):
        """Test schema registry is created with all products."""
        from product_packaging.schemas import create_schema_registry
        from product_packaging.models import ProductType
        
        registry = create_schema_registry()
        
        for product_type in ProductType:
            schema = registry.get_schema(product_type)
            assert schema is not None
            assert schema.product_type == product_type
    
    def test_sentiment_schema_fields(self):
        """Test sentiment schema has required fields."""
        from product_packaging.schemas import create_sentiment_index_schema
        
        schema = create_sentiment_index_schema()
        
        field_names = [f.name for f in schema.fields]
        
        assert "timestamp_bucket" in field_names
        assert "symbol" in field_names
        assert "sentiment_score" in field_names
        assert "sentiment_confidence" in field_names
        assert "source_count" in field_names
    
    def test_schema_json_export(self):
        """Test schema can be exported to JSON schema format."""
        from product_packaging.schemas import create_sentiment_index_schema
        
        schema = create_sentiment_index_schema()
        json_schema = schema.to_json_schema()
        
        assert "$schema" in json_schema
        assert "properties" in json_schema
        assert "sentiment_score" in json_schema["properties"]
    
    def test_schema_versioning(self):
        """Test schema versioning works correctly."""
        from product_packaging.models import SchemaVersion
        
        v1 = SchemaVersion(major=1, minor=0, patch=0)
        v2 = SchemaVersion(major=1, minor=1, patch=0)
        v3 = SchemaVersion(major=2, minor=0, patch=0)
        
        # Same major = compatible
        assert v1.is_compatible_with(v2)
        
        # Different major = incompatible
        assert not v1.is_compatible_with(v3)
        
        # Version comparison
        assert v2.is_newer_than(v1)
        assert v3.is_newer_than(v2)
    
    def test_all_product_definitions(self):
        """Test all product definitions are valid."""
        from product_packaging.schemas import get_all_product_definitions
        
        definitions = get_all_product_definitions()
        
        assert len(definitions) == 5
        
        for definition in definitions:
            assert definition.product_id is not None
            assert definition.schema is not None
            assert len(definition.allowed_sources) > 0


# ============================================================
# EXTRACTOR TESTS
# ============================================================

class TestExtractors:
    """Tests for data extractors."""
    
    def test_data_source_validation(self):
        """Test data source validation blocks prohibited sources."""
        from product_packaging.extractors import DataSourceValidator
        
        # Allowed sources
        assert DataSourceValidator.validate_source("raw_data")
        assert DataSourceValidator.validate_source("derived_scores")
        
        # Prohibited sources
        assert not DataSourceValidator.validate_source("execution_logic")
        assert not DataSourceValidator.validate_source("strategy_logic")
        assert not DataSourceValidator.validate_source("api_key")
        assert not DataSourceValidator.validate_source("account_balance")
    
    def test_extractor_factory(self):
        """Test extractor factory creates correct extractors."""
        from product_packaging.extractors import ExtractorFactory
        from product_packaging.models import ProductType
        
        sentiment_extractor = ExtractorFactory.create(ProductType.SENTIMENT_INDEX)
        assert sentiment_extractor.product_type == ProductType.SENTIMENT_INDEX
        
        flow_extractor = ExtractorFactory.create(ProductType.FLOW_PRESSURE)
        assert flow_extractor.product_type == ProductType.FLOW_PRESSURE
    
    def test_extractor_allowed_sources(self):
        """Test extractors only access allowed sources."""
        from product_packaging.extractors import ExtractorFactory
        from product_packaging.models import ProductType, AllowedDataSource
        
        sentiment_extractor = ExtractorFactory.create(ProductType.SENTIMENT_INDEX)
        
        # Should allow derived scores
        assert AllowedDataSource.DERIVED_SCORES in sentiment_extractor.allowed_sources
        
        # Validate access works
        assert sentiment_extractor.validate_access(AllowedDataSource.DERIVED_SCORES)


# ============================================================
# TRANSFORMER TESTS
# ============================================================

class TestTransformers:
    """Tests for data transformers."""
    
    def test_time_delay_filter(self):
        """Test time delay filtering works."""
        from product_packaging.transformers import TimeDelayTransformer
        from product_packaging.models import DelayConfig
        from product_packaging.extractors import ExtractedRecord
        from product_packaging.models import AllowedDataSource
        
        # 15 minute delay
        config = DelayConfig(min_delay_seconds=900, max_delay_seconds=900)
        transformer = TimeDelayTransformer(config)
        
        now = datetime.utcnow()
        
        # Create records: some within delay, some outside
        records = [
            ExtractedRecord(
                record_id="old",
                source=AllowedDataSource.DERIVED_SCORES,
                timestamp=now - timedelta(hours=1),
                data={"value": 1},
            ),
            ExtractedRecord(
                record_id="new",
                source=AllowedDataSource.DERIVED_SCORES,
                timestamp=now - timedelta(minutes=5),  # Too new
                data={"value": 2},
            ),
        ]
        
        filtered = transformer.filter_by_delay(records, now)
        
        # Only old record should remain
        assert len(filtered) == 1
        assert filtered[0].record_id == "old"
    
    def test_aggregation_mean(self):
        """Test mean aggregation."""
        from product_packaging.transformers import AggregationTransformer
        from product_packaging.models import AggregationConfig, TimeBucket
        
        config = AggregationConfig(
            method="mean",
            time_bucket=TimeBucket.HOUR_1,
            min_samples=2,
        )
        transformer = AggregationTransformer(config)
        
        values = [10.0, 20.0, 30.0]
        result = transformer.aggregate_values(values)
        
        assert result == 20.0
    
    def test_aggregation_minimum_samples(self):
        """Test aggregation respects minimum samples."""
        from product_packaging.transformers import AggregationTransformer
        from product_packaging.models import AggregationConfig, TimeBucket
        
        config = AggregationConfig(
            method="mean",
            time_bucket=TimeBucket.HOUR_1,
            min_samples=5,  # Require 5 samples
        )
        transformer = AggregationTransformer(config)
        
        # Only 3 samples - should return None
        values = [10.0, 20.0, 30.0]
        result = transformer.aggregate_values(values)
        
        assert result is None
    
    def test_normalization_min_max(self):
        """Test min-max normalization."""
        from product_packaging.transformers import NormalizationTransformer
        from product_packaging.models import NormalizationConfig
        
        config = NormalizationConfig(
            method="min_max",
            min_value=0.0,
            max_value=1.0,
        )
        transformer = NormalizationTransformer(config)
        
        values = [0.0, 50.0, 100.0]
        normalized = transformer.normalize_series(values)
        
        assert normalized[0] == 0.0
        assert normalized[1] == 0.5
        assert normalized[2] == 1.0


# ============================================================
# SAFETY TESTS
# ============================================================

class TestSafety:
    """Tests for safety checks."""
    
    def test_non_actionable_validation_blocks_signals(self, actionable_data):
        """Test non-actionable validator blocks trading signals."""
        from product_packaging.safety import NonActionableValidator
        
        validator = NonActionableValidator()
        result = validator.validate(actionable_data)
        
        assert not result.is_valid
        assert len(result.violations) > 0
        assert len(result.signal_types_found) > 0
    
    def test_non_actionable_validation_allows_safe_data(self, safe_data):
        """Test non-actionable validator allows safe data."""
        from product_packaging.safety import NonActionableValidator
        
        validator = NonActionableValidator()
        result = validator.validate(safe_data)
        
        assert result.is_valid
        assert len(result.violations) == 0
    
    def test_anonymizer_removes_prohibited_fields(self):
        """Test anonymizer removes prohibited fields."""
        from product_packaging.safety import DataAnonymizer
        
        data = {
            "symbol": "BTC",
            "sentiment_score": 0.75,
            "api_key": "secret123",
            "wallet_address": "0x123...",
            "user_id": "user_456",
        }
        
        anonymizer = DataAnonymizer()
        result = anonymizer.anonymize(data)
        
        # Prohibited fields removed
        assert "api_key" not in result
        assert "wallet_address" not in result
        assert "user_id" not in result
        
        # Safe fields remain
        assert "symbol" in result
        assert "sentiment_score" in result
    
    def test_safety_checker_full_validation(self, safe_data):
        """Test safety checker performs complete validation."""
        from product_packaging.safety import SafetyChecker
        from product_packaging.transformers import TransformedRecord
        from product_packaging.models import ProductType, TimeBucket
        
        checker = SafetyChecker()
        
        records = [
            TransformedRecord(
                record_id="rec_1",
                product_type=ProductType.SENTIMENT_INDEX,
                timestamp_bucket=datetime.utcnow(),
                time_bucket_size=TimeBucket.HOUR_1,
                data=safe_data,
                record_count=5,
            ),
        ]
        
        sanitized, result = checker.check_and_sanitize(records)
        
        assert result.is_safe or len(result.issues) == 0
        assert result.anonymization_applied
        assert result.precision_obscured
    
    def test_reverse_engineering_prevention(self):
        """Test reverse engineering prevention obscures precision."""
        from product_packaging.safety import ReverseEngineeringPrevention
        
        prevention = ReverseEngineeringPrevention()
        
        data = {
            "sentiment_score": 0.12345678,
            "risk_score": 0.87654321,
            "latency_ms": 123.456,
        }
        
        obscured = prevention.obscure_precision(data)
        
        # Scores should be rounded to 2 decimal places
        assert obscured["sentiment_score"] == 0.12
        assert obscured["risk_score"] == 0.88


# ============================================================
# FORMATTER TESTS
# ============================================================

class TestFormatters:
    """Tests for output formatters."""
    
    def test_json_formatter(self):
        """Test JSON formatter output."""
        from product_packaging.formatters import JsonFormatter
        from product_packaging.transformers import TransformedRecord
        from product_packaging.models import (
            ProductType, TimeBucket, OutputFormat, ExportMetadata
        )
        
        formatter = JsonFormatter()
        
        records = [
            TransformedRecord(
                record_id="rec_1",
                product_type=ProductType.SENTIMENT_INDEX,
                timestamp_bucket=datetime(2025, 1, 10, 12, 0),
                time_bucket_size=TimeBucket.HOUR_1,
                data={"symbol": "BTC", "sentiment_score": 0.75},
            ),
        ]
        
        metadata = ExportMetadata(
            export_id="exp_1",
            product_id="sentiment_index_v1",
            product_type=ProductType.SENTIMENT_INDEX,
            schema_version="1.0.0",
            data_start_time=datetime(2025, 1, 10, 12, 0),
            data_end_time=datetime(2025, 1, 10, 12, 0),
            time_bucket=TimeBucket.HOUR_1,
            record_count=1,
            aggregation_method="mean",
            data_freshness_seconds=900,
            completeness_ratio=1.0,
            exported_at=datetime.utcnow(),
            format=OutputFormat.JSON,
            checksum="",
            schema_checksum="abc123",
            known_limitations=[],
            update_frequency="hourly",
        )
        
        output = formatter.format_records(records, metadata)
        
        assert output.format == OutputFormat.JSON
        assert output.content_type == "application/json"
        assert "sentiment_score" in output.content
        assert output.record_count == 1
    
    def test_csv_formatter(self):
        """Test CSV formatter output."""
        from product_packaging.formatters import CsvFormatter
        from product_packaging.transformers import TransformedRecord
        from product_packaging.models import (
            ProductType, TimeBucket, OutputFormat, ExportMetadata
        )
        
        formatter = CsvFormatter()
        
        records = [
            TransformedRecord(
                record_id="rec_1",
                product_type=ProductType.SENTIMENT_INDEX,
                timestamp_bucket=datetime(2025, 1, 10, 12, 0),
                time_bucket_size=TimeBucket.HOUR_1,
                data={"symbol": "BTC", "sentiment_score": 0.75},
            ),
        ]
        
        metadata = ExportMetadata(
            export_id="exp_1",
            product_id="sentiment_index_v1",
            product_type=ProductType.SENTIMENT_INDEX,
            schema_version="1.0.0",
            data_start_time=datetime(2025, 1, 10, 12, 0),
            data_end_time=datetime(2025, 1, 10, 12, 0),
            time_bucket=TimeBucket.HOUR_1,
            record_count=1,
            aggregation_method="mean",
            data_freshness_seconds=900,
            completeness_ratio=1.0,
            exported_at=datetime.utcnow(),
            format=OutputFormat.CSV,
            checksum="",
            schema_checksum="abc123",
            known_limitations=[],
            update_frequency="hourly",
        )
        
        output = formatter.format_records(records, metadata)
        
        assert output.format == OutputFormat.CSV
        assert output.content_type == "text/csv"
        assert "sentiment_score" in output.content


# ============================================================
# ACCESS CONTROL TESTS
# ============================================================

class TestAccessControl:
    """Tests for access control."""
    
    def test_rate_limiter(self):
        """Test rate limiter blocks excessive requests."""
        from product_packaging.access import RateLimiter
        from product_packaging.models import RateLimitConfig
        
        config = RateLimitConfig(
            requests_per_minute=3,
            requests_per_hour=100,
            requests_per_day=1000,
        )
        limiter = RateLimiter(config)
        
        client = "client_1"
        
        # First 3 should pass
        for _ in range(3):
            allowed, reason, _ = limiter.check_limit(client)
            assert allowed
            limiter.record_request(client)
        
        # 4th should be blocked
        allowed, reason, _ = limiter.check_limit(client)
        assert not allowed
    
    def test_read_only_enforcer(self):
        """Test read-only enforcer blocks write operations."""
        from product_packaging.access import ReadOnlyEnforcer
        
        # Allowed operations
        allowed, _ = ReadOnlyEnforcer.check_operation("export")
        assert allowed
        
        allowed, _ = ReadOnlyEnforcer.check_operation("query")
        assert allowed
        
        # Denied operations
        allowed, _ = ReadOnlyEnforcer.check_operation("write")
        assert not allowed
        
        allowed, _ = ReadOnlyEnforcer.check_operation("delete")
        assert not allowed
    
    def test_access_logger(self):
        """Test access logger records all requests."""
        from product_packaging.access import AccessLogger
        from product_packaging.models import ProductType
        
        logger = AccessLogger()
        
        # Log some requests
        logger.log_request(
            requester_id="client_1",
            product_id="sentiment_v1",
            product_type=ProductType.SENTIMENT_INDEX,
            action="export",
            success=True,
        )
        
        logger.log_request(
            requester_id="client_1",
            product_id="flow_v1",
            product_type=ProductType.FLOW_PRESSURE,
            action="export",
            success=False,
            error_message="Rate limit exceeded",
        )
        
        # Get logs
        logs = logger.get_logs(requester_id="client_1")
        assert len(logs) == 2
        
        # Get statistics
        stats = logger.get_statistics(requester_id="client_1")
        assert stats["total_requests"] == 2
        assert stats["successful_requests"] == 1
        assert stats["failed_requests"] == 1


# ============================================================
# PIPELINE TESTS
# ============================================================

class TestPipeline:
    """Tests for the packaging pipeline."""
    
    def test_pipeline_config(self):
        """Test pipeline configuration."""
        from product_packaging.pipeline import PipelineConfig
        
        config = PipelineConfig(
            max_records_per_request=5000,
            max_time_range_days=180,
        )
        
        assert config.max_records_per_request == 5000
        assert config.max_time_range_days == 180
    
    def test_pipeline_factory(self):
        """Test pipeline factory creates pipelines."""
        from product_packaging.pipeline import create_pipeline_factory
        from product_packaging.models import ProductType
        
        factory = create_pipeline_factory()
        
        pipeline = factory.get_pipeline(ProductType.SENTIMENT_INDEX)
        assert pipeline.product_type == ProductType.SENTIMENT_INDEX
    
    @pytest.mark.asyncio
    async def test_pipeline_validation(self):
        """Test pipeline validates requests."""
        from product_packaging.pipeline import create_pipeline
        from product_packaging.models import (
            ProductType, TimeBucket, OutputFormat, DeliveryMethod, ExportRequest
        )
        
        pipeline = create_pipeline(ProductType.SENTIMENT_INDEX)
        
        # Invalid request (start after end)
        request = ExportRequest(
            request_id="req_1",
            product_id="sentiment_v1",
            product_type=ProductType.SENTIMENT_INDEX,
            start_time=datetime(2025, 1, 10),
            end_time=datetime(2025, 1, 1),  # Before start
            time_bucket=TimeBucket.HOUR_1,
            format=OutputFormat.JSON,
            delivery_method=DeliveryMethod.FILE_DOWNLOAD,
        )
        
        result = await pipeline.execute(request)
        
        assert not result.success
        assert "before end time" in result.error_message.lower() or \
               "start time" in result.error_message.lower()


# ============================================================
# MANAGER TESTS
# ============================================================

class TestManager:
    """Tests for the packaging manager."""
    
    def test_product_catalog(self):
        """Test product catalog lists products."""
        from product_packaging.manager import ProductCatalog
        from product_packaging.models import ProductType
        
        catalog = ProductCatalog()
        
        products = catalog.list_products()
        assert len(products) == 5
        
        product_types = [p.product_type for p in products]
        assert ProductType.SENTIMENT_INDEX in product_types
        assert ProductType.FLOW_PRESSURE in product_types
    
    def test_fail_safe_wrapper(self):
        """Test fail-safe wrapper catches errors."""
        from product_packaging.manager import FailSafeWrapper
        import asyncio
        
        wrapper = FailSafeWrapper("test")
        
        def failing_function():
            raise ValueError("Test error")
        
        # Should not raise, should return default
        result = asyncio.get_event_loop().run_until_complete(
            wrapper.safe_execute(failing_function, default_result="default")
        )
        
        assert result == "default"
        
        health = wrapper.get_health()
        assert health.error_count == 1
    
    def test_manager_list_products(self):
        """Test manager lists products."""
        from product_packaging.manager import ProductPackagingManager
        
        manager = ProductPackagingManager()
        
        products = manager.list_products()
        assert len(products) == 5
    
    def test_manager_get_schema(self):
        """Test manager returns schema."""
        from product_packaging.manager import ProductPackagingManager
        from product_packaging.models import ProductType
        
        manager = ProductPackagingManager()
        
        schema = manager.get_schema(ProductType.SENTIMENT_INDEX)
        
        assert schema is not None
        assert "properties" in schema
    
    def test_manager_health(self):
        """Test manager reports health."""
        from product_packaging.manager import ProductPackagingManager
        from product_packaging.manager import HealthStatus
        
        manager = ProductPackagingManager()
        
        health = manager.get_health()
        
        assert health.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        assert health.total_requests == 0  # No requests yet


# ============================================================
# INTEGRATION TESTS
# ============================================================

class TestIntegration:
    """Integration tests for the complete pipeline."""
    
    @pytest.mark.asyncio
    async def test_full_export_flow(self):
        """Test complete export flow with mock data."""
        from product_packaging.manager import ProductPackagingManager
        from product_packaging.models import ProductType, TimeBucket, OutputFormat
        
        manager = ProductPackagingManager()
        
        # Export (will have empty data since no data store)
        response = await manager.export(
            client_id="test_client",
            product_type=ProductType.SENTIMENT_INDEX,
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 10),
            time_bucket=TimeBucket.HOUR_1,
            output_format=OutputFormat.JSON,
        )
        
        # Should complete (possibly with no data)
        assert response is not None
        assert response.request_id is not None
    
    @pytest.mark.asyncio
    async def test_fail_safe_manager(self):
        """Test fail-safe manager handles errors gracefully."""
        from product_packaging.manager import FailSafePackagingManager
        from product_packaging.models import ProductType, TimeBucket, OutputFormat
        
        manager = FailSafePackagingManager()
        
        # Even if internal error, should not raise
        response = await manager.export(
            client_id="test_client",
            product_type=ProductType.SENTIMENT_INDEX,
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 10),
            time_bucket=TimeBucket.HOUR_1,
            output_format=OutputFormat.JSON,
        )
        
        assert response is not None
        
        # Health check should work
        health = manager.get_health()
        assert health is not None


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
