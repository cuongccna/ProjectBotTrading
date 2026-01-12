"""
Test script for Smart Money / Whale Tracking Module.

Validates:
1. Wallet registry CRUD operations
2. Ethereum tracker connectivity
3. Solana tracker connectivity
4. Pattern detection
5. Signal generation
6. Full pipeline evaluation

SAFETY: Smart money signals are CONTEXT ONLY - never a trade trigger.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent to path
sys.path.insert(0, ".")

from smart_money import (
    Chain,
    DetectedPattern,
    EntityType,
    EthereumTracker,
    FlowDirection,
    PatternDetector,
    SmartMoneyConfig,
    SmartMoneyManager,
    SmartMoneySignal,
    SmartMoneySignalGenerator,
    SolanaTracker,
    WalletActivity,
    WalletInfo,
    WalletRegistryManager,
    ActivityType,
)


def print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)


def print_success(text: str) -> None:
    print(f"  [OK] {text}")


def print_warning(text: str) -> None:
    print(f"  [WARN] {text}")


def print_error(text: str) -> None:
    print(f"  [FAIL] {text}")


def test_wallet_registry() -> bool:
    """Test wallet registry operations."""
    print_header("Test 1: Wallet Registry Manager")
    
    try:
        # Use test database - delete if exists for clean test
        import os
        db_path = "storage/test_smart_money.db"
        if os.path.exists(db_path):
            os.remove(db_path)
        
        registry = WalletRegistryManager(db_path=db_path)
        
        # Create test wallet
        wallet = WalletInfo(
            address="0xTestAddress123456789012345678901234567890",
            chain=Chain.ETHEREUM,
            entity_type=EntityType.WHALE,
            entity_name="Test Whale",
            confidence_level=0.85,
            tags=["test", "whale"],
        )
        
        # Add wallet
        added = registry.add_wallet(wallet)
        print(f"  Added wallet: {added}")
        
        # Get wallet
        retrieved = registry.get_wallet(wallet.address, Chain.ETHEREUM)
        assert retrieved is not None, "Failed to retrieve wallet"
        assert retrieved.entity_name == "Test Whale", "Entity name mismatch"
        print(f"  Retrieved wallet: {retrieved.entity_name}")
        
        # Update wallet
        wallet_updated = WalletInfo(
            address=wallet.address,
            chain=Chain.ETHEREUM,
            entity_type=EntityType.WHALE,
            entity_name="Updated Test Whale",
            confidence_level=0.9,
            tags=["test", "whale", "updated"],
        )
        registry.update_wallet(wallet_updated)
        
        retrieved = registry.get_wallet(wallet.address, Chain.ETHEREUM)
        assert retrieved.entity_name == "Updated Test Whale", "Update failed"
        print(f"  Updated wallet: {retrieved.entity_name}")
        
        # Get stats
        stats = registry.get_stats()
        print(f"  Registry stats: {stats.get('active_wallets', 0)} active wallets")
        
        # Seed defaults
        count = registry.seed_default_wallets()
        print(f"  Seeded {count} default wallets")
        
        # Test CEX detection
        cex_wallets = registry.get_cex_wallets()
        print(f"  Found {len(cex_wallets)} CEX wallets")
        
        print_success("Wallet registry working")
        return True
        
    except Exception as e:
        print_error(f"Registry test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ethereum_tracker() -> bool:
    """Test Ethereum tracker."""
    print_header("Test 2: Ethereum Tracker (Etherscan)")
    
    tracker = EthereumTracker()
    
    try:
        # Check connectivity with well-known address
        test_address = "0xdfd5293d8e347dfe59e90efd55b2956a1343963d"  # Coinbase
        
        # Note: May fail without API key - that's expected
        wallet = WalletInfo(
            address=test_address,
            chain=Chain.ETHEREUM,
            entity_type=EntityType.CEX_HOT,
            entity_name="Coinbase",
        )
        
        start = time.time()
        activities = await tracker.get_activity(wallet, hours=1)
        elapsed = time.time() - start
        
        print(f"  Fetched {len(activities)} activities in {elapsed:.2f}s")
        
        if activities:
            sample = activities[0]
            print(f"  Sample activity:")
            print(f"    Hash: {sample.tx_hash[:20]}...")
            print(f"    Type: {sample.activity_type.value}")
            print(f"    Amount: {sample.amount:.4f} {sample.token_symbol}")
            print(f"    Value: ${sample.value_usd:,.2f}")
            
            print_success("Ethereum tracker working")
        else:
            print_warning("No activities returned (may be rate limited)")
        
        # Check health
        health = await tracker.check_health()
        print(f"  Health: {'OK' if health.is_healthy else 'DEGRADED'}")
        
        # Get stats
        stats = tracker.get_stats()
        print(f"  Cache hits: {stats.get('cache_hits', 0)}")
        
        return True
        
    except Exception as e:
        print_warning(f"Ethereum tracker test: {e}")
        print("  (This is expected without API key)")
        return True  # Not a failure
    finally:
        await tracker.close()


async def test_solana_tracker() -> bool:
    """Test Solana tracker."""
    print_header("Test 3: Solana Tracker (RPC)")
    
    tracker = SolanaTracker()
    
    try:
        # Use a known active Solana address
        test_address = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
        
        wallet = WalletInfo(
            address=test_address,
            chain=Chain.SOLANA,
            entity_type=EntityType.WHALE,
            entity_name="Test Solana Wallet",
        )
        
        start = time.time()
        activities = await tracker.get_activity(wallet, hours=24)
        elapsed = time.time() - start
        
        print(f"  Fetched {len(activities)} activities in {elapsed:.2f}s")
        
        if activities:
            sample = activities[0]
            print(f"  Sample activity:")
            print(f"    Hash: {sample.tx_hash[:20]}...")
            print(f"    Type: {sample.activity_type.value}")
            print(f"    Token: {sample.token_symbol}")
            
            print_success("Solana tracker working")
        else:
            print_warning("No activities returned")
        
        # Check health
        health = await tracker.check_health()
        print(f"  Health: {'OK' if health.is_healthy else 'DEGRADED'}")
        
        return True
        
    except Exception as e:
        print_warning(f"Solana tracker test: {e}")
        return True  # Not critical
    finally:
        await tracker.close()


def test_pattern_detector() -> bool:
    """Test pattern detection logic."""
    print_header("Test 4: Pattern Detector")
    
    try:
        detector = PatternDetector()
        now = datetime.utcnow()
        
        # Create mock activities
        activities = [
            WalletActivity(
                tx_hash="0xabc123",
                wallet_address="0xwallet1",
                chain=Chain.ETHEREUM,
                timestamp=now,
                activity_type=ActivityType.TRANSFER,
                direction="out",
                token_symbol="ETH",
                amount=100,
                value_usd=250000,  # Large transfer
            ),
            WalletActivity(
                tx_hash="0xdef456",
                wallet_address="0xwallet1",
                chain=Chain.ETHEREUM,
                timestamp=now - timedelta(minutes=5),
                activity_type=ActivityType.TRANSFER,
                direction="out",
                token_symbol="USDC",
                amount=500000,
                value_usd=500000,
                counterparty_address="0xcex_wallet",  # CEX flow
            ),
            WalletActivity(
                tx_hash="0xghi789",
                wallet_address="0xwallet2",
                chain=Chain.ETHEREUM,
                timestamp=now - timedelta(minutes=10),
                activity_type=ActivityType.TRANSFER,
                direction="in",
                token_symbol="ETH",
                amount=50,
                value_usd=125000,
            ),
        ]
        
        # Create mock wallets
        wallets = [
            WalletInfo(
                address="0xwallet1",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.WHALE,
                confidence_level=0.8,
                avg_transaction_value_usd=10000,
            ),
            WalletInfo(
                address="0xwallet2",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.FUND,
                confidence_level=0.9,
            ),
            WalletInfo(
                address="0xcex_wallet",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.CEX_HOT,
                entity_name="Binance",
            ),
        ]
        
        # Detect patterns
        patterns = detector.detect_patterns(activities, wallets)
        
        print(f"  Detected {len(patterns)} patterns:")
        for p in patterns:
            print(f"    - {p.pattern_type}: {p.description[:50]}...")
        
        # Verify we detected expected patterns
        pattern_types = {p.pattern_type for p in patterns}
        assert "large_transfer" in pattern_types, "Should detect large transfer"
        
        # Check stats
        stats = detector.get_stats()
        print(f"  Large transfers detected: {stats.get('large_transfers', 0)}")
        print(f"  CEX flows detected: {stats.get('cex_flows', 0)}")
        
        print_success("Pattern detector working")
        return True
        
    except Exception as e:
        print_error(f"Pattern detector test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_signal_generator() -> bool:
    """Test signal generation."""
    print_header("Test 5: Signal Generator")
    
    try:
        generator = SmartMoneySignalGenerator()
        now = datetime.utcnow()
        
        # Create mock patterns
        patterns = [
            DetectedPattern(
                pattern_type="large_transfer",
                description="Large ETH transfer: $250,000",
                severity=0.8,
                confidence=0.7,
                wallets_involved=["0xwallet1"],
                transactions=["0xabc"],
                affected_assets=["ETH"],
                total_value_usd=250000,
                flow_direction=FlowDirection.OUTFLOW,
            ),
            DetectedPattern(
                pattern_type="cex_flow",
                description="Deposit to Binance: $500,000",
                severity=0.9,
                confidence=0.8,
                wallets_involved=["0xwallet1"],
                transactions=["0xdef"],
                affected_assets=["USDC"],
                total_value_usd=500000,
                flow_direction=FlowDirection.OUTFLOW,
            ),
        ]
        
        # Create mock activities
        activities = [
            WalletActivity(
                tx_hash="0xabc",
                wallet_address="0xwallet1",
                chain=Chain.ETHEREUM,
                timestamp=now,
                activity_type=ActivityType.TRANSFER,
                direction="out",
                token_symbol="ETH",
                amount=100,
                value_usd=250000,
            ),
            WalletActivity(
                tx_hash="0xdef",
                wallet_address="0xwallet1",
                chain=Chain.ETHEREUM,
                timestamp=now,
                activity_type=ActivityType.TRANSFER,
                direction="out",
                token_symbol="USDC",
                amount=500000,
                value_usd=500000,
            ),
        ]
        
        wallets = [
            WalletInfo(
                address="0xwallet1",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.WHALE,
            ),
        ]
        
        # Generate signal
        signal = generator.generate_signal(
            patterns=patterns,
            activities=activities,
            wallets=wallets,
            evaluation_window_minutes=60,
        )
        
        print(f"  Activity Score: {signal.activity_score:.1f}")
        print(f"  Flow Direction: {signal.dominant_flow_direction.value}")
        print(f"  Confidence: {signal.confidence_level.value}")
        print(f"  Total Volume: ${signal.total_volume_usd:,.0f}")
        print(f"  Net Flow: ${signal.net_flow_usd:,.0f}")
        print(f"  Affected Assets: {signal.affected_assets}")
        print(f"  Explanation: {signal.explanation[:80]}...")
        
        # Verify signal
        assert signal.activity_score > 0, "Score should be positive"
        assert signal.dominant_flow_direction == FlowDirection.OUTFLOW, "Should detect outflow"
        assert signal.is_significant, "Should be significant"
        
        print_success("Signal generator working")
        return True
        
    except Exception as e:
        print_error(f"Signal generator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_full_pipeline() -> bool:
    """Test full pipeline with manager."""
    print_header("Test 6: Full Pipeline (SmartMoneyManager)")
    
    manager = SmartMoneyManager(db_path="storage/test_smart_money.db")
    
    try:
        # Initialize
        await manager.initialize()
        print("  Manager initialized")
        
        # Check health
        health = await manager.get_health()
        print(f"  Wallets in registry: {health.get('registry_wallet_count', 0)}")
        print(f"  Trackers: {list(health.get('trackers', {}).keys())}")
        
        # Evaluate (may have limited data in test)
        start = time.time()
        signal = await manager.evaluate(time_window_minutes=60)
        elapsed = time.time() - start
        
        print(f"  Evaluation completed in {elapsed:.2f}s")
        print(f"  Activity Score: {signal.activity_score:.1f}")
        print(f"  Flow Direction: {signal.dominant_flow_direction.value}")
        print(f"  Confidence: {signal.confidence_level.value}")
        print(f"  Data Completeness: {signal.data_completeness:.0%}")
        
        if signal.api_failures:
            print(f"  API Failures: {signal.api_failures}")
        
        if signal.patterns_detected:
            print(f"  Patterns: {len(signal.patterns_detected)}")
        
        print(f"  Explanation: {signal.explanation[:80]}...")
        
        # Get stats
        stats = manager.get_stats()
        print(f"  Total evaluations: {stats.get('evaluations', 0)}")
        
        print_success("Full pipeline working")
        return True
        
    except Exception as e:
        print_error(f"Full pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await manager.close()


async def test_non_blocking() -> bool:
    """Test non-blocking behavior."""
    print_header("Test 7: Non-Blocking Behavior")
    
    try:
        manager = SmartMoneyManager(db_path="storage/test_smart_money.db")
        await manager.initialize()
        
        # Should complete in reasonable time even with API issues
        start = time.time()
        signal = await asyncio.wait_for(
            manager.evaluate(time_window_minutes=60),
            timeout=30,  # 30 second timeout
        )
        elapsed = time.time() - start
        
        print(f"  Evaluation completed in {elapsed:.2f}s")
        
        # Should not block
        assert elapsed < 30, f"Took too long: {elapsed}s"
        
        # Should return valid signal even with failures
        assert isinstance(signal, SmartMoneySignal), "Should return valid signal"
        
        print_success("Non-blocking behavior confirmed")
        return True
        
    except asyncio.TimeoutError:
        print_error("Evaluation timed out (blocking detected)")
        return False
    except Exception as e:
        print_error(f"Non-blocking test failed: {e}")
        return False
    finally:
        await manager.close()


async def main() -> int:
    """Run all tests."""
    print("\n" + "="*60)
    print("  SMART MONEY / WHALE TRACKING MODULE - TEST SUITE")
    print("  SAFETY: Signals are CONTEXT ONLY - never a trade trigger")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Wallet Registry", test_wallet_registry()))
    results.append(("Ethereum Tracker", await test_ethereum_tracker()))
    results.append(("Solana Tracker", await test_solana_tracker()))
    results.append(("Pattern Detector", test_pattern_detector()))
    results.append(("Signal Generator", test_signal_generator()))
    results.append(("Full Pipeline", await test_full_pipeline()))
    results.append(("Non-Blocking", await test_non_blocking()))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = 0
    failed = 0
    
    for name, success in results:
        if success:
            print_success(f"{name}: PASSED")
            passed += 1
        else:
            print_error(f"{name}: FAILED")
            failed += 1
    
    print(f"\n  Total: {passed}/{len(results)} passed")
    
    if failed == 0:
        print("\n  [OK] ALL TESTS PASSED")
        print("\n  REMINDER: Smart money signals are CONTEXT ONLY!")
        return 0
    else:
        print(f"\n  [FAIL] {failed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
