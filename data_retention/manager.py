"""
Data Retention Manager.

============================================================
PURPOSE
============================================================
Main orchestrator for the Data Retention and Monetization layer.

This is the primary interface for:
- Storing data with proper classification
- Managing retention lifecycle
- Tracking data lineage
- Preparing data for monetization

CRITICAL:
- Data retention failure must NOT stop trading
- Data corruption must be detected and logged
- No silent data loss allowed

============================================================
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .models import (
    DataCategory,
    DataSubCategory,
    StorageTier,
    RetentionPolicy,
    DataRecord,
    DataLineage,
    AuditAction,
    AuditRecord,
    MonetizationMetadata,
    generate_record_id,
    generate_correlation_id,
    compute_data_hash,
)
from .categories import DataClassifier, create_classifier
from .lineage import (
    LineageRegistry,
    LineageBuilder,
    CorrelationManager,
    create_lineage_registry,
    create_correlation_manager,
)
from .policies import (
    PolicyRegistry,
    RetentionEvaluator,
    RetentionExecutor,
    RetentionScheduler,
    create_policy_registry,
    create_retention_executor,
    create_retention_scheduler,
)
from .storage import (
    StorageManager,
    DeduplicationManager,
    StorageSummary,
    create_storage_manager,
    create_deduplication_manager,
)
from .anonymizer import (
    MonetizationPreparer,
    PIIDetector,
    create_monetization_preparer,
    create_pii_detector,
)
from .access_control import (
    AccessController,
    ExportController,
    ImmutabilityEnforcer,
    AuditLogger,
    create_access_controller,
    create_export_controller,
    create_immutability_enforcer,
    create_audit_logger,
)


logger = logging.getLogger(__name__)


# ============================================================
# DATA RETENTION MANAGER
# ============================================================

class DataRetentionManager:
    """
    Main orchestrator for data retention.
    
    Provides a unified interface for:
    - Storing classified data
    - Managing retention lifecycle
    - Tracking lineage
    - Access control
    - Monetization preparation
    """
    
    def __init__(
        self,
        classifier: Optional[DataClassifier] = None,
        policy_registry: Optional[PolicyRegistry] = None,
        storage_manager: Optional[StorageManager] = None,
        lineage_registry: Optional[LineageRegistry] = None,
        access_controller: Optional[AccessController] = None,
        monetization_preparer: Optional[MonetizationPreparer] = None,
        fail_silently: bool = True,  # Don't stop trading on retention failure
    ):
        # Core components
        self._classifier = classifier or create_classifier()
        self._policy_registry = policy_registry or create_policy_registry()
        self._storage_manager = storage_manager or create_storage_manager()
        self._lineage_registry = lineage_registry or create_lineage_registry()
        self._access_controller = access_controller or create_access_controller()
        self._monetization_preparer = monetization_preparer or create_monetization_preparer()
        
        # Support components
        self._correlation_manager = create_correlation_manager()
        self._dedup_manager = create_deduplication_manager()
        self._immutability_enforcer = create_immutability_enforcer()
        self._audit_logger = create_audit_logger()
        self._pii_detector = create_pii_detector()
        
        # Retention execution
        self._retention_executor = create_retention_executor(
            registry=self._policy_registry,
            audit_callback=self._audit_logger.log,
        )
        self._retention_scheduler = create_retention_scheduler(
            executor=self._retention_executor,
        )
        
        # Export controller
        self._export_controller = create_export_controller(
            access_controller=self._access_controller,
        )
        
        # Configuration
        self._fail_silently = fail_silently
        
        # State
        self._records: Dict[str, DataRecord] = {}
        self._is_running = False
    
    async def store(
        self,
        data: Dict[str, Any],
        source_type: str,
        source_name: str,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        correlation_id: Optional[str] = None,
        parent_record_ids: Optional[List[str]] = None,
        hint_category: Optional[DataCategory] = None,
        hint_subcategory: Optional[DataSubCategory] = None,
    ) -> Optional[str]:
        """
        Store data with automatic classification and lineage tracking.
        
        Returns record_id on success, None on failure.
        
        CRITICAL: Failure here must NOT stop trading.
        """
        try:
            # Generate record ID
            record_id = generate_record_id()
            
            # Serialize data
            import json
            data_bytes = json.dumps(data, default=str).encode()
            
            # Compute hash for deduplication
            data_hash = compute_data_hash(data_bytes)
            
            # Check for duplicates
            if self._dedup_manager.is_duplicate(data_hash):
                existing = self._dedup_manager.get_existing_records(data_hash)
                logger.debug(f"Duplicate data detected, existing records: {existing}")
                # Still store to maintain lineage, but log the duplication
            
            # Classify data
            category, subcategory, sensitivity, confidence = self._classifier.classify(
                data=data,
                source_type=source_type,
                source_name=source_name,
                hint_category=hint_category,
                hint_subcategory=hint_subcategory,
            )
            
            # Get retention policy
            policy = self._policy_registry.get_policy_for_category(category, subcategory)
            
            # Build lineage
            lineage = (
                LineageBuilder(record_id)
                .with_source(source_type, source_name)
                .with_parent_records(parent_record_ids or [])
                .with_correlation_id(correlation_id)
                .build()
            )
            
            # Create record
            record = DataRecord(
                record_id=record_id,
                category=category,
                subcategory=subcategory,
                created_at=datetime.utcnow(),
                data_hash=data_hash,
                size_bytes=len(data_bytes),
                storage_tier=StorageTier.HOT,
                lineage=lineage,
                policy=policy,
                correlation_id=correlation_id,
                symbol=symbol,
                exchange=exchange,
            )
            
            # Store data
            stored = await self._storage_manager.store(record, data_bytes)
            if not stored:
                logger.error(f"Failed to store data for record {record_id}")
                return None
            
            # Register lineage
            await self._lineage_registry.save_lineage(lineage)
            
            # Register for deduplication
            self._dedup_manager.register_hash(data_hash, record_id)
            
            # Track record
            self._records[record_id] = record
            
            # Seal for immutability
            self._immutability_enforcer.seal_record(record)
            
            # Log audit
            self._audit_logger.log(AuditRecord(
                audit_id=f"audit_{uuid.uuid4().hex}",
                record_id=record_id,
                action=AuditAction.CREATE,
                timestamp=datetime.utcnow(),
                actor="data_retention_manager",
                actor_type="system",
                details={
                    "category": category.value,
                    "subcategory": subcategory.value if subcategory else None,
                    "size_bytes": len(data_bytes),
                    "classification_confidence": confidence,
                },
            ))
            
            logger.debug(
                f"Stored record {record_id}: {category.value}/{subcategory.value if subcategory else 'none'}"
            )
            
            return record_id
            
        except Exception as e:
            logger.error(f"Data retention error: {e}", exc_info=True)
            
            if self._fail_silently:
                return None
            raise
    
    async def retrieve(
        self,
        record_id: str,
        actor: str = "system",
        actor_type: str = "system",
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve data for a record.
        
        Enforces access control.
        """
        record = self._records.get(record_id)
        if not record:
            logger.warning(f"Record not found: {record_id}")
            return None
        
        # Check access
        allowed, reason = self._access_controller.check_access(
            actor=actor,
            actor_type=actor_type,
            record=record,
            action=AuditAction.READ,
        )
        
        if not allowed:
            logger.warning(f"Access denied for {actor}: {reason}")
            return None
        
        # Retrieve data
        data_bytes = await self._storage_manager.retrieve(record)
        if not data_bytes:
            return None
        
        # Parse
        import json
        return json.loads(data_bytes.decode())
    
    async def get_lineage(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Get lineage report for a record."""
        return await self._lineage_registry.export_lineage_report(record_id)
    
    def start_correlation(
        self,
        context: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start a correlation group for related records.
        
        Returns correlation_id to use when storing related data.
        """
        return self._correlation_manager.create_correlation(context, metadata)
    
    def end_correlation(self, correlation_id: str) -> None:
        """End a correlation group."""
        self._correlation_manager.close_correlation(correlation_id)
    
    async def run_retention_cycle(
        self,
        records: Optional[List[DataRecord]] = None,
    ) -> Dict[str, Any]:
        """
        Run a retention maintenance cycle.
        
        This handles:
        - Tier migrations
        - Expiration checking
        - Deletion execution
        """
        if records is None:
            records = list(self._records.values())
        
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "records_processed": len(records),
            "migrations": {},
            "deletions": {},
            "errors": [],
        }
        
        try:
            # Execute tier migrations
            migration_results = await self._storage_manager.execute_migrations(records)
            results["migrations"] = migration_results
            
            # Check for expired records
            expired_count = 0
            for record in records:
                if self._retention_executor._evaluator.is_eligible_for_deletion(record):
                    if self._retention_executor.mark_for_deletion(record, "Retention expired"):
                        expired_count += 1
            
            results["deletions"]["marked_for_deletion"] = expired_count
            
            # Execute pending deletions
            deletion_results = self._retention_executor.execute_pending_deletions()
            results["deletions"].update(deletion_results)
            
        except Exception as e:
            logger.error(f"Retention cycle error: {e}", exc_info=True)
            results["errors"].append(str(e))
        
        return results
    
    def get_storage_summary(self) -> StorageSummary:
        """Get storage metrics summary."""
        return self._storage_manager.get_metrics()
    
    def get_audit_statistics(self) -> Dict[str, Any]:
        """Get audit statistics."""
        return self._audit_logger.get_statistics()
    
    async def prepare_for_monetization(
        self,
        record_id: str,
        actor: str,
    ) -> Optional[tuple]:
        """
        Prepare a record for monetization.
        
        Returns (anonymized_data, metadata) or None if not allowed.
        """
        record = self._records.get(record_id)
        if not record:
            logger.warning(f"Record not found: {record_id}")
            return None
        
        # Check if category can be monetized
        if not self._monetization_preparer.can_monetize(record.category):
            logger.warning(f"Category {record.category.value} cannot be monetized")
            return None
        
        # Check export permission
        allowed, _, reason = self._export_controller.can_export(actor, [record])
        if not allowed:
            logger.warning(f"Export not allowed: {reason}")
            return None
        
        # Retrieve data
        data = await self.retrieve(record_id, actor, "export")
        if not data:
            return None
        
        # Prepare for monetization
        return self._monetization_preparer.prepare_for_monetization(
            data=data,
            category=record.category,
            original_record_id=record_id,
        )
    
    def get_record(self, record_id: str) -> Optional[DataRecord]:
        """Get a record by ID."""
        return self._records.get(record_id)
    
    def get_records_by_category(
        self,
        category: DataCategory,
        limit: int = 100,
    ) -> List[DataRecord]:
        """Get records by category."""
        return [
            r for r in self._records.values()
            if r.category == category
        ][:limit]
    
    def get_records_by_correlation(
        self,
        correlation_id: str,
    ) -> List[DataRecord]:
        """Get records by correlation ID."""
        return [
            r for r in self._records.values()
            if r.correlation_id == correlation_id
        ]


# ============================================================
# FAILURE-SAFE WRAPPER
# ============================================================

class FailSafeRetentionWrapper:
    """
    Wraps DataRetentionManager with failure isolation.
    
    CRITICAL: Data retention failure must NOT stop trading.
    """
    
    def __init__(self, manager: DataRetentionManager):
        self._manager = manager
        self._failure_count = 0
        self._last_failure: Optional[datetime] = None
    
    async def store(self, *args, **kwargs) -> Optional[str]:
        """Store with failure isolation."""
        try:
            return await self._manager.store(*args, **kwargs)
        except Exception as e:
            self._failure_count += 1
            self._last_failure = datetime.utcnow()
            logger.error(f"Retention store failed (count={self._failure_count}): {e}")
            return None
    
    async def retrieve(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Retrieve with failure isolation."""
        try:
            return await self._manager.retrieve(*args, **kwargs)
        except Exception as e:
            logger.error(f"Retention retrieve failed: {e}")
            return None
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status."""
        return {
            "failure_count": self._failure_count,
            "last_failure": self._last_failure.isoformat() if self._last_failure else None,
            "is_healthy": self._failure_count < 10,
        }


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_data_retention_manager(
    fail_silently: bool = True,
) -> DataRetentionManager:
    """Create a DataRetentionManager with default configuration."""
    return DataRetentionManager(fail_silently=fail_silently)


def create_fail_safe_retention(
    manager: Optional[DataRetentionManager] = None,
) -> FailSafeRetentionWrapper:
    """Create a failure-safe retention wrapper."""
    return FailSafeRetentionWrapper(
        manager=manager or create_data_retention_manager()
    )
