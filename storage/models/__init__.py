"""
Storage Models Package.

This package contains all ORM models for the trading system database.
Models are organized by domain for clarity and maintainability.

============================================================
MODEL ORGANIZATION
============================================================

Domain 1: Raw Data (raw_data.py)
- RawNewsData
- RawMarketData
- RawOnChainData

Domain 2: Processed Data (processed_data.py)
- ProcessedNewsData
- CleanedTextData
- TopicClassification
- RiskKeywordDetection

Domain 3: Sentiment & Scoring (scoring.py)
- SentimentAnalysisResult
- ConfidenceCalibration
- RiskScore
- FlowScore
- SentimentScore
- CompositeScore

Domain 4: Decision Layer (decisions.py)
- TradeEligibilityEvaluation
- VetoEvent
- TradingDecision
- DecisionStateTransition

Domain 5: Risk Management (risk_management.py)
- SystemHalt
- StrategyPause
- DrawdownEvent
- RiskThresholdBreach
- RiskConfigurationAudit

Domain 6: Execution (execution.py)
- Order
- OrderStateTransition
- Execution
- ExecutionValidation
- Position
- PositionSnapshot
- BalanceSnapshot
- TradeRecord

Domain 7: Monitoring & Alerts (monitoring.py)
- HealthCheckResult
- HealthCheckHistory
- Alert
- AlertDelivery
- IncidentRecord
- IncidentTimeline
- TelegramMessage
- SystemHeartbeat

Domain 8: Backtesting (backtesting.py)
- BacktestRun
- BacktestParameter
- BacktestTrade
- BacktestPerformanceMetric
- ParityValidation
- ParityMismatch
- ReplayCheckpoint

Domain 9: Data Products (data_products.py)
- DataProductDefinition
- DataProductSchemaVersion
- AggregatedSentimentData
- AggregatedFlowData
- AggregatedMarketIndicator
- AnonymizationRun
- AnonymizedDataBatch
- ExportConfiguration
- ExportRun
- ExportDeliveryLog
- DataProductAccessLog
- DataProductSubscription
- DataQualityMetric

============================================================
DESIGN PRINCIPLES
============================================================

- All models use explicit column definitions
- All timestamps are timezone-aware (TIMESTAMPTZ)
- All models include created_at tracking
- Foreign keys are explicitly defined
- Indexes match schema specifications
- No business logic in models

============================================================
"""

# Import all models for convenient access
from storage.models.base import Base, TimestampMixin

from storage.models.raw_data import (
    RawNewsData,
    RawMarketData,
    RawOnChainData,
)

from storage.models.processed_data import (
    ProcessedNewsData,
    CleanedTextData,
    TopicClassification,
    RiskKeywordDetection,
    NewsFeatureVector,
    MarketFeatureVector,
    OnChainFeatureVector,
)

from storage.models.scoring import (
    SentimentAnalysisResult,
    ConfidenceCalibration,
    RiskScore,
    FlowScore,
    SentimentScore,
    CompositeScore,
)

from storage.models.decisions import (
    TradeEligibilityEvaluation,
    VetoEvent,
    TradingDecision,
    DecisionStateTransition,
)

from storage.models.risk_management import (
    SystemHalt,
    StrategyPause,
    DrawdownEvent,
    RiskThresholdBreach,
    RiskConfigurationAudit,
)

from storage.models.execution import (
    Order,
    OrderStateTransition,
    Execution,
    ExecutionValidation,
    Position,
    PositionSnapshot,
    BalanceSnapshot,
    TradeRecord,
)

from storage.models.monitoring import (
    HealthCheckResult,
    HealthCheckHistory,
    Alert,
    AlertDelivery,
    IncidentRecord,
    IncidentTimeline,
    TelegramMessage,
    SystemHeartbeat,
)

from storage.models.backtesting import (
    BacktestRun,
    BacktestParameter,
    BacktestTrade,
    BacktestPerformanceMetric,
    ParityValidation,
    ParityMismatch,
    ReplayCheckpoint,
)

from storage.models.data_products import (
    DataProductDefinition,
    SchemaVersion,  # Was: DataProductSchemaVersion
    AggregatedSentimentData,
    AggregatedFlowData,
    AggregatedMarketData,  # Was: AggregatedMarketIndicator
    AnonymizationRun,
    AnonymizedDataBatch,
    ExportConfiguration,
    ExportRun,
    ExportDeliveryLog,
    AccessLog,  # Was: DataProductAccessLog
    Subscription,  # Was: DataProductSubscription
    QualityMetric,  # Was: DataQualityMetric
)

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    # Raw Data
    "RawNewsData",
    "RawMarketData",
    "RawOnChainData",
    # Processed Data
    "ProcessedNewsData",
    "CleanedTextData",
    "TopicClassification",
    "RiskKeywordDetection",
    "NewsFeatureVector",
    "MarketFeatureVector",
    "OnChainFeatureVector",
    # Scoring
    "SentimentAnalysisResult",
    "ConfidenceCalibration",
    "RiskScore",
    "FlowScore",
    "SentimentScore",
    "CompositeScore",
    # Decisions
    "TradeEligibilityEvaluation",
    "VetoEvent",
    "TradingDecision",
    "DecisionStateTransition",
    # Risk Management
    "SystemHalt",
    "StrategyPause",
    "DrawdownEvent",
    "RiskThresholdBreach",
    "RiskConfigurationAudit",
    # Execution
    "Order",
    "OrderStateTransition",
    "Execution",
    "ExecutionValidation",
    "Position",
    "PositionSnapshot",
    "BalanceSnapshot",
    "TradeRecord",
    # Monitoring
    "HealthCheckResult",
    "HealthCheckHistory",
    "Alert",
    "AlertDelivery",
    "IncidentRecord",
    "IncidentTimeline",
    "TelegramMessage",
    "SystemHeartbeat",
    # Backtesting
    "BacktestRun",
    "BacktestParameter",
    "BacktestTrade",
    "BacktestPerformanceMetric",
    "ParityValidation",
    "ParityMismatch",
    "ReplayCheckpoint",
    # Data Products
    "DataProductDefinition",
    "SchemaVersion",
    "AggregatedSentimentData",
    "AggregatedFlowData",
    "AggregatedMarketData",
    "AnonymizationRun",
    "AnonymizedDataBatch",
    "ExportConfiguration",
    "ExportRun",
    "ExportDeliveryLog",
    "AccessLog",
    "Subscription",
    "QualityMetric",
]
