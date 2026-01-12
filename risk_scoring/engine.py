"""
Risk Scoring Engine - Main Orchestrator.

============================================================
PURPOSE
============================================================
The RiskScoringEngine is the main entry point for risk assessment.

It orchestrates:
1. Input validation
2. Individual dimension assessments
3. Score aggregation
4. State change detection
5. Result packaging

============================================================
DESIGN PRINCIPLES
============================================================
- Single responsibility: orchestration only
- Delegates to individual assessors
- Deterministic and stateless per call
- Tracks state changes for alerting
- Capital-agnostic (no dollar amounts)

============================================================
USAGE
============================================================
    from risk_scoring import RiskScoringEngine, RiskScoringInput
    
    engine = RiskScoringEngine()
    
    input_data = RiskScoringInput(
        market=MarketDataInput(...),
        liquidity=LiquidityDataInput(...),
        volatility=VolatilityDataInput(...),
        system_integrity=SystemIntegrityDataInput(...),
        timestamp=datetime.utcnow()
    )
    
    result = engine.score(input_data)
    
    print(f"Risk Level: {result.risk_level.name}")
    print(f"Total Score: {result.total_score}/8")

============================================================
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from .types import (
    RiskState,
    RiskLevel,
    RiskDimension,
    DimensionAssessment,
    RiskScoringInput,
    RiskScoringOutput,
    RiskStateChange,
    RiskScoringError,
    InsufficientDataError,
    DataFreshnessStatus,
)
from .config import RiskScoringConfig
from .assessors import (
    MarketRiskAssessor,
    LiquidityRiskAssessor,
    VolatilityRiskAssessor,
    SystemIntegrityRiskAssessor,
)


class RiskScoringEngine:
    """
    Main orchestrator for the Risk Scoring Engine.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    1. Initialize and configure assessors
    2. Validate input data
    3. Run all assessments
    4. Aggregate scores into total
    5. Classify risk level
    6. Track state changes
    7. Package output
    
    ============================================================
    STATE MANAGEMENT
    ============================================================
    The engine tracks the previous assessment to detect state
    changes for alerting purposes.
    
    ============================================================
    """
    
    def __init__(
        self,
        config: Optional[RiskScoringConfig] = None,
        previous_output: Optional[RiskScoringOutput] = None
    ):
        """
        Initialize the Risk Scoring Engine.
        
        Args:
            config: Engine and assessor configuration.
                    Uses defaults if not provided.
            previous_output: Previous scoring output for state change detection.
        """
        self.config = config or RiskScoringConfig()
        self._previous_output = previous_output
        
        # Initialize assessors with their specific configs
        self._market_assessor = MarketRiskAssessor(self.config.market)
        self._liquidity_assessor = LiquidityRiskAssessor(self.config.liquidity)
        self._volatility_assessor = VolatilityRiskAssessor(self.config.volatility)
        self._system_integrity_assessor = SystemIntegrityRiskAssessor(self.config.system_integrity)
    
    def score(self, input_data: RiskScoringInput) -> RiskScoringOutput:
        """
        Perform a complete risk assessment.
        
        This is the main entry point for scoring. It:
        1. Validates input data
        2. Runs all dimension assessors
        3. Calculates total score
        4. Determines risk level
        5. Detects state changes
        6. Packages the result
        
        Args:
            input_data: Complete input data for all dimensions
        
        Returns:
            RiskScoringOutput with complete assessment
        
        Raises:
            RiskScoringError: On catastrophic failure
        """
        try:
            # --------------------------------------------------
            # Step 1: Validate input
            # --------------------------------------------------
            self._validate_input(input_data)
            
            # --------------------------------------------------
            # Step 2: Run all assessors
            # --------------------------------------------------
            assessments: Dict[RiskDimension, DimensionAssessment] = {}
            
            # Market assessment
            assessments[RiskDimension.MARKET] = self._market_assessor.assess(
                input_data.market
            )
            
            # Liquidity assessment
            assessments[RiskDimension.LIQUIDITY] = self._liquidity_assessor.assess(
                input_data.liquidity
            )
            
            # Volatility assessment
            assessments[RiskDimension.VOLATILITY] = self._volatility_assessor.assess(
                input_data.volatility
            )
            
            # System integrity assessment
            assessments[RiskDimension.SYSTEM_INTEGRITY] = self._system_integrity_assessor.assess(
                input_data.system_integrity
            )
            
            # --------------------------------------------------
            # Step 3: Calculate total score
            # --------------------------------------------------
            total_score = self._calculate_total_score(assessments)
            
            # --------------------------------------------------
            # Step 4: Determine risk level
            # --------------------------------------------------
            risk_level = RiskLevel.from_total_score(total_score)
            
            # --------------------------------------------------
            # Step 5: Detect state changes
            # --------------------------------------------------
            state_changes = self._detect_state_changes(assessments, risk_level)
            
            # --------------------------------------------------
            # Step 6: Build output
            # --------------------------------------------------
            output = RiskScoringOutput(
                total_score=total_score,
                risk_level=risk_level,
                market_assessment=assessments[RiskDimension.MARKET],
                liquidity_assessment=assessments[RiskDimension.LIQUIDITY],
                volatility_assessment=assessments[RiskDimension.VOLATILITY],
                system_integrity_assessment=assessments[RiskDimension.SYSTEM_INTEGRITY],
                timestamp=input_data.timestamp,
                input_timestamp=input_data.timestamp,
                engine_version=self.config.engine_version,
                state_changes=state_changes if state_changes else None,
            )
            
            # --------------------------------------------------
            # Step 7: Update previous state for next call
            # --------------------------------------------------
            self._previous_output = output
            
            return output
            
        except InsufficientDataError:
            raise
        except Exception as e:
            raise RiskScoringError(f"Scoring failed: {str(e)}") from e
    
    def _validate_input(self, input_data: RiskScoringInput) -> None:
        """
        Validate input data has minimum required fields.
        
        Raises:
            InsufficientDataError: If critical data is missing
        """
        if input_data is None:
            raise InsufficientDataError("Input data is None")
        
        if input_data.timestamp is None:
            raise InsufficientDataError("Input timestamp is required")
        
        # Note: Individual assessors handle missing data within their dimension
        # The engine-level validation just ensures we have the input structure
    
    def _calculate_total_score(
        self,
        assessments: Dict[RiskDimension, DimensionAssessment]
    ) -> int:
        """
        Calculate total risk score from all assessments.
        
        Total = Market(0-2) + Liquidity(0-2) + Volatility(0-2) + SystemIntegrity(0-2)
        Range: 0 to 8
        
        Args:
            assessments: All dimension assessments
        
        Returns:
            Total score (0-8)
        """
        total = 0
        
        for dimension in RiskDimension:
            if dimension in assessments:
                assessment = assessments[dimension]
                total += assessment.state.value
        
        return total
    
    def _detect_state_changes(
        self,
        current_assessments: Dict[RiskDimension, DimensionAssessment],
        current_level: RiskLevel
    ) -> List[RiskStateChange]:
        """
        Detect changes from previous assessment.
        
        Used for alerting on risk escalation.
        
        Args:
            current_assessments: Current dimension assessments
            current_level: Current overall risk level
        
        Returns:
            List of state changes (empty if no changes or no previous)
        """
        if self._previous_output is None:
            return []
        
        changes: List[RiskStateChange] = []
        now = datetime.utcnow()
        
        # Check each dimension for state changes
        previous_assessments = {
            RiskDimension.MARKET: self._previous_output.market_assessment,
            RiskDimension.LIQUIDITY: self._previous_output.liquidity_assessment,
            RiskDimension.VOLATILITY: self._previous_output.volatility_assessment,
            RiskDimension.SYSTEM_INTEGRITY: self._previous_output.system_integrity_assessment,
        }
        
        for dimension, current in current_assessments.items():
            previous = previous_assessments.get(dimension)
            if previous and current.state != previous.state:
                changes.append(RiskStateChange(
                    dimension=dimension,
                    old_state=previous.state,
                    new_state=current.state,
                    reason=current.reason,
                    timestamp=now,
                ))
        
        # Check overall level change
        if current_level != self._previous_output.risk_level:
            # Record as a synthetic "change" for alerting
            # Using SYSTEM_INTEGRITY dimension as placeholder
            # The reason will indicate it's an overall level change
            changes.append(RiskStateChange(
                dimension=RiskDimension.SYSTEM_INTEGRITY,
                old_state=RiskState(self._previous_output.total_score // 4),  # Approximate
                new_state=RiskState(min(2, current_assessments[RiskDimension.SYSTEM_INTEGRITY].state.value)),
                reason=f"Overall risk level changed: {self._previous_output.risk_level.name} → {current_level.name}",
                timestamp=now,
            ))
        
        return changes
    
    def get_previous_output(self) -> Optional[RiskScoringOutput]:
        """Return the previous scoring output if available."""
        return self._previous_output
    
    def set_previous_output(self, output: RiskScoringOutput) -> None:
        """
        Set the previous output for state change detection.
        
        Useful when restoring engine state from persistence.
        """
        self._previous_output = output
    
    def get_config(self) -> RiskScoringConfig:
        """Return the current engine configuration."""
        return self.config


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================


def score_risk(
    input_data: RiskScoringInput,
    config: Optional[RiskScoringConfig] = None,
    previous_output: Optional[RiskScoringOutput] = None
) -> RiskScoringOutput:
    """
    Convenience function to score risk in one call.
    
    Creates a temporary engine and runs the assessment.
    For repeated scoring, prefer creating a persistent
    RiskScoringEngine instance.
    
    Args:
        input_data: Complete input data for all dimensions
        config: Optional engine configuration
        previous_output: Optional previous output for state change detection
    
    Returns:
        RiskScoringOutput with complete assessment
    """
    engine = RiskScoringEngine(config=config, previous_output=previous_output)
    return engine.score(input_data)


def get_risk_level_from_score(total_score: int) -> RiskLevel:
    """
    Get risk level classification from a total score.
    
    Args:
        total_score: Score from 0-8
    
    Returns:
        RiskLevel classification
    """
    return RiskLevel.from_total_score(total_score)


def is_safe_to_trade(output: RiskScoringOutput) -> bool:
    """
    Simple check if conditions are safe for trading.
    
    Note: This is a helper for downstream consumers.
    The Risk Scoring Engine itself does NOT decide trade execution.
    
    Args:
        output: Risk scoring output
    
    Returns:
        True if risk level is LOW or MEDIUM
    """
    return output.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)


def should_pause_trading(output: RiskScoringOutput) -> bool:
    """
    Simple check if trading should be paused.
    
    Note: This is a helper for downstream consumers.
    The Risk Scoring Engine itself does NOT decide trade execution.
    
    Args:
        output: Risk scoring output
    
    Returns:
        True if risk level is CRITICAL
    """
    return output.risk_level == RiskLevel.CRITICAL


def format_risk_summary(output: RiskScoringOutput) -> str:
    """
    Format a human-readable risk summary.
    
    Useful for logging, alerts, and dashboards.
    
    Args:
        output: Risk scoring output
    
    Returns:
        Formatted summary string
    """
    lines = [
        "=" * 50,
        "RISK ASSESSMENT SUMMARY",
        "=" * 50,
        f"Total Score: {output.total_score}/8",
        f"Risk Level: {output.risk_level.name}",
        f"Timestamp: {output.timestamp.isoformat() if output.timestamp else 'N/A'}",
        "",
        "Dimension Breakdown:",
        f"  Market:           {output.market_assessment.state.name} ({output.market_assessment.state.value})",
        f"  Liquidity:        {output.liquidity_assessment.state.name} ({output.liquidity_assessment.state.value})",
        f"  Volatility:       {output.volatility_assessment.state.name} ({output.volatility_assessment.state.value})",
        f"  System Integrity: {output.system_integrity_assessment.state.name} ({output.system_integrity_assessment.state.value})",
        "",
        "Details:",
        f"  Market:           {output.market_assessment.reason}",
        f"  Liquidity:        {output.liquidity_assessment.reason}",
        f"  Volatility:       {output.volatility_assessment.reason}",
        f"  System Integrity: {output.system_integrity_assessment.reason}",
        "=" * 50,
    ]
    
    return "\n".join(lines)
