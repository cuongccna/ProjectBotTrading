"""
Risk Scoring Engine - Assessors.

============================================================
PURPOSE
============================================================
Individual risk assessors for each dimension.

Each assessor:
1. Takes typed input data
2. Applies threshold-based logic
3. Returns a DimensionAssessment with state + explanation

============================================================
DESIGN PRINCIPLES
============================================================
- Pure functions: same input = same output
- No external state or side effects
- Threshold-based, deterministic logic
- Capital-agnostic (no dollar amounts)
- Comprehensive failure handling

============================================================
ASSESSMENT LOGIC PATTERN
============================================================
For each metric:
    if metric >= DANGEROUS_THRESHOLD:
        contribute DANGEROUS
    elif metric >= WARNING_THRESHOLD:
        contribute WARNING
    else:
        contribute SAFE

Final state = MAX(all metric states)
Reason = highest severity factor

============================================================
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional

from .types import (
    RiskState,
    RiskDimension,
    DimensionAssessment,
    MarketDataInput,
    LiquidityDataInput,
    VolatilityDataInput,
    SystemIntegrityDataInput,
    DataFreshnessStatus,
)
from .config import (
    MarketRiskConfig,
    LiquidityRiskConfig,
    VolatilityRiskConfig,
    SystemIntegrityRiskConfig,
)


# ============================================================
# BASE ASSESSOR
# ============================================================


class BaseRiskAssessor(ABC):
    """
    Abstract base class for risk assessors.
    
    Provides common patterns for threshold checking
    and reason aggregation.
    """
    
    @property
    @abstractmethod
    def dimension(self) -> RiskDimension:
        """Return the risk dimension this assessor handles."""
        pass
    
    def _check_threshold(
        self,
        value: float,
        warning_threshold: float,
        dangerous_threshold: float,
        comparison: str = "gte"  # gte, lte, abs_gte
    ) -> RiskState:
        """
        Check a value against thresholds.
        
        Args:
            value: The metric value to check
            warning_threshold: Threshold for WARNING state
            dangerous_threshold: Threshold for DANGEROUS state
            comparison: Type of comparison
                - "gte": value >= threshold (higher is worse)
                - "lte": value <= threshold (lower is worse)
                - "abs_gte": |value| >= threshold (magnitude matters)
        
        Returns:
            RiskState based on thresholds
        """
        if comparison == "gte":
            if value >= dangerous_threshold:
                return RiskState.DANGEROUS
            elif value >= warning_threshold:
                return RiskState.WARNING
            return RiskState.SAFE
            
        elif comparison == "lte":
            if value <= dangerous_threshold:
                return RiskState.DANGEROUS
            elif value <= warning_threshold:
                return RiskState.WARNING
            return RiskState.SAFE
            
        elif comparison == "abs_gte":
            abs_value = abs(value)
            if abs_value >= dangerous_threshold:
                return RiskState.DANGEROUS
            elif abs_value >= warning_threshold:
                return RiskState.WARNING
            return RiskState.SAFE
            
        return RiskState.SAFE
    
    def _aggregate_states(
        self,
        states: List[Tuple[RiskState, str, float]]
    ) -> Tuple[RiskState, str, List[str]]:
        """
        Aggregate multiple metric states into final assessment.
        
        Args:
            states: List of (state, reason, value) tuples
        
        Returns:
            (final_state, primary_reason, all_contributing_factors)
        """
        if not states:
            return RiskState.SAFE, "No metrics evaluated", []
        
        # Find highest severity
        max_state = max(states, key=lambda x: x[0].value)
        
        # Collect all reasons at that severity level
        contributing_factors = [
            f"{reason}: {value:.2f}" if isinstance(value, float) else f"{reason}: {value}"
            for state, reason, value in states
            if state.value >= RiskState.WARNING.value
        ]
        
        primary_reason = max_state[1] if max_state[0] != RiskState.SAFE else "All metrics within safe limits"
        
        return max_state[0], primary_reason, contributing_factors


# ============================================================
# MARKET RISK ASSESSOR
# ============================================================


class MarketRiskAssessor(BaseRiskAssessor):
    """
    Assess Market Risk based on broad market indicators.
    
    ============================================================
    METRICS EVALUATED
    ============================================================
    1. BTC 24h price change
    2. ETH 24h price change
    3. Market breadth (advancing vs declining)
    4. Extreme movement count (assets moving >10%)
    
    ============================================================
    ASSESSMENT LOGIC
    ============================================================
    - Check each metric against thresholds
    - Final state = MAX(all metric states)
    - If any input missing = use defaults or degrade gracefully
    
    ============================================================
    """
    
    def __init__(self, config: Optional[MarketRiskConfig] = None):
        self.config = config or MarketRiskConfig()
    
    @property
    def dimension(self) -> RiskDimension:
        return RiskDimension.MARKET
    
    def assess(self, data: MarketDataInput) -> DimensionAssessment:
        """
        Assess market risk from input data.
        
        Args:
            data: MarketDataInput with market indicators
        
        Returns:
            DimensionAssessment with state and explanation
        """
        states: List[Tuple[RiskState, str, float]] = []
        
        # --------------------------------------------------
        # 1. BTC 24h price change
        # --------------------------------------------------
        if data.btc_price_change_24h_pct is not None:
            btc_state = self._check_threshold(
                value=data.btc_price_change_24h_pct,
                warning_threshold=self.config.btc_change_warning_pct,
                dangerous_threshold=self.config.btc_change_dangerous_pct,
                comparison="abs_gte"
            )
            states.append((btc_state, "BTC 24h change", data.btc_price_change_24h_pct))
        
        # --------------------------------------------------
        # 2. ETH 24h price change
        # --------------------------------------------------
        if data.eth_price_change_24h_pct is not None:
            eth_state = self._check_threshold(
                value=data.eth_price_change_24h_pct,
                warning_threshold=self.config.eth_change_warning_pct,
                dangerous_threshold=self.config.eth_change_dangerous_pct,
                comparison="abs_gte"
            )
            states.append((eth_state, "ETH 24h change", data.eth_price_change_24h_pct))
        
        # --------------------------------------------------
        # 3. Market breadth (% declining)
        # --------------------------------------------------
        if data.declining_assets_pct is not None:
            breadth_state = self._check_threshold(
                value=data.declining_assets_pct,
                warning_threshold=self.config.breadth_warning_declining_pct,
                dangerous_threshold=self.config.breadth_dangerous_declining_pct,
                comparison="gte"
            )
            states.append((breadth_state, "Declining assets %", data.declining_assets_pct))
        
        # --------------------------------------------------
        # 4. Extreme movement count
        # --------------------------------------------------
        if data.extreme_move_count is not None:
            extreme_state = self._check_threshold(
                value=data.extreme_move_count,
                warning_threshold=self.config.extreme_move_warning_count,
                dangerous_threshold=self.config.extreme_move_dangerous_count,
                comparison="gte"
            )
            states.append((extreme_state, "Extreme moves", data.extreme_move_count))
        
        # --------------------------------------------------
        # Aggregate and build assessment
        # --------------------------------------------------
        if not states:
            # No metrics available - degrade gracefully
            return DimensionAssessment(
                dimension=self.dimension,
                state=RiskState.WARNING,
                reason="Insufficient market data for assessment",
                contributing_factors=["No market metrics available"],
                thresholds_used={
                    "btc_warning": self.config.btc_change_warning_pct,
                    "btc_dangerous": self.config.btc_change_dangerous_pct,
                }
            )
        
        final_state, primary_reason, factors = self._aggregate_states(states)
        
        return DimensionAssessment(
            dimension=self.dimension,
            state=final_state,
            reason=self._format_reason(final_state, primary_reason),
            contributing_factors=factors if factors else ["All metrics within safe limits"],
            thresholds_used={
                "btc_warning": self.config.btc_change_warning_pct,
                "btc_dangerous": self.config.btc_change_dangerous_pct,
                "eth_warning": self.config.eth_change_warning_pct,
                "eth_dangerous": self.config.eth_change_dangerous_pct,
                "breadth_warning": self.config.breadth_warning_declining_pct,
                "breadth_dangerous": self.config.breadth_dangerous_declining_pct,
            }
        )
    
    def _format_reason(self, state: RiskState, primary_reason: str) -> str:
        """Format the reason string based on state."""
        if state == RiskState.SAFE:
            return "Market conditions stable"
        elif state == RiskState.WARNING:
            return f"Elevated market stress: {primary_reason}"
        else:
            return f"Severe market stress: {primary_reason}"


# ============================================================
# LIQUIDITY RISK ASSESSOR
# ============================================================


class LiquidityRiskAssessor(BaseRiskAssessor):
    """
    Assess Liquidity Risk based on volume and spread metrics.
    
    ============================================================
    METRICS EVALUATED
    ============================================================
    1. Volume ratio (current/average)
    2. Bid-ask spread percentage
    3. Order book depth score
    
    ============================================================
    ASSESSMENT LOGIC
    ============================================================
    - Low volume = harder to execute
    - Wide spreads = higher slippage cost
    - Thin depth = price impact risk
    
    ============================================================
    """
    
    def __init__(self, config: Optional[LiquidityRiskConfig] = None):
        self.config = config or LiquidityRiskConfig()
    
    @property
    def dimension(self) -> RiskDimension:
        return RiskDimension.LIQUIDITY
    
    def assess(self, data: LiquidityDataInput) -> DimensionAssessment:
        """
        Assess liquidity risk from input data.
        
        Args:
            data: LiquidityDataInput with liquidity metrics
        
        Returns:
            DimensionAssessment with state and explanation
        """
        states: List[Tuple[RiskState, str, float]] = []
        
        # --------------------------------------------------
        # 1. Volume ratio (lower = worse)
        # --------------------------------------------------
        if data.volume_ratio_vs_average is not None:
            volume_state = self._check_threshold(
                value=data.volume_ratio_vs_average,
                warning_threshold=self.config.volume_ratio_warning,
                dangerous_threshold=self.config.volume_ratio_dangerous,
                comparison="lte"
            )
            states.append((volume_state, "Volume ratio", data.volume_ratio_vs_average))
        
        # --------------------------------------------------
        # 2. Bid-ask spread (higher = worse)
        # --------------------------------------------------
        if data.bid_ask_spread_pct is not None:
            spread_state = self._check_threshold(
                value=data.bid_ask_spread_pct,
                warning_threshold=self.config.spread_warning_pct,
                dangerous_threshold=self.config.spread_dangerous_pct,
                comparison="gte"
            )
            states.append((spread_state, "Bid-ask spread", data.bid_ask_spread_pct))
        
        # --------------------------------------------------
        # 3. Order book depth (lower = worse)
        # --------------------------------------------------
        if data.order_book_depth_score is not None:
            depth_state = self._check_threshold(
                value=data.order_book_depth_score,
                warning_threshold=self.config.depth_warning,
                dangerous_threshold=self.config.depth_dangerous,
                comparison="lte"
            )
            states.append((depth_state, "Order book depth", data.order_book_depth_score))
        
        # --------------------------------------------------
        # Aggregate and build assessment
        # --------------------------------------------------
        if not states:
            return DimensionAssessment(
                dimension=self.dimension,
                state=RiskState.WARNING,
                reason="Insufficient liquidity data for assessment",
                contributing_factors=["No liquidity metrics available"],
                thresholds_used={
                    "volume_warning": self.config.volume_ratio_warning,
                    "volume_dangerous": self.config.volume_ratio_dangerous,
                }
            )
        
        final_state, primary_reason, factors = self._aggregate_states(states)
        
        return DimensionAssessment(
            dimension=self.dimension,
            state=final_state,
            reason=self._format_reason(final_state, primary_reason),
            contributing_factors=factors if factors else ["Liquidity metrics within safe limits"],
            thresholds_used={
                "volume_warning": self.config.volume_ratio_warning,
                "volume_dangerous": self.config.volume_ratio_dangerous,
                "spread_warning": self.config.spread_warning_pct,
                "spread_dangerous": self.config.spread_dangerous_pct,
                "depth_warning": self.config.depth_warning,
                "depth_dangerous": self.config.depth_dangerous,
            }
        )
    
    def _format_reason(self, state: RiskState, primary_reason: str) -> str:
        """Format the reason string based on state."""
        if state == RiskState.SAFE:
            return "Liquidity conditions adequate"
        elif state == RiskState.WARNING:
            return f"Reduced liquidity: {primary_reason}"
        else:
            return f"Critical liquidity shortage: {primary_reason}"


# ============================================================
# VOLATILITY RISK ASSESSOR
# ============================================================


class VolatilityRiskAssessor(BaseRiskAssessor):
    """
    Assess Volatility Risk based on price range and movement metrics.
    
    ============================================================
    METRICS EVALUATED
    ============================================================
    1. Price range (1h, 4h, 24h)
    2. Volatility ratio vs historical
    3. Abnormal candle count
    
    ============================================================
    ASSESSMENT LOGIC
    ============================================================
    - High volatility = unpredictable moves
    - Wide ranges = large price swings
    - Abnormal candles = potential manipulation or news
    
    ============================================================
    """
    
    def __init__(self, config: Optional[VolatilityRiskConfig] = None):
        self.config = config or VolatilityRiskConfig()
    
    @property
    def dimension(self) -> RiskDimension:
        return RiskDimension.VOLATILITY
    
    def assess(self, data: VolatilityDataInput) -> DimensionAssessment:
        """
        Assess volatility risk from input data.
        
        Args:
            data: VolatilityDataInput with volatility metrics
        
        Returns:
            DimensionAssessment with state and explanation
        """
        states: List[Tuple[RiskState, str, float]] = []
        
        # --------------------------------------------------
        # 1. 24h price range
        # --------------------------------------------------
        if data.price_range_24h_pct is not None:
            range_24h_state = self._check_threshold(
                value=data.price_range_24h_pct,
                warning_threshold=self.config.range_24h_warning_pct,
                dangerous_threshold=self.config.range_24h_dangerous_pct,
                comparison="gte"
            )
            states.append((range_24h_state, "24h price range", data.price_range_24h_pct))
        
        # --------------------------------------------------
        # 2. 4h price range
        # --------------------------------------------------
        if data.price_range_4h_pct is not None:
            range_4h_state = self._check_threshold(
                value=data.price_range_4h_pct,
                warning_threshold=self.config.range_4h_warning_pct,
                dangerous_threshold=self.config.range_4h_dangerous_pct,
                comparison="gte"
            )
            states.append((range_4h_state, "4h price range", data.price_range_4h_pct))
        
        # --------------------------------------------------
        # 3. 1h price range
        # --------------------------------------------------
        if data.price_range_1h_pct is not None:
            range_1h_state = self._check_threshold(
                value=data.price_range_1h_pct,
                warning_threshold=self.config.range_1h_warning_pct,
                dangerous_threshold=self.config.range_1h_dangerous_pct,
                comparison="gte"
            )
            states.append((range_1h_state, "1h price range", data.price_range_1h_pct))
        
        # --------------------------------------------------
        # 4. Volatility ratio vs baseline
        # --------------------------------------------------
        if data.volatility_vs_baseline_ratio is not None:
            vol_ratio_state = self._check_threshold(
                value=data.volatility_vs_baseline_ratio,
                warning_threshold=self.config.volatility_ratio_warning,
                dangerous_threshold=self.config.volatility_ratio_dangerous,
                comparison="gte"
            )
            states.append((vol_ratio_state, "Volatility ratio", data.volatility_vs_baseline_ratio))
        
        # --------------------------------------------------
        # 5. Abnormal candle count
        # --------------------------------------------------
        if data.abnormal_candle_count_24h is not None:
            abnormal_state = self._check_threshold(
                value=data.abnormal_candle_count_24h,
                warning_threshold=self.config.abnormal_candle_warning_count,
                dangerous_threshold=self.config.abnormal_candle_dangerous_count,
                comparison="gte"
            )
            states.append((abnormal_state, "Abnormal candles", data.abnormal_candle_count_24h))
        
        # --------------------------------------------------
        # Aggregate and build assessment
        # --------------------------------------------------
        if not states:
            return DimensionAssessment(
                dimension=self.dimension,
                state=RiskState.WARNING,
                reason="Insufficient volatility data for assessment",
                contributing_factors=["No volatility metrics available"],
                thresholds_used={
                    "range_24h_warning": self.config.range_24h_warning_pct,
                    "range_24h_dangerous": self.config.range_24h_dangerous_pct,
                }
            )
        
        final_state, primary_reason, factors = self._aggregate_states(states)
        
        return DimensionAssessment(
            dimension=self.dimension,
            state=final_state,
            reason=self._format_reason(final_state, primary_reason),
            contributing_factors=factors if factors else ["Volatility within normal range"],
            thresholds_used={
                "range_24h_warning": self.config.range_24h_warning_pct,
                "range_24h_dangerous": self.config.range_24h_dangerous_pct,
                "range_4h_warning": self.config.range_4h_warning_pct,
                "range_4h_dangerous": self.config.range_4h_dangerous_pct,
                "range_1h_warning": self.config.range_1h_warning_pct,
                "range_1h_dangerous": self.config.range_1h_dangerous_pct,
                "volatility_ratio_warning": self.config.volatility_ratio_warning,
                "volatility_ratio_dangerous": self.config.volatility_ratio_dangerous,
            }
        )
    
    def _format_reason(self, state: RiskState, primary_reason: str) -> str:
        """Format the reason string based on state."""
        if state == RiskState.SAFE:
            return "Volatility within normal parameters"
        elif state == RiskState.WARNING:
            return f"Elevated volatility: {primary_reason}"
        else:
            return f"Extreme volatility detected: {primary_reason}"


# ============================================================
# SYSTEM INTEGRITY RISK ASSESSOR
# ============================================================


class SystemIntegrityRiskAssessor(BaseRiskAssessor):
    """
    Assess System Integrity Risk based on data pipeline health.
    
    ============================================================
    METRICS EVALUATED
    ============================================================
    1. Data freshness (market, news, on-chain)
    2. Pipeline success rates
    3. API latency
    4. Error counts
    
    ============================================================
    FAIL-SAFE BEHAVIOR
    ============================================================
    If ANY data status is MISSING or INVALID:
    - Immediately return DANGEROUS (2)
    - This is non-negotiable for system safety
    
    ============================================================
    """
    
    def __init__(self, config: Optional[SystemIntegrityRiskConfig] = None):
        self.config = config or SystemIntegrityRiskConfig()
    
    @property
    def dimension(self) -> RiskDimension:
        return RiskDimension.SYSTEM_INTEGRITY
    
    def assess(self, data: SystemIntegrityDataInput) -> DimensionAssessment:
        """
        Assess system integrity risk from input data.
        
        FAIL-SAFE: If data is missing or invalid, return DANGEROUS.
        
        Args:
            data: SystemIntegrityDataInput with system health metrics
        
        Returns:
            DimensionAssessment with state and explanation
        """
        # --------------------------------------------------
        # FAIL-SAFE CHECK: Missing/Invalid data = DANGEROUS
        # --------------------------------------------------
        missing_data_sources = []
        
        if data.market_data_status in (DataFreshnessStatus.MISSING, DataFreshnessStatus.INVALID):
            missing_data_sources.append("Market data")
        
        if data.news_data_status in (DataFreshnessStatus.MISSING, DataFreshnessStatus.INVALID):
            missing_data_sources.append("News data")
        
        if data.onchain_data_status in (DataFreshnessStatus.MISSING, DataFreshnessStatus.INVALID):
            missing_data_sources.append("On-chain data")
        
        if data.feature_pipeline_status in (DataFreshnessStatus.MISSING, DataFreshnessStatus.INVALID):
            missing_data_sources.append("Feature pipeline")
        
        if missing_data_sources:
            return DimensionAssessment(
                dimension=self.dimension,
                state=RiskState.DANGEROUS,
                reason=f"Critical data unavailable: {', '.join(missing_data_sources)}",
                contributing_factors=[f"{src} - MISSING/INVALID" for src in missing_data_sources],
                thresholds_used={"fail_safe": "MISSING/INVALID data = DANGEROUS"}
            )
        
        # --------------------------------------------------
        # Normal assessment: Check thresholds
        # --------------------------------------------------
        states: List[Tuple[RiskState, str, float]] = []
        
        # Market data age
        if data.market_data_age_seconds is not None:
            market_age_state = self._check_threshold(
                value=data.market_data_age_seconds,
                warning_threshold=self.config.market_data_warning_age_seconds,
                dangerous_threshold=self.config.market_data_dangerous_age_seconds,
                comparison="gte"
            )
            states.append((market_age_state, "Market data age (s)", data.market_data_age_seconds))
        
        # News data age
        if data.news_data_age_seconds is not None:
            news_age_state = self._check_threshold(
                value=data.news_data_age_seconds,
                warning_threshold=self.config.news_data_warning_age_seconds,
                dangerous_threshold=self.config.news_data_dangerous_age_seconds,
                comparison="gte"
            )
            states.append((news_age_state, "News data age (s)", data.news_data_age_seconds))
        
        # On-chain data age
        if data.onchain_data_age_seconds is not None:
            onchain_age_state = self._check_threshold(
                value=data.onchain_data_age_seconds,
                warning_threshold=self.config.onchain_data_warning_age_seconds,
                dangerous_threshold=self.config.onchain_data_dangerous_age_seconds,
                comparison="gte"
            )
            states.append((onchain_age_state, "On-chain data age (s)", data.onchain_data_age_seconds))
        
        # Pipeline success rate (lower = worse)
        if data.pipeline_success_rate is not None:
            pipeline_state = self._check_threshold(
                value=data.pipeline_success_rate,
                warning_threshold=self.config.pipeline_warning_success_rate,
                dangerous_threshold=self.config.pipeline_dangerous_success_rate,
                comparison="lte"
            )
            states.append((pipeline_state, "Pipeline success rate", data.pipeline_success_rate))
        
        # API latency
        if data.api_latency_ms is not None:
            latency_state = self._check_threshold(
                value=data.api_latency_ms,
                warning_threshold=self.config.api_latency_warning_ms,
                dangerous_threshold=self.config.api_latency_dangerous_ms,
                comparison="gte"
            )
            states.append((latency_state, "API latency (ms)", data.api_latency_ms))
        
        # Error count
        if data.error_count_last_hour is not None:
            error_state = self._check_threshold(
                value=data.error_count_last_hour,
                warning_threshold=self.config.error_warning_count,
                dangerous_threshold=self.config.error_dangerous_count,
                comparison="gte"
            )
            states.append((error_state, "Errors (last hour)", data.error_count_last_hour))
        
        # Critical error count
        if data.critical_error_count_last_hour is not None:
            critical_state = self._check_threshold(
                value=data.critical_error_count_last_hour,
                warning_threshold=self.config.critical_error_warning_count,
                dangerous_threshold=self.config.critical_error_dangerous_count,
                comparison="gte"
            )
            states.append((critical_state, "Critical errors (last hour)", data.critical_error_count_last_hour))
        
        # --------------------------------------------------
        # Aggregate and build assessment
        # --------------------------------------------------
        if not states:
            # No metrics but data wasn't marked as missing = WARNING
            return DimensionAssessment(
                dimension=self.dimension,
                state=RiskState.WARNING,
                reason="Limited system health metrics available",
                contributing_factors=["Incomplete system monitoring"],
                thresholds_used={}
            )
        
        final_state, primary_reason, factors = self._aggregate_states(states)
        
        return DimensionAssessment(
            dimension=self.dimension,
            state=final_state,
            reason=self._format_reason(final_state, primary_reason),
            contributing_factors=factors if factors else ["All systems operational"],
            thresholds_used={
                "market_data_warning_age": self.config.market_data_warning_age_seconds,
                "market_data_dangerous_age": self.config.market_data_dangerous_age_seconds,
                "pipeline_warning_rate": self.config.pipeline_warning_success_rate,
                "pipeline_dangerous_rate": self.config.pipeline_dangerous_success_rate,
                "api_latency_warning": self.config.api_latency_warning_ms,
                "api_latency_dangerous": self.config.api_latency_dangerous_ms,
            }
        )
    
    def _format_reason(self, state: RiskState, primary_reason: str) -> str:
        """Format the reason string based on state."""
        if state == RiskState.SAFE:
            return "All systems operational"
        elif state == RiskState.WARNING:
            return f"System health degraded: {primary_reason}"
        else:
            return f"Critical system issue: {primary_reason}"
