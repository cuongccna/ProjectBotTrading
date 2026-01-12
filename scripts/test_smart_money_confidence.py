"""
Smart Money Confidence - Test Script.

============================================================
COMPREHENSIVE TEST COVERAGE
============================================================

Tests all components of the Smart Money Confidence module:
1. Models and enums
2. Configuration
3. WalletConfidenceModel
4. NoiseFilter
5. ClusterAnalyzer
6. ConfidenceWeightCalculator
7. ConfidenceEngine
8. Integration tests

============================================================
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List
import traceback

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from smart_money_confidence import (
    # Models
    EntityType,
    ConfidenceLevel,
    BehaviorType,
    ActivityType,
    DataSource,
    WalletProfile,
    ActivityRecord,
    ClusterSignal,
    ConfidenceOutput,
    MarketContext,
    # Config
    ConfidenceConfig,
    EntityWeights,
    NoiseFilterConfig,
    ClusterConfig,
    get_default_config,
    # Exceptions
    SmartMoneyConfidenceError,
    InsufficientDataError,
    # Components
    WalletConfidenceModel,
    NoiseFilter,
    ClusterAnalyzer,
    ConfidenceWeightCalculator,
    ConfidenceEngine,
)


# =============================================================
# TEST UTILITIES
# =============================================================


class TestResult:
    """Test result container."""
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []
    
    def record(self, success: bool, message: str = ""):
        if success:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(message)
    
    @property
    def total(self) -> int:
        return self.passed + self.failed
    
    def __str__(self) -> str:
        status = "✓" if self.failed == 0 else "✗"
        return f"{status} {self.name}: {self.passed}/{self.total} passed"


def assert_true(condition: bool, message: str, result: TestResult):
    """Assert that condition is true."""
    result.record(condition, message if not condition else "")
    if not condition:
        print(f"  ✗ FAILED: {message}")
    return condition


def assert_equal(actual, expected, message: str, result: TestResult):
    """Assert equality."""
    condition = actual == expected
    full_message = f"{message}: expected {expected}, got {actual}"
    result.record(condition, full_message if not condition else "")
    if not condition:
        print(f"  ✗ FAILED: {full_message}")
    return condition


def assert_in_range(value: float, min_val: float, max_val: float, message: str, result: TestResult):
    """Assert value is in range."""
    condition = min_val <= value <= max_val
    full_message = f"{message}: {value} not in range [{min_val}, {max_val}]"
    result.record(condition, full_message if not condition else "")
    if not condition:
        print(f"  ✗ FAILED: {full_message}")
    return condition


# =============================================================
# TEST DATA GENERATORS
# =============================================================


def create_test_activity(
    wallet: str = "0xWallet1",
    activity_type: ActivityType = ActivityType.BUY,
    token: str = "BTC",
    amount_usd: float = 100_000,
    hours_ago: float = 0,
) -> ActivityRecord:
    """Create test activity record."""
    return ActivityRecord(
        wallet_address=wallet,
        activity_type=activity_type,
        token=token,
        amount_usd=amount_usd,
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
    )


def create_test_activities(
    count: int = 5,
    behavior: BehaviorType = BehaviorType.ACCUMULATION,
    token: str = "BTC",
    unique_wallets: int = 3,
) -> List[ActivityRecord]:
    """Create a list of test activities."""
    activities = []
    
    for i in range(count):
        wallet = f"0xWallet{i % unique_wallets}"
        
        if behavior == BehaviorType.ACCUMULATION:
            activity_type = ActivityType.BUY
        elif behavior == BehaviorType.DISTRIBUTION:
            activity_type = ActivityType.SELL
        else:
            activity_type = ActivityType.BUY if i % 2 == 0 else ActivityType.SELL
        
        activities.append(create_test_activity(
            wallet=wallet,
            activity_type=activity_type,
            token=token,
            amount_usd=100_000 + (i * 10_000),
            hours_ago=i * 0.5,
        ))
    
    return activities


# =============================================================
# TESTS: MODELS
# =============================================================


def test_models() -> TestResult:
    """Test data models."""
    result = TestResult("Models")
    print("\n" + "=" * 60)
    print("Testing Models...")
    print("=" * 60)
    
    # Test EntityType
    assert_equal(
        EntityType.FUND.get_base_credibility(), 0.9,
        "FUND credibility", result
    )
    assert_equal(
        EntityType.UNKNOWN.get_base_credibility(), 0.2,
        "UNKNOWN credibility", result
    )
    
    # Test ConfidenceLevel
    assert_equal(
        ConfidenceLevel.from_score(80), ConfidenceLevel.HIGH,
        "High confidence from score 80", result
    )
    assert_equal(
        ConfidenceLevel.from_score(50), ConfidenceLevel.MEDIUM,
        "Medium confidence from score 50", result
    )
    assert_equal(
        ConfidenceLevel.from_score(30), ConfidenceLevel.LOW,
        "Low confidence from score 30", result
    )
    
    # Test ActivityType
    assert_true(
        ActivityType.BUY.is_bullish(),
        "BUY should be bullish", result
    )
    assert_true(
        ActivityType.SELL.is_bearish(),
        "SELL should be bearish", result
    )
    
    # Test DataSource
    assert_true(
        DataSource.ARKHAM.get_reliability() > DataSource.UNKNOWN.get_reliability(),
        "ARKHAM more reliable than UNKNOWN", result
    )
    
    # Test ActivityRecord
    activity = create_test_activity(amount_usd=150_000)
    assert_true(
        activity.is_significant,
        "Activity > $100k should be significant", result
    )
    
    activity_whale = create_test_activity(amount_usd=1_500_000)
    assert_true(
        activity_whale.is_whale_sized,
        "Activity > $1M should be whale-sized", result
    )
    
    # Test WalletProfile
    profile = WalletProfile(
        address="0xTest",
        entity_type=EntityType.FUND,
        verified=True,
    )
    assert_equal(profile.entity_type, EntityType.FUND, "Profile entity type", result)
    
    # Test ConfidenceOutput
    output = ConfidenceOutput.neutral("BTC", "Test reason")
    assert_equal(output.score, 50.0, "Neutral score", result)
    assert_equal(output.level, ConfidenceLevel.LOW, "Neutral level", result)
    
    print(f"\n{result}")
    return result


# =============================================================
# TESTS: CONFIGURATION
# =============================================================


def test_configuration() -> TestResult:
    """Test configuration."""
    result = TestResult("Configuration")
    print("\n" + "=" * 60)
    print("Testing Configuration...")
    print("=" * 60)
    
    # Test default config
    config = get_default_config()
    assert_true(config is not None, "Default config exists", result)
    
    # Test entity weights
    weights = config.entity_weights
    assert_equal(weights.fund, 1.0, "Fund weight", result)
    assert_true(weights.fund > weights.whale, "Fund > Whale weight", result)
    
    # Test noise filter config
    nf = config.noise_filter
    assert_true(nf.filter_dust_transactions, "Dust filtering enabled", result)
    assert_equal(nf.dust_threshold_usd, 100.0, "Dust threshold", result)
    
    # Test cluster config
    cc = config.cluster
    assert_true(cc.enabled, "Clustering enabled", result)
    assert_equal(cc.min_cluster_size, 3, "Min cluster size", result)
    
    # Test thresholds
    th = config.thresholds
    assert_true(th.low_max < th.medium_max, "LOW < MEDIUM threshold", result)
    
    # Test to_dict
    config_dict = config.to_dict()
    assert_true('entity_weights' in config_dict, "Config has entity_weights", result)
    
    print(f"\n{result}")
    return result


# =============================================================
# TESTS: WALLET MODEL
# =============================================================


def test_wallet_model() -> TestResult:
    """Test WalletConfidenceModel."""
    result = TestResult("WalletConfidenceModel")
    print("\n" + "=" * 60)
    print("Testing WalletConfidenceModel...")
    print("=" * 60)
    
    model = WalletConfidenceModel()
    
    # Test profile creation
    profile = model.set_profile(
        address="0xFund1",
        entity_type=EntityType.FUND,
        entity_name="Test Fund",
        verified=True,
    )
    assert_equal(profile.entity_type, EntityType.FUND, "Profile entity type", result)
    assert_true(profile.verified, "Profile verified", result)
    
    # Test profile retrieval
    retrieved = model.get_profile("0xFund1")
    assert_true(retrieved is not None, "Profile retrieved", result)
    assert_equal(retrieved.entity_name, "Test Fund", "Profile name", result)
    
    # Test confidence calculation
    confidence = model.get_confidence_score("0xFund1")
    assert_in_range(confidence, 0, 100, "Confidence in range", result)
    
    # Test activity recording
    activity = create_test_activity(wallet="0xFund1")
    updated_profile = model.record_activity(activity)
    assert_equal(updated_profile.total_activities, 1, "Activity count", result)
    
    # Test behavior tracking
    for _ in range(5):
        model.record_activity(create_test_activity(
            wallet="0xFund1",
            activity_type=ActivityType.BUY,
        ))
    
    profile = model.get_profile("0xFund1")
    assert_equal(
        profile.dominant_behavior, BehaviorType.ACCUMULATION,
        "Dominant behavior", result
    )
    
    # Test unknown wallet
    unknown = model.get_or_create_profile("0xUnknown")
    assert_equal(unknown.entity_type, EntityType.UNKNOWN, "Unknown type", result)
    
    # Test export/import
    exported = model.export_profiles()
    assert_true(len(exported) > 0, "Profiles exported", result)
    
    print(f"\n{result}")
    return result


# =============================================================
# TESTS: NOISE FILTER
# =============================================================


def test_noise_filter() -> TestResult:
    """Test NoiseFilter."""
    result = TestResult("NoiseFilter")
    print("\n" + "=" * 60)
    print("Testing NoiseFilter...")
    print("=" * 60)
    
    nf = NoiseFilter()
    
    # Test dust filtering
    dust_activity = create_test_activity(amount_usd=50)  # Below $100 threshold
    noise_result = nf.analyze_activity(dust_activity, [dust_activity], None)
    assert_true(noise_result.is_noise, "Dust detected as noise", result)
    assert_equal(noise_result.noise_type, "dust", "Noise type is dust", result)
    
    # Test significant activity not filtered
    significant = create_test_activity(amount_usd=500_000)
    noise_result = nf.analyze_activity(significant, [significant], None)
    assert_true(not noise_result.is_noise, "Significant activity not noise", result)
    
    # Test round-trip detection
    buy = create_test_activity(
        wallet="0xRoundTrip",
        activity_type=ActivityType.BUY,
        amount_usd=100_000,
        hours_ago=0,
    )
    sell = create_test_activity(
        wallet="0xRoundTrip",
        activity_type=ActivityType.SELL,
        amount_usd=100_000,
        hours_ago=1,  # Within 4 hour window
    )
    
    all_activities = [buy, sell]
    noise_result = nf.analyze_activity(buy, all_activities, None)
    assert_true(noise_result.is_noise, "Round-trip detected", result)
    assert_equal(noise_result.noise_type, "round_trip", "Noise type is round_trip", result)
    
    # Test batch filtering
    activities = [
        create_test_activity(amount_usd=50),   # Dust
        create_test_activity(amount_usd=500_000),  # Valid
        create_test_activity(amount_usd=300_000),  # Valid
    ]
    
    filtered, stats = nf.filter_activities(activities, None)
    assert_equal(len(filtered), 2, "Two activities remain", result)
    assert_equal(stats.dust_filtered, 1, "One dust filtered", result)
    
    print(f"\n{result}")
    return result


# =============================================================
# TESTS: CLUSTER ANALYZER
# =============================================================


def test_cluster_analyzer() -> TestResult:
    """Test ClusterAnalyzer."""
    result = TestResult("ClusterAnalyzer")
    print("\n" + "=" * 60)
    print("Testing ClusterAnalyzer...")
    print("=" * 60)
    
    analyzer = ClusterAnalyzer()
    
    # Test with no activities
    signals = analyzer.analyze([])
    assert_equal(len(signals), 0, "No signals from empty list", result)
    
    # Test with insufficient activities
    small_list = [create_test_activity()]
    signals = analyzer.analyze(small_list)
    assert_equal(len(signals), 0, "No signals from single activity", result)
    
    # Test cluster detection
    # Create activities from multiple wallets, same direction, same time
    now = datetime.utcnow()
    cluster_activities = [
        ActivityRecord(
            wallet_address=f"0xWallet{i}",
            activity_type=ActivityType.BUY,
            token="ETH",
            amount_usd=200_000,
            timestamp=now - timedelta(minutes=i * 10),  # Within 1 hour
        )
        for i in range(5)
    ]
    
    signals = analyzer.analyze(cluster_activities)
    # Should detect at least one cluster
    assert_true(len(signals) >= 1, "Cluster detected", result)
    
    if signals:
        signal = signals[0]
        assert_true(signal.wallet_count >= 3, "Cluster has 3+ wallets", result)
        assert_equal(signal.dominant_behavior, BehaviorType.ACCUMULATION, "Cluster behavior", result)
        assert_true(signal.behavior_alignment >= 0.7, "High alignment", result)
    
    # Test cluster boost
    boost, sigs = analyzer.get_cluster_boost(cluster_activities, None)
    assert_true(boost > 0, "Positive cluster boost", result)
    
    # Test dominant behavior
    behavior, alignment = analyzer.get_dominant_behavior(cluster_activities)
    assert_equal(behavior, BehaviorType.ACCUMULATION, "Dominant behavior", result)
    
    print(f"\n{result}")
    return result


# =============================================================
# TESTS: CALCULATOR
# =============================================================


def test_calculator() -> TestResult:
    """Test ConfidenceWeightCalculator."""
    result = TestResult("ConfidenceWeightCalculator")
    print("\n" + "=" * 60)
    print("Testing ConfidenceWeightCalculator...")
    print("=" * 60)
    
    calc = ConfidenceWeightCalculator()
    
    # Register some wallets
    calc.wallet_model.set_profile(
        address="0xFund1",
        entity_type=EntityType.FUND,
        entity_name="Test Fund",
        verified=True,
    )
    calc.wallet_model.set_profile(
        address="0xWhale1",
        entity_type=EntityType.WHALE,
    )
    
    # Test with no activities
    output = calc.calculate("BTC", [])
    assert_equal(output.level, ConfidenceLevel.LOW, "No activities = low", result)
    assert_true("No activities" in output.explanation, "Explanation mentions no activities", result)
    
    # Test with known fund wallet
    fund_activities = [
        create_test_activity(wallet="0xFund1", amount_usd=500_000),
        create_test_activity(wallet="0xFund1", amount_usd=300_000),
        create_test_activity(wallet="0xFund1", amount_usd=400_000),
    ]
    
    output = calc.calculate("BTC", fund_activities)
    assert_in_range(output.score, 0, 100, "Score in range", result)
    assert_true(output.entity_credibility_score > 50, "High credibility for fund", result)
    
    # Test with unknown wallets
    unknown_activities = [
        create_test_activity(wallet="0xUnknown1", amount_usd=500_000),
        create_test_activity(wallet="0xUnknown2", amount_usd=300_000),
        create_test_activity(wallet="0xUnknown3", amount_usd=400_000),
    ]
    
    output_unknown = calc.calculate("BTC", unknown_activities)
    assert_true(
        output_unknown.entity_credibility_score < output.entity_credibility_score,
        "Unknown has lower credibility", result
    )
    
    # Test with market context
    context = MarketContext(
        token="BTC",
        trend_direction="down",
        near_support=True,
    )
    
    output_context = calc.calculate("BTC", fund_activities, context)
    assert_true(
        output_context.context_alignment_score >= 50,
        "Context alignment calculated", result
    )
    
    # Test output structure
    assert_true(output.token == "BTC", "Token set", result)
    assert_true(output.total_activities_analyzed > 0, "Activities counted", result)
    assert_true(output.wallets_involved > 0, "Wallets counted", result)
    assert_true(output.total_volume_usd > 0, "Volume calculated", result)
    
    print(f"\n{result}")
    return result


# =============================================================
# TESTS: ENGINE
# =============================================================


def test_engine() -> TestResult:
    """Test ConfidenceEngine."""
    result = TestResult("ConfidenceEngine")
    print("\n" + "=" * 60)
    print("Testing ConfidenceEngine...")
    print("=" * 60)
    
    engine = ConfidenceEngine()
    
    # Test status
    status = engine.get_status()
    assert_equal(status['status'], 'healthy', "Engine healthy", result)
    
    # Test wallet registration
    profile = engine.register_wallet(
        address="0xTestFund",
        entity_type=EntityType.FUND,
        entity_name="Integration Test Fund",
        verified=True,
    )
    assert_equal(profile.entity_name, "Integration Test Fund", "Wallet registered", result)
    
    # Test bulk registration
    count = engine.register_wallets_bulk([
        {'address': '0xBulk1', 'entity_type': 'whale'},
        {'address': '0xBulk2', 'entity_type': 'market_maker'},
    ])
    assert_equal(count, 2, "Bulk registration", result)
    
    # Test wallet confidence
    confidence = engine.get_wallet_confidence("0xTestFund")
    assert_in_range(confidence, 0, 100, "Wallet confidence", result)
    
    # Test activity recording
    activity = create_test_activity(wallet="0xTestFund")
    engine.record_activity(activity)
    profile = engine.get_wallet_profile("0xTestFund")
    assert_equal(profile.total_activities, 1, "Activity recorded", result)
    
    # Test confidence calculation
    activities = create_test_activities(count=5, unique_wallets=3)
    output = engine.calculate_confidence("ETH", activities)
    
    assert_true(output is not None, "Output generated", result)
    assert_in_range(output.score, 0, 100, "Output score in range", result)
    assert_true(output.level in ConfidenceLevel, "Valid confidence level", result)
    assert_true(output.dominant_behavior in BehaviorType, "Valid behavior type", result)
    
    # Test quick score
    quick = engine.quick_score("ETH", activities)
    assert_equal(quick, output.score, "Quick score matches", result)
    
    # Test risk adjustment
    risk_adj = engine.get_risk_adjustment("ETH", activities)
    assert_in_range(risk_adj, 0.5, 1.5, "Risk adjustment in range", result)
    
    # Test noise management
    engine.add_cex_address("0xBinance")
    engine.add_bridge_address("0xBridge")
    
    # Test cluster analysis
    clusters = engine.analyze_clusters(activities)
    assert_true(isinstance(clusters, list), "Clusters returned", result)
    
    # Test noise filtering
    filtered, stats = engine.filter_noise(activities)
    assert_true(isinstance(filtered, list), "Filtered list returned", result)
    
    # Test export
    exported = engine.export_profiles()
    assert_true(len(exported) > 0, "Profiles exported", result)
    
    print(f"\n{result}")
    return result


# =============================================================
# TESTS: INTEGRATION
# =============================================================


def test_integration() -> TestResult:
    """Integration test: realistic scenario."""
    result = TestResult("Integration")
    print("\n" + "=" * 60)
    print("Testing Integration Scenario...")
    print("=" * 60)
    
    # Create engine
    engine = ConfidenceEngine()
    
    # Register known entities
    engine.register_wallet("0xFund1", EntityType.FUND, "Alpha Capital", verified=True)
    engine.register_wallet("0xFund2", EntityType.FUND, "Beta Ventures", verified=True)
    engine.register_wallet("0xMM1", EntityType.MARKET_MAKER, "MM Corp")
    engine.register_wallet("0xWhale1", EntityType.WHALE)
    
    # Add CEX addresses
    engine.import_cex_addresses(["0xBinance", "0xCoinbase"])
    
    # Simulate accumulation scenario
    # Multiple funds and whales buying BTC
    now = datetime.utcnow()
    accumulation_activities = [
        # Fund 1 - large buys
        ActivityRecord("0xFund1", ActivityType.BUY, "BTC", 2_000_000, now - timedelta(hours=1)),
        ActivityRecord("0xFund1", ActivityType.BUY, "BTC", 1_500_000, now - timedelta(hours=2)),
        # Fund 2 - large buys
        ActivityRecord("0xFund2", ActivityType.BUY, "BTC", 1_800_000, now - timedelta(hours=1.5)),
        # Market maker
        ActivityRecord("0xMM1", ActivityType.BUY, "BTC", 500_000, now - timedelta(hours=1)),
        # Whale
        ActivityRecord("0xWhale1", ActivityType.BUY, "BTC", 800_000, now - timedelta(hours=2)),
    ]
    
    # Calculate confidence with bullish context
    context = MarketContext(
        token="BTC",
        trend_direction="down",
        near_support=True,
        volatility_percentile=30,  # Low volatility
    )
    
    output = engine.calculate_confidence("BTC", accumulation_activities, context)
    
    print(f"\n  Accumulation Scenario:")
    print(f"    Score: {output.score:.1f}")
    print(f"    Level: {output.level.value}")
    print(f"    Behavior: {output.dominant_behavior.value}")
    print(f"    Risk Adjustment: {output.get_risk_adjustment():.2f}")
    print(f"    Explanation: {output.explanation[:100]}...")
    
    # Validate accumulation scenario
    assert_true(
        output.dominant_behavior == BehaviorType.ACCUMULATION,
        "Detected accumulation", result
    )
    assert_true(
        output.level in (ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH),
        "Medium or high confidence", result
    )
    assert_true(
        output.entity_credibility_score > 60,
        "High entity credibility (funds)", result
    )
    
    # Simulate distribution scenario
    distribution_activities = [
        ActivityRecord("0xFund1", ActivityType.SELL, "ETH", 3_000_000, now - timedelta(hours=1)),
        ActivityRecord("0xFund2", ActivityType.SELL, "ETH", 2_500_000, now - timedelta(hours=1.5)),
        ActivityRecord("0xWhale1", ActivityType.SELL, "ETH", 1_000_000, now - timedelta(hours=2)),
    ]
    
    output_dist = engine.calculate_confidence("ETH", distribution_activities)
    
    print(f"\n  Distribution Scenario:")
    print(f"    Score: {output_dist.score:.1f}")
    print(f"    Level: {output_dist.level.value}")
    print(f"    Behavior: {output_dist.dominant_behavior.value}")
    print(f"    Risk Adjustment: {output_dist.get_risk_adjustment():.2f}")
    
    assert_true(
        output_dist.dominant_behavior == BehaviorType.DISTRIBUTION,
        "Detected distribution", result
    )
    assert_true(
        output_dist.get_risk_adjustment() < 1.0,
        "Risk adjustment reduced for distribution", result
    )
    
    # Simulate noisy scenario (dust + round trips)
    noisy_activities = [
        ActivityRecord("0xNoisy", ActivityType.BUY, "SOL", 50, now),  # Dust
        ActivityRecord("0xNoisy", ActivityType.SELL, "SOL", 50, now),  # Round trip
        ActivityRecord("0xNoisy", ActivityType.BUY, "SOL", 100_000, now - timedelta(hours=1)),
    ]
    
    output_noisy = engine.calculate_confidence("SOL", noisy_activities)
    
    print(f"\n  Noisy Scenario:")
    print(f"    Score: {output_noisy.score:.1f}")
    print(f"    Warnings: {output_noisy.warnings}")
    
    # Noisy data should have low confidence or warnings
    assert_true(
        output_noisy.noise_penalty > 0 or len(output_noisy.warnings) > 0,
        "Noise detected", result
    )
    
    print(f"\n{result}")
    return result


# =============================================================
# MAIN
# =============================================================


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SMART MONEY CONFIDENCE - TEST SUITE")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(test_models())
    except Exception as e:
        print(f"✗ Models tests failed with exception: {e}")
        traceback.print_exc()
    
    try:
        results.append(test_configuration())
    except Exception as e:
        print(f"✗ Configuration tests failed with exception: {e}")
        traceback.print_exc()
    
    try:
        results.append(test_wallet_model())
    except Exception as e:
        print(f"✗ WalletConfidenceModel tests failed with exception: {e}")
        traceback.print_exc()
    
    try:
        results.append(test_noise_filter())
    except Exception as e:
        print(f"✗ NoiseFilter tests failed with exception: {e}")
        traceback.print_exc()
    
    try:
        results.append(test_cluster_analyzer())
    except Exception as e:
        print(f"✗ ClusterAnalyzer tests failed with exception: {e}")
        traceback.print_exc()
    
    try:
        results.append(test_calculator())
    except Exception as e:
        print(f"✗ Calculator tests failed with exception: {e}")
        traceback.print_exc()
    
    try:
        results.append(test_engine())
    except Exception as e:
        print(f"✗ Engine tests failed with exception: {e}")
        traceback.print_exc()
    
    try:
        results.append(test_integration())
    except Exception as e:
        print(f"✗ Integration tests failed with exception: {e}")
        traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total = total_passed + total_failed
    
    for r in results:
        print(r)
    
    print("-" * 60)
    print(f"TOTAL: {total_passed}/{total} passed")
    
    if total_failed == 0:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n✗ {total_failed} TESTS FAILED")
        for r in results:
            for error in r.errors:
                print(f"  - {error}")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
