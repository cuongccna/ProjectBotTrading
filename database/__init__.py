"""
Database Package Initialization.

============================================================
INSTITUTIONAL-GRADE DATABASE PERSISTENCE LAYER
============================================================

This package provides REAL database persistence for the
trading bot pipeline. All writes are to actual PostgreSQL
tables with proper transaction management.

FORBIDDEN:
- Stubs, mocks, or fake implementations
- Logging-only persistence
- Silent try/except blocks
- TODO/placeholder comments

REQUIRED:
- Every function performs REAL database writes
- Every write is logged with structured format
- Every failure raises hard exceptions
- All transactions are explicit with commit/rollback

============================================================
"""

# Core engine and session management
from .engine import (
    # Declarative base
    Base,
    
    # Engine creation
    create_database_engine,
    get_engine,
    
    # Session management
    SessionFactory,
    get_db_session,
    transaction_scope,
    
    # Database initialization
    initialize_database,
    verify_required_tables,
    get_table_row_counts,
    
    # Database URL
    DATABASE_URL,
    REQUIRED_TABLES,
    
    # Exceptions
    DatabasePersistenceError,
    DatabaseConnectionError,
    DatabaseInitializationError,
    PersistenceValidationError,
)

# ORM Models - All 12 required tables
from .models import (
    # Data ingestion
    RawNews,
    CleanedNews,
    
    # Analysis
    SentimentScore,
    MarketData,
    OnchainFlowRaw,
    FlowScore,
    
    # State assessment
    MarketState,
    RiskState,
    
    # Decision & execution
    EntryDecision,
    PositionSizing,
    ExecutionRecord,
    
    # Monitoring
    SystemMonitoring,
)

# Individual persistence functions
from .persistence import (
    persist_raw_news,
    persist_cleaned_news,
    persist_sentiment_scores,
    persist_market_data,
    persist_onchain_flow_raw,
    persist_flow_scores,
    persist_market_state,
    persist_risk_state,
    persist_entry_decision,
    persist_position_sizing,
    persist_execution_record,
    persist_system_monitoring,
    persist_system_monitoring_batch,
)

# Pipeline-level persistence
from .pipeline_persistence import (
    PipelineCycleData,
    PersistenceResult,
    persist_pipeline_cycle,
    persist_stage_with_transaction,
    persist_monitoring_event_immediate,
    persist_health_check,
    persist_error_event,
    get_persistence_statistics,
)


# =============================================================
# PACKAGE VERSION
# =============================================================

__version__ = "1.0.0"


# =============================================================
# ALL EXPORTS
# =============================================================

__all__ = [
    # Version
    "__version__",
    
    # Engine
    "Base",
    "create_database_engine",
    "get_engine",
    "SessionFactory",
    "get_db_session",
    "transaction_scope",
    "initialize_database",
    "verify_required_tables",
    "get_table_row_counts",
    "DATABASE_URL",
    "REQUIRED_TABLES",
    
    # Exceptions
    "DatabasePersistenceError",
    "DatabaseConnectionError",
    "DatabaseInitializationError",
    "PersistenceValidationError",
    
    # Models
    "RawNews",
    "CleanedNews",
    "SentimentScore",
    "MarketData",
    "OnchainFlowRaw",
    "FlowScore",
    "MarketState",
    "RiskState",
    "EntryDecision",
    "PositionSizing",
    "ExecutionRecord",
    "SystemMonitoring",
    
    # Individual persistence
    "persist_raw_news",
    "persist_cleaned_news",
    "persist_sentiment_scores",
    "persist_market_data",
    "persist_onchain_flow_raw",
    "persist_flow_scores",
    "persist_market_state",
    "persist_risk_state",
    "persist_entry_decision",
    "persist_position_sizing",
    "persist_execution_record",
    "persist_system_monitoring",
    "persist_system_monitoring_batch",
    
    # Pipeline persistence
    "PipelineCycleData",
    "PersistenceResult",
    "persist_pipeline_cycle",
    "persist_stage_with_transaction",
    "persist_monitoring_event_immediate",
    "persist_health_check",
    "persist_error_event",
    "get_persistence_statistics",
]
