"""
Risk Scoring Engine - Configuration.

============================================================
PURPOSE
============================================================
Defines all configuration dataclasses and threshold values
for the Risk Scoring Engine.

All thresholds are documented with rationale.
All values are capital-agnostic (no dollar amounts).

============================================================
DESIGN PRINCIPLES
============================================================
- All thresholds are percentages or ratios
- Conservative defaults (err on the side of caution)
- Each threshold has documentation
- Immutable configurations

============================================================
THRESHOLD PHILOSOPHY
============================================================
Two thresholds per dimension:
- WARNING threshold: Elevated concern, not yet critical
- DANGEROUS threshold: High risk, maximum caution

Below WARNING = SAFE
Between WARNING and DANGEROUS = WARNING
At or above DANGEROUS = DANGEROUS

============================================================
"""

from dataclasses import dataclass, field
from typing import Dict, Any


# ============================================================
# MARKET RISK CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class MarketRiskConfig:
    """
    Configuration for Market Risk assessment.
    
    ============================================================
    WHAT WE MEASURE
    ============================================================
    - BTC/ETH 24h price change (market leaders)
    - Market breadth (advancing vs declining assets)
    - Extreme movements (assets down/up >10%)
    
    ============================================================
    THRESHOLD RATIONALE
    ============================================================
    BTC 24h change:
    - WARNING at 5%: Significant daily move
    - DANGEROUS at 10%: Major market event
    
    Market breadth:
    - WARNING when 70% declining: Clear downtrend
    - DANGEROUS when 85% declining: Capitulation risk
    
    ============================================================
    """
    
    # BTC 24h price change thresholds (absolute percentage)
    btc_change_warning_pct: float = 5.0       # WARNING if |change| >= 5%
    btc_change_dangerous_pct: float = 10.0    # DANGEROUS if |change| >= 10%
    
    # ETH 24h price change thresholds (absolute percentage)
    eth_change_warning_pct: float = 7.0       # WARNING if |change| >= 7%
    eth_change_dangerous_pct: float = 15.0    # DANGEROUS if |change| >= 15%
    
    # Market breadth thresholds (% of assets declining)
    breadth_warning_declining_pct: float = 70.0    # WARNING if 70%+ declining
    breadth_dangerous_declining_pct: float = 85.0  # DANGEROUS if 85%+ declining
    
    # Extreme movement count thresholds
    extreme_move_warning_count: int = 5       # WARNING if 5+ assets moved >10%
    extreme_move_dangerous_count: int = 15    # DANGEROUS if 15+ assets moved >10%
    
    # Data staleness threshold (seconds)
    max_data_age_seconds: float = 300.0       # 5 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "btc_change_warning_pct": self.btc_change_warning_pct,
            "btc_change_dangerous_pct": self.btc_change_dangerous_pct,
            "eth_change_warning_pct": self.eth_change_warning_pct,
            "eth_change_dangerous_pct": self.eth_change_dangerous_pct,
            "breadth_warning_declining_pct": self.breadth_warning_declining_pct,
            "breadth_dangerous_declining_pct": self.breadth_dangerous_declining_pct,
            "extreme_move_warning_count": self.extreme_move_warning_count,
            "extreme_move_dangerous_count": self.extreme_move_dangerous_count,
            "max_data_age_seconds": self.max_data_age_seconds,
        }


# ============================================================
# LIQUIDITY RISK CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class LiquidityRiskConfig:
    """
    Configuration for Liquidity Risk assessment.
    
    ============================================================
    WHAT WE MEASURE
    ============================================================
    - Volume vs historical average (declining volume = risk)
    - Bid-ask spread (widening = thin liquidity)
    - Order book depth (normalized score)
    
    ============================================================
    THRESHOLD RATIONALE
    ============================================================
    Volume ratio (current/average):
    - WARNING below 0.5: Volume 50% of normal
    - DANGEROUS below 0.25: Volume 25% of normal (very thin)
    
    Bid-ask spread:
    - WARNING at 0.5%: Elevated spread
    - DANGEROUS at 1.5%: Significant slippage risk
    
    ============================================================
    """
    
    # Volume ratio thresholds (current/average, lower = worse)
    volume_ratio_warning: float = 0.5         # WARNING if ratio < 0.5
    volume_ratio_dangerous: float = 0.25      # DANGEROUS if ratio < 0.25
    
    # Bid-ask spread thresholds (percentage)
    spread_warning_pct: float = 0.5           # WARNING if spread >= 0.5%
    spread_dangerous_pct: float = 1.5         # DANGEROUS if spread >= 1.5%
    
    # Order book depth score thresholds (0-1, lower = thinner)
    depth_warning: float = 0.4                # WARNING if depth < 0.4
    depth_dangerous: float = 0.2              # DANGEROUS if depth < 0.2
    
    # Data staleness threshold (seconds)
    max_data_age_seconds: float = 120.0       # 2 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "volume_ratio_warning": self.volume_ratio_warning,
            "volume_ratio_dangerous": self.volume_ratio_dangerous,
            "spread_warning_pct": self.spread_warning_pct,
            "spread_dangerous_pct": self.spread_dangerous_pct,
            "depth_warning": self.depth_warning,
            "depth_dangerous": self.depth_dangerous,
            "max_data_age_seconds": self.max_data_age_seconds,
        }


# ============================================================
# VOLATILITY RISK CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class VolatilityRiskConfig:
    """
    Configuration for Volatility Risk assessment.
    
    ============================================================
    WHAT WE MEASURE
    ============================================================
    - Price range expansion (1h, 4h, 24h)
    - Volatility vs historical baseline
    - Abnormal candle detection
    
    ============================================================
    THRESHOLD RATIONALE
    ============================================================
    24h price range:
    - WARNING at 8%: Elevated volatility
    - DANGEROUS at 15%: Extreme volatility
    
    Volatility ratio (current/average):
    - WARNING at 1.5x: 50% above normal
    - DANGEROUS at 2.5x: 150% above normal
    
    ============================================================
    """
    
    # 24h price range thresholds (percentage)
    range_24h_warning_pct: float = 8.0        # WARNING if range >= 8%
    range_24h_dangerous_pct: float = 15.0     # DANGEROUS if range >= 15%
    
    # 4h price range thresholds (percentage)
    range_4h_warning_pct: float = 4.0         # WARNING if range >= 4%
    range_4h_dangerous_pct: float = 8.0       # DANGEROUS if range >= 8%
    
    # 1h price range thresholds (percentage)
    range_1h_warning_pct: float = 2.5         # WARNING if range >= 2.5%
    range_1h_dangerous_pct: float = 5.0       # DANGEROUS if range >= 5%
    
    # Volatility ratio thresholds (current/average)
    volatility_ratio_warning: float = 1.5     # WARNING if ratio >= 1.5
    volatility_ratio_dangerous: float = 2.5   # DANGEROUS if ratio >= 2.5
    
    # Abnormal candle count thresholds (last 24h)
    abnormal_candle_warning_count: int = 3    # WARNING if 3+ abnormal candles
    abnormal_candle_dangerous_count: int = 8  # DANGEROUS if 8+ abnormal candles
    
    # Data staleness threshold (seconds)
    max_data_age_seconds: float = 120.0       # 2 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "range_24h_warning_pct": self.range_24h_warning_pct,
            "range_24h_dangerous_pct": self.range_24h_dangerous_pct,
            "range_4h_warning_pct": self.range_4h_warning_pct,
            "range_4h_dangerous_pct": self.range_4h_dangerous_pct,
            "range_1h_warning_pct": self.range_1h_warning_pct,
            "range_1h_dangerous_pct": self.range_1h_dangerous_pct,
            "volatility_ratio_warning": self.volatility_ratio_warning,
            "volatility_ratio_dangerous": self.volatility_ratio_dangerous,
            "abnormal_candle_warning_count": self.abnormal_candle_warning_count,
            "abnormal_candle_dangerous_count": self.abnormal_candle_dangerous_count,
            "max_data_age_seconds": self.max_data_age_seconds,
        }


# ============================================================
# SYSTEM INTEGRITY RISK CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class SystemIntegrityRiskConfig:
    """
    Configuration for System Integrity Risk assessment.
    
    ============================================================
    WHAT WE MEASURE
    ============================================================
    - Data pipeline freshness
    - Feature pipeline health
    - System latency
    - Error rates
    
    ============================================================
    THRESHOLD RATIONALE
    ============================================================
    Data age:
    - WARNING at 5 min: Data getting stale
    - DANGEROUS at 15 min: Stale data, unreliable
    
    Error rate:
    - WARNING at 5 errors/hour: Elevated issues
    - DANGEROUS at 20 errors/hour: Systemic problems
    
    ============================================================
    FAIL-SAFE BEHAVIOR
    ============================================================
    If data is MISSING or INVALID:
    - Immediately set to DANGEROUS (2)
    - This is non-negotiable for safety
    
    ============================================================
    """
    
    # Market data age thresholds (seconds)
    market_data_warning_age_seconds: float = 300.0      # 5 minutes
    market_data_dangerous_age_seconds: float = 900.0    # 15 minutes
    
    # News data age thresholds (seconds)
    news_data_warning_age_seconds: float = 600.0        # 10 minutes
    news_data_dangerous_age_seconds: float = 1800.0     # 30 minutes
    
    # On-chain data age thresholds (seconds)
    onchain_data_warning_age_seconds: float = 900.0     # 15 minutes
    onchain_data_dangerous_age_seconds: float = 3600.0  # 1 hour
    
    # Feature pipeline age thresholds (seconds)
    pipeline_warning_age_seconds: float = 600.0         # 10 minutes
    pipeline_dangerous_age_seconds: float = 1800.0      # 30 minutes
    
    # Pipeline success rate thresholds (0-1)
    pipeline_warning_success_rate: float = 0.9          # WARNING if < 90%
    pipeline_dangerous_success_rate: float = 0.7        # DANGEROUS if < 70%
    
    # API latency thresholds (milliseconds)
    api_latency_warning_ms: float = 1000.0              # 1 second
    api_latency_dangerous_ms: float = 5000.0            # 5 seconds
    
    # Error count thresholds (per hour)
    error_warning_count: int = 5
    error_dangerous_count: int = 20
    
    # Critical error count thresholds (per hour)
    critical_error_warning_count: int = 1               # Any critical = WARNING
    critical_error_dangerous_count: int = 3
    
    # Data sync lag thresholds (seconds)
    sync_lag_warning_seconds: float = 60.0              # 1 minute
    sync_lag_dangerous_seconds: float = 300.0           # 5 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_data_warning_age_seconds": self.market_data_warning_age_seconds,
            "market_data_dangerous_age_seconds": self.market_data_dangerous_age_seconds,
            "news_data_warning_age_seconds": self.news_data_warning_age_seconds,
            "news_data_dangerous_age_seconds": self.news_data_dangerous_age_seconds,
            "onchain_data_warning_age_seconds": self.onchain_data_warning_age_seconds,
            "onchain_data_dangerous_age_seconds": self.onchain_data_dangerous_age_seconds,
            "pipeline_warning_age_seconds": self.pipeline_warning_age_seconds,
            "pipeline_dangerous_age_seconds": self.pipeline_dangerous_age_seconds,
            "pipeline_warning_success_rate": self.pipeline_warning_success_rate,
            "pipeline_dangerous_success_rate": self.pipeline_dangerous_success_rate,
            "api_latency_warning_ms": self.api_latency_warning_ms,
            "api_latency_dangerous_ms": self.api_latency_dangerous_ms,
            "error_warning_count": self.error_warning_count,
            "error_dangerous_count": self.error_dangerous_count,
            "critical_error_warning_count": self.critical_error_warning_count,
            "critical_error_dangerous_count": self.critical_error_dangerous_count,
            "sync_lag_warning_seconds": self.sync_lag_warning_seconds,
            "sync_lag_dangerous_seconds": self.sync_lag_dangerous_seconds,
        }


# ============================================================
# ALERTING CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class AlertingConfig:
    """
    Configuration for risk state change alerting.
    
    ============================================================
    ALERT PHILOSOPHY
    ============================================================
    - Always alert on escalation to HIGH or CRITICAL
    - Rate-limit repeated alerts
    - Include context for actionability
    
    ============================================================
    """
    
    # Alert on these level transitions
    alert_on_high: bool = True                # Alert when reaching HIGH
    alert_on_critical: bool = True            # Alert when reaching CRITICAL
    alert_on_de_escalation: bool = False      # Alert when risk decreases
    
    # Rate limiting
    min_seconds_between_alerts: float = 300.0  # 5 minutes between same alerts
    
    # Telegram integration
    telegram_enabled: bool = True
    telegram_include_details: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_on_high": self.alert_on_high,
            "alert_on_critical": self.alert_on_critical,
            "alert_on_de_escalation": self.alert_on_de_escalation,
            "min_seconds_between_alerts": self.min_seconds_between_alerts,
            "telegram_enabled": self.telegram_enabled,
            "telegram_include_details": self.telegram_include_details,
        }


# ============================================================
# MASTER CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class RiskScoringConfig:
    """
    Master configuration for the Risk Scoring Engine.
    
    Aggregates all dimension configs and engine settings.
    """
    
    # Dimension configurations
    market: MarketRiskConfig = field(default_factory=MarketRiskConfig)
    liquidity: LiquidityRiskConfig = field(default_factory=LiquidityRiskConfig)
    volatility: VolatilityRiskConfig = field(default_factory=VolatilityRiskConfig)
    system_integrity: SystemIntegrityRiskConfig = field(default_factory=SystemIntegrityRiskConfig)
    
    # Alerting configuration
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    
    # Engine settings
    engine_version: str = "1.0.0"
    
    # Scoring interval (seconds)
    scoring_interval_seconds: float = 60.0    # Re-score every minute
    
    # Persistence settings
    persist_all_scores: bool = True           # Persist every assessment
    persist_changes_only: bool = False        # Only persist on state change
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market.to_dict(),
            "liquidity": self.liquidity.to_dict(),
            "volatility": self.volatility.to_dict(),
            "system_integrity": self.system_integrity.to_dict(),
            "alerting": self.alerting.to_dict(),
            "engine_version": self.engine_version,
            "scoring_interval_seconds": self.scoring_interval_seconds,
            "persist_all_scores": self.persist_all_scores,
            "persist_changes_only": self.persist_changes_only,
        }


# ============================================================
# DEFAULT CONFIGURATION
# ============================================================


def get_default_config() -> RiskScoringConfig:
    """
    Return the default Risk Scoring Engine configuration.
    
    This provides conservative defaults suitable for production.
    """
    return RiskScoringConfig()


def get_conservative_config() -> RiskScoringConfig:
    """
    Return a more conservative configuration.
    
    Lower thresholds = earlier warnings = more caution.
    """
    return RiskScoringConfig(
        market=MarketRiskConfig(
            btc_change_warning_pct=3.0,
            btc_change_dangerous_pct=7.0,
            eth_change_warning_pct=5.0,
            eth_change_dangerous_pct=10.0,
        ),
        volatility=VolatilityRiskConfig(
            range_24h_warning_pct=5.0,
            range_24h_dangerous_pct=10.0,
            volatility_ratio_warning=1.3,
            volatility_ratio_dangerous=2.0,
        ),
        system_integrity=SystemIntegrityRiskConfig(
            market_data_warning_age_seconds=180.0,  # 3 minutes
            market_data_dangerous_age_seconds=600.0,  # 10 minutes
        ),
    )


def get_aggressive_config() -> RiskScoringConfig:
    """
    Return a more aggressive configuration.
    
    Higher thresholds = later warnings = less caution.
    Use only in well-understood, stable market conditions.
    """
    return RiskScoringConfig(
        market=MarketRiskConfig(
            btc_change_warning_pct=8.0,
            btc_change_dangerous_pct=15.0,
            eth_change_warning_pct=10.0,
            eth_change_dangerous_pct=20.0,
        ),
        volatility=VolatilityRiskConfig(
            range_24h_warning_pct=12.0,
            range_24h_dangerous_pct=20.0,
            volatility_ratio_warning=2.0,
            volatility_ratio_dangerous=3.5,
        ),
    )
