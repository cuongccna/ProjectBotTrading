"""
Risk Scoring Engine - Package.

============================================================
PURPOSE
============================================================
The Risk Scoring Engine is an informational layer that assesses
the overall market and system risk environment.

============================================================
WHAT IT IS
============================================================
- Capital-agnostic environmental risk assessment
- Deterministic, threshold-based scoring
- Produces discrete states: SAFE(0), WARNING(1), DANGEROUS(2)
- Purely informational - does NOT decide trade execution

============================================================
WHAT IT IS NOT
============================================================
- NOT a trade decision maker
- NOT based on position size, account equity, or stop loss
- NOT using ML or probabilistic models
- NOT a strategy executor

============================================================
FOUR RISK DIMENSIONS
============================================================
1. MARKET: Broad market stress (BTC/ETH moves, breadth)
2. LIQUIDITY: Trading condition quality (volume, spread, depth)
3. VOLATILITY: Price range and movement intensity
4. SYSTEM INTEGRITY: Data pipeline and system health

============================================================
SCORING
============================================================
Each dimension: 0 (Safe), 1 (Warning), 2 (Dangerous)
Total: 0-8

Classification:
- LOW (0-2): Normal conditions
- MEDIUM (3-4): Elevated caution
- HIGH (5-6): Significant risk
- CRITICAL (7-8): Maximum caution, consider halting

============================================================
USAGE
============================================================
    from risk_scoring import (
        RiskScoringEngine,
        RiskScoringInput,
        MarketDataInput,
        LiquidityDataInput,
        VolatilityDataInput,
        SystemIntegrityDataInput,
        DataFreshnessStatus,
    )
    from datetime import datetime
    
    # Create engine
    engine = RiskScoringEngine()
    
    # Prepare input data
    input_data = RiskScoringInput(
        market=MarketDataInput(
            btc_price_change_24h_pct=-3.5,
            eth_price_change_24h_pct=-4.2,
            advancing_assets=40,
            declining_assets=60,
        ),
        liquidity=LiquidityDataInput(
            volume_ratio_vs_average=0.8,
            bid_ask_spread_pct=0.2,
            order_book_depth_score=0.7,
        ),
        volatility=VolatilityDataInput(
            price_range_24h_pct=6.5,
            volatility_vs_baseline_ratio=1.2,
        ),
        system_integrity=SystemIntegrityDataInput(
            market_data_status=DataFreshnessStatus.FRESH,
            market_data_age_seconds=30.0,
            pipeline_success_rate=0.95,
        ),
        timestamp=datetime.utcnow(),
    )
    
    # Run assessment
    result = engine.score(input_data)
    
    # Access results
    print(f"Risk Level: {result.risk_level.name}")
    print(f"Total Score: {result.total_score}/8")
    print(f"Market: {result.market_assessment.reason}")

============================================================
"""

# Types
from .types import (
    # Enums
    RiskDimension,
    RiskState,
    RiskLevel,
    DataFreshnessStatus,
    
    # Input types
    MarketDataInput,
    LiquidityDataInput,
    VolatilityDataInput,
    SystemIntegrityDataInput,
    RiskScoringInput,
    
    # Output types
    DimensionAssessment,
    RiskScoringOutput,
    RiskStateChange,
    
    # Exceptions
    RiskScoringError,
    InsufficientDataError,
    AssessmentError,
)

# Configuration
from .config import (
    MarketRiskConfig,
    LiquidityRiskConfig,
    VolatilityRiskConfig,
    SystemIntegrityRiskConfig,
    AlertingConfig,
    RiskScoringConfig,
    get_default_config,
    get_conservative_config,
    get_aggressive_config,
)

# Assessors
from .assessors import (
    BaseRiskAssessor,
    MarketRiskAssessor,
    LiquidityRiskAssessor,
    VolatilityRiskAssessor,
    SystemIntegrityRiskAssessor,
)

# Engine
from .engine import (
    RiskScoringEngine,
    score_risk,
    get_risk_level_from_score,
    is_safe_to_trade,
    should_pause_trading,
    format_risk_summary,
)

# Alerting
from .alerting import (
    RiskAlert,
    AlertSender,
    TelegramAlertSender,
    ConsoleAlertSender,
    AlertRateLimiter,
    RiskAlertingService,
    create_telegram_alerting_service,
    create_console_alerting_service,
)

# Persistence
from .models import (
    RiskSnapshot,
    RiskDimensionScore,
    RiskStateTransition,
)

from .repository import (
    RiskScoringRepository,
)


__all__ = [
    # Enums
    "RiskDimension",
    "RiskState",
    "RiskLevel",
    "DataFreshnessStatus",
    
    # Input types
    "MarketDataInput",
    "LiquidityDataInput",
    "VolatilityDataInput",
    "SystemIntegrityDataInput",
    "RiskScoringInput",
    
    # Output types
    "DimensionAssessment",
    "RiskScoringOutput",
    "RiskStateChange",
    
    # Exceptions
    "RiskScoringError",
    "InsufficientDataError",
    "AssessmentError",
    
    # Configuration
    "MarketRiskConfig",
    "LiquidityRiskConfig",
    "VolatilityRiskConfig",
    "SystemIntegrityRiskConfig",
    "AlertingConfig",
    "RiskScoringConfig",
    "get_default_config",
    "get_conservative_config",
    "get_aggressive_config",
    
    # Assessors
    "BaseRiskAssessor",
    "MarketRiskAssessor",
    "LiquidityRiskAssessor",
    "VolatilityRiskAssessor",
    "SystemIntegrityRiskAssessor",
    
    # Engine
    "RiskScoringEngine",
    "score_risk",
    "get_risk_level_from_score",
    "is_safe_to_trade",
    "should_pause_trading",
    "format_risk_summary",
    
    # Alerting
    "RiskAlert",
    "AlertSender",
    "TelegramAlertSender",
    "ConsoleAlertSender",
    "AlertRateLimiter",
    "RiskAlertingService",
    "create_telegram_alerting_service",
    "create_console_alerting_service",
    
    # Persistence
    "RiskSnapshot",
    "RiskDimensionScore",
    "RiskStateTransition",
    "RiskScoringRepository",
]


__version__ = "1.0.0"
