"""
Pattern Detector - Detects smart money behavior patterns.

Analyzes wallet activity to detect:
- Large transfers (vs historical average)
- CEX flows (deposits/withdrawals)
- Dormancy breaks (sudden activity after long inactivity)
- Clustered activity (multiple wallets moving together)
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from .config import DetectionConfig, SmartMoneyConfig, get_config
from .models import (
    ActivityType,
    Chain,
    DetectedPattern,
    EntityType,
    FlowDirection,
    WalletActivity,
    WalletInfo,
)
from .registry import WalletRegistryManager


logger = logging.getLogger(__name__)


class PatternDetector:
    """
    Detects patterns in smart money wallet activity.
    
    Pattern types:
    - large_transfer: Transfer above threshold or wallet average
    - cex_flow: Deposits/withdrawals involving CEX wallets
    - dormancy_break: Activity after period of inactivity
    - cluster: Multiple wallets moving in same timeframe
    
    SAFETY: These patterns are CONTEXT signals only.
    """
    
    def __init__(
        self,
        config: Optional[SmartMoneyConfig] = None,
        registry: Optional[WalletRegistryManager] = None,
    ) -> None:
        self.config = config or get_config()
        self.detection_config = self.config.detection
        self.registry = registry
        
        # Statistics
        self._stats = {
            "patterns_detected": 0,
            "large_transfers": 0,
            "cex_flows": 0,
            "dormancy_breaks": 0,
            "clusters": 0,
        }
    
    def detect_patterns(
        self,
        activities: list[WalletActivity],
        wallets: list[WalletInfo],
        time_window_minutes: int = 60,
    ) -> list[DetectedPattern]:
        """
        Detect all patterns in the given activities.
        
        Args:
            activities: List of wallet activities
            wallets: List of wallets being tracked
            time_window_minutes: Time window for pattern detection
            
        Returns:
            List of detected patterns
        """
        patterns: list[DetectedPattern] = []
        
        if not activities:
            return patterns
        
        # Create wallet lookup
        wallet_map = {w.address.lower(): w for w in wallets}
        
        # Detect each pattern type
        patterns.extend(self._detect_large_transfers(activities, wallet_map))
        patterns.extend(self._detect_cex_flows(activities, wallet_map))
        patterns.extend(self._detect_dormancy_breaks(activities, wallet_map))
        patterns.extend(self._detect_clusters(activities, time_window_minutes))
        
        # Update stats
        self._stats["patterns_detected"] += len(patterns)
        
        return patterns
    
    def _detect_large_transfers(
        self,
        activities: list[WalletActivity],
        wallet_map: dict[str, WalletInfo],
    ) -> list[DetectedPattern]:
        """Detect transfers above threshold or wallet historical average."""
        patterns: list[DetectedPattern] = []
        
        for activity in activities:
            if activity.activity_type != ActivityType.TRANSFER:
                continue
            
            is_large = False
            reason = ""
            
            # Check absolute threshold
            if activity.value_usd >= self.detection_config.large_transfer_usd_threshold:
                is_large = True
                reason = f"Above ${self.detection_config.large_transfer_usd_threshold:,.0f} threshold"
            
            # Check vs wallet average
            wallet = wallet_map.get(activity.wallet_address.lower())
            if wallet and wallet.avg_transaction_value_usd > 0:
                multiplier = activity.value_usd / wallet.avg_transaction_value_usd
                if multiplier >= self.detection_config.large_transfer_multiplier:
                    is_large = True
                    reason = f"{multiplier:.1f}x wallet average"
            
            if is_large:
                activity.is_large = True
                
                # Determine flow direction
                if activity.direction == "in":
                    flow = FlowDirection.INFLOW
                elif activity.direction == "out":
                    flow = FlowDirection.OUTFLOW
                else:
                    flow = FlowDirection.NEUTRAL
                
                pattern = DetectedPattern(
                    pattern_type="large_transfer",
                    description=f"Large transfer detected: ${activity.value_usd:,.0f} ({reason})",
                    severity=self._calculate_severity(activity.value_usd),
                    confidence=wallet.confidence_level if wallet else 0.5,
                    wallets_involved=[activity.wallet_address],
                    transactions=[activity.tx_hash],
                    affected_assets=[activity.token_symbol],
                    timestamp=activity.timestamp,
                    total_value_usd=activity.value_usd,
                    flow_direction=flow,
                )
                patterns.append(pattern)
                self._stats["large_transfers"] += 1
        
        return patterns
    
    def _detect_cex_flows(
        self,
        activities: list[WalletActivity],
        wallet_map: dict[str, WalletInfo],
    ) -> list[DetectedPattern]:
        """Detect deposits/withdrawals to/from CEX wallets."""
        patterns: list[DetectedPattern] = []
        
        # Get CEX wallet addresses
        cex_addresses: set[str] = set()
        for wallet in wallet_map.values():
            if wallet.entity_type in (EntityType.CEX_HOT, EntityType.CEX_COLD):
                cex_addresses.add(wallet.address.lower())
        
        # Also check registry if available
        if self.registry:
            for wallet in self.registry.get_cex_wallets():
                cex_addresses.add(wallet.address.lower())
        
        for activity in activities:
            if activity.value_usd < self.detection_config.cex_flow_usd_threshold:
                continue
            
            counterparty = activity.counterparty_address
            if not counterparty:
                continue
            
            counterparty_lower = counterparty.lower()
            wallet_lower = activity.wallet_address.lower()
            
            # Check if either party is CEX
            is_cex_involved = (
                counterparty_lower in cex_addresses or
                wallet_lower in cex_addresses
            )
            
            if not is_cex_involved:
                continue
            
            activity.is_cex_related = True
            
            # Determine direction
            if counterparty_lower in cex_addresses:
                # Sending to CEX = potential sell
                flow = FlowDirection.OUTFLOW
                description = f"Deposit to CEX: ${activity.value_usd:,.0f}"
            else:
                # Receiving from CEX = potential buy
                flow = FlowDirection.INFLOW
                description = f"Withdrawal from CEX: ${activity.value_usd:,.0f}"
            
            # Get CEX name if available
            cex_wallet = wallet_map.get(counterparty_lower) or wallet_map.get(wallet_lower)
            if cex_wallet and cex_wallet.entity_name:
                description += f" ({cex_wallet.entity_name})"
            
            pattern = DetectedPattern(
                pattern_type="cex_flow",
                description=description,
                severity=self._calculate_severity(activity.value_usd) * 1.2,  # Boost CEX flows
                confidence=0.8,  # High confidence for CEX detection
                wallets_involved=[activity.wallet_address],
                transactions=[activity.tx_hash],
                affected_assets=[activity.token_symbol],
                timestamp=activity.timestamp,
                total_value_usd=activity.value_usd,
                flow_direction=flow,
            )
            patterns.append(pattern)
            self._stats["cex_flows"] += 1
        
        return patterns
    
    def _detect_dormancy_breaks(
        self,
        activities: list[WalletActivity],
        wallet_map: dict[str, WalletInfo],
    ) -> list[DetectedPattern]:
        """Detect wallets becoming active after period of inactivity."""
        patterns: list[DetectedPattern] = []
        
        dormancy_threshold = timedelta(days=self.detection_config.dormancy_days_threshold)
        now = datetime.utcnow()
        
        # Group activities by wallet
        wallet_activities: dict[str, list[WalletActivity]] = defaultdict(list)
        for activity in activities:
            wallet_activities[activity.wallet_address.lower()].append(activity)
        
        for address, acts in wallet_activities.items():
            wallet = wallet_map.get(address)
            if not wallet:
                continue
            
            # Check if wallet was dormant
            if wallet.last_activity:
                inactive_time = now - wallet.last_activity
                if inactive_time >= dormancy_threshold:
                    # Wallet was dormant, now active
                    total_value = sum(a.value_usd for a in acts)
                    
                    pattern = DetectedPattern(
                        pattern_type="dormancy_break",
                        description=f"Wallet active after {inactive_time.days} days dormancy",
                        severity=min(1.0, 0.6 + inactive_time.days / 100),
                        confidence=wallet.confidence_level,
                        wallets_involved=[address],
                        transactions=[a.tx_hash for a in acts[:5]],
                        affected_assets=list(set(a.token_symbol for a in acts)),
                        timestamp=acts[0].timestamp,
                        total_value_usd=total_value,
                        flow_direction=self._get_dominant_direction(acts),
                    )
                    patterns.append(pattern)
                    self._stats["dormancy_breaks"] += 1
        
        return patterns
    
    def _detect_clusters(
        self,
        activities: list[WalletActivity],
        time_window_minutes: int,
    ) -> list[DetectedPattern]:
        """Detect multiple wallets moving in the same time window."""
        patterns: list[DetectedPattern] = []
        
        if len(activities) < self.detection_config.cluster_min_transactions:
            return patterns
        
        # Group by time windows
        window_size = timedelta(minutes=self.detection_config.cluster_time_window_minutes)
        
        # Sort by time
        sorted_activities = sorted(activities, key=lambda a: a.timestamp)
        
        # Sliding window clustering
        i = 0
        while i < len(sorted_activities):
            window_start = sorted_activities[i].timestamp
            window_end = window_start + window_size
            
            # Collect activities in window
            window_activities: list[WalletActivity] = []
            for j in range(i, len(sorted_activities)):
                if sorted_activities[j].timestamp <= window_end:
                    window_activities.append(sorted_activities[j])
                else:
                    break
            
            # Check if this is a cluster
            unique_wallets = set(a.wallet_address for a in window_activities)
            
            if (
                len(unique_wallets) >= self.detection_config.cluster_min_wallets and
                len(window_activities) >= self.detection_config.cluster_min_transactions
            ):
                total_value = sum(a.value_usd for a in window_activities)
                affected_assets = list(set(a.token_symbol for a in window_activities))
                
                pattern = DetectedPattern(
                    pattern_type="cluster",
                    description=f"Clustered activity: {len(unique_wallets)} wallets, {len(window_activities)} txs in {self.detection_config.cluster_time_window_minutes}min",
                    severity=min(1.0, len(unique_wallets) * 0.2 + len(window_activities) * 0.1),
                    confidence=0.6,
                    wallets_involved=list(unique_wallets),
                    transactions=[a.tx_hash for a in window_activities[:10]],
                    affected_assets=affected_assets,
                    timestamp=window_start,
                    time_window_minutes=self.detection_config.cluster_time_window_minutes,
                    total_value_usd=total_value,
                    flow_direction=self._get_dominant_direction(window_activities),
                )
                patterns.append(pattern)
                self._stats["clusters"] += 1
                
                # Skip to end of this window
                i += len(window_activities)
            else:
                i += 1
        
        return patterns
    
    def _calculate_severity(self, value_usd: float) -> float:
        """Calculate severity based on USD value."""
        thresholds = [
            (self.detection_config.volume_very_high_usd, 1.0),
            (self.detection_config.volume_high_usd, 0.8),
            (self.detection_config.volume_medium_usd, 0.6),
            (self.detection_config.volume_low_usd, 0.4),
        ]
        
        for threshold, severity in thresholds:
            if value_usd >= threshold:
                return severity
        
        return 0.2
    
    def _get_dominant_direction(
        self,
        activities: list[WalletActivity],
    ) -> FlowDirection:
        """Get dominant flow direction from activities."""
        inflow = sum(a.value_usd for a in activities if a.direction == "in")
        outflow = sum(a.value_usd for a in activities if a.direction == "out")
        
        if inflow > outflow * 1.2:
            return FlowDirection.INFLOW
        elif outflow > inflow * 1.2:
            return FlowDirection.OUTFLOW
        else:
            return FlowDirection.NEUTRAL
    
    def get_stats(self) -> dict[str, Any]:
        """Get detector statistics."""
        return self._stats.copy()
