"""
Institutional Risk Review Committee Simulation.

============================================================
PURPOSE
============================================================
Simulate how a professional trading firm reviews system risk
BEFORE allowing continuation or escalation of trading.

This module does NOT trade.
This module does NOT modify market data.
This module has VETO AUTHORITY over trading modes.

============================================================
COMMITTEE COMPOSITION
============================================================
1. Data Integrity Reviewer
2. Market Risk Reviewer  
3. Execution Quality Reviewer
4. Capital Preservation Reviewer

============================================================
DECISION AUTHORITY
============================================================
- APPROVE → allow continuation of current mode only
- HOLD → freeze new trades, allow monitoring
- BLOCK → trigger System Risk Controller global halt

============================================================
"""

from .types import (
    # Enums
    DataIntegrityStatus,
    MarketRiskLevel,
    ExecutionQuality,
    CapitalSafetyStatus,
    CommitteeDecision,
    ReviewerType,
    
    # Dataclasses
    ReviewerVerdict,
    DataIntegrityReport,
    MarketRiskReport,
    ExecutionQualityReport,
    CapitalSafetyReport,
    CommitteeReport,
)

from .reviewers import (
    BaseReviewer,
    DataIntegrityReviewer,
    MarketRiskReviewer,
    ExecutionQualityReviewer,
    CapitalPreservationReviewer,
)

from .engine import RiskCommitteeEngine, create_risk_committee


__all__ = [
    # Enums
    "DataIntegrityStatus",
    "MarketRiskLevel",
    "ExecutionQuality",
    "CapitalSafetyStatus",
    "CommitteeDecision",
    "ReviewerType",
    
    # Reports
    "ReviewerVerdict",
    "DataIntegrityReport",
    "MarketRiskReport",
    "ExecutionQualityReport",
    "CapitalSafetyReport",
    "CommitteeReport",
    
    # Reviewers
    "BaseReviewer",
    "DataIntegrityReviewer",
    "MarketRiskReviewer",
    "ExecutionQualityReviewer",
    "CapitalPreservationReviewer",
    
    # Engine
    "RiskCommitteeEngine",
    "create_risk_committee",
]
