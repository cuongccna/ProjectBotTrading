"""
Product Data Packaging Layer.

============================================================
PURPOSE
============================================================
Convert internal retained data into standardized, sellable
data products for external consumption.

============================================================
CRITICAL CONSTRAINTS
============================================================
- This module does NOT trade
- This module does NOT affect internal decisions
- This module ONLY prepares data for external consumption
- All data products are NON-ACTIONABLE
- All failures are isolated from trading operations

============================================================
DATA PRODUCT TYPES
============================================================
1. Sentiment Index - Aggregated sentiment scores
2. Flow Pressure - On-chain flow pressure indicators
3. Market Condition Timeline - Historical regime classifications
4. Risk Regime Dataset - Historical risk states
5. System Health Metrics - Operational health indicators

============================================================
SAFETY GUARANTEES
============================================================
- All data is delayed (time-lagged)
- All data is aggregated (no individual points)
- All data is normalized (no absolute values)
- No trading signals (buy/sell/long/short)
- No directional bias
- No identifiers or PII
- No system internals exposed

============================================================
USAGE
============================================================

# Create the packaging manager
from product_packaging import create_product_packaging_manager

manager = create_product_packaging_manager()

# List available products
products = manager.list_products()

# Export data
response = await manager.export(
    client_id="client_123",
    product_type=ProductType.SENTIMENT_INDEX,
    start_time=datetime(2025, 1, 1),
    end_time=datetime(2025, 1, 10),
    time_bucket=TimeBucket.HOUR_1,
    output_format=OutputFormat.JSON,
)

# Check health
health = manager.get_health()

============================================================
"""

from .models import (
    # Product Types
    ProductType,
    ProductTier,
    TimeBucket,
    OutputFormat,
    DeliveryMethod,
    
    # Data Sources
    AllowedDataSource,
    ProhibitedDataSource,
    
    # Schema
    SchemaVersion,
    SchemaField,
    ProductSchema,
    
    # Configuration
    AggregationConfig,
    DelayConfig,
    NormalizationConfig,
    ProductDefinition,
    
    # Export
    ExportMetadata,
    ExportRequest,
    ExportResponse,
    ExportStatus,
    
    # Safety
    ActionableSignalType,
    NonActionableCheck,
    
    # Access
    RateLimitConfig,
    AccessLog,
    
    # Factories
    create_schema_version,
    create_default_delay_config,
    create_default_aggregation_config,
    create_default_normalization_config,
    create_default_rate_limit,
)

from .schemas import (
    # Registry
    SchemaRegistry,
    create_schema_registry,
    
    # Schema Factories
    create_sentiment_index_schema,
    create_flow_pressure_schema,
    create_market_condition_schema,
    create_risk_regime_schema,
    create_system_health_schema,
    
    # Product Factories
    create_sentiment_index_product,
    create_flow_pressure_product,
    create_market_condition_product,
    create_risk_regime_product,
    create_system_health_product,
    
    # Utilities
    get_all_product_definitions,
    get_product_definition,
)

from .extractors import (
    # Validation
    DataSourceValidator,
    
    # Models
    ExtractedRecord,
    ExtractionResult,
    ExtractionQuery,
    
    # Interface
    DataStoreInterface,
    
    # Extractors
    BaseExtractor,
    SentimentExtractor,
    FlowPressureExtractor,
    MarketConditionExtractor,
    RiskRegimeExtractor,
    SystemHealthExtractor,
    
    # Factory
    ExtractorFactory,
    create_extractor,
    create_data_source_validator,
)

from .transformers import (
    # Models
    TransformedRecord,
    TransformationResult,
    
    # Transformers
    TimeDelayTransformer,
    TimeBucketTransformer,
    AggregationTransformer,
    AggregationMethod,
    NormalizationTransformer,
    RollingWindowTransformer,
    ProductTransformer,
    
    # Factories
    create_delay_transformer,
    create_bucket_transformer,
    create_aggregation_transformer,
    create_normalization_transformer,
    create_product_transformer,
)

from .safety import (
    # Terms
    ProhibitedTerms,
    
    # Validators
    NonActionableValidator,
    DataAnonymizer,
    ReverseEngineeringPrevention,
    
    # Results
    SafetyCheckResult,
    
    # Checker
    SafetyChecker,
    
    # Factories
    create_non_actionable_validator,
    create_anonymizer,
    create_safety_checker,
    create_reverse_engineering_prevention,
)

from .formatters import (
    # Output
    FormattedOutput,
    
    # Formatters
    BaseFormatter,
    JsonFormatter,
    CsvFormatter,
    ParquetFormatter,
    
    # Builder
    MetadataBuilder,
    
    # Manager
    FormatterFactory,
    OutputManager,
    
    # Factories
    create_json_formatter,
    create_csv_formatter,
    create_parquet_formatter,
    create_formatter,
    create_output_manager,
    create_metadata_builder,
)

from .pipeline import (
    # Status
    PipelineStage,
    StageResult,
    PipelineResult,
    
    # Config
    PipelineConfig,
    
    # Pipeline
    ProductPipeline,
    PipelineFactory,
    PipelineExecutor,
    
    # Factories
    create_pipeline,
    create_pipeline_factory,
    create_pipeline_executor,
    create_pipeline_config,
)

from .access import (
    # Levels
    AccessLevel,
    RequestDenialReason,
    
    # Rate Limiting
    RateLimiter,
    RateLimitBucket,
    
    # Logging
    AccessLogger,
    
    # Validation
    RequestValidator,
    ReadOnlyEnforcer,
    
    # Controller
    AccessCheckResult,
    AccessController,
    
    # API Keys
    ApiKeyManager,
    
    # Factories
    create_rate_limiter,
    create_access_logger,
    create_access_controller,
    create_request_validator,
    create_api_key_manager,
)

from .manager import (
    # Health
    HealthStatus,
    ComponentHealth,
    SystemHealth,
    
    # Catalog
    ProductInfo,
    ProductCatalog,
    
    # Wrapper
    FailSafeWrapper,
    
    # Manager
    ProductPackagingManager,
    FailSafePackagingManager,
    
    # Factories
    create_product_packaging_manager,
    create_fail_safe_packaging_manager,
    create_product_catalog,
)


__version__ = "1.0.0"

__all__ = [
    # Version
    "__version__",
    
    # === MODELS ===
    # Product Types
    "ProductType",
    "ProductTier",
    "TimeBucket",
    "OutputFormat",
    "DeliveryMethod",
    
    # Data Sources
    "AllowedDataSource",
    "ProhibitedDataSource",
    
    # Schema
    "SchemaVersion",
    "SchemaField",
    "ProductSchema",
    
    # Configuration
    "AggregationConfig",
    "DelayConfig",
    "NormalizationConfig",
    "ProductDefinition",
    
    # Export
    "ExportMetadata",
    "ExportRequest",
    "ExportResponse",
    "ExportStatus",
    
    # Safety
    "ActionableSignalType",
    "NonActionableCheck",
    
    # Access
    "RateLimitConfig",
    "AccessLog",
    
    # === SCHEMAS ===
    "SchemaRegistry",
    "create_schema_registry",
    "create_sentiment_index_schema",
    "create_flow_pressure_schema",
    "create_market_condition_schema",
    "create_risk_regime_schema",
    "create_system_health_schema",
    "create_sentiment_index_product",
    "create_flow_pressure_product",
    "create_market_condition_product",
    "create_risk_regime_product",
    "create_system_health_product",
    "get_all_product_definitions",
    "get_product_definition",
    
    # === EXTRACTORS ===
    "DataSourceValidator",
    "ExtractedRecord",
    "ExtractionResult",
    "ExtractionQuery",
    "DataStoreInterface",
    "BaseExtractor",
    "SentimentExtractor",
    "FlowPressureExtractor",
    "MarketConditionExtractor",
    "RiskRegimeExtractor",
    "SystemHealthExtractor",
    "ExtractorFactory",
    "create_extractor",
    "create_data_source_validator",
    
    # === TRANSFORMERS ===
    "TransformedRecord",
    "TransformationResult",
    "TimeDelayTransformer",
    "TimeBucketTransformer",
    "AggregationTransformer",
    "AggregationMethod",
    "NormalizationTransformer",
    "RollingWindowTransformer",
    "ProductTransformer",
    "create_delay_transformer",
    "create_bucket_transformer",
    "create_aggregation_transformer",
    "create_normalization_transformer",
    "create_product_transformer",
    
    # === SAFETY ===
    "ProhibitedTerms",
    "NonActionableValidator",
    "DataAnonymizer",
    "ReverseEngineeringPrevention",
    "SafetyCheckResult",
    "SafetyChecker",
    "create_non_actionable_validator",
    "create_anonymizer",
    "create_safety_checker",
    "create_reverse_engineering_prevention",
    
    # === FORMATTERS ===
    "FormattedOutput",
    "BaseFormatter",
    "JsonFormatter",
    "CsvFormatter",
    "ParquetFormatter",
    "MetadataBuilder",
    "FormatterFactory",
    "OutputManager",
    "create_json_formatter",
    "create_csv_formatter",
    "create_parquet_formatter",
    "create_formatter",
    "create_output_manager",
    "create_metadata_builder",
    
    # === PIPELINE ===
    "PipelineStage",
    "StageResult",
    "PipelineResult",
    "PipelineConfig",
    "ProductPipeline",
    "PipelineFactory",
    "PipelineExecutor",
    "create_pipeline",
    "create_pipeline_factory",
    "create_pipeline_executor",
    "create_pipeline_config",
    
    # === ACCESS ===
    "AccessLevel",
    "RequestDenialReason",
    "RateLimiter",
    "RateLimitBucket",
    "AccessLogger",
    "RequestValidator",
    "ReadOnlyEnforcer",
    "AccessCheckResult",
    "AccessController",
    "ApiKeyManager",
    "create_rate_limiter",
    "create_access_logger",
    "create_access_controller",
    "create_request_validator",
    "create_api_key_manager",
    
    # === MANAGER ===
    "HealthStatus",
    "ComponentHealth",
    "SystemHealth",
    "ProductInfo",
    "ProductCatalog",
    "FailSafeWrapper",
    "ProductPackagingManager",
    "FailSafePackagingManager",
    "create_product_packaging_manager",
    "create_fail_safe_packaging_manager",
    "create_product_catalog",
    
    # === FACTORY FUNCTIONS (MODELS) ===
    "create_schema_version",
    "create_default_delay_config",
    "create_default_aggregation_config",
    "create_default_normalization_config",
    "create_default_rate_limit",
]
