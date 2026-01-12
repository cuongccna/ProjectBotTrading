"""
Product Data Packaging - Schema Definitions.

============================================================
PURPOSE
============================================================
Define standardized schemas for all data product types:
1. Sentiment Index Products
2. Flow Pressure Indicators
3. Market Condition Timelines
4. Risk Regime Datasets
5. System Health Metrics

============================================================
CRITICAL CONSTRAINTS
============================================================
- All schemas must be NON-ACTIONABLE
- No buy/sell/long/short signals
- No directional bias
- Data must be delayed and aggregated

============================================================
"""

from datetime import datetime
from typing import Dict, List

from .models import (
    ProductType,
    ProductTier,
    ProductSchema,
    ProductDefinition,
    SchemaVersion,
    SchemaField,
    TimeBucket,
    OutputFormat,
    DeliveryMethod,
    AllowedDataSource,
    AggregationConfig,
    DelayConfig,
    NormalizationConfig,
    create_schema_version,
    create_default_delay_config,
    create_default_aggregation_config,
    create_default_normalization_config,
)


# ============================================================
# SCHEMA VERSION REGISTRY
# ============================================================

class SchemaRegistry:
    """
    Registry for all product schemas.
    
    Maintains version history and backward compatibility.
    """
    
    def __init__(self):
        self._schemas: Dict[ProductType, Dict[str, ProductSchema]] = {}
        self._latest: Dict[ProductType, str] = {}
    
    def register(self, schema: ProductSchema) -> None:
        """Register a new schema version."""
        product_type = schema.product_type
        version_key = schema.version.version_string
        
        if product_type not in self._schemas:
            self._schemas[product_type] = {}
        
        self._schemas[product_type][version_key] = schema
        
        # Update latest if newer
        if product_type not in self._latest:
            self._latest[product_type] = version_key
        else:
            current_latest = self._schemas[product_type][self._latest[product_type]]
            if schema.version.is_newer_than(current_latest.version):
                self._latest[product_type] = version_key
    
    def get_schema(
        self,
        product_type: ProductType,
        version: str = None
    ) -> ProductSchema:
        """Get schema for product type and version."""
        if product_type not in self._schemas:
            raise ValueError(f"Unknown product type: {product_type}")
        
        if version is None:
            version = self._latest[product_type]
        
        if version not in self._schemas[product_type]:
            raise ValueError(f"Unknown version: {version}")
        
        return self._schemas[product_type][version]
    
    def get_latest_version(self, product_type: ProductType) -> str:
        """Get latest version for product type."""
        if product_type not in self._latest:
            raise ValueError(f"Unknown product type: {product_type}")
        return self._latest[product_type]
    
    def list_versions(self, product_type: ProductType) -> List[str]:
        """List all versions for product type."""
        if product_type not in self._schemas:
            return []
        return list(self._schemas[product_type].keys())
    
    def is_compatible(
        self,
        product_type: ProductType,
        version1: str,
        version2: str
    ) -> bool:
        """Check if two versions are compatible."""
        schema1 = self.get_schema(product_type, version1)
        schema2 = self.get_schema(product_type, version2)
        return schema1.version.is_compatible_with(schema2.version)


# ============================================================
# SENTIMENT INDEX SCHEMA
# ============================================================

def create_sentiment_index_schema() -> ProductSchema:
    """
    Create schema for Sentiment Index products.
    
    Aggregated sentiment scores, time-bucketed.
    No individual news items exposed.
    """
    return ProductSchema(
        product_type=ProductType.SENTIMENT_INDEX,
        version=create_schema_version(1, 0, 0),
        name="Sentiment Index",
        description=(
            "Aggregated sentiment scores derived from multiple sources. "
            "Time-bucketed for historical analysis. "
            "Does not include individual news items or source attribution."
        ),
        fields=[
            SchemaField(
                name="timestamp_bucket",
                data_type="string",
                description="Start of the time bucket (ISO 8601 format)",
                required=True,
                format="date-time",
                example="2025-01-11T12:00:00Z",
            ),
            SchemaField(
                name="time_bucket_size",
                data_type="string",
                description="Size of the time bucket",
                required=True,
                enum_values=["15m", "1h", "4h", "1d", "1w"],
                example="1h",
            ),
            SchemaField(
                name="symbol",
                data_type="string",
                description="Trading symbol or asset identifier",
                required=True,
                example="BTC",
            ),
            SchemaField(
                name="sentiment_score",
                data_type="number",
                description="Normalized sentiment score (0.0 = extremely negative, 1.0 = extremely positive)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.65,
            ),
            SchemaField(
                name="sentiment_confidence",
                data_type="number",
                description="Confidence level of the sentiment score (0.0 to 1.0)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.85,
            ),
            SchemaField(
                name="source_count",
                data_type="integer",
                description="Number of sources aggregated (minimum threshold applies)",
                required=True,
                min_value=3,
                example=15,
            ),
            SchemaField(
                name="sentiment_change",
                data_type="number",
                description="Change from previous bucket (normalized)",
                required=False,
                nullable=True,
                min_value=-1.0,
                max_value=1.0,
                example=0.05,
            ),
            SchemaField(
                name="volatility_indicator",
                data_type="number",
                description="Sentiment volatility within the bucket (0.0 to 1.0)",
                required=False,
                nullable=True,
                min_value=0.0,
                max_value=1.0,
                example=0.3,
            ),
        ],
        update_frequency="hourly",
        time_buckets=[TimeBucket.HOUR_1, TimeBucket.HOURS_4, TimeBucket.DAY_1],
        known_limitations=[
            "Data is delayed by at least 15 minutes",
            "Individual news items are not exposed",
            "Source attribution is not provided",
            "Minimum aggregation threshold of 3 sources applies",
            "Sentiment scores are normalized and may not reflect raw values",
        ],
        data_delay_seconds=900,  # 15 minutes
        min_aggregation_count=3,
    )


# ============================================================
# FLOW PRESSURE SCHEMA
# ============================================================

def create_flow_pressure_schema() -> ProductSchema:
    """
    Create schema for Flow Pressure products.
    
    Aggregated on-chain flow pressure indicators.
    No wallet-level data.
    """
    return ProductSchema(
        product_type=ProductType.FLOW_PRESSURE,
        version=create_schema_version(1, 0, 0),
        name="Flow Pressure Indicators",
        description=(
            "Aggregated on-chain flow pressure indicators. "
            "Includes exchange inflow/outflow intensity. "
            "No wallet-level or transaction-level data is exposed."
        ),
        fields=[
            SchemaField(
                name="timestamp_bucket",
                data_type="string",
                description="Start of the time bucket (ISO 8601 format)",
                required=True,
                format="date-time",
                example="2025-01-11T12:00:00Z",
            ),
            SchemaField(
                name="time_bucket_size",
                data_type="string",
                description="Size of the time bucket",
                required=True,
                enum_values=["1h", "4h", "1d"],
                example="4h",
            ),
            SchemaField(
                name="symbol",
                data_type="string",
                description="Asset identifier",
                required=True,
                example="BTC",
            ),
            SchemaField(
                name="net_flow_pressure",
                data_type="number",
                description="Net flow pressure indicator (-1.0 = strong outflow, 1.0 = strong inflow)",
                required=True,
                min_value=-1.0,
                max_value=1.0,
                example=0.25,
            ),
            SchemaField(
                name="inflow_intensity",
                data_type="number",
                description="Normalized inflow intensity (0.0 to 1.0)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.6,
            ),
            SchemaField(
                name="outflow_intensity",
                data_type="number",
                description="Normalized outflow intensity (0.0 to 1.0)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.35,
            ),
            SchemaField(
                name="flow_volatility",
                data_type="number",
                description="Flow volatility indicator (0.0 to 1.0)",
                required=False,
                nullable=True,
                min_value=0.0,
                max_value=1.0,
                example=0.4,
            ),
            SchemaField(
                name="exchange_count",
                data_type="integer",
                description="Number of exchanges aggregated",
                required=True,
                min_value=1,
                example=5,
            ),
        ],
        update_frequency="every_4_hours",
        time_buckets=[TimeBucket.HOUR_1, TimeBucket.HOURS_4, TimeBucket.DAY_1],
        known_limitations=[
            "Data is delayed by at least 15 minutes",
            "Individual wallet addresses are not exposed",
            "Transaction-level data is not available",
            "Flow values are normalized and relative",
            "Exchange coverage may vary by asset",
        ],
        data_delay_seconds=900,
        min_aggregation_count=3,
    )


# ============================================================
# MARKET CONDITION TIMELINE SCHEMA
# ============================================================

def create_market_condition_schema() -> ProductSchema:
    """
    Create schema for Market Condition Timeline products.
    
    Historical trend/range/volatility regime classifications.
    """
    return ProductSchema(
        product_type=ProductType.MARKET_CONDITION_TIMELINE,
        version=create_schema_version(1, 0, 0),
        name="Market Condition Timeline",
        description=(
            "Historical market condition classifications. "
            "Includes trend, range, and volatility regime states. "
            "Designed for regime analysis, not trading signals."
        ),
        fields=[
            SchemaField(
                name="timestamp_bucket",
                data_type="string",
                description="Start of the time bucket (ISO 8601 format)",
                required=True,
                format="date-time",
                example="2025-01-11T00:00:00Z",
            ),
            SchemaField(
                name="time_bucket_size",
                data_type="string",
                description="Size of the time bucket",
                required=True,
                enum_values=["4h", "1d", "1w"],
                example="1d",
            ),
            SchemaField(
                name="symbol",
                data_type="string",
                description="Trading symbol",
                required=True,
                example="BTCUSDT",
            ),
            SchemaField(
                name="trend_regime",
                data_type="string",
                description="Trend classification (historical observation, not prediction)",
                required=True,
                enum_values=["strong_trend", "weak_trend", "no_trend"],
                example="strong_trend",
            ),
            SchemaField(
                name="range_regime",
                data_type="string",
                description="Range classification",
                required=True,
                enum_values=["tight_range", "normal_range", "wide_range"],
                example="normal_range",
            ),
            SchemaField(
                name="volatility_regime",
                data_type="string",
                description="Volatility classification",
                required=True,
                enum_values=["low_volatility", "normal_volatility", "high_volatility", "extreme_volatility"],
                example="normal_volatility",
            ),
            SchemaField(
                name="regime_stability",
                data_type="number",
                description="How stable the regime has been (0.0 to 1.0)",
                required=False,
                nullable=True,
                min_value=0.0,
                max_value=1.0,
                example=0.75,
            ),
            SchemaField(
                name="regime_duration_buckets",
                data_type="integer",
                description="Number of consecutive buckets with same regime",
                required=False,
                nullable=True,
                min_value=1,
                example=5,
            ),
        ],
        update_frequency="daily",
        time_buckets=[TimeBucket.HOURS_4, TimeBucket.DAY_1, TimeBucket.WEEK_1],
        known_limitations=[
            "Classifications are historical observations, not predictions",
            "Regime boundaries may vary across different analysis methods",
            "Data is delayed by at least 15 minutes",
            "Regime classifications are subjective categorizations",
            "No directional trading signals are implied",
        ],
        data_delay_seconds=900,
        min_aggregation_count=1,
    )


# ============================================================
# RISK REGIME DATASET SCHEMA
# ============================================================

def create_risk_regime_schema() -> ProductSchema:
    """
    Create schema for Risk Regime Dataset products.
    
    Historical risk state classifications.
    """
    return ProductSchema(
        product_type=ProductType.RISK_REGIME_DATASET,
        version=create_schema_version(1, 0, 0),
        name="Risk Regime Dataset",
        description=(
            "Historical risk regime classifications. "
            "Includes frequency and duration of risk states. "
            "For analytical purposes only, not trading decisions."
        ),
        fields=[
            SchemaField(
                name="timestamp_bucket",
                data_type="string",
                description="Start of the time bucket (ISO 8601 format)",
                required=True,
                format="date-time",
                example="2025-01-11T00:00:00Z",
            ),
            SchemaField(
                name="time_bucket_size",
                data_type="string",
                description="Size of the time bucket",
                required=True,
                enum_values=["1h", "4h", "1d"],
                example="1d",
            ),
            SchemaField(
                name="symbol",
                data_type="string",
                description="Asset or market identifier",
                required=False,
                nullable=True,
                example="BTC",
            ),
            SchemaField(
                name="risk_level",
                data_type="string",
                description="Risk level classification",
                required=True,
                enum_values=["minimal", "low", "moderate", "elevated", "high", "critical"],
                example="moderate",
            ),
            SchemaField(
                name="risk_score",
                data_type="number",
                description="Normalized risk score (0.0 = minimal risk, 1.0 = maximum risk)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.45,
            ),
            SchemaField(
                name="risk_components",
                data_type="object",
                description="Breakdown of risk components (normalized)",
                required=False,
                nullable=True,
                example={
                    "market_risk": 0.4,
                    "volatility_risk": 0.5,
                    "liquidity_risk": 0.3,
                },
            ),
            SchemaField(
                name="regime_change_probability",
                data_type="number",
                description="Historical probability of regime change (0.0 to 1.0)",
                required=False,
                nullable=True,
                min_value=0.0,
                max_value=1.0,
                example=0.2,
            ),
            SchemaField(
                name="consecutive_buckets",
                data_type="integer",
                description="Consecutive buckets at current risk level",
                required=False,
                nullable=True,
                min_value=1,
                example=3,
            ),
        ],
        update_frequency="hourly",
        time_buckets=[TimeBucket.HOUR_1, TimeBucket.HOURS_4, TimeBucket.DAY_1],
        known_limitations=[
            "Risk classifications are historical observations",
            "Does not predict future risk states",
            "Risk thresholds are not disclosed",
            "Data is delayed by at least 15 minutes",
            "Component breakdown is normalized and abstracted",
        ],
        data_delay_seconds=900,
        min_aggregation_count=1,
    )


# ============================================================
# SYSTEM HEALTH METRICS SCHEMA
# ============================================================

def create_system_health_schema() -> ProductSchema:
    """
    Create schema for System Health Metrics products.
    
    Operational health indicators (optional product).
    """
    return ProductSchema(
        product_type=ProductType.SYSTEM_HEALTH_METRICS,
        version=create_schema_version(1, 0, 0),
        name="System Health Metrics",
        description=(
            "Aggregated system health and stability indicators. "
            "Includes data freshness, latency, and availability metrics. "
            "For transparency and trust building."
        ),
        fields=[
            SchemaField(
                name="timestamp_bucket",
                data_type="string",
                description="Start of the time bucket (ISO 8601 format)",
                required=True,
                format="date-time",
                example="2025-01-11T12:00:00Z",
            ),
            SchemaField(
                name="time_bucket_size",
                data_type="string",
                description="Size of the time bucket",
                required=True,
                enum_values=["1h", "4h", "1d"],
                example="1h",
            ),
            SchemaField(
                name="data_freshness_score",
                data_type="number",
                description="Data freshness indicator (0.0 = stale, 1.0 = fresh)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.95,
            ),
            SchemaField(
                name="average_latency_ms",
                data_type="integer",
                description="Average processing latency in milliseconds",
                required=True,
                min_value=0,
                example=150,
            ),
            SchemaField(
                name="availability_ratio",
                data_type="number",
                description="System availability ratio (0.0 to 1.0)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.999,
            ),
            SchemaField(
                name="data_completeness",
                data_type="number",
                description="Data completeness ratio (0.0 to 1.0)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.98,
            ),
            SchemaField(
                name="error_rate",
                data_type="number",
                description="Error rate (0.0 to 1.0)",
                required=True,
                min_value=0.0,
                max_value=1.0,
                example=0.001,
            ),
            SchemaField(
                name="stability_indicator",
                data_type="string",
                description="Overall stability classification",
                required=True,
                enum_values=["stable", "degraded", "unstable"],
                example="stable",
            ),
        ],
        update_frequency="hourly",
        time_buckets=[TimeBucket.HOUR_1, TimeBucket.HOURS_4, TimeBucket.DAY_1],
        known_limitations=[
            "Metrics are aggregated and delayed",
            "Does not expose internal system architecture",
            "Latency values are averages, not real-time",
            "Stability classifications are simplified",
        ],
        data_delay_seconds=3600,  # 1 hour delay for health metrics
        min_aggregation_count=1,
    )


# ============================================================
# PRODUCT DEFINITION FACTORY
# ============================================================

def create_sentiment_index_product() -> ProductDefinition:
    """Create Sentiment Index product definition."""
    return ProductDefinition(
        product_id="sentiment_index_v1",
        product_type=ProductType.SENTIMENT_INDEX,
        name="Crypto Sentiment Index",
        description="Aggregated sentiment indicators across major cryptocurrencies",
        schema=create_sentiment_index_schema(),
        tier=ProductTier.STANDARD,
        allowed_sources=[
            AllowedDataSource.DERIVED_SCORES,
            AllowedDataSource.PROCESSED_DATA,
        ],
        aggregation=AggregationConfig(
            method="mean",
            time_bucket=TimeBucket.HOUR_1,
            min_samples=3,
            rolling_window=False,
        ),
        delay=DelayConfig(
            min_delay_seconds=900,
            max_delay_seconds=900,
            jitter_enabled=False,
        ),
        normalization=NormalizationConfig(
            method="min_max",
            min_value=0.0,
            max_value=1.0,
            clip_outliers=True,
        ),
        supported_formats=[OutputFormat.JSON, OutputFormat.CSV],
        supported_delivery=[DeliveryMethod.FILE_DOWNLOAD, DeliveryMethod.REST_API],
    )


def create_flow_pressure_product() -> ProductDefinition:
    """Create Flow Pressure product definition."""
    return ProductDefinition(
        product_id="flow_pressure_v1",
        product_type=ProductType.FLOW_PRESSURE,
        name="Crypto Flow Pressure Indicators",
        description="Aggregated on-chain flow pressure for major cryptocurrencies",
        schema=create_flow_pressure_schema(),
        tier=ProductTier.PREMIUM,
        allowed_sources=[
            AllowedDataSource.PROCESSED_DATA,
            AllowedDataSource.DERIVED_SCORES,
        ],
        aggregation=AggregationConfig(
            method="mean",
            time_bucket=TimeBucket.HOURS_4,
            min_samples=3,
            rolling_window=False,
        ),
        delay=create_default_delay_config(),
        normalization=create_default_normalization_config(),
        supported_formats=[OutputFormat.JSON, OutputFormat.CSV, OutputFormat.PARQUET],
        supported_delivery=[DeliveryMethod.FILE_DOWNLOAD, DeliveryMethod.REST_API],
    )


def create_market_condition_product() -> ProductDefinition:
    """Create Market Condition Timeline product definition."""
    return ProductDefinition(
        product_id="market_condition_v1",
        product_type=ProductType.MARKET_CONDITION_TIMELINE,
        name="Market Condition Timeline",
        description="Historical market regime classifications",
        schema=create_market_condition_schema(),
        tier=ProductTier.STANDARD,
        allowed_sources=[
            AllowedDataSource.MARKET_CONDITION_STATES,
            AllowedDataSource.PROCESSED_DATA,
        ],
        aggregation=AggregationConfig(
            method="mode",  # Most common regime
            time_bucket=TimeBucket.DAY_1,
            min_samples=1,
            rolling_window=False,
        ),
        delay=create_default_delay_config(),
        normalization=NormalizationConfig(
            method="none",  # Categorical data
            min_value=0.0,
            max_value=1.0,
            clip_outliers=False,
        ),
        supported_formats=[OutputFormat.JSON, OutputFormat.CSV],
        supported_delivery=[DeliveryMethod.FILE_DOWNLOAD, DeliveryMethod.REST_API],
    )


def create_risk_regime_product() -> ProductDefinition:
    """Create Risk Regime Dataset product definition."""
    return ProductDefinition(
        product_id="risk_regime_v1",
        product_type=ProductType.RISK_REGIME_DATASET,
        name="Risk Regime Dataset",
        description="Historical risk regime data for analysis",
        schema=create_risk_regime_schema(),
        tier=ProductTier.PREMIUM,
        allowed_sources=[
            AllowedDataSource.DERIVED_SCORES,
            AllowedDataSource.MARKET_CONDITION_STATES,
        ],
        aggregation=AggregationConfig(
            method="mean",
            time_bucket=TimeBucket.HOUR_1,
            min_samples=1,
            rolling_window=False,
        ),
        delay=create_default_delay_config(),
        normalization=create_default_normalization_config(),
        supported_formats=[OutputFormat.JSON, OutputFormat.CSV, OutputFormat.PARQUET],
        supported_delivery=[DeliveryMethod.FILE_DOWNLOAD, DeliveryMethod.REST_API],
    )


def create_system_health_product() -> ProductDefinition:
    """Create System Health Metrics product definition."""
    return ProductDefinition(
        product_id="system_health_v1",
        product_type=ProductType.SYSTEM_HEALTH_METRICS,
        name="System Health Metrics",
        description="Operational health and stability indicators",
        schema=create_system_health_schema(),
        tier=ProductTier.BASIC,
        allowed_sources=[
            AllowedDataSource.PROCESSED_DATA,
        ],
        aggregation=AggregationConfig(
            method="mean",
            time_bucket=TimeBucket.HOUR_1,
            min_samples=1,
            rolling_window=False,
        ),
        delay=DelayConfig(
            min_delay_seconds=3600,  # 1 hour delay
            max_delay_seconds=3600,
            jitter_enabled=False,
        ),
        normalization=create_default_normalization_config(),
        supported_formats=[OutputFormat.JSON, OutputFormat.CSV],
        supported_delivery=[DeliveryMethod.FILE_DOWNLOAD, DeliveryMethod.REST_API],
    )


# ============================================================
# SCHEMA REGISTRY INITIALIZATION
# ============================================================

def create_schema_registry() -> SchemaRegistry:
    """Create and populate schema registry with all product schemas."""
    registry = SchemaRegistry()
    
    # Register all schemas
    registry.register(create_sentiment_index_schema())
    registry.register(create_flow_pressure_schema())
    registry.register(create_market_condition_schema())
    registry.register(create_risk_regime_schema())
    registry.register(create_system_health_schema())
    
    return registry


def get_all_product_definitions() -> List[ProductDefinition]:
    """Get all product definitions."""
    return [
        create_sentiment_index_product(),
        create_flow_pressure_product(),
        create_market_condition_product(),
        create_risk_regime_product(),
        create_system_health_product(),
    ]


def get_product_definition(product_type: ProductType) -> ProductDefinition:
    """Get product definition by type."""
    mapping = {
        ProductType.SENTIMENT_INDEX: create_sentiment_index_product,
        ProductType.FLOW_PRESSURE: create_flow_pressure_product,
        ProductType.MARKET_CONDITION_TIMELINE: create_market_condition_product,
        ProductType.RISK_REGIME_DATASET: create_risk_regime_product,
        ProductType.SYSTEM_HEALTH_METRICS: create_system_health_product,
    }
    
    if product_type not in mapping:
        raise ValueError(f"Unknown product type: {product_type}")
    
    return mapping[product_type]()
