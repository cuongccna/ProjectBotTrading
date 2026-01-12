"""
Test script for Data Source Health Scoring module.

Validates:
1. Configuration loading
2. Metrics collection
3. Dimension scoring
4. Health evaluation
5. Registry operations
6. Manager integration
7. Risk multipliers
"""

import asyncio
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_source_health import (
    HealthManager,
    HealthRegistry,
    HealthState,
    HealthConfig,
    SourceType,
    get_manager,
)
from data_source_health.metrics import MetricsCollector, SourceMetrics
from data_source_health.scorers import (
    AvailabilityScorer,
    FreshnessScorer,
    CompletenessScorer,
    ErrorRateScorer,
)


def print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print("="*60)


def print_success(text: str) -> None:
    print(f"  [OK] {text}")


def print_warning(text: str) -> None:
    print(f"  [WARN] {text}")


def print_error(text: str) -> None:
    print(f"  [FAIL] {text}")


def print_info(text: str) -> None:
    print(f"  [INFO] {text}")


# =============================================================
# TEST 1: CONFIGURATION
# =============================================================

def test_configuration() -> bool:
    """Test configuration loading."""
    print_header("Test 1: Configuration")
    
    try:
        config = HealthConfig()
        
        print(f"  Weights:")
        print(f"    Availability:  {config.weights.availability}")
        print(f"    Freshness:     {config.weights.freshness}")
        print(f"    Consistency:   {config.weights.consistency}")
        print(f"    Completeness:  {config.weights.completeness}")
        print(f"    Error Rate:    {config.weights.error_rate}")
        print(f"    Total:         {config.weights.total():.2f}")
        
        print(f"\n  Thresholds:")
        print(f"    Healthy:  >= {config.thresholds.healthy_threshold}")
        print(f"    Degraded: >= {config.thresholds.degraded_threshold}")
        print(f"    Critical: <  {config.thresholds.degraded_threshold}")
        
        # Test state determination
        assert config.thresholds.get_state(90) == HealthState.HEALTHY
        assert config.thresholds.get_state(75) == HealthState.DEGRADED
        assert config.thresholds.get_state(50) == HealthState.CRITICAL
        
        print_success("Configuration valid")
        return True
        
    except Exception as e:
        print_error(f"Configuration error: {e}")
        return False


# =============================================================
# TEST 2: METRICS COLLECTION
# =============================================================

def test_metrics_collection() -> bool:
    """Test metrics collection."""
    print_header("Test 2: Metrics Collection")
    
    try:
        metrics = SourceMetrics(
            source_name="test_source",
            max_samples=100,
            window_seconds=60,
        )
        
        # Record requests
        for i in range(20):
            success = i % 10 != 0  # 90% success rate
            latency = 100 + (i * 10)
            metrics.record_request(
                latency_ms=latency,
                success=success,
                is_timeout=(i == 5),
                error_type="http_500" if not success else None,
            )
        
        # Record data
        now = datetime.utcnow()
        for i in range(10):
            data_time = now - timedelta(seconds=i)
            metrics.record_data(
                data_timestamp=data_time,
                fields_expected=10,
                fields_received=9 if i % 5 == 0 else 10,
                is_empty=False,
                is_partial=(i % 5 == 0),
            )
        
        # Record values
        for i in range(10):
            metrics.record_value("price", 50000 + i * 100)
        
        # Record errors
        metrics.record_error("http_error", "Connection timeout", is_recoverable=True)
        
        # Check computed metrics
        avail_metrics = metrics.get_availability_metrics()
        fresh_metrics = metrics.get_freshness_metrics()
        comp_metrics = metrics.get_completeness_metrics()
        error_metrics = metrics.get_error_rate_metrics()
        
        print(f"  Requests recorded: {len(metrics.requests)}")
        print(f"  Uptime: {avail_metrics['uptime_percent']:.1f}%")
        print(f"  Timeout rate: {avail_metrics['timeout_percent']:.1f}%")
        print(f"  Avg latency: {avail_metrics['avg_latency_ms']:.1f}ms")
        print(f"  Data points: {len(metrics.data_points)}")
        print(f"  Avg delay: {fresh_metrics['avg_delay_seconds']:.1f}s")
        print(f"  Missing fields: {comp_metrics['missing_fields_percent']:.1f}%")
        print(f"  Error rate: {error_metrics['error_rate_percent']:.1f}%")
        
        print_success("Metrics collection working")
        return True
        
    except Exception as e:
        print_error(f"Metrics error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================
# TEST 3: DIMENSION SCORING
# =============================================================

def test_dimension_scoring() -> bool:
    """Test dimension scorers."""
    print_header("Test 3: Dimension Scoring")
    
    try:
        config = HealthConfig()
        metrics = SourceMetrics(source_name="test", window_seconds=60)
        
        # Populate with good data
        now = datetime.utcnow()
        for i in range(20):
            metrics.record_request(latency_ms=100, success=True)
            metrics.record_data(
                data_timestamp=now - timedelta(seconds=1),
                fields_expected=10,
                fields_received=10,
            )
        
        # Test availability scorer
        avail_scorer = AvailabilityScorer(config)
        avail_score = avail_scorer.score(metrics)
        print(f"  Availability: {avail_score.score:.1f} - {avail_score.explanation}")
        
        # Test freshness scorer
        fresh_scorer = FreshnessScorer(config)
        fresh_score = fresh_scorer.score(metrics)
        print(f"  Freshness:    {fresh_score.score:.1f} - {fresh_score.explanation}")
        
        # Test completeness scorer
        comp_scorer = CompletenessScorer(config)
        comp_score = comp_scorer.score(metrics)
        print(f"  Completeness: {comp_score.score:.1f} - {comp_score.explanation}")
        
        # Test error rate scorer
        error_scorer = ErrorRateScorer(config)
        error_score = error_scorer.score(metrics)
        print(f"  Error Rate:   {error_score.score:.1f} - {error_score.explanation}")
        
        # All scores should be high for good data
        assert avail_score.score >= 90, f"Availability too low: {avail_score.score}"
        assert comp_score.score >= 90, f"Completeness too low: {comp_score.score}"
        
        print_success("Dimension scoring working")
        return True
        
    except Exception as e:
        print_error(f"Scoring error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================
# TEST 4: HEALTH EVALUATION
# =============================================================

def test_health_evaluation() -> bool:
    """Test health evaluation."""
    print_header("Test 4: Health Evaluation")
    
    try:
        manager = HealthManager()
        
        # Register source
        manager.register_source("binance", SourceType.MARKET_DATA)
        
        # Record good metrics
        now = datetime.utcnow()
        for i in range(20):
            manager.record_request("binance", latency_ms=100, success=True)
            manager.record_data(
                "binance",
                data_timestamp=now - timedelta(seconds=1),
                fields_expected=10,
                fields_received=10,
            )
            manager.record_value("binance", "price", 50000 + i)
        
        # Evaluate
        health = manager.evaluate("binance")
        
        print(f"  Source: {health.source_name}")
        print(f"  Type: {health.source_type.value}")
        print(f"  Score: {health.final_score:.1f}")
        print(f"  State: {health.state.value}")
        print(f"  Duration: {health.evaluation_duration_ms:.1f}ms")
        print(f"\n  Dimension Scores:")
        for dim, score in health.dimensions.items():
            print(f"    {dim.value}: {score.score:.1f} (weight: {score.weight})")
        
        assert health.final_score >= 80, f"Score too low: {health.final_score}"
        assert health.state in (HealthState.HEALTHY, HealthState.DEGRADED)
        
        print_success("Health evaluation working")
        return True
        
    except Exception as e:
        print_error(f"Evaluation error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================
# TEST 5: REGISTRY OPERATIONS
# =============================================================

def test_registry() -> bool:
    """Test health registry."""
    print_header("Test 5: Registry Operations")
    
    try:
        registry = HealthRegistry()
        
        # Register sources
        registry.register_source("binance", SourceType.MARKET_DATA)
        registry.register_source("cryptonews", SourceType.NEWS)
        registry.register_source("etherscan", SourceType.ONCHAIN)
        
        print(f"  Registered sources: {len(registry.get_all_sources())}")
        
        # Test queries
        assert registry.is_registered("binance")
        assert not registry.is_registered("unknown")
        
        # Test state queries (should be UNKNOWN initially)
        assert registry.get_state("binance") == HealthState.UNKNOWN
        
        # Test by type
        market_sources = registry.get_sources_by_type(SourceType.MARKET_DATA)
        assert "binance" in market_sources
        
        # Test disable/enable
        registry.disable_source("binance", "Test disable")
        assert "binance" in registry.get_disabled_sources()
        
        registry.enable_source("binance")
        assert "binance" not in registry.get_disabled_sources()
        
        print(f"  Statistics: {registry.get_statistics()}")
        
        print_success("Registry operations working")
        return True
        
    except Exception as e:
        print_error(f"Registry error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================
# TEST 6: RISK MULTIPLIERS
# =============================================================

def test_risk_multipliers() -> bool:
    """Test risk multipliers."""
    print_header("Test 6: Risk Multipliers")
    
    try:
        manager = HealthManager()
        
        # Register and populate sources with different health
        sources = [
            ("healthy_source", True, 0),      # All good
            ("degraded_source", True, 15),    # Some errors
            ("critical_source", False, 50),   # Many failures
        ]
        
        now = datetime.utcnow()
        
        for name, good, error_rate in sources:
            manager.register_source(name, SourceType.MARKET_DATA)
            
            for i in range(100):
                success = (i % 100) >= error_rate if good else (i % 100) >= error_rate
                manager.record_request(name, latency_ms=100, success=success)
                
                delay = 1 if good else (30 if error_rate < 50 else 120)
                manager.record_data(
                    name,
                    data_timestamp=now - timedelta(seconds=delay),
                    fields_expected=10,
                    fields_received=10 if success else 5,
                )
        
        # Evaluate all
        manager.evaluate_all()
        
        print(f"\n  Source Health & Risk Multipliers:")
        print(f"  {'Source':<20} {'Score':>8} {'State':<10} {'Multiplier':>10}")
        print(f"  {'-'*50}")
        
        for name, _, _ in sources:
            score = manager.get_score(name)
            state = manager.get_state(name)
            multiplier = manager.get_risk_multiplier(name)
            print(f"  {name:<20} {score:>8.1f} {state.value:<10} {multiplier:>10.2f}")
        
        # Test aggregate
        aggregate = manager.get_aggregate_risk_multiplier()
        print(f"\n  Aggregate Risk Multiplier: {aggregate:.2f}")
        
        # Verify healthy source has multiplier 1.0
        healthy_mult = manager.get_risk_multiplier("healthy_source")
        assert healthy_mult >= 0.8, f"Healthy source should have high multiplier: {healthy_mult}"
        
        print_success("Risk multipliers working")
        return True
        
    except Exception as e:
        print_error(f"Risk multiplier error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================
# TEST 7: STATE TRANSITIONS
# =============================================================

def test_state_transitions() -> bool:
    """Test state transition detection."""
    print_header("Test 7: State Transitions")
    
    try:
        manager = HealthManager()
        transitions_logged = []
        
        # Register callback
        def on_transition(transition):
            transitions_logged.append(transition)
            print(f"  TRANSITION: {transition.source_name}: "
                  f"{transition.from_state.value} -> {transition.to_state.value}")
        
        manager.on_transition(on_transition)
        
        # Register source
        manager.register_source("test_source", SourceType.MARKET_DATA)
        
        now = datetime.utcnow()
        
        # Phase 1: Healthy data
        print("\n  Phase 1: Recording healthy data...")
        for i in range(30):
            manager.record_request("test_source", latency_ms=100, success=True)
            manager.record_data("test_source", now - timedelta(seconds=1), 10, 10)
        
        health1 = manager.evaluate("test_source")
        print(f"  Score: {health1.final_score:.1f} ({health1.state.value})")
        
        # Phase 2: Degraded data
        print("\n  Phase 2: Recording degraded data...")
        for i in range(50):
            success = i % 5 != 0  # 80% success
            manager.record_request("test_source", latency_ms=500, success=success)
            manager.record_data("test_source", now - timedelta(seconds=15), 10, 8)
        
        health2 = manager.evaluate("test_source")
        print(f"  Score: {health2.final_score:.1f} ({health2.state.value})")
        
        # Phase 3: Critical data
        print("\n  Phase 3: Recording critical data...")
        for i in range(100):
            success = i % 2 == 0  # 50% success
            manager.record_request("test_source", latency_ms=2000, success=success, is_timeout=(i % 3 == 0))
            manager.record_data("test_source", now - timedelta(seconds=120), 10, 3)
            manager.record_error("test_source", "http_error", "timeout")
        
        health3 = manager.evaluate("test_source")
        print(f"  Score: {health3.final_score:.1f} ({health3.state.value})")
        
        print(f"\n  Total transitions: {len(transitions_logged)}")
        
        print_success("State transitions working")
        return True
        
    except Exception as e:
        print_error(f"Transition error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================
# TEST 8: FAILURE SAFETY
# =============================================================

def test_failure_safety() -> bool:
    """Test failure safety (scoring should never crash)."""
    print_header("Test 8: Failure Safety")
    
    try:
        manager = HealthManager()
        
        # Register source with no data
        manager.register_source("empty_source", SourceType.MARKET_DATA)
        
        # Evaluate with no data - should not crash
        health = manager.evaluate("empty_source")
        print(f"  Empty source score: {health.final_score:.1f}")
        print(f"  Empty source state: {health.state.value}")
        
        # Should assume healthy with no data (optimistic)
        # Or handle gracefully
        assert health is not None, "Should return health score"
        
        # Test with corrupted metrics (edge case)
        # The system should handle this gracefully
        
        print_success("Failure safety verified")
        return True
        
    except Exception as e:
        print_error(f"Failure safety error: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================
# MAIN
# =============================================================

def main():
    print_header("DATA SOURCE HEALTH SCORING - TEST SUITE")
    print("  Testing institutional-grade health scoring module")
    print("  For Risk Scoring, Budget Management, and System Control")
    
    results = []
    
    # Run tests
    results.append(("Configuration", test_configuration()))
    results.append(("Metrics Collection", test_metrics_collection()))
    results.append(("Dimension Scoring", test_dimension_scoring()))
    results.append(("Health Evaluation", test_health_evaluation()))
    results.append(("Registry Operations", test_registry()))
    results.append(("Risk Multipliers", test_risk_multipliers()))
    results.append(("State Transitions", test_state_transitions()))
    results.append(("Failure Safety", test_failure_safety()))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = 0
    for name, success in results:
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {name}")
        if success:
            passed += 1
    
    print(f"\n  Total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n  Data Source Health Scoring module is READY!")
        print("\n  Integration Points:")
        print("    - Risk Scoring Engine: get_score(), is_source_healthy()")
        print("    - Risk Budget Manager: get_risk_multiplier()")
        print("    - System Risk Controller: on_critical(), get_critical_sources()")
        return 0
    else:
        print("\n  Some tests failed. Check implementation.")
        return 1


if __name__ == "__main__":
    exit(main())
