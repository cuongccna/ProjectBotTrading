"""
Strategy Engine - Main Orchestrator.

============================================================
PURPOSE
============================================================
The StrategyEngine is the main entry point for trade intent generation.

It orchestrates:
1. Input validation
2. Signal generation from each source
3. Signal combination and alignment checking
4. Confidence calculation
5. Trade intent or NO_TRADE output

============================================================
DESIGN PRINCIPLES
============================================================
- Hypothesis generator, not decision maker
- Capital-agnostic (no position sizing)
- Deterministic and rule-based
- Fewer, higher-quality intents over frequency
- No single signal source is sufficient alone

============================================================
CORE RULES
============================================================
1. Market structure + Volume must align for any intent
2. Sentiment modifies but NEVER creates intent
3. Risk level CRITICAL blocks all intents
4. Missing data = NO_TRADE (no partial signals)

============================================================
USAGE
============================================================
    from strategy_engine import StrategyEngine, StrategyInput
    
    engine = StrategyEngine()
    
    input_data = StrategyInput(
        market_structure=MarketStructureInput(...),
        volume_flow=VolumeFlowInput(...),
        sentiment=SentimentInput(...),
        environment=EnvironmentalContext(...),
    )
    
    result = engine.evaluate(input_data)
    
    if result.has_intent:
        print(f"Intent: {result.trade_intent.direction}")
    else:
        print(f"No trade: {result.no_trade.reason}")

============================================================
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List, Dict, Any
from uuid import uuid4
import time

from .types import (
    TradeDirection,
    ConfidenceLevel,
    SignalStrength,
    SignalOutput,
    SentimentModifierOutput,
    StrategyInput,
    StrategyEngineOutput,
    TradeIntent,
    NoTradeResult,
    NoTradeReason,
    StrategyReasonCode,
    MarketContextSnapshot,
    MarketRegime,
    InsufficientDataError,
    StrategyEngineError,
    # New signal types
    SignalType,
    StrategySignal,
    SignalBundle,
)
from .config import StrategyEngineConfig
from .signals import (
    MarketStructureSignalGenerator,
    VolumeFlowSignalGenerator,
    SentimentModifierGenerator,
)

# Import ProcessedMarketState for typed signals
from data_processing.contracts import (
    ProcessedMarketState,
    ProcessedMarketStateBundle,
    TrendState,
    VolatilityLevel,
)


class StrategyEngine:
    """
    Main orchestrator for the Strategy Engine.
    
    ============================================================
    RESPONSIBILITIES
    ============================================================
    1. Validate input data
    2. Generate signals from each source
    3. Check signal alignment
    4. Calculate confidence
    5. Build trade intent or NO_TRADE result
    
    ============================================================
    WHAT IT DOES NOT DO
    ============================================================
    - Execute trades
    - Manage risk budgets or position sizing
    - Override risk controls
    - React to account performance
    
    ============================================================
    """
    
    def __init__(
        self,
        config: Optional[StrategyEngineConfig] = None,
    ):
        """
        Initialize the Strategy Engine.
        
        Args:
            config: Engine configuration. Uses defaults if not provided.
        """
        self.config = config or StrategyEngineConfig()
        
        # Initialize signal generators
        self._market_structure_gen = MarketStructureSignalGenerator(
            config=self.config.market_structure
        )
        self._volume_flow_gen = VolumeFlowSignalGenerator(
            config=self.config.volume_flow
        )
        self._sentiment_gen = SentimentModifierGenerator(
            config=self.config.sentiment
        )
    
    def evaluate(self, input_data: StrategyInput) -> StrategyEngineOutput:
        """
        Evaluate market conditions and generate trade intent.
        
        This is the main entry point. It:
        1. Validates input data
        2. Checks environmental risk
        3. Generates signals
        4. Checks alignment
        5. Calculates confidence
        6. Returns intent or NO_TRADE
        
        Args:
            input_data: Complete input data bundle
        
        Returns:
            StrategyEngineOutput with intent or no_trade
        """
        start_time = time.time()
        evaluation_id = str(uuid4())[:8]
        
        try:
            # --------------------------------------------------
            # Step 1: Validate input data
            # --------------------------------------------------
            validation_result = self._validate_input(input_data)
            if validation_result is not None:
                return self._build_output(
                    no_trade=validation_result,
                    evaluation_id=evaluation_id,
                    start_time=start_time,
                )
            
            # --------------------------------------------------
            # Step 2: Check environmental risk
            # --------------------------------------------------
            risk_result = self._check_environmental_risk(input_data)
            if risk_result is not None:
                return self._build_output(
                    no_trade=risk_result,
                    evaluation_id=evaluation_id,
                    start_time=start_time,
                )
            
            # --------------------------------------------------
            # Step 3: Generate signals
            # --------------------------------------------------
            market_signal = self._market_structure_gen.generate(
                input_data.market_structure
            )
            
            volume_signal = self._volume_flow_gen.generate(
                input_data.volume_flow
            )
            
            # --------------------------------------------------
            # Step 4: Check signal alignment
            # --------------------------------------------------
            alignment_result = self._check_signal_alignment(
                market_signal=market_signal,
                volume_signal=volume_signal,
                input_data=input_data,
            )
            
            if alignment_result is not None:
                return self._build_output(
                    no_trade=alignment_result,
                    evaluation_id=evaluation_id,
                    start_time=start_time,
                )
            
            # --------------------------------------------------
            # Step 5: Determine direction (they're aligned at this point)
            # --------------------------------------------------
            direction = self._determine_direction(market_signal, volume_signal)
            
            # --------------------------------------------------
            # Step 6: Generate sentiment modifier
            # --------------------------------------------------
            sentiment_modifier = self._sentiment_gen.generate(
                input_data.sentiment,
                proposed_direction=direction,
            )
            
            # Check if sentiment suggests delay
            if sentiment_modifier.effect == "DELAY":
                no_trade = NoTradeResult(
                    reason=NoTradeReason.SENTIMENT_OVERRIDE,
                    explanation=sentiment_modifier.reason,
                    market_context=self._build_market_context(input_data),
                    market_structure_signal=market_signal,
                    volume_flow_signal=volume_signal,
                    sentiment_modifier=sentiment_modifier,
                    symbol=input_data.symbol,
                    exchange=input_data.exchange,
                    timeframe=input_data.primary_timeframe,
                    timestamp=input_data.timestamp,
                )
                return self._build_output(
                    no_trade=no_trade,
                    evaluation_id=evaluation_id,
                    start_time=start_time,
                )
            
            # --------------------------------------------------
            # Step 7: Calculate confidence
            # --------------------------------------------------
            confidence = self._calculate_confidence(
                market_signal=market_signal,
                volume_signal=volume_signal,
                sentiment_modifier=sentiment_modifier,
                environment=input_data.environment,
            )
            
            # --------------------------------------------------
            # Step 8: Determine reason code
            # --------------------------------------------------
            reason_code = self._determine_reason_code(
                direction=direction,
                market_signal=market_signal,
                input_data=input_data,
            )
            
            # --------------------------------------------------
            # Step 9: Build trade intent
            # --------------------------------------------------
            intent = TradeIntent(
                direction=direction,
                confidence=confidence,
                reason_code=reason_code,
                market_context=self._build_market_context(input_data),
                symbol=input_data.symbol,
                exchange=input_data.exchange,
                timeframe=input_data.primary_timeframe,
                timestamp=input_data.timestamp,
                market_structure_signal=market_signal,
                volume_flow_signal=volume_signal,
                sentiment_modifier=sentiment_modifier,
                expires_at=input_data.timestamp + timedelta(
                    minutes=self.config.lifecycle.default_expiration_minutes
                ),
            )
            
            return self._build_output(
                trade_intent=intent,
                evaluation_id=evaluation_id,
                start_time=start_time,
            )
            
        except InsufficientDataError as e:
            no_trade = NoTradeResult(
                reason=NoTradeReason.MISSING_INPUT_DATA,
                explanation=str(e),
                symbol=input_data.symbol,
                exchange=input_data.exchange,
                timeframe=input_data.primary_timeframe,
                timestamp=input_data.timestamp,
            )
            return self._build_output(
                no_trade=no_trade,
                evaluation_id=evaluation_id,
                start_time=start_time,
            )
        except Exception as e:
            raise StrategyEngineError(f"Evaluation failed: {str(e)}") from e
    
    def _validate_input(self, input_data: StrategyInput) -> Optional[NoTradeResult]:
        """
        Validate input data has minimum requirements.
        
        Returns NoTradeResult if validation fails, None if valid.
        """
        if input_data is None:
            return NoTradeResult(
                reason=NoTradeReason.MISSING_INPUT_DATA,
                explanation="Input data is None",
                timestamp=datetime.utcnow(),
            )
        
        if not input_data.has_minimum_data:
            return NoTradeResult(
                reason=NoTradeReason.MISSING_INPUT_DATA,
                explanation="Insufficient input data for evaluation",
                symbol=input_data.symbol,
                exchange=input_data.exchange,
                timeframe=input_data.primary_timeframe,
                timestamp=input_data.timestamp,
            )
        
        return None
    
    def _check_environmental_risk(
        self,
        input_data: StrategyInput
    ) -> Optional[NoTradeResult]:
        """
        Check if environmental risk blocks trading.
        
        Returns NoTradeResult if blocked, None if OK.
        """
        env = input_data.environment
        
        # CRITICAL risk blocks all intents
        if self.config.combination.block_on_critical and env.is_critical:
            return NoTradeResult(
                reason=NoTradeReason.RISK_LEVEL_CRITICAL,
                explanation=f"Risk level CRITICAL (score: {env.risk_score_total}/8)",
                market_context=self._build_market_context(input_data),
                symbol=input_data.symbol,
                exchange=input_data.exchange,
                timeframe=input_data.primary_timeframe,
                timestamp=input_data.timestamp,
            )
        
        # Extreme volatility check
        if env.volatility_regime == "EXTREME":
            return NoTradeResult(
                reason=NoTradeReason.VOLATILITY_EXTREME,
                explanation="Extreme volatility regime detected",
                market_context=self._build_market_context(input_data),
                symbol=input_data.symbol,
                exchange=input_data.exchange,
                timeframe=input_data.primary_timeframe,
                timestamp=input_data.timestamp,
            )
        
        return None
    
    def _check_signal_alignment(
        self,
        market_signal: SignalOutput,
        volume_signal: SignalOutput,
        input_data: StrategyInput,
    ) -> Optional[NoTradeResult]:
        """
        Check if market structure and volume signals align.
        
        Returns NoTradeResult if not aligned, None if aligned.
        """
        config = self.config.combination
        
        # --------------------------------------------------
        # Check minimum strength requirements
        # --------------------------------------------------
        if market_signal.strength.value < config.min_structure_strength:
            return NoTradeResult(
                reason=NoTradeReason.SIGNALS_TOO_WEAK,
                explanation=f"Market structure signal too weak ({market_signal.strength.name})",
                market_context=self._build_market_context(input_data),
                market_structure_signal=market_signal,
                volume_flow_signal=volume_signal,
                symbol=input_data.symbol,
                exchange=input_data.exchange,
                timeframe=input_data.primary_timeframe,
                timestamp=input_data.timestamp,
            )
        
        if volume_signal.strength.value < config.min_volume_strength:
            # Allow neutral volume if configured
            if not (config.allow_neutral_volume and 
                    volume_signal.direction == TradeDirection.NEUTRAL):
                return NoTradeResult(
                    reason=NoTradeReason.VOLUME_INSUFFICIENT,
                    explanation=f"Volume signal too weak ({volume_signal.strength.name})",
                    market_context=self._build_market_context(input_data),
                    market_structure_signal=market_signal,
                    volume_flow_signal=volume_signal,
                    symbol=input_data.symbol,
                    exchange=input_data.exchange,
                    timeframe=input_data.primary_timeframe,
                    timestamp=input_data.timestamp,
                )
        
        # --------------------------------------------------
        # Check direction alignment
        # --------------------------------------------------
        if config.require_direction_alignment:
            # Both neutral = no signal
            if (market_signal.direction == TradeDirection.NEUTRAL and 
                volume_signal.direction == TradeDirection.NEUTRAL):
                return NoTradeResult(
                    reason=NoTradeReason.MARKET_STRUCTURE_UNCLEAR,
                    explanation="Both signals neutral, no directional bias",
                    market_context=self._build_market_context(input_data),
                    market_structure_signal=market_signal,
                    volume_flow_signal=volume_signal,
                    symbol=input_data.symbol,
                    exchange=input_data.exchange,
                    timeframe=input_data.primary_timeframe,
                    timestamp=input_data.timestamp,
                )
            
            # Conflicting directions (both non-neutral but opposite)
            if (market_signal.direction != TradeDirection.NEUTRAL and
                volume_signal.direction != TradeDirection.NEUTRAL and
                market_signal.direction != volume_signal.direction):
                return NoTradeResult(
                    reason=NoTradeReason.SIGNALS_CONFLICTING,
                    explanation=f"Signals conflict: Structure={market_signal.direction.value}, Volume={volume_signal.direction.value}",
                    market_context=self._build_market_context(input_data),
                    market_structure_signal=market_signal,
                    volume_flow_signal=volume_signal,
                    symbol=input_data.symbol,
                    exchange=input_data.exchange,
                    timeframe=input_data.primary_timeframe,
                    timestamp=input_data.timestamp,
                )
        
        return None
    
    def _determine_direction(
        self,
        market_signal: SignalOutput,
        volume_signal: SignalOutput,
    ) -> TradeDirection:
        """
        Determine final direction from aligned signals.
        
        At this point, signals are already validated as aligned.
        """
        # Prefer non-neutral signal
        if market_signal.direction != TradeDirection.NEUTRAL:
            return market_signal.direction
        
        if volume_signal.direction != TradeDirection.NEUTRAL:
            return volume_signal.direction
        
        # Shouldn't reach here if alignment check passed
        return TradeDirection.NEUTRAL
    
    def _calculate_confidence(
        self,
        market_signal: SignalOutput,
        volume_signal: SignalOutput,
        sentiment_modifier: SentimentModifierOutput,
        environment,
    ) -> ConfidenceLevel:
        """
        Calculate confidence level from signals and modifiers.
        
        Uses weighted combination of signal strengths.
        """
        config = self.config.combination
        
        # --------------------------------------------------
        # Base score from signal strengths
        # --------------------------------------------------
        # Normalize strength to 0-1 (NONE=0, WEAK=0.33, MODERATE=0.66, STRONG=1)
        structure_score = market_signal.strength.value / 3.0
        volume_score = volume_signal.strength.value / 3.0
        
        # Weighted combination
        base_score = (
            structure_score * config.structure_weight +
            volume_score * config.volume_weight
        )
        
        # --------------------------------------------------
        # Apply sentiment modifier
        # --------------------------------------------------
        sentiment_adjustment = 0.0
        
        if sentiment_modifier.effect == "STRENGTHEN":
            adjustment = sentiment_modifier.magnitude * config.max_sentiment_boost
            sentiment_adjustment = adjustment
        elif sentiment_modifier.effect == "WEAKEN":
            adjustment = sentiment_modifier.magnitude * config.max_sentiment_reduction
            sentiment_adjustment = -adjustment
        
        final_score = base_score + sentiment_adjustment
        
        # --------------------------------------------------
        # Apply risk level adjustment
        # --------------------------------------------------
        if config.reduce_confidence_on_high and environment.risk_level == "HIGH":
            final_score -= config.high_risk_confidence_reduction
        
        # --------------------------------------------------
        # Clamp and convert to level
        # --------------------------------------------------
        final_score = max(0.0, min(1.0, final_score))
        
        return ConfidenceLevel.from_score(final_score)
    
    def _determine_reason_code(
        self,
        direction: TradeDirection,
        market_signal: SignalOutput,
        input_data: StrategyInput,
    ) -> StrategyReasonCode:
        """
        Determine the strategy reason code.
        
        Based on direction and market context.
        """
        # Check for breakout
        if input_data.market_structure.breakout_detected:
            if direction == TradeDirection.LONG:
                return StrategyReasonCode.BREAKOUT_LONG
            else:
                return StrategyReasonCode.BREAKOUT_SHORT
        
        # Check for S/R trades
        if input_data.market_structure.near_support and direction == TradeDirection.LONG:
            return StrategyReasonCode.RANGE_SUPPORT_LONG
        
        if input_data.market_structure.near_resistance and direction == TradeDirection.SHORT:
            return StrategyReasonCode.RANGE_RESISTANCE_SHORT
        
        # Check for volume breakout
        volume_ratio = input_data.volume_flow.volume_ratio_vs_average or 1.0
        if volume_ratio >= self.config.volume_flow.volume_spike_threshold:
            if direction == TradeDirection.LONG:
                return StrategyReasonCode.VOLUME_BREAKOUT_LONG
            else:
                return StrategyReasonCode.VOLUME_BREAKOUT_SHORT
        
        # Default: Trend continuation
        if direction == TradeDirection.LONG:
            return StrategyReasonCode.TREND_CONTINUATION_LONG
        else:
            return StrategyReasonCode.TREND_CONTINUATION_SHORT
    
    def _build_market_context(self, input_data: StrategyInput) -> MarketContextSnapshot:
        """
        Build market context snapshot from input data.
        """
        ms = input_data.market_structure
        vf = input_data.volume_flow
        se = input_data.sentiment
        env = input_data.environment
        
        # Determine trend direction string
        trend_1h = ms.trend_direction_1h or 0
        if trend_1h > 0.3:
            trend_dir = "UP"
        elif trend_1h < -0.3:
            trend_dir = "DOWN"
        else:
            trend_dir = "NEUTRAL"
        
        # Determine volume bias
        buy_ratio = vf.buy_volume_ratio or 0.5
        if buy_ratio >= 0.55:
            volume_bias = "BUY"
        elif buy_ratio <= 0.45:
            volume_bias = "SELL"
        else:
            volume_bias = "NEUTRAL"
        
        return MarketContextSnapshot(
            price=ms.current_price,
            market_regime=env.market_regime,
            volatility_regime=env.volatility_regime,
            trend_direction=trend_dir,
            trend_strength=ms.trend_strength,
            volume_ratio=vf.volume_ratio_vs_average,
            volume_bias=volume_bias,
            sentiment_regime=se.sentiment_regime,
            sentiment_score=se.sentiment_score,
            risk_level=env.risk_level,
            risk_score=env.risk_score_total,
            timestamp=input_data.timestamp,
        )
    
    def _build_output(
        self,
        trade_intent: Optional[TradeIntent] = None,
        no_trade: Optional[NoTradeResult] = None,
        evaluation_id: str = "",
        start_time: float = 0,
    ) -> StrategyEngineOutput:
        """
        Build the final output.
        """
        duration_ms = (time.time() - start_time) * 1000 if start_time else None
        
        return StrategyEngineOutput(
            trade_intent=trade_intent,
            no_trade=no_trade,
            evaluation_id=evaluation_id,
            engine_version=self.config.engine_version,
            evaluation_duration_ms=duration_ms,
        )
    
    def get_config(self) -> StrategyEngineConfig:
        """Return the current engine configuration."""
        return self.config
    
    # ============================================================
    # SIGNAL GENERATION FROM PROCESSED MARKET STATE
    # ============================================================
    
    def generate_signal(
        self,
        market_state: ProcessedMarketState,
        risk_allows_trading: bool = True,
    ) -> StrategySignal:
        """
        Generate a trading signal from ProcessedMarketState.
        
        ============================================================
        PURPOSE
        ============================================================
        This is the primary method for generating signals from the
        canonical ProcessedMarketState contract. It does NOT:
        - Execute trades
        - Bypass risk controls
        - Read from raw MarketData
        
        ============================================================
        PROCESS
        ============================================================
        1. Validate market state
        2. Check risk constraints (respects risk module decision)
        3. Classify signal type from trend/volatility
        4. Determine direction
        5. Calculate confidence score
        6. Package supporting features
        
        Args:
            market_state: Processed market state from ProcessingPipelineModule
            risk_allows_trading: Whether risk module allows trading
                                 (MUST be checked by caller, not bypassed)
        
        Returns:
            StrategySignal with signal_type, direction, confidence_score,
            and supporting_features
        """
        start_time = time.time()
        
        # --------------------------------------------------
        # Step 1: Validate market state
        # --------------------------------------------------
        if market_state is None:
            return StrategySignal.no_signal(
                reason="Market state is None - cannot generate signal"
            )
        
        symbol = market_state.symbol
        timeframe = market_state.timeframe
        exchange = market_state.exchange
        
        # --------------------------------------------------
        # Step 2: Check risk constraints (NEVER bypass)
        # --------------------------------------------------
        if not risk_allows_trading:
            return StrategySignal(
                signal_type=SignalType.NONE,
                direction=TradeDirection.NEUTRAL,
                confidence_score=0.0,
                symbol=symbol,
                timeframe=timeframe,
                exchange=exchange,
                explanation="Risk module does not allow trading",
                source_state_id=str(market_state.state_id),
            )
        
        # --------------------------------------------------
        # Step 3: Check if state is tradeable
        # --------------------------------------------------
        if not market_state.is_tradeable:
            return StrategySignal(
                signal_type=SignalType.NONE,
                direction=TradeDirection.NEUTRAL,
                confidence_score=0.0,
                symbol=symbol,
                timeframe=timeframe,
                exchange=exchange,
                explanation=f"Market state not tradeable: "
                           f"volatility={market_state.volatility_level.value}, "
                           f"liquidity={market_state.liquidity_grade.value}",
                source_state_id=str(market_state.state_id),
            )
        
        # --------------------------------------------------
        # Step 4: Classify signal type from trend/volatility
        # --------------------------------------------------
        signal_type, reason_code = self._classify_signal_type(market_state)
        
        # --------------------------------------------------
        # Step 5: Determine direction
        # --------------------------------------------------
        direction = self._determine_direction_from_state(market_state)
        
        # --------------------------------------------------
        # Step 6: Calculate confidence score
        # --------------------------------------------------
        confidence_score = self._calculate_confidence_from_state(market_state)
        
        # --------------------------------------------------
        # Step 7: Build supporting features
        # --------------------------------------------------
        supporting_features = self._build_supporting_features(market_state)
        
        # --------------------------------------------------
        # Step 8: Build explanation
        # --------------------------------------------------
        explanation = self._build_signal_explanation(
            market_state=market_state,
            signal_type=signal_type,
            direction=direction,
            confidence_score=confidence_score,
        )
        
        # --------------------------------------------------
        # Step 9: Build and return signal
        # --------------------------------------------------
        signal = StrategySignal(
            signal_type=signal_type,
            direction=direction,
            confidence_score=confidence_score,
            confidence_level=ConfidenceLevel.from_score(confidence_score),
            symbol=symbol,
            timeframe=timeframe,
            exchange=exchange,
            supporting_features=supporting_features,
            reason_code=reason_code,
            explanation=explanation,
            source_state_id=str(market_state.state_id),
            generated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(
                minutes=self.config.lifecycle.default_expiration_minutes
            ),
            engine_version=self.config.engine_version,
        )
        
        return signal
    
    def generate_signals_from_bundle(
        self,
        state_bundle: ProcessedMarketStateBundle,
        risk_allows_trading: bool = True,
    ) -> SignalBundle:
        """
        Generate signals for multiple symbols from a state bundle.
        
        Args:
            state_bundle: Bundle of processed market states
            risk_allows_trading: Whether risk module allows trading
        
        Returns:
            SignalBundle with signals for all states in bundle
        """
        start_time = time.time()
        evaluation_id = str(uuid4())[:8]
        
        signals: List[StrategySignal] = []
        symbols_evaluated: List[str] = []
        timeframes_evaluated: List[str] = []
        
        for key, state in state_bundle.states.items():
            signal = self.generate_signal(
                market_state=state,
                risk_allows_trading=risk_allows_trading,
            )
            signals.append(signal)
            
            if state.symbol not in symbols_evaluated:
                symbols_evaluated.append(state.symbol)
            if state.timeframe not in timeframes_evaluated:
                timeframes_evaluated.append(state.timeframe)
        
        duration_ms = (time.time() - start_time) * 1000
        
        return SignalBundle(
            signals=signals,
            evaluation_id=evaluation_id,
            timestamp=datetime.now(timezone.utc),
            symbols_evaluated=symbols_evaluated,
            timeframes_evaluated=timeframes_evaluated,
            evaluation_duration_ms=duration_ms,
        )
    
    def _classify_signal_type(
        self,
        state: ProcessedMarketState,
    ) -> Tuple[SignalType, Optional[StrategyReasonCode]]:
        """
        Classify the signal type based on market state.
        
        Returns (SignalType, StrategyReasonCode)
        """
        trend = state.trend_state
        volatility = state.volatility_level
        
        # Strong trends -> Trend following
        if trend == TrendState.STRONG_UPTREND:
            return SignalType.TREND_FOLLOWING, StrategyReasonCode.TREND_CONTINUATION_LONG
        elif trend == TrendState.STRONG_DOWNTREND:
            return SignalType.TREND_FOLLOWING, StrategyReasonCode.TREND_CONTINUATION_SHORT
        
        # Normal trends
        if trend == TrendState.UPTREND:
            return SignalType.MOMENTUM, StrategyReasonCode.TREND_CONTINUATION_LONG
        elif trend == TrendState.DOWNTREND:
            return SignalType.MOMENTUM, StrategyReasonCode.TREND_CONTINUATION_SHORT
        
        # Ranging -> Mean reversion
        if trend == TrendState.RANGING:
            return SignalType.MEAN_REVERSION, None
        
        # High/extreme volatility -> Volatility signals
        if volatility in (VolatilityLevel.HIGH, VolatilityLevel.EXTREME):
            return SignalType.VOLATILITY_EXPANSION, None
        
        # Default: No clear signal type
        return SignalType.NONE, None
    
    def _determine_direction_from_state(
        self,
        state: ProcessedMarketState,
    ) -> TradeDirection:
        """
        Determine trade direction from market state.
        """
        trend = state.trend_state
        
        if trend.is_bullish:
            return TradeDirection.LONG
        elif trend.is_bearish:
            return TradeDirection.SHORT
        else:
            return TradeDirection.NEUTRAL
    
    def _calculate_confidence_from_state(
        self,
        state: ProcessedMarketState,
    ) -> float:
        """
        Calculate confidence score from market state.
        
        Factors:
        - Trend strength
        - Volatility level (extreme reduces confidence)
        - Liquidity score
        - Data quality
        
        Returns: 0.0 to 1.0
        """
        base_confidence = 0.5
        
        # Trend contribution (0 to +0.3)
        trend_contrib = 0.0
        if state.trend_state in (TrendState.STRONG_UPTREND, TrendState.STRONG_DOWNTREND):
            trend_contrib = 0.3
        elif state.trend_state in (TrendState.UPTREND, TrendState.DOWNTREND):
            trend_contrib = 0.15
        
        # Trend strength contribution (0 to +0.1)
        strength_contrib = (state.trend_strength or 0.0) * 0.1
        
        # Volatility adjustment (-0.2 to 0)
        vol_adjustment = state.volatility_level.confidence_adjustment - 1.0
        vol_adjustment = max(-0.2, vol_adjustment)
        
        # Liquidity contribution (0 to +0.15)
        liq_contrib = state.liquidity_score * 0.15
        
        # Data quality contribution (0 to +0.05)
        quality_contrib = (state.data_quality_score or 0.5) * 0.05
        
        # Neutral trend reduces to near zero
        if state.trend_state.is_neutral:
            return max(0.0, 0.1 + quality_contrib)
        
        total = base_confidence + trend_contrib + strength_contrib + vol_adjustment + liq_contrib + quality_contrib
        
        return max(0.0, min(1.0, total))
    
    def _build_supporting_features(
        self,
        state: ProcessedMarketState,
    ) -> Dict[str, Any]:
        """
        Build supporting features dictionary for transparency.
        """
        return {
            # Trend features
            "trend_state": state.trend_state.value,
            "trend_direction_numeric": state.trend_direction_numeric,
            "trend_strength": state.trend_strength,
            
            # Volatility features
            "volatility_level": state.volatility_level.value,
            "volatility_raw": state.volatility_raw,
            "volatility_percentile": state.volatility_percentile,
            "volatility_risk_multiplier": state.volatility_level.risk_multiplier,
            
            # Liquidity features
            "liquidity_score": state.liquidity_score,
            "liquidity_grade": state.liquidity_grade.value,
            
            # Price features
            "current_price": state.current_price,
            "price_change_pct": state.price_change_pct,
            
            # Volume features
            "volume_ratio": state.volume_ratio,
            
            # Quality
            "data_quality_score": state.data_quality_score,
            "is_tradeable": state.is_tradeable,
            "risk_score_hint": state.risk_score_hint,
        }
    
    def _build_signal_explanation(
        self,
        market_state: ProcessedMarketState,
        signal_type: SignalType,
        direction: TradeDirection,
        confidence_score: float,
    ) -> str:
        """
        Build human-readable explanation for the signal.
        """
        if direction == TradeDirection.NEUTRAL:
            return (
                f"{market_state.symbol} {market_state.timeframe}: "
                f"No directional signal - trend={market_state.trend_state.value}, "
                f"volatility={market_state.volatility_level.value}"
            )
        
        dir_str = "bullish" if direction == TradeDirection.LONG else "bearish"
        conf_str = ConfidenceLevel.from_score(confidence_score).name.lower()
        
        return (
            f"{market_state.symbol} {market_state.timeframe}: "
            f"{signal_type.value} signal - {dir_str} with {conf_str} confidence. "
            f"Trend={market_state.trend_state.value}, "
            f"volatility={market_state.volatility_level.value}, "
            f"liquidity={market_state.liquidity_grade.value}"
        )


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================


def evaluate_market(
    input_data: StrategyInput,
    config: Optional[StrategyEngineConfig] = None,
) -> StrategyEngineOutput:
    """
    Convenience function to evaluate market in one call.
    
    For repeated evaluations, prefer creating a persistent
    StrategyEngine instance.
    
    Args:
        input_data: Complete input data
        config: Optional engine configuration
    
    Returns:
        StrategyEngineOutput
    """
    engine = StrategyEngine(config=config)
    return engine.evaluate(input_data)


def format_intent_summary(output: StrategyEngineOutput) -> str:
    """
    Format a human-readable summary of the output.
    
    Useful for logging, alerts, and dashboards.
    """
    lines = ["=" * 50]
    
    if output.has_intent:
        intent = output.trade_intent
        lines.append("TRADE INTENT GENERATED")
        lines.append("=" * 50)
        lines.append(f"Direction:  {intent.direction.value}")
        lines.append(f"Confidence: {intent.confidence.name}")
        lines.append(f"Reason:     {intent.reason_code.value}")
        lines.append(f"Symbol:     {intent.symbol}")
        lines.append(f"Timeframe:  {intent.timeframe}")
        lines.append("")
        lines.append("Signal Breakdown:")
        lines.append(f"  Structure: {intent.market_structure_signal.direction.value} ({intent.market_structure_signal.strength.name})")
        lines.append(f"  Volume:    {intent.volume_flow_signal.direction.value} ({intent.volume_flow_signal.strength.name})")
        lines.append(f"  Sentiment: {intent.sentiment_modifier.effect}")
        lines.append("")
        lines.append(f"Context: {intent.market_structure_signal.reason}")
        lines.append(f"Expires: {intent.expires_at.isoformat() if intent.expires_at else 'N/A'}")
    else:
        no_trade = output.no_trade
        lines.append("NO TRADE")
        lines.append("=" * 50)
        lines.append(f"Reason:      {no_trade.reason.value}")
        lines.append(f"Explanation: {no_trade.explanation}")
        lines.append(f"Symbol:      {no_trade.symbol}")
        lines.append(f"Timeframe:   {no_trade.timeframe}")
    
    lines.append("=" * 50)
    lines.append(f"Evaluation ID: {output.evaluation_id}")
    lines.append(f"Duration:      {output.evaluation_duration_ms:.2f}ms" if output.evaluation_duration_ms else "")
    
    return "\n".join(lines)
