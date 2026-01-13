"""
Data Processing Module for Orchestrator.

============================================================
PURPOSE
============================================================
Wraps the data processing pipeline as an orchestrator-compatible
module. Provides lifecycle management for processing stages.

Computes derived features from raw market data:
- Price returns (absolute and percentage)
- Volatility (standard deviation of returns)
- Volume changes (vs previous period)

Produces ProcessedMarketState for downstream consumers:
- RiskScoringEngine
- StrategyEngine

============================================================
"""

import logging
import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database.engine import get_session
from database.models import MarketData, ProcessedMarketData, ProcessedMarketStateRecord

from .contracts import (
    ProcessedMarketState,
    ProcessedMarketStateBundle,
    TrendState,
    VolatilityLevel,
    LiquidityGrade,
)


logger = logging.getLogger("data_processing.module")


class ProcessingPipelineModule:
    """
    Real data processing module for orchestrator.
    
    ============================================================
    RESPONSIBILITY
    ============================================================
    - Initialize processing pipeline on start
    - Provide health status
    - Run processing stages
    
    ============================================================
    NOT A PLACEHOLDER
    ============================================================
    This is a REAL module that wraps the data processing pipeline.
    
    ============================================================
    """
    
    # Class marker: This is NOT a placeholder
    _is_placeholder: bool = False
    
    def __init__(
        self,
        session_factory=None,
        **kwargs,
    ) -> None:
        """
        Initialize the processing pipeline module.
        
        Args:
            session_factory: Optional factory for database sessions
            **kwargs: Additional arguments (for orchestrator compatibility)
        """
        self._session_factory = session_factory or get_session
        self._running = False
        self._processed_count = 0
        self._last_run_time: Optional[float] = None
        
        logger.info("ProcessingPipelineModule initialized")
    
    # --------------------------------------------------------
    # ORCHESTRATOR INTERFACE
    # --------------------------------------------------------
    
    async def start(self) -> None:
        """Start the processing pipeline module."""
        logger.info("Starting ProcessingPipelineModule...")
        self._running = True
        logger.info("ProcessingPipelineModule started")
    
    async def stop(self) -> None:
        """Stop the processing pipeline module."""
        logger.info("Stopping ProcessingPipelineModule...")
        self._running = False
        logger.info("ProcessingPipelineModule stopped")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status for monitoring."""
        return {
            "status": "healthy" if self._running else "stopped",
            "module": "ProcessingPipelineModule",
            "is_placeholder": False,
            "processed_count": self._processed_count,
            "last_run_time": self._last_run_time,
        }
    
    def can_trade(self) -> bool:
        """Check if module allows trading (for compatibility)."""
        return self._running
    
    def is_halted(self) -> bool:
        """Check if module is halted (for compatibility)."""
        return not self._running
    
    # --------------------------------------------------------
    # PROCESSING METHODS
    # --------------------------------------------------------
    
    async def run_processing_cycle(self) -> Dict[str, Any]:
        """
        Run a processing cycle.
        
        Reads recent MarketData, aggregates by symbol and interval,
        computes derived features (return, volatility, volume_change),
        and persists to processed_market_data table.
        
        Returns:
            Dict with processing results:
            {
                "processed_symbols": List[str],
                "records_processed": int,
                "time_window": {"start": str, "end": str}
            }
        """
        import time
        start_time = time.time()
        
        logger.info("Running processing cycle...")
        
        now = datetime.now(timezone.utc)
        processed_symbols: Set[str] = set()
        total_records_processed = 0
        
        # Define aggregation intervals
        intervals = [
            ("1h", timedelta(hours=1)),
            ("24h", timedelta(hours=24)),
        ]
        
        # Time window for fetching raw data (look back 24h for context)
        lookback_hours = 48  # Need extra context for volume change calculation
        window_start = now - timedelta(hours=lookback_hours)
        window_end = now
        
        session: Optional[Session] = None
        
        try:
            session = self._session_factory()
            
            # 1. Fetch recent market data
            raw_data = self._fetch_recent_market_data(session, window_start, window_end)
            
            if not raw_data:
                logger.warning("No market data found in the specified time window")
                result = {
                    "success": True,
                    "processed_symbols": [],
                    "records_processed": 0,
                    "time_window": {
                        "start": window_start.isoformat(),
                        "end": window_end.isoformat(),
                    },
                    "cycle": self._processed_count,
                    "duration": time.time() - start_time,
                }
                return result
            
            logger.info(f"Fetched {len(raw_data)} raw market data records")
            
            # 2. Group data by symbol and exchange
            grouped_data = self._group_market_data(raw_data)
            
            # 3. Process each interval
            all_processed_records: List[Dict[str, Any]] = []
            
            for interval_name, interval_delta in intervals:
                # Calculate window for this interval
                interval_end = now
                interval_start = interval_end - interval_delta
                
                # Also need previous period for volume change
                prev_start = interval_start - interval_delta
                prev_end = interval_start
                
                for (symbol, exchange), candles in grouped_data.items():
                    # Filter candles for current interval
                    current_candles = [
                        c for c in candles
                        if self._normalize_to_utc(interval_start) <= self._normalize_to_utc(c.candle_open_time) < self._normalize_to_utc(interval_end)
                    ]
                    
                    if not current_candles:
                        continue
                    
                    # Get previous period candles for volume change
                    prev_candles = [
                        c for c in candles
                        if self._normalize_to_utc(prev_start) <= self._normalize_to_utc(c.candle_open_time) < self._normalize_to_utc(prev_end)
                    ]
                    
                    # Compute features
                    processed_record = self._compute_features(
                        symbol=symbol,
                        exchange=exchange,
                        interval=interval_name,
                        candles=current_candles,
                        prev_candles=prev_candles,
                        window_start=interval_start,
                        window_end=interval_end,
                    )
                    
                    if processed_record:
                        all_processed_records.append(processed_record)
                        processed_symbols.add(symbol)
            
            # 4. Persist processed records
            if all_processed_records:
                stored_count = self._persist_processed_records(session, all_processed_records)
                total_records_processed = stored_count
                logger.info(f"Persisted {stored_count} processed market data records")
            
            # 5. Compute and persist market states
            market_states: List[ProcessedMarketState] = []
            for record in all_processed_records:
                state = self.compute_market_state(record)
                market_states.append(state)
                self.persist_market_state(session, state)
            
            if market_states:
                logger.info(f"Computed and persisted {len(market_states)} market states")
            
            session.commit()
            
        except Exception as e:
            logger.error(f"Processing cycle failed: {e}", exc_info=True)
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()
        
        self._processed_count += 1
        self._last_run_time = time.time() - start_time
        
        result = {
            "success": True,
            "processed_symbols": sorted(list(processed_symbols)),
            "records_processed": total_records_processed,
            "time_window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
            "intervals_processed": [i[0] for i in intervals],
            "cycle": self._processed_count,
            "duration": self._last_run_time,
        }
        
        logger.info(
            f"Processing cycle completed in {self._last_run_time:.2f}s - "
            f"{total_records_processed} records, {len(processed_symbols)} symbols"
        )
        
        return result
    
    # --------------------------------------------------------
    # HELPER METHODS
    # --------------------------------------------------------
    
    def _normalize_to_utc(self, dt: datetime) -> datetime:
        """
        Normalize a datetime to UTC for comparison.
        
        Handles both timezone-aware and naive datetimes.
        Naive datetimes are assumed to be UTC.
        
        Args:
            dt: Datetime to normalize
            
        Returns:
            Timezone-naive datetime (for comparison)
        """
        if dt is None:
            return None
        
        if dt.tzinfo is not None:
            # Convert to UTC and make naive
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            # Already naive, assume UTC
            return dt
    
    def _fetch_recent_market_data(
        self,
        session: Session,
        start_time: datetime,
        end_time: datetime,
    ) -> List[MarketData]:
        """
        Fetch recent market data from database.
        
        Args:
            session: Database session
            start_time: Start of time window
            end_time: End of time window
            
        Returns:
            List of MarketData records
        """
        query = session.query(MarketData).filter(
            and_(
                MarketData.candle_open_time >= start_time,
                MarketData.candle_open_time < end_time,
            )
        ).order_by(MarketData.symbol, MarketData.candle_open_time)
        
        return query.all()
    
    def _group_market_data(
        self,
        records: List[MarketData],
    ) -> Dict[Tuple[str, str], List[MarketData]]:
        """
        Group market data by symbol and exchange.
        
        Args:
            records: List of MarketData records
            
        Returns:
            Dict mapping (symbol, exchange) to list of records
        """
        grouped: Dict[Tuple[str, str], List[MarketData]] = defaultdict(list)
        
        for record in records:
            key = (record.symbol, record.exchange)
            grouped[key].append(record)
        
        # Sort each group by time
        for key in grouped:
            grouped[key].sort(key=lambda x: x.candle_open_time)
        
        return grouped
    
    def _compute_features(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        candles: List[MarketData],
        prev_candles: List[MarketData],
        window_start: datetime,
        window_end: datetime,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute derived features from raw candle data.
        
        Features computed:
        - price_return: (close - open) / open
        - volatility: standard deviation of per-candle returns
        - volume_change: current volume vs previous period
        
        Args:
            symbol: Trading symbol (e.g., BTC)
            exchange: Exchange name
            interval: Aggregation interval (1h, 24h)
            candles: List of candles in current period
            prev_candles: List of candles in previous period
            window_start: Start of current window
            window_end: End of current window
            
        Returns:
            Dict with processed features, or None if insufficient data
        """
        if not candles:
            return None
        
        # Sort candles by time
        candles = sorted(candles, key=lambda x: x.candle_open_time)
        
        # OHLCV aggregation
        open_price = candles[0].open_price
        close_price = candles[-1].close_price
        high_price = max(c.high_price for c in candles)
        low_price = min(c.low_price for c in candles)
        total_volume = sum(c.volume for c in candles)
        total_quote_volume = sum(c.quote_volume or 0 for c in candles)
        avg_volume = total_volume / len(candles) if candles else 0
        
        # Compute VWAP
        vwap = None
        if total_volume > 0:
            vwap_numerator = sum(
                ((c.high_price + c.low_price + c.close_price) / 3) * c.volume
                for c in candles
            )
            vwap = vwap_numerator / total_volume
        
        # Trade count
        trade_count = sum(c.trade_count or 0 for c in candles)
        
        # 1. Price Return
        price_return = None
        price_return_pct = None
        if open_price and open_price > 0:
            price_return = (close_price - open_price) / open_price
            price_return_pct = price_return * 100
        
        # 2. High-Low Range
        high_low_range = None
        if low_price and low_price > 0:
            high_low_range = (high_price - low_price) / low_price
        
        # 3. Volatility (std dev of per-candle returns)
        volatility = None
        if len(candles) >= 2:
            returns = []
            for i in range(1, len(candles)):
                prev_close = candles[i - 1].close_price
                curr_close = candles[i].close_price
                if prev_close and prev_close > 0:
                    ret = (curr_close - prev_close) / prev_close
                    returns.append(ret)
            
            if len(returns) >= 2:
                mean_return = sum(returns) / len(returns)
                variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
                volatility = math.sqrt(variance)
        
        # 4. Volume Change (vs previous period)
        volume_change = None
        volume_change_pct = None
        if prev_candles:
            prev_volume = sum(c.volume for c in prev_candles)
            if prev_volume > 0:
                volume_change = total_volume - prev_volume
                volume_change_pct = (volume_change / prev_volume) * 100
        
        # Data quality assessment
        # Estimate expected candle count based on interval
        if interval == "1h":
            # Assuming 1m candles, expect ~60
            expected_candles = 60
        elif interval == "24h":
            # Assuming 1m candles, expect ~1440
            expected_candles = 1440
        else:
            expected_candles = len(candles)
        
        data_quality_score = min(1.0, len(candles) / expected_candles) if expected_candles > 0 else 1.0
        has_gaps = len(candles) < expected_candles * 0.9  # More than 10% missing
        
        return {
            "correlation_id": str(uuid.uuid4()),
            "symbol": symbol,
            "interval": interval,
            "exchange": exchange,
            "window_start": window_start,
            "window_end": window_end,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "close_price": close_price,
            "vwap": vwap,
            "total_volume": total_volume,
            "total_quote_volume": total_quote_volume if total_quote_volume > 0 else None,
            "avg_volume": avg_volume,
            "price_return": price_return,
            "price_return_pct": price_return_pct,
            "volatility": volatility,
            "high_low_range": high_low_range,
            "volume_change": volume_change,
            "volume_change_pct": volume_change_pct,
            "candle_count": len(candles),
            "trade_count": trade_count if trade_count > 0 else None,
            "data_quality_score": data_quality_score,
            "has_gaps": has_gaps,
            "source_module": "ProcessingPipelineModule",
            "processing_version": "1.0.0",
            "calculated_at": datetime.now(timezone.utc),
        }
    
    def _persist_processed_records(
        self,
        session: Session,
        records: List[Dict[str, Any]],
    ) -> int:
        """
        Persist processed market data records using upsert.
        
        Args:
            session: Database session
            records: List of processed record dicts
            
        Returns:
            Number of records persisted
        """
        if not records:
            return 0
        
        persisted_count = 0
        
        for record in records:
            try:
                # Use PostgreSQL INSERT ... ON CONFLICT for upsert
                stmt = pg_insert(ProcessedMarketData).values(**record)
                
                # On conflict, update the values
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_processed_market_data",
                    set_={
                        "open_price": stmt.excluded.open_price,
                        "high_price": stmt.excluded.high_price,
                        "low_price": stmt.excluded.low_price,
                        "close_price": stmt.excluded.close_price,
                        "vwap": stmt.excluded.vwap,
                        "total_volume": stmt.excluded.total_volume,
                        "total_quote_volume": stmt.excluded.total_quote_volume,
                        "avg_volume": stmt.excluded.avg_volume,
                        "price_return": stmt.excluded.price_return,
                        "price_return_pct": stmt.excluded.price_return_pct,
                        "volatility": stmt.excluded.volatility,
                        "high_low_range": stmt.excluded.high_low_range,
                        "volume_change": stmt.excluded.volume_change,
                        "volume_change_pct": stmt.excluded.volume_change_pct,
                        "candle_count": stmt.excluded.candle_count,
                        "trade_count": stmt.excluded.trade_count,
                        "data_quality_score": stmt.excluded.data_quality_score,
                        "has_gaps": stmt.excluded.has_gaps,
                        "calculated_at": stmt.excluded.calculated_at,
                    },
                )
                
                session.execute(stmt)
                persisted_count += 1
                
            except Exception as e:
                logger.warning(
                    f"Failed to persist processed record for "
                    f"{record.get('symbol')}/{record.get('interval')}: {e}"
                )
        
        return persisted_count

    # --------------------------------------------------------
    # MARKET STATE COMPUTATION
    # --------------------------------------------------------
    
    def compute_market_state(
        self,
        processed_data: Dict[str, Any],
        historical_volatility: Optional[List[float]] = None,
    ) -> ProcessedMarketState:
        """
        Compute ProcessedMarketState from processed market data.
        
        This is the canonical method for creating market state
        that downstream modules (RiskScoringEngine, StrategyEngine)
        can consume deterministically.
        
        Args:
            processed_data: Dict from _compute_features()
            historical_volatility: Optional list of historical vol values
                                   for percentile calculation
        
        Returns:
            ProcessedMarketState ready for persistence and consumption
        """
        symbol = processed_data.get("symbol", "UNKNOWN")
        timeframe = processed_data.get("interval", "1h")
        exchange = processed_data.get("exchange", "binance")
        
        # Extract raw values
        price_return = processed_data.get("price_return", 0.0) or 0.0
        volatility_raw = processed_data.get("volatility", 0.0) or 0.0
        volume_ratio = 1.0  # Default
        if processed_data.get("volume_change_pct") is not None:
            # Convert volume change % to ratio
            volume_ratio = 1.0 + (processed_data["volume_change_pct"] / 100.0)
        
        # 1. Determine trend state from returns
        trend_state = self._classify_trend(price_return)
        trend_strength = min(1.0, abs(price_return) * 10)  # Scale to 0-1
        
        # 2. Determine volatility level
        volatility_percentile = self._calculate_volatility_percentile(
            volatility_raw, historical_volatility
        )
        volatility_level = self._classify_volatility(volatility_percentile)
        
        # 3. Compute liquidity score
        # Based on volume ratio and data quality
        data_quality = processed_data.get("data_quality_score", 0.5) or 0.5
        liquidity_score = self._compute_liquidity_score(
            volume_ratio=volume_ratio,
            data_quality=data_quality,
            has_gaps=processed_data.get("has_gaps", False),
        )
        
        # Build the state object
        state = ProcessedMarketState(
            symbol=symbol.upper(),
            timeframe=timeframe,
            exchange=exchange,
            trend_state=trend_state,
            volatility_level=volatility_level,
            liquidity_score=liquidity_score,
            current_price=processed_data.get("close_price"),
            price_change_pct=processed_data.get("price_return_pct"),
            volatility_raw=volatility_raw,
            volatility_percentile=volatility_percentile,
            volume_ratio=volume_ratio,
            trend_strength=trend_strength,
            data_quality_score=data_quality,
            window_start=processed_data.get("window_start"),
            window_end=processed_data.get("window_end"),
            calculated_at=processed_data.get("calculated_at") or datetime.now(timezone.utc),
            source_module="ProcessingPipelineModule",
        )
        
        return state
    
    def _classify_trend(self, price_return: float) -> TrendState:
        """
        Classify trend based on price return.
        
        Thresholds:
        - Strong: |return| > 5%
        - Normal: |return| > 1%
        - Neutral/Ranging: |return| <= 1%
        """
        if price_return > 0.05:
            return TrendState.STRONG_UPTREND
        elif price_return > 0.01:
            return TrendState.UPTREND
        elif price_return < -0.05:
            return TrendState.STRONG_DOWNTREND
        elif price_return < -0.01:
            return TrendState.DOWNTREND
        else:
            return TrendState.NEUTRAL
    
    def _calculate_volatility_percentile(
        self,
        current_vol: float,
        historical: Optional[List[float]] = None,
    ) -> float:
        """
        Calculate volatility percentile.
        
        If historical data available, compute actual percentile.
        Otherwise, use heuristic based on typical crypto volatility.
        """
        if historical and len(historical) > 10:
            # Compute actual percentile
            sorted_hist = sorted(historical)
            count_below = sum(1 for v in sorted_hist if v < current_vol)
            return (count_below / len(sorted_hist)) * 100
        
        # Heuristic for crypto (typical daily vol ~2-5%)
        # Scale current hourly vol to approximate percentile
        if current_vol < 0.001:
            return 10.0
        elif current_vol < 0.002:
            return 30.0
        elif current_vol < 0.005:
            return 50.0
        elif current_vol < 0.01:
            return 70.0
        elif current_vol < 0.02:
            return 85.0
        else:
            return 95.0
    
    def _classify_volatility(self, percentile: float) -> VolatilityLevel:
        """Classify volatility level from percentile."""
        if percentile < 10:
            return VolatilityLevel.VERY_LOW
        elif percentile < 30:
            return VolatilityLevel.LOW
        elif percentile < 70:
            return VolatilityLevel.NORMAL
        elif percentile < 90:
            return VolatilityLevel.HIGH
        else:
            return VolatilityLevel.EXTREME
    
    def _compute_liquidity_score(
        self,
        volume_ratio: float,
        data_quality: float,
        has_gaps: bool,
    ) -> float:
        """
        Compute liquidity score (0-1).
        
        Higher volume ratio = more liquid
        Better data quality = higher confidence
        Gaps reduce score
        """
        # Base score from volume ratio
        # volume_ratio of 1.0 = average = 0.5 base
        # volume_ratio of 2.0 = 2x average = 0.8 base
        # volume_ratio of 0.5 = half average = 0.3 base
        base_score = min(1.0, 0.3 + (volume_ratio * 0.35))
        
        # Adjust for data quality
        quality_factor = 0.7 + (data_quality * 0.3)
        
        # Penalize for gaps
        gap_penalty = 0.9 if has_gaps else 1.0
        
        final_score = base_score * quality_factor * gap_penalty
        
        return max(0.0, min(1.0, final_score))
    
    def persist_market_state(
        self,
        session: Session,
        state: ProcessedMarketState,
    ) -> bool:
        """
        Persist ProcessedMarketState to database.
        
        Uses upsert to handle duplicate timestamps.
        
        Args:
            session: Database session
            state: ProcessedMarketState to persist
            
        Returns:
            True if persisted successfully
        """
        try:
            record_data = {
                "state_id": str(state.state_id),
                "symbol": state.symbol,
                "timeframe": state.timeframe,
                "exchange": state.exchange,
                "trend_state": state.trend_state.value,
                "volatility_level": state.volatility_level.value,
                "liquidity_score": state.liquidity_score,
                "liquidity_grade": state.liquidity_grade.value,
                "current_price": state.current_price,
                "price_change_pct": state.price_change_pct,
                "volatility_raw": state.volatility_raw,
                "volatility_percentile": state.volatility_percentile,
                "volume_ratio": state.volume_ratio,
                "spread_pct": state.spread_pct,
                "trend_strength": state.trend_strength,
                "trend_direction_numeric": state.trend_direction_numeric,
                "trend_duration_periods": state.trend_duration_periods,
                "data_quality_score": state.data_quality_score,
                "is_tradeable": state.is_tradeable,
                "risk_score_hint": state.risk_score_hint,
                "window_start": state.window_start,
                "window_end": state.window_end,
                "source_module": state.source_module,
                "version": state.version,
                "calculated_at": state.calculated_at,
            }
            
            stmt = pg_insert(ProcessedMarketStateRecord).values(**record_data)
            
            stmt = stmt.on_conflict_do_update(
                constraint="uq_processed_market_state",
                set_={
                    "state_id": stmt.excluded.state_id,
                    "trend_state": stmt.excluded.trend_state,
                    "volatility_level": stmt.excluded.volatility_level,
                    "liquidity_score": stmt.excluded.liquidity_score,
                    "liquidity_grade": stmt.excluded.liquidity_grade,
                    "current_price": stmt.excluded.current_price,
                    "price_change_pct": stmt.excluded.price_change_pct,
                    "volatility_raw": stmt.excluded.volatility_raw,
                    "volatility_percentile": stmt.excluded.volatility_percentile,
                    "volume_ratio": stmt.excluded.volume_ratio,
                    "trend_strength": stmt.excluded.trend_strength,
                    "trend_direction_numeric": stmt.excluded.trend_direction_numeric,
                    "is_tradeable": stmt.excluded.is_tradeable,
                    "risk_score_hint": stmt.excluded.risk_score_hint,
                },
            )
            
            session.execute(stmt)
            return True
            
        except Exception as e:
            logger.warning(
                f"Failed to persist market state for {state.symbol}/{state.timeframe}: {e}"
            )
            return False
    
    def get_latest_market_state(
        self,
        session: Session,
        symbol: str,
        timeframe: str,
        exchange: str = "binance",
    ) -> Optional[ProcessedMarketState]:
        """
        Retrieve the latest persisted market state.
        
        This is the canonical method for downstream modules to
        read market state deterministically.
        
        Args:
            session: Database session
            symbol: Asset symbol (e.g., "BTC")
            timeframe: Timeframe (e.g., "1h")
            exchange: Exchange name
            
        Returns:
            ProcessedMarketState if found, None otherwise
        """
        try:
            record = session.query(ProcessedMarketStateRecord).filter(
                and_(
                    ProcessedMarketStateRecord.symbol == symbol.upper(),
                    ProcessedMarketStateRecord.timeframe == timeframe,
                    ProcessedMarketStateRecord.exchange == exchange,
                )
            ).order_by(
                ProcessedMarketStateRecord.calculated_at.desc()
            ).first()
            
            if not record:
                return None
            
            # Reconstruct the dataclass
            return ProcessedMarketState(
                symbol=record.symbol,
                timeframe=record.timeframe,
                exchange=record.exchange,
                trend_state=TrendState(record.trend_state),
                volatility_level=VolatilityLevel(record.volatility_level),
                liquidity_score=record.liquidity_score,
                current_price=record.current_price,
                price_change_pct=record.price_change_pct,
                volatility_raw=record.volatility_raw,
                volatility_percentile=record.volatility_percentile,
                volume_ratio=record.volume_ratio,
                spread_pct=record.spread_pct,
                trend_strength=record.trend_strength,
                trend_duration_periods=record.trend_duration_periods,
                data_quality_score=record.data_quality_score,
                window_start=record.window_start,
                window_end=record.window_end,
                calculated_at=record.calculated_at,
                state_id=uuid.UUID(record.state_id),
                source_module=record.source_module,
                version=record.version,
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve market state: {e}")
            return None
    
    def get_latest_states_bundle(
        self,
        session: Session,
        symbols: List[str],
        timeframe: str = "1h",
        exchange: str = "binance",
    ) -> ProcessedMarketStateBundle:
        """
        Retrieve latest states for multiple symbols as a bundle.
        
        Convenience method for portfolio-level operations.
        
        Args:
            session: Database session
            symbols: List of symbols to fetch
            timeframe: Timeframe to fetch
            exchange: Exchange name
            
        Returns:
            ProcessedMarketStateBundle with all available states
        """
        bundle = ProcessedMarketStateBundle()
        
        for symbol in symbols:
            state = self.get_latest_market_state(
                session=session,
                symbol=symbol,
                timeframe=timeframe,
                exchange=exchange,
            )
            if state:
                bundle.add(state)
        
        return bundle
