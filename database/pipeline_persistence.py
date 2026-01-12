"""
Pipeline Persistence Layer.

============================================================
TRANSACTION-BOUNDED PIPELINE PERSISTENCE
============================================================

This module provides the unified persistence layer for complete
pipeline cycles with explicit transaction management.

MANDATORY BEHAVIOR:
- Every pipeline cycle is wrapped in ONE transaction
- All 12 tables are written in atomic operation
- Success = commit all, Failure = rollback all
- Structured logging with exact row counts
- Hard failure on any persistence error

============================================================
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .engine import (
    transaction_scope,
    get_table_row_counts,
    DatabasePersistenceError,
)
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

logger = logging.getLogger(__name__)


# =============================================================
# DATA CLASSES FOR PIPELINE DATA
# =============================================================

@dataclass
class PipelineCycleData:
    """
    Container for all data generated in a single pipeline cycle.
    
    This is the mandatory input for persist_pipeline_cycle().
    All fields are optional to support partial cycles.
    """
    
    # Correlation ID for this cycle
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Cycle metadata
    cycle_start_time: datetime = field(default_factory=datetime.utcnow)
    cycle_end_time: Optional[datetime] = None
    
    # Stage 1: Raw data ingestion
    raw_news: List[Dict[str, Any]] = field(default_factory=list)
    raw_news_source: str = "unknown"
    
    # Stage 2: Cleaned/processed data
    cleaned_news: List[Dict[str, Any]] = field(default_factory=list)
    
    # Stage 3: Sentiment analysis results
    sentiment_scores: List[Dict[str, Any]] = field(default_factory=list)
    
    # Stage 4: Market data
    market_data: List[Dict[str, Any]] = field(default_factory=list)
    market_data_symbol: str = "UNKNOWN"
    market_data_exchange: str = "binance"
    
    # Stage 5: On-chain flow data
    onchain_flows: List[Dict[str, Any]] = field(default_factory=list)
    onchain_flows_source: str = "unknown"
    
    # Stage 6: Flow scores
    flow_scores: List[Dict[str, Any]] = field(default_factory=list)
    
    # Stage 7: Market state assessment
    market_state: Optional[Dict[str, Any]] = None
    
    # Stage 8: Risk assessment
    risk_state: Optional[Dict[str, Any]] = None
    
    # Stage 9: Entry decision
    entry_decision: Optional[Dict[str, Any]] = None
    
    # Stage 10: Position sizing
    position_sizing: Optional[Dict[str, Any]] = None
    
    # Stage 11: Execution record
    execution_record: Optional[Dict[str, Any]] = None
    
    # Stage 12: Monitoring events
    monitoring_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PersistenceResult:
    """Result of a pipeline persistence operation."""
    
    success: bool
    correlation_id: str
    total_records_inserted: int
    records_by_table: Dict[str, int]
    duration_ms: int
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "correlation_id": self.correlation_id,
            "total_records_inserted": self.total_records_inserted,
            "records_by_table": self.records_by_table,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }


# =============================================================
# MAIN PIPELINE PERSISTENCE FUNCTION
# =============================================================

def persist_pipeline_cycle(data: PipelineCycleData) -> PersistenceResult:
    """
    Persist all data from a complete pipeline cycle.
    
    This is the MAIN entry point for pipeline persistence.
    
    BEHAVIOR:
    - Wraps ALL writes in ONE database transaction
    - Commits all on success
    - Rolls back all on any failure
    - Returns detailed persistence result
    
    Args:
        data: PipelineCycleData containing all pipeline outputs
        
    Returns:
        PersistenceResult with success status and row counts
        
    Raises:
        DatabasePersistenceError on critical failures
    """
    start_time = datetime.utcnow()
    correlation_id = data.correlation_id
    records_by_table: Dict[str, int] = {}
    
    logger.info(f"=== PIPELINE PERSISTENCE START: {correlation_id} ===")
    
    try:
        with transaction_scope() as session:
            # Stage 1: Raw News
            records_by_table["raw_news"] = persist_raw_news(
                session, data.raw_news, correlation_id, data.raw_news_source
            )
            
            # Stage 2: Cleaned News
            records_by_table["cleaned_news"] = persist_cleaned_news(
                session, data.cleaned_news, correlation_id
            )
            
            # Stage 3: Sentiment Scores
            records_by_table["sentiment_scores"] = persist_sentiment_scores(
                session, data.sentiment_scores, correlation_id
            )
            
            # Stage 4: Market Data
            records_by_table["market_data"] = persist_market_data(
                session, data.market_data, correlation_id,
                data.market_data_symbol, data.market_data_exchange
            )
            
            # Stage 5: On-chain Flows
            records_by_table["onchain_flow_raw"] = persist_onchain_flow_raw(
                session, data.onchain_flows, correlation_id, data.onchain_flows_source
            )
            
            # Stage 6: Flow Scores
            records_by_table["flow_scores"] = persist_flow_scores(
                session, data.flow_scores, correlation_id
            )
            
            # Stage 7: Market State
            if data.market_state:
                records_by_table["market_state"] = persist_market_state(
                    session, data.market_state, correlation_id
                )
            else:
                records_by_table["market_state"] = 0
            
            # Stage 8: Risk State
            if data.risk_state:
                records_by_table["risk_state"] = persist_risk_state(
                    session, data.risk_state, correlation_id
                )
            else:
                records_by_table["risk_state"] = 0
            
            # Stage 9: Entry Decision
            if data.entry_decision:
                records_by_table["entry_decision"] = persist_entry_decision(
                    session, data.entry_decision, correlation_id
                )
            else:
                records_by_table["entry_decision"] = 0
            
            # Stage 10: Position Sizing
            if data.position_sizing:
                records_by_table["position_sizing"] = persist_position_sizing(
                    session, data.position_sizing, correlation_id
                )
            else:
                records_by_table["position_sizing"] = 0
            
            # Stage 11: Execution Record
            if data.execution_record:
                records_by_table["execution_records"] = persist_execution_record(
                    session, data.execution_record, correlation_id
                )
            else:
                records_by_table["execution_records"] = 0
            
            # Stage 12: Monitoring Events
            records_by_table["system_monitoring"] = persist_system_monitoring_batch(
                session, data.monitoring_events, correlation_id
            )
            
            # Transaction is committed automatically by transaction_scope
        
        # Calculate totals
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        total_records = sum(records_by_table.values())
        
        # Log success summary
        logger.info(f"=== PIPELINE PERSISTENCE COMPLETE ===")
        logger.info(f"Correlation ID: {correlation_id}")
        logger.info(f"Total records inserted: {total_records}")
        logger.info(f"Duration: {duration_ms}ms")
        logger.info(f"Records by table: {records_by_table}")
        logger.info(f"Database transaction committed successfully")
        
        return PersistenceResult(
            success=True,
            correlation_id=correlation_id,
            total_records_inserted=total_records,
            records_by_table=records_by_table,
            duration_ms=duration_ms,
        )
        
    except (DatabasePersistenceError, SQLAlchemyError) as e:
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        
        logger.error(f"=== PIPELINE PERSISTENCE FAILED ===")
        logger.error(f"Correlation ID: {correlation_id}")
        logger.error(f"Error: {e}")
        logger.error(f"Database transaction rolled back")
        
        return PersistenceResult(
            success=False,
            correlation_id=correlation_id,
            total_records_inserted=0,
            records_by_table=records_by_table,
            duration_ms=duration_ms,
            error_message=str(e),
        )


# =============================================================
# INDIVIDUAL STAGE PERSISTENCE (with own transaction)
# =============================================================

def persist_stage_with_transaction(
    stage_name: str,
    persist_func,
    data: Any,
    correlation_id: str,
    **kwargs,
) -> int:
    """
    Persist a single stage with its own transaction.
    
    Use this for out-of-band persistence (e.g., monitoring events
    that should be persisted even if the main cycle fails).
    
    Args:
        stage_name: Name of the stage for logging
        persist_func: The persistence function to call
        data: Data to persist
        correlation_id: Correlation ID
        **kwargs: Additional arguments for the persist function
        
    Returns:
        Number of records inserted
    """
    logger.info(f"Persist stage '{stage_name}' with independent transaction")
    
    try:
        with transaction_scope() as session:
            count = persist_func(session, data, correlation_id, **kwargs)
        
        logger.info(f"Stage '{stage_name}' committed: {count} records")
        return count
        
    except (DatabasePersistenceError, SQLAlchemyError) as e:
        logger.error(f"Stage '{stage_name}' failed: {e}")
        raise


# =============================================================
# MONITORING-SPECIFIC PERSISTENCE
# =============================================================

def persist_monitoring_event_immediate(event: Dict[str, Any]) -> bool:
    """
    Persist a monitoring event immediately with its own transaction.
    
    Use this for critical monitoring events that must be persisted
    regardless of the main pipeline state.
    
    Args:
        event: Monitoring event dictionary
        
    Returns:
        True if persisted successfully
    """
    try:
        with transaction_scope() as session:
            persist_system_monitoring(session, event, event.get("correlation_id"))
        return True
    except Exception as e:
        logger.error(f"Failed to persist immediate monitoring event: {e}")
        return False


def persist_health_check(
    module_name: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Persist a health check event.
    
    Args:
        module_name: Name of the module
        status: Health status (healthy, degraded, unhealthy)
        details: Optional additional details
        
    Returns:
        True if persisted successfully
    """
    event = {
        "event_type": "health_check",
        "severity": "info" if status == "healthy" else "warning",
        "module_name": module_name,
        "message": f"Health check: {status}",
        "details": details,
    }
    return persist_monitoring_event_immediate(event)


def persist_error_event(
    module_name: str,
    error_type: str,
    error_message: str,
    correlation_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Persist an error event immediately.
    
    Args:
        module_name: Name of the module where error occurred
        error_type: Type of error
        error_message: Error message
        correlation_id: Optional correlation ID
        details: Optional additional details
        
    Returns:
        True if persisted successfully
    """
    event = {
        "event_type": f"error_{error_type}",
        "severity": "error",
        "module_name": module_name,
        "message": error_message,
        "details": details,
        "correlation_id": correlation_id,
    }
    return persist_monitoring_event_immediate(event)


# =============================================================
# DATABASE STATISTICS
# =============================================================

def get_persistence_statistics() -> Dict[str, Any]:
    """
    Get current database persistence statistics.
    
    Returns:
        Dictionary with table row counts and statistics
    """
    try:
        row_counts = get_table_row_counts()
        total_rows = sum(row_counts.values())
        
        return {
            "success": True,
            "total_rows": total_rows,
            "row_counts": row_counts,
            "tables_with_data": [t for t, c in row_counts.items() if c > 0],
            "empty_tables": [t for t, c in row_counts.items() if c == 0],
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to get persistence statistics: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


# =============================================================
# EXPORTS
# =============================================================

__all__ = [
    "PipelineCycleData",
    "PersistenceResult",
    "persist_pipeline_cycle",
    "persist_stage_with_transaction",
    "persist_monitoring_event_immediate",
    "persist_health_check",
    "persist_error_event",
    "get_persistence_statistics",
]
