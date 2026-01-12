"""
Tiered Storage Management.

============================================================
PURPOSE
============================================================
Manages tiered storage for cost optimization.

Storage tiers:
- HOT: Frequently accessed, fast retrieval, highest cost
- WARM: Occasionally accessed, moderate latency
- COLD: Rarely accessed, high latency, lowest cost
- ARCHIVE: Long-term preservation, very high latency

Key responsibilities:
- Route data to appropriate tier
- Migrate data between tiers
- Track storage costs
- Avoid unnecessary duplication

============================================================
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set

from .models import (
    DataCategory,
    StorageTier,
    StorageTierConfig,
    DataRecord,
    AuditAction,
    AuditRecord,
    create_storage_tier_configs,
)


logger = logging.getLogger(__name__)


# ============================================================
# STORAGE METRICS
# ============================================================

@dataclass
class StorageMetrics:
    """Metrics for a storage tier."""
    tier: StorageTier
    record_count: int = 0
    total_size_bytes: int = 0
    avg_record_size_bytes: int = 0
    oldest_record_age_days: int = 0
    newest_record_age_days: int = 0
    access_count_last_24h: int = 0
    estimated_monthly_cost: Decimal = Decimal("0")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.value,
            "record_count": self.record_count,
            "total_size_bytes": self.total_size_bytes,
            "total_size_gb": round(self.total_size_bytes / (1024**3), 2),
            "avg_record_size_bytes": self.avg_record_size_bytes,
            "oldest_record_age_days": self.oldest_record_age_days,
            "newest_record_age_days": self.newest_record_age_days,
            "access_count_last_24h": self.access_count_last_24h,
            "estimated_monthly_cost": str(self.estimated_monthly_cost),
        }


@dataclass
class StorageSummary:
    """Overall storage summary."""
    timestamp: datetime
    tier_metrics: Dict[StorageTier, StorageMetrics] = field(default_factory=dict)
    total_records: int = 0
    total_size_bytes: int = 0
    total_monthly_cost: Decimal = Decimal("0")
    category_breakdown: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_records": self.total_records,
            "total_size_bytes": self.total_size_bytes,
            "total_size_gb": round(self.total_size_bytes / (1024**3), 2),
            "total_monthly_cost": str(self.total_monthly_cost),
            "tiers": {
                tier.value: metrics.to_dict()
                for tier, metrics in self.tier_metrics.items()
            },
            "category_breakdown": self.category_breakdown,
        }


# ============================================================
# TIER ROUTER
# ============================================================

class TierRouter:
    """
    Routes data to appropriate storage tier.
    """
    
    def __init__(self, tier_configs: Optional[Dict[StorageTier, StorageTierConfig]] = None):
        self._configs = tier_configs or create_storage_tier_configs()
        self._custom_rules: List[Callable[[DataRecord], Optional[StorageTier]]] = []
    
    def get_initial_tier(self, record: DataRecord) -> StorageTier:
        """
        Determine initial storage tier for a new record.
        
        New data always starts in HOT tier unless policy specifies otherwise.
        """
        # Check custom rules first
        for rule in self._custom_rules:
            tier = rule(record)
            if tier:
                return tier
        
        # Default: new data goes to HOT
        return StorageTier.HOT
    
    def get_target_tier_for_age(
        self,
        age_days: int,
        allowed_tiers: List[StorageTier],
    ) -> StorageTier:
        """Determine appropriate tier based on data age."""
        # Find the coldest tier that matches the age
        tier_order = [StorageTier.HOT, StorageTier.WARM, StorageTier.COLD, StorageTier.ARCHIVE]
        
        for tier in reversed(tier_order):
            if tier not in allowed_tiers:
                continue
            
            config = self._configs.get(tier)
            if not config:
                continue
            
            if config.max_age_days is None:
                # Archive tier - no age limit
                return tier
            
            if age_days >= config.max_age_days:
                return tier
        
        # Default to hottest allowed tier
        for tier in tier_order:
            if tier in allowed_tiers:
                return tier
        
        return StorageTier.HOT
    
    def should_migrate(
        self,
        record: DataRecord,
        current_tier: StorageTier,
    ) -> Optional[StorageTier]:
        """
        Check if record should migrate to a different tier.
        
        Returns target tier or None if no migration needed.
        """
        age_days = (datetime.utcnow() - record.created_at).days
        target_tier = self.get_target_tier_for_age(
            age_days, record.policy.storage_tiers
        )
        
        if target_tier != current_tier:
            # Ensure we only migrate forward (to colder tiers)
            tier_order = [StorageTier.HOT, StorageTier.WARM, StorageTier.COLD, StorageTier.ARCHIVE]
            try:
                current_idx = tier_order.index(current_tier)
                target_idx = tier_order.index(target_tier)
                if target_idx > current_idx:
                    return target_tier
            except ValueError:
                pass
        
        return None
    
    def add_custom_rule(
        self,
        rule: Callable[[DataRecord], Optional[StorageTier]],
    ) -> None:
        """Add a custom routing rule."""
        self._custom_rules.append(rule)
        logger.info("Added custom tier routing rule")


# ============================================================
# STORAGE BACKEND
# ============================================================

class StorageBackend:
    """
    Abstract storage backend interface.
    
    Implementations handle actual storage operations.
    """
    
    async def store(
        self,
        record_id: str,
        data: bytes,
        tier: StorageTier,
        metadata: Dict[str, Any],
    ) -> bool:
        """Store data in the specified tier."""
        raise NotImplementedError
    
    async def retrieve(
        self,
        record_id: str,
        tier: StorageTier,
    ) -> Optional[bytes]:
        """Retrieve data from the specified tier."""
        raise NotImplementedError
    
    async def delete(
        self,
        record_id: str,
        tier: StorageTier,
    ) -> bool:
        """Delete data from the specified tier."""
        raise NotImplementedError
    
    async def migrate(
        self,
        record_id: str,
        from_tier: StorageTier,
        to_tier: StorageTier,
    ) -> bool:
        """Migrate data between tiers."""
        raise NotImplementedError
    
    async def get_size(
        self,
        record_id: str,
        tier: StorageTier,
    ) -> int:
        """Get size of stored data."""
        raise NotImplementedError


class InMemoryStorageBackend(StorageBackend):
    """In-memory storage backend for testing."""
    
    def __init__(self):
        self._storage: Dict[StorageTier, Dict[str, bytes]] = {
            tier: {} for tier in StorageTier
        }
        self._metadata: Dict[str, Dict[str, Any]] = {}
    
    async def store(
        self,
        record_id: str,
        data: bytes,
        tier: StorageTier,
        metadata: Dict[str, Any],
    ) -> bool:
        self._storage[tier][record_id] = data
        self._metadata[record_id] = metadata
        return True
    
    async def retrieve(
        self,
        record_id: str,
        tier: StorageTier,
    ) -> Optional[bytes]:
        return self._storage[tier].get(record_id)
    
    async def delete(
        self,
        record_id: str,
        tier: StorageTier,
    ) -> bool:
        if record_id in self._storage[tier]:
            del self._storage[tier][record_id]
            return True
        return False
    
    async def migrate(
        self,
        record_id: str,
        from_tier: StorageTier,
        to_tier: StorageTier,
    ) -> bool:
        data = self._storage[from_tier].get(record_id)
        if data:
            self._storage[to_tier][record_id] = data
            del self._storage[from_tier][record_id]
            return True
        return False
    
    async def get_size(
        self,
        record_id: str,
        tier: StorageTier,
    ) -> int:
        data = self._storage[tier].get(record_id)
        return len(data) if data else 0


# ============================================================
# STORAGE MANAGER
# ============================================================

class StorageManager:
    """
    Manages tiered storage operations.
    
    Key responsibilities:
    - Route data to appropriate tier
    - Track storage metrics
    - Manage tier migrations
    - Calculate costs
    """
    
    def __init__(
        self,
        backend: Optional[StorageBackend] = None,
        tier_configs: Optional[Dict[StorageTier, StorageTierConfig]] = None,
        audit_callback: Optional[Callable[[AuditRecord], None]] = None,
    ):
        self._backend = backend or InMemoryStorageBackend()
        self._configs = tier_configs or create_storage_tier_configs()
        self._router = TierRouter(self._configs)
        self._audit_callback = audit_callback
        
        # Tracking
        self._record_tiers: Dict[str, StorageTier] = {}
        self._record_sizes: Dict[str, int] = {}
        self._access_log: List[Dict[str, Any]] = []
    
    async def store(
        self,
        record: DataRecord,
        data: bytes,
    ) -> bool:
        """
        Store a data record.
        
        Automatically routes to appropriate tier.
        """
        tier = self._router.get_initial_tier(record)
        
        success = await self._backend.store(
            record_id=record.record_id,
            data=data,
            tier=tier,
            metadata={
                "category": record.category.value,
                "created_at": record.created_at.isoformat(),
            },
        )
        
        if success:
            self._record_tiers[record.record_id] = tier
            self._record_sizes[record.record_id] = len(data)
            record.storage_tier = tier
            record.size_bytes = len(data)
            
            logger.debug(f"Stored {record.record_id} in {tier.value}")
        
        return success
    
    async def retrieve(
        self,
        record: DataRecord,
    ) -> Optional[bytes]:
        """
        Retrieve data for a record.
        
        Updates access tracking.
        """
        tier = self._record_tiers.get(record.record_id, record.storage_tier)
        
        data = await self._backend.retrieve(record.record_id, tier)
        
        if data:
            record.last_accessed = datetime.utcnow()
            record.access_count += 1
            
            self._access_log.append({
                "record_id": record.record_id,
                "tier": tier.value,
                "timestamp": datetime.utcnow(),
                "size_bytes": len(data),
            })
        
        return data
    
    async def migrate(
        self,
        record: DataRecord,
        target_tier: StorageTier,
        reason: str,
    ) -> bool:
        """
        Migrate record to a different tier.
        """
        current_tier = self._record_tiers.get(record.record_id, record.storage_tier)
        
        if current_tier == target_tier:
            return True  # Already in target tier
        
        success = await self._backend.migrate(
            record_id=record.record_id,
            from_tier=current_tier,
            to_tier=target_tier,
        )
        
        if success:
            self._record_tiers[record.record_id] = target_tier
            record.storage_tier = target_tier
            
            logger.info(
                f"Migrated {record.record_id} from {current_tier.value} "
                f"to {target_tier.value}: {reason}"
            )
        
        return success
    
    async def delete(
        self,
        record: DataRecord,
    ) -> bool:
        """Delete a record from storage."""
        tier = self._record_tiers.get(record.record_id, record.storage_tier)
        
        success = await self._backend.delete(record.record_id, tier)
        
        if success:
            self._record_tiers.pop(record.record_id, None)
            self._record_sizes.pop(record.record_id, None)
            
            logger.info(f"Deleted {record.record_id} from {tier.value}")
        
        return success
    
    def check_migrations(
        self,
        records: List[DataRecord],
    ) -> List[tuple]:
        """
        Check which records should be migrated.
        
        Returns list of (record, target_tier) tuples.
        """
        migrations = []
        
        for record in records:
            current_tier = self._record_tiers.get(record.record_id, record.storage_tier)
            target_tier = self._router.should_migrate(record, current_tier)
            
            if target_tier:
                migrations.append((record, target_tier))
        
        return migrations
    
    async def execute_migrations(
        self,
        records: List[DataRecord],
    ) -> Dict[str, int]:
        """Execute pending migrations."""
        migrations = self.check_migrations(records)
        
        results = {"migrated": 0, "failed": 0}
        
        for record, target_tier in migrations:
            if await self.migrate(record, target_tier, "Scheduled tier migration"):
                results["migrated"] += 1
            else:
                results["failed"] += 1
        
        return results
    
    def get_metrics(self) -> StorageSummary:
        """Get storage metrics."""
        summary = StorageSummary(timestamp=datetime.utcnow())
        
        for tier in StorageTier:
            metrics = StorageMetrics(tier=tier)
            
            for record_id, record_tier in self._record_tiers.items():
                if record_tier == tier:
                    metrics.record_count += 1
                    metrics.total_size_bytes += self._record_sizes.get(record_id, 0)
            
            if metrics.record_count > 0:
                metrics.avg_record_size_bytes = metrics.total_size_bytes // metrics.record_count
            
            # Calculate cost
            config = self._configs.get(tier)
            if config:
                size_gb = Decimal(metrics.total_size_bytes) / Decimal(1024**3)
                metrics.estimated_monthly_cost = size_gb * config.cost_per_gb_month
            
            summary.tier_metrics[tier] = metrics
            summary.total_records += metrics.record_count
            summary.total_size_bytes += metrics.total_size_bytes
            summary.total_monthly_cost += metrics.estimated_monthly_cost
        
        return summary
    
    def get_access_statistics(
        self,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get access statistics."""
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)
        
        recent_accesses = [
            a for a in self._access_log
            if a["timestamp"] >= since
        ]
        
        tier_counts = {}
        for access in recent_accesses:
            tier = access["tier"]
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        return {
            "since": since.isoformat(),
            "total_accesses": len(recent_accesses),
            "tier_breakdown": tier_counts,
        }


# ============================================================
# DEDUPLICATION
# ============================================================

class DeduplicationManager:
    """
    Manages data deduplication.
    
    Avoids unnecessary duplication to reduce storage costs.
    """
    
    def __init__(self):
        self._hash_to_records: Dict[str, Set[str]] = {}
    
    def register_hash(self, data_hash: str, record_id: str) -> None:
        """Register a data hash."""
        if data_hash not in self._hash_to_records:
            self._hash_to_records[data_hash] = set()
        self._hash_to_records[data_hash].add(record_id)
    
    def is_duplicate(self, data_hash: str) -> bool:
        """Check if data hash already exists."""
        return data_hash in self._hash_to_records
    
    def get_existing_records(self, data_hash: str) -> List[str]:
        """Get existing records with same hash."""
        return list(self._hash_to_records.get(data_hash, set()))
    
    def get_duplicate_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        duplicate_count = sum(
            len(records) - 1
            for records in self._hash_to_records.values()
            if len(records) > 1
        )
        
        return {
            "unique_hashes": len(self._hash_to_records),
            "duplicate_records": duplicate_count,
            "dedup_ratio": duplicate_count / max(sum(len(r) for r in self._hash_to_records.values()), 1),
        }


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_tier_router(
    configs: Optional[Dict[StorageTier, StorageTierConfig]] = None,
) -> TierRouter:
    """Create a TierRouter."""
    return TierRouter(configs)


def create_storage_backend() -> StorageBackend:
    """Create an in-memory storage backend."""
    return InMemoryStorageBackend()


def create_storage_manager(
    backend: Optional[StorageBackend] = None,
    tier_configs: Optional[Dict[StorageTier, StorageTierConfig]] = None,
) -> StorageManager:
    """Create a StorageManager."""
    return StorageManager(
        backend=backend,
        tier_configs=tier_configs,
    )


def create_deduplication_manager() -> DeduplicationManager:
    """Create a DeduplicationManager."""
    return DeduplicationManager()
