"""
Database Verification Script.

============================================================
VERIFY REAL DATABASE PERSISTENCE
============================================================

This script:
1. Initializes the database connection
2. Creates all required tables
3. Runs a test pipeline cycle with sample data
4. Verifies data was actually written
5. Prints row counts for ALL 12 tables

EXIT CODES:
- 0: All tables have data, persistence verified
- 1: Database connection failed
- 2: Table creation failed
- 3: Persistence failed
- 4: Verification failed (tables empty)

============================================================
"""

import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("verify_database")


def create_sample_pipeline_data():
    """Create sample data for a complete pipeline cycle."""
    from database import PipelineCycleData
    
    now = datetime.utcnow()
    
    return PipelineCycleData(
        # Raw news
        raw_news=[
            {
                "external_id": "news_001",
                "title": "Bitcoin ETF sees record inflows",
                "content": "Institutional investors continue to pour money into spot Bitcoin ETFs...",
                "source_name": "CryptoNews",
                "published_at": now - timedelta(hours=2),
            },
            {
                "external_id": "news_002",
                "title": "Ethereum upgrade scheduled for next month",
                "content": "The Ethereum foundation announced the next major upgrade...",
                "source_name": "BlockchainDaily",
                "published_at": now - timedelta(hours=1),
            },
            {
                "external_id": "news_003",
                "title": "Whale wallet moves 10,000 BTC to exchange",
                "content": "Large wallet activity detected as major holder transfers BTC...",
                "source_name": "WhaleAlert",
                "published_at": now - timedelta(minutes=30),
            },
        ],
        raw_news_source="test_verification",
        
        # Cleaned news
        cleaned_news=[
            {
                "cleaned_title": "bitcoin etf sees record inflows",
                "cleaned_content": "institutional investors continue pour money spot bitcoin etfs",
                "tokens_mentioned": ["BTC"],
                "quality_score": 0.85,
                "relevance_score": 0.9,
            },
            {
                "cleaned_title": "ethereum upgrade scheduled next month",
                "cleaned_content": "ethereum foundation announced next major upgrade",
                "tokens_mentioned": ["ETH"],
                "quality_score": 0.8,
                "relevance_score": 0.85,
            },
        ],
        
        # Sentiment scores
        sentiment_scores=[
            {
                "token": "BTC",
                "score": 0.75,
                "label": "positive",
                "confidence": 0.88,
                "model": "finbert",
                "source_type": "news",
            },
            {
                "token": "ETH",
                "score": 0.65,
                "label": "positive",
                "confidence": 0.82,
                "model": "finbert",
                "source_type": "news",
            },
        ],
        
        # Market data
        market_data=[
            {
                "pair": "BTCUSDT",
                "open": 67500.0,
                "high": 68200.0,
                "low": 67100.0,
                "close": 67850.0,
                "volume": 15000.0,
                "interval": "1h",
                "open_time": now - timedelta(hours=1),
                "close_time": now,
            },
        ],
        market_data_symbol="BTC",
        market_data_exchange="binance",
        
        # On-chain flows
        onchain_flows=[
            {
                "token": "BTC",
                "chain": "bitcoin",
                "flow_type": "exchange_inflow",
                "amount": 500.5,
                "amount_usd": 33925000.0,
                "to_entity": "binance",
                "tx_hash": "abc123def456...",
            },
            {
                "token": "ETH",
                "chain": "ethereum",
                "flow_type": "whale_transfer",
                "amount": 10000.0,
                "amount_usd": 35000000.0,
                "from_entity": "unknown_whale",
                "tx_hash": "eth789ghi012...",
            },
        ],
        onchain_flows_source="test_verification",
        
        # Flow scores
        flow_scores=[
            {
                "token": "BTC",
                "exchange_flow_score": 0.65,
                "whale_activity_score": 0.7,
                "smart_money_score": 0.72,
                "composite_score": 0.68,
                "signal": "bullish",
                "confidence": 0.75,
                "data_points": 24,
            },
        ],
        
        # Market state
        market_state={
            "token": "BTC",
            "regime": "trending",
            "regime_confidence": 0.8,
            "trend_direction": "up",
            "trend_strength": 0.65,
            "volatility_percentile": 45,
            "volatility_expanding": False,
            "current_price": 67850.0,
            "near_support": False,
            "near_resistance": True,
            "resistance_level": 68500.0,
        },
        
        # Risk state
        risk_state={
            "token": "BTC",
            "global_risk_score": 35,
            "risk_level": "low",
            "sentiment_risk_raw": 25,
            "flow_risk_raw": 30,
            "smart_money_risk_raw": 28,
            "market_condition_risk_raw": 40,
            "sentiment_risk_normalized": 0.25,
            "flow_risk_normalized": 0.30,
            "smart_money_risk_normalized": 0.28,
            "market_condition_risk_normalized": 0.40,
            "weights": {"sentiment": 0.25, "flow": 0.25, "smart_money": 0.25, "market": 0.25},
            "trading_allowed": True,
        },
        
        # Entry decision
        entry_decision={
            "token": "BTC",
            "pair": "BTCUSDT",
            "decision": "ALLOW",
            "direction": "long",
            "reason_code": "all_signals_aligned",
            "reason_details": "Sentiment positive, flows bullish, risk low",
            "trade_guard_intervention": False,
            "sentiment_score": 0.75,
            "flow_score": 0.68,
            "smart_money_score": 0.72,
            "risk_score": 35,
        },
        
        # Position sizing
        position_sizing={
            "token": "BTC",
            "pair": "BTCUSDT",
            "calculated_size": 0.05,
            "size_usd": 3392.50,
            "size_percent": 2.5,
            "risk_per_trade": 150.0,
            "risk_percent": 1.0,
            "stop_loss_price": 66000.0,
            "stop_loss_percent": 2.7,
            "portfolio_value": 135700.0,
            "available_balance": 50000.0,
            "current_exposure": 85700.0,
            "max_position_size": 0.1,
            "risk_adjusted": True,
            "adjustment_factor": 0.85,
            "adjustment_reason": "near_resistance_reduction",
            "final_size": 0.0425,
            "final_size_usd": 2883.63,
        },
        
        # Execution record
        execution_record={
            "order_id": "ORD_TEST_001",
            "client_order_id": "CLI_TEST_001",
            "token": "BTC",
            "pair": "BTCUSDT",
            "exchange": "binance",
            "order_type": "market",
            "side": "buy",
            "requested_size": 0.0425,
            "status": "filled",
            "executed_size": 0.0425,
            "executed_price": 67860.0,
            "avg_fill_price": 67860.0,
            "commission": 2.88,
            "commission_asset": "USDT",
            "slippage": 10.0,
            "slippage_percent": 0.015,
            "latency_ms": 45,
            "executed_at": now,
        },
        
        # Monitoring events
        monitoring_events=[
            {
                "event_type": "pipeline_start",
                "severity": "info",
                "module_name": "pipeline",
                "message": "Pipeline cycle started",
            },
            {
                "event_type": "pipeline_complete",
                "severity": "info",
                "module_name": "pipeline",
                "message": "Pipeline cycle completed successfully",
                "metric_name": "cycle_duration_ms",
                "metric_value": 1250.5,
                "metric_unit": "ms",
            },
        ],
    )


def verify_table_counts() -> Dict[str, int]:
    """Get row counts for all tables."""
    from database import get_table_row_counts
    return get_table_row_counts()


def print_verification_report(
    counts: Dict[str, int],
    persistence_result: Any,
) -> bool:
    """Print verification report and return success status."""
    print("\n" + "=" * 70)
    print("DATABASE PERSISTENCE VERIFICATION REPORT")
    print("=" * 70)
    
    print(f"\nCorrelation ID: {persistence_result.correlation_id}")
    print(f"Persistence Success: {persistence_result.success}")
    print(f"Duration: {persistence_result.duration_ms}ms")
    print(f"Total Records Inserted: {persistence_result.total_records_inserted}")
    
    print("\n" + "-" * 70)
    print("RECORDS INSERTED PER TABLE (This Cycle)")
    print("-" * 70)
    
    for table, count in sorted(persistence_result.records_by_table.items()):
        status = "✓" if count > 0 else "○"
        print(f"  {status} {table:30s} : {count:6d} records")
    
    print("\n" + "-" * 70)
    print("TOTAL DATABASE ROW COUNTS (All Time)")
    print("-" * 70)
    
    tables_with_data = 0
    for table, count in sorted(counts.items()):
        status = "✓" if count > 0 else "✗"
        if count > 0:
            tables_with_data += 1
        print(f"  {status} {table:30s} : {count:6d} rows")
    
    print("\n" + "-" * 70)
    print("SUMMARY")
    print("-" * 70)
    
    total_rows = sum(counts.values())
    required_tables = 12
    
    print(f"  Tables with data: {tables_with_data}/{required_tables}")
    print(f"  Total rows in database: {total_rows}")
    
    if tables_with_data >= required_tables:
        print("\n  ✓ ALL TABLES HAVE DATA - PERSISTENCE VERIFIED")
        return True
    else:
        empty_tables = [t for t, c in counts.items() if c == 0]
        print(f"\n  ✗ VERIFICATION FAILED - Empty tables: {empty_tables}")
        return False


def main() -> int:
    """Main verification function."""
    print("\n" + "=" * 70)
    print("STARTING DATABASE PERSISTENCE VERIFICATION")
    print("=" * 70)
    
    # Step 1: Initialize database
    print("\n[1/4] Initializing database connection...")
    try:
        from database import initialize_database
        initialize_database()
        print("  ✓ Database initialized successfully")
    except Exception as e:
        print(f"  ✗ Database initialization failed: {e}")
        return 1
    
    # Step 2: Verify tables exist
    print("\n[2/4] Verifying required tables...")
    try:
        from database import verify_required_tables
        missing = verify_required_tables()
        if missing:
            print(f"  ✗ Missing tables: {missing}")
            return 2
        print("  ✓ All 12 required tables exist")
    except Exception as e:
        print(f"  ✗ Table verification failed: {e}")
        return 2
    
    # Step 3: Run test pipeline persistence
    print("\n[3/4] Running test pipeline persistence...")
    try:
        from database import persist_pipeline_cycle
        sample_data = create_sample_pipeline_data()
        result = persist_pipeline_cycle(sample_data)
        
        if not result.success:
            print(f"  ✗ Persistence failed: {result.error_message}")
            return 3
        
        print(f"  ✓ Persisted {result.total_records_inserted} records in {result.duration_ms}ms")
    except Exception as e:
        print(f"  ✗ Pipeline persistence failed: {e}")
        import traceback
        traceback.print_exc()
        return 3
    
    # Step 4: Verify data exists
    print("\n[4/4] Verifying database contents...")
    try:
        counts = verify_table_counts()
        success = print_verification_report(counts, result)
        
        if success:
            print("\n" + "=" * 70)
            print("✓ DATABASE PERSISTENCE VERIFICATION PASSED")
            print("=" * 70)
            return 0
        else:
            print("\n" + "=" * 70)
            print("✗ DATABASE PERSISTENCE VERIFICATION FAILED")
            print("=" * 70)
            return 4
            
    except Exception as e:
        print(f"  ✗ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 4


if __name__ == "__main__":
    sys.exit(main())
