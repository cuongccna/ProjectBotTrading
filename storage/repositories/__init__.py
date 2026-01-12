"""
Repository Layer Package.

============================================================
PURPOSE
============================================================
The Repository Layer is the ONLY gateway to persistent storage.
All database access MUST go through repository classes.

============================================================
ARCHITECTURE PRINCIPLES
============================================================
1. DAO Pattern: One repository per domain (or tightly related set)
2. Session Injection: Sessions are injected, not created internally
3. Explicit Methods: No generic 'execute', clear method names
4. Immutability: Raw data is append-only, state changes via transitions
5. Exception Handling: All DB errors wrapped in repository exceptions

============================================================
REPOSITORY GROUPS
============================================================

RAW DATA (Append-Only)
----------------------
- RawNewsRepository: Raw news article data
- RawMarketDataRepository: Raw market/price data  
- RawOnChainRepository: Raw blockchain data

PROCESSED DATA
--------------
- ProcessedTextRepository: Cleaned/normalized text data
- LabeledDataRepository: Topic/risk labels and classifications

SCORING DATA
------------
- SentimentScoreRepository: Sentiment analysis results
- FlowScoreRepository: Fund flow and volume scores
- CompositeScoreRepository: Combined scores and risk metrics

DECISION & RISK
---------------
- TradeDecisionRepository: Trading decisions and eligibility
- RiskEventRepository: Risk events and system halts

EXECUTION
---------
- OrderRepository: Order management and state tracking
- ExecutionResultRepository: Execution results and validation

MONITORING & ALERTS
-------------------
- SystemHealthRepository: Health checks and heartbeats
- AlertLogRepository: Alerts and incident tracking

============================================================
USAGE
============================================================

    from sqlalchemy.orm import Session
    from storage.repositories import RawNewsRepository
    
    def ingest_news(session: Session, data: dict):
        repo = RawNewsRepository(session)
        raw_news = repo.create_raw_news(
            source="rss",
            collected_at=datetime.utcnow(),
            payload=data,
            payload_hash=compute_hash(data),
            version="1.0.0",
        )
        session.commit()
        return raw_news

============================================================
"""

# =============================================================
# EXCEPTIONS
# =============================================================
from storage.repositories.exceptions import (
    RepositoryException,
    RecordNotFoundError,
    DuplicateRecordError,
    IntegrityError,
    ConnectionError,
    QueryError,
    TransactionError,
    ImmutableRecordError,
    ValidationError,
)

# =============================================================
# BASE REPOSITORY
# =============================================================
from storage.repositories.base import BaseRepository

# =============================================================
# RAW DATA REPOSITORIES
# =============================================================
from storage.repositories.raw_data import (
    RawNewsRepository,
    RawMarketDataRepository,
    RawOnChainRepository,
)

# =============================================================
# PROCESSED DATA REPOSITORIES
# =============================================================
from storage.repositories.processed_data import (
    ProcessedTextRepository,
    LabeledDataRepository,
)

# =============================================================
# SCORING REPOSITORIES
# =============================================================
from storage.repositories.scoring import (
    SentimentScoreRepository,
    FlowScoreRepository,
    CompositeScoreRepository,
)

# =============================================================
# DECISION & RISK REPOSITORIES
# =============================================================
from storage.repositories.decisions import (
    TradeDecisionRepository,
    RiskEventRepository,
)

# =============================================================
# EXECUTION REPOSITORIES
# =============================================================
from storage.repositories.execution import (
    OrderRepository,
    ExecutionResultRepository,
)

# =============================================================
# MONITORING & ALERT REPOSITORIES
# =============================================================
from storage.repositories.monitoring import (
    SystemHealthRepository,
    AlertLogRepository,
)

# =============================================================
# PUBLIC API
# =============================================================
__all__ = [
    # Exceptions
    "RepositoryException",
    "RecordNotFoundError",
    "DuplicateRecordError",
    "IntegrityError",
    "ConnectionError",
    "QueryError",
    "TransactionError",
    "ImmutableRecordError",
    "ValidationError",
    
    # Base
    "BaseRepository",
    
    # Raw Data
    "RawNewsRepository",
    "RawMarketDataRepository",
    "RawOnChainRepository",
    
    # Processed Data
    "ProcessedTextRepository",
    "LabeledDataRepository",
    
    # Scoring
    "SentimentScoreRepository",
    "FlowScoreRepository",
    "CompositeScoreRepository",
    
    # Decisions
    "TradeDecisionRepository",
    "RiskEventRepository",
    
    # Execution
    "OrderRepository",
    "ExecutionResultRepository",
    
    # Monitoring
    "SystemHealthRepository",
    "AlertLogRepository",
]
