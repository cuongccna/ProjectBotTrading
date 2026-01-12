"""
Smart Money Manager - Main orchestrator for the module.

Coordinates:
- Wallet registry
- On-chain trackers
- Pattern detection
- Signal generation

SAFETY: All output is CONTEXT ONLY for Flow Scoring.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from .config import SmartMoneyConfig, get_config
from .detector import PatternDetector
from .models import Chain, SmartMoneySignal, WalletActivity, WalletInfo
from .registry import WalletRegistryManager
from .signal_generator import SmartMoneySignalGenerator
from .trackers import BaseOnChainTracker, EthereumTracker, SolanaTracker


logger = logging.getLogger(__name__)


class SmartMoneyManager:
    """
    Main orchestrator for the Smart Money module.
    
    Usage:
        manager = SmartMoneyManager()
        await manager.initialize()
        
        # Get smart money signal
        signal = await manager.evaluate()
        print(f"Activity Score: {signal.activity_score}")
        print(f"Flow Direction: {signal.dominant_flow_direction.value}")
    
    SAFETY: All signals are CONTEXT ONLY - feed into Flow Scoring.
    """
    
    def __init__(
        self,
        config: Optional[SmartMoneyConfig] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self.config = config or get_config()
        
        # Initialize components
        self.registry = WalletRegistryManager(self.config, db_path)
        self.detector = PatternDetector(self.config, self.registry)
        self.signal_generator = SmartMoneySignalGenerator(self.config)
        
        # Trackers (initialized in initialize())
        self._trackers: dict[Chain, BaseOnChainTracker] = {}
        self._initialized = False
        
        # Last signal for caching
        self._last_signal: Optional[SmartMoneySignal] = None
        self._last_evaluation: Optional[datetime] = None
        
        # Statistics
        self._stats = {
            "evaluations": 0,
            "successful_evaluations": 0,
            "partial_evaluations": 0,
            "failed_evaluations": 0,
        }
    
    async def initialize(self) -> None:
        """Initialize trackers and seed registry if empty."""
        if self._initialized:
            return
        
        # Initialize trackers for enabled chains
        for chain in self.config.get_enabled_chains():
            if chain == Chain.ETHEREUM:
                self._trackers[chain] = EthereumTracker(self.config)
            elif chain == Chain.SOLANA:
                self._trackers[chain] = SolanaTracker(self.config)
        
        # Seed registry if empty
        if self.registry.count_wallets() == 0:
            logger.info("Seeding wallet registry with defaults...")
            self.registry.seed_default_wallets()
        
        self._initialized = True
        logger.info(f"SmartMoneyManager initialized with {len(self._trackers)} trackers")
    
    async def evaluate(
        self,
        time_window_minutes: int = 60,
        force: bool = False,
    ) -> SmartMoneySignal:
        """
        Evaluate current smart money activity.
        
        NEVER blocks indefinitely - returns partial/cached on failure.
        
        Args:
            time_window_minutes: Lookback period
            force: Force fresh evaluation (ignore cache)
            
        Returns:
            SmartMoneySignal with activity data
        """
        if not self._initialized:
            await self.initialize()
        
        self._stats["evaluations"] += 1
        
        # Check cache
        if not force and self._last_signal and self._last_evaluation:
            cache_age = (datetime.utcnow() - self._last_evaluation).total_seconds()
            if cache_age < self.config.cache_ttl_seconds:
                return self._last_signal
        
        # Get wallets
        wallets = self.registry.get_all_wallets(active_only=True)
        
        if not wallets:
            logger.warning("No wallets in registry")
            return SmartMoneySignal.empty("No wallets in registry")
        
        # Fetch activities from all chains
        all_activities: list[WalletActivity] = []
        api_failures: list[str] = []
        
        hours = max(1, time_window_minutes // 60)
        
        # Fetch concurrently per chain
        for chain, tracker in self._trackers.items():
            chain_wallets = [w for w in wallets if w.chain == chain]
            
            if not chain_wallets:
                continue
            
            try:
                chain_activities = await self._fetch_chain_activities(
                    tracker, chain_wallets, hours
                )
                all_activities.extend(chain_activities)
            except Exception as e:
                logger.error(f"Failed to fetch {chain.value} activities: {e}")
                api_failures.append(chain.value)
        
        # Detect patterns
        patterns = self.detector.detect_patterns(
            all_activities, wallets, time_window_minutes
        )
        
        # Generate signal
        signal = self.signal_generator.generate_signal(
            patterns=patterns,
            activities=all_activities,
            wallets=wallets,
            evaluation_window_minutes=time_window_minutes,
            api_failures=api_failures,
        )
        
        # Update stats
        if not api_failures:
            self._stats["successful_evaluations"] += 1
        elif all_activities:
            self._stats["partial_evaluations"] += 1
        else:
            self._stats["failed_evaluations"] += 1
        
        # Cache result
        self._last_signal = signal
        self._last_evaluation = datetime.utcnow()
        
        # Update last activity in registry
        await self._update_wallet_activities(all_activities)
        
        return signal
    
    async def _fetch_chain_activities(
        self,
        tracker: BaseOnChainTracker,
        wallets: list[WalletInfo],
        hours: int,
    ) -> list[WalletActivity]:
        """Fetch activities for wallets on a chain."""
        activities: list[WalletActivity] = []
        
        # Limit concurrent requests
        semaphore = asyncio.Semaphore(3)
        
        async def fetch_wallet(wallet: WalletInfo) -> list[WalletActivity]:
            async with semaphore:
                return await tracker.get_activity(wallet, hours)
        
        # Limit number of wallets to check
        max_wallets = self.config.max_wallets_per_chain
        wallets_to_check = wallets[:max_wallets]
        
        tasks = [fetch_wallet(w) for w in wallets_to_check]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                activities.extend(result)
            elif isinstance(result, Exception):
                logger.debug(f"Wallet fetch error: {result}")
        
        return activities
    
    async def _update_wallet_activities(
        self,
        activities: list[WalletActivity],
    ) -> None:
        """Update last activity timestamps in registry."""
        # Group by wallet
        latest_per_wallet: dict[str, datetime] = {}
        
        for activity in activities:
            key = f"{activity.chain.value}:{activity.wallet_address.lower()}"
            if key not in latest_per_wallet or activity.timestamp > latest_per_wallet[key]:
                latest_per_wallet[key] = activity.timestamp
        
        # Update registry
        for key, timestamp in latest_per_wallet.items():
            chain_str, address = key.split(":", 1)
            try:
                chain = Chain(chain_str)
                self.registry.update_last_activity(address, chain, timestamp)
            except Exception:
                pass
    
    async def get_health(self) -> dict[str, Any]:
        """Get health status of all components."""
        tracker_health = {}
        for chain, tracker in self._trackers.items():
            health = await tracker.check_health()
            tracker_health[chain.value] = health.to_dict()
        
        return {
            "initialized": self._initialized,
            "registry_wallet_count": self.registry.count_wallets(),
            "trackers": tracker_health,
            "last_evaluation": self._last_evaluation.isoformat() if self._last_evaluation else None,
        }
    
    def get_stats(self) -> dict[str, Any]:
        """Get module statistics."""
        tracker_stats = {}
        for chain, tracker in self._trackers.items():
            tracker_stats[chain.value] = tracker.get_stats()
        
        return {
            **self._stats,
            "registry_stats": self.registry.get_stats(),
            "detector_stats": self.detector.get_stats(),
            "generator_stats": self.signal_generator.get_stats(),
            "tracker_stats": tracker_stats,
        }
    
    async def close(self) -> None:
        """Cleanup resources."""
        for tracker in self._trackers.values():
            await tracker.close()
        self._trackers.clear()
        self._initialized = False


# Singleton instance
_default_manager: Optional[SmartMoneyManager] = None


def get_manager() -> SmartMoneyManager:
    """Get the default smart money manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = SmartMoneyManager()
    return _default_manager


async def evaluate_smart_money(
    time_window_minutes: int = 60,
) -> SmartMoneySignal:
    """
    Convenience function to evaluate smart money activity.
    
    SAFETY: Returns CONTEXT signal only.
    """
    manager = get_manager()
    return await manager.evaluate(time_window_minutes)
