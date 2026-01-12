"""
Retention Policy Engine.

============================================================
PURPOSE
============================================================
Manages data retention policies and enforces retention rules.

Key responsibilities:
- Define retention rules per category
- Identify data eligible for deletion/archival
- Enforce retention policies deterministically
- Log all retention actions

CRITICAL: Retention failure must NOT stop trading.

============================================================
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from .models import (
    DataCategory,
    DataSubCategory,
    RetentionDuration,
    RetentionPolicy,
    StorageTier,
    DataRecord,
    AuditAction,
    AuditRecord,
    create_default_retention_policies,
)


logger = logging.getLogger(__name__)


# ============================================================
# POLICY REGISTRY
# ============================================================

class PolicyRegistry:
    """
    Registry for retention policies.
    
    Policies must be configurable and logged.
    """
    
    def __init__(self):
        self._policies: Dict[str, RetentionPolicy] = {}
        self._category_policies: Dict[DataCategory, RetentionPolicy] = {}
        self._subcategory_policies: Dict[DataSubCategory, RetentionPolicy] = {}
        self._policy_history: List[Dict[str, Any]] = []
        
        # Load defaults
        self._load_default_policies()
    
    def _load_default_policies(self) -> None:
        """Load default retention policies."""
        defaults = create_default_retention_policies()
        for category, policy in defaults.items():
            self.register_policy(policy)
            self._category_policies[category] = policy
    
    def register_policy(
        self,
        policy: RetentionPolicy,
        reason: str = "Policy registration",
    ) -> None:
        """Register a retention policy."""
        self._policies[policy.policy_id] = policy
        
        # Track history
        self._policy_history.append({
            "action": "register",
            "policy_id": policy.policy_id,
            "category": policy.category.value,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason,
        })
        
        logger.info(f"Registered policy: {policy.policy_id} for {policy.category.value}")
    
    def get_policy(self, policy_id: str) -> Optional[RetentionPolicy]:
        """Get policy by ID."""
        return self._policies.get(policy_id)
    
    def get_policy_for_category(
        self,
        category: DataCategory,
        subcategory: Optional[DataSubCategory] = None,
    ) -> RetentionPolicy:
        """Get the applicable policy for a category/subcategory."""
        # Check subcategory-specific policy first
        if subcategory and subcategory in self._subcategory_policies:
            return self._subcategory_policies[subcategory]
        
        # Fall back to category policy
        if category in self._category_policies:
            return self._category_policies[category]
        
        # Default to system metadata policy
        logger.warning(f"No policy found for {category}, using default")
        return RetentionPolicy.for_system_metadata()
    
    def update_policy(
        self,
        policy_id: str,
        updates: Dict[str, Any],
        reason: str,
    ) -> bool:
        """
        Update an existing policy.
        
        Policy changes must be logged.
        """
        policy = self._policies.get(policy_id)
        if not policy:
            logger.error(f"Policy not found: {policy_id}")
            return False
        
        # Track history
        self._policy_history.append({
            "action": "update",
            "policy_id": policy_id,
            "updates": updates,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason,
        })
        
        logger.info(f"Updated policy: {policy_id}, reason: {reason}")
        return True
    
    def set_subcategory_policy(
        self,
        subcategory: DataSubCategory,
        policy: RetentionPolicy,
        reason: str,
    ) -> None:
        """Set a specific policy for a subcategory."""
        self._subcategory_policies[subcategory] = policy
        
        self._policy_history.append({
            "action": "set_subcategory",
            "subcategory": subcategory.value,
            "policy_id": policy.policy_id,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason,
        })
        
        logger.info(f"Set subcategory policy: {subcategory.value} -> {policy.policy_id}")
    
    def get_policy_history(self) -> List[Dict[str, Any]]:
        """Get policy change history."""
        return self._policy_history.copy()
    
    def list_all_policies(self) -> List[RetentionPolicy]:
        """List all registered policies."""
        return list(self._policies.values())


# ============================================================
# RETENTION EVALUATOR
# ============================================================

class RetentionEvaluator:
    """
    Evaluates data records against retention policies.
    """
    
    def __init__(self, policy_registry: PolicyRegistry):
        self._registry = policy_registry
    
    def is_eligible_for_deletion(self, record: DataRecord) -> bool:
        """
        Check if a record is eligible for deletion.
        
        Returns True if record has exceeded retention period.
        """
        if record.is_deleted:
            return False  # Already deleted
        
        return record.is_expired()
    
    def is_eligible_for_tier_migration(
        self,
        record: DataRecord,
        target_tier: StorageTier,
    ) -> bool:
        """Check if record should migrate to a different tier."""
        policy = record.policy
        
        # Check if target tier is in policy's allowed tiers
        if target_tier not in policy.storage_tiers:
            return False
        
        # Get current tier index
        try:
            current_idx = policy.storage_tiers.index(record.storage_tier)
            target_idx = policy.storage_tiers.index(target_tier)
        except ValueError:
            return False
        
        # Can only migrate forward (hot -> warm -> cold -> archive)
        if target_idx <= current_idx:
            return False
        
        # Check age thresholds (simplified)
        age_days = (datetime.utcnow() - record.created_at).days
        
        tier_age_thresholds = {
            StorageTier.HOT: 0,
            StorageTier.WARM: 7,
            StorageTier.COLD: 30,
            StorageTier.ARCHIVE: 180,
        }
        
        return age_days >= tier_age_thresholds.get(target_tier, 0)
    
    def get_next_tier(self, record: DataRecord) -> Optional[StorageTier]:
        """Get the next tier for migration."""
        policy = record.policy
        
        try:
            current_idx = policy.storage_tiers.index(record.storage_tier)
            if current_idx + 1 < len(policy.storage_tiers):
                return policy.storage_tiers[current_idx + 1]
        except ValueError:
            pass
        
        return None
    
    def get_expiration_status(
        self,
        record: DataRecord,
    ) -> Dict[str, Any]:
        """Get detailed expiration status."""
        expiration_date = record.get_expiration_date()
        is_expired = record.is_expired()
        
        if expiration_date:
            days_until_expiration = (expiration_date - datetime.utcnow()).days
        else:
            days_until_expiration = None
        
        return {
            "record_id": record.record_id,
            "category": record.category.value,
            "created_at": record.created_at.isoformat(),
            "expiration_date": expiration_date.isoformat() if expiration_date else None,
            "is_expired": is_expired,
            "days_until_expiration": days_until_expiration,
            "is_indefinite": record.policy.retention_duration.indefinite,
            "current_tier": record.storage_tier.value,
        }


# ============================================================
# RETENTION EXECUTOR
# ============================================================

class RetentionExecutor:
    """
    Executes retention actions.
    
    All actions must be logged and auditable.
    """
    
    def __init__(
        self,
        policy_registry: PolicyRegistry,
        audit_callback: Optional[Callable[[AuditRecord], None]] = None,
    ):
        self._registry = policy_registry
        self._evaluator = RetentionEvaluator(policy_registry)
        self._audit_callback = audit_callback
        self._pending_deletions: List[str] = []
        self._pending_migrations: List[Dict[str, Any]] = []
    
    def _create_audit_record(
        self,
        record_id: str,
        action: AuditAction,
        details: Dict[str, Any],
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditRecord:
        """Create an audit record."""
        import uuid
        
        audit = AuditRecord(
            audit_id=f"audit_{uuid.uuid4().hex}",
            record_id=record_id,
            action=action,
            timestamp=datetime.utcnow(),
            actor="retention_executor",
            actor_type="system",
            details=details,
            success=success,
            error_message=error_message,
        )
        
        if self._audit_callback:
            self._audit_callback(audit)
        
        return audit
    
    def mark_for_deletion(
        self,
        record: DataRecord,
        reason: str,
    ) -> bool:
        """
        Mark a record for deletion.
        
        Deletion actions must be explicit and auditable.
        """
        if not self._evaluator.is_eligible_for_deletion(record):
            logger.warning(
                f"Record {record.record_id} not eligible for deletion"
            )
            return False
        
        record.mark_deleted(reason)
        self._pending_deletions.append(record.record_id)
        
        self._create_audit_record(
            record_id=record.record_id,
            action=AuditAction.MARK_DELETED,
            details={
                "reason": reason,
                "category": record.category.value,
                "created_at": record.created_at.isoformat(),
                "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None,
            },
        )
        
        logger.info(f"Marked for deletion: {record.record_id}, reason: {reason}")
        return True
    
    def migrate_tier(
        self,
        record: DataRecord,
        target_tier: StorageTier,
        reason: str,
    ) -> bool:
        """
        Migrate record to a different storage tier.
        """
        if not self._evaluator.is_eligible_for_tier_migration(record, target_tier):
            logger.warning(
                f"Record {record.record_id} not eligible for migration to {target_tier.value}"
            )
            return False
        
        old_tier = record.storage_tier
        record.storage_tier = target_tier
        
        self._pending_migrations.append({
            "record_id": record.record_id,
            "from_tier": old_tier.value,
            "to_tier": target_tier.value,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        self._create_audit_record(
            record_id=record.record_id,
            action=AuditAction.TIER_MIGRATE,
            details={
                "from_tier": old_tier.value,
                "to_tier": target_tier.value,
                "reason": reason,
            },
        )
        
        logger.info(
            f"Migrated tier: {record.record_id} from {old_tier.value} to {target_tier.value}"
        )
        return True
    
    def execute_pending_deletions(
        self,
        hard_delete_callback: Optional[Callable[[str], bool]] = None,
    ) -> Dict[str, int]:
        """
        Execute pending deletions.
        
        Hard delete requires explicit callback.
        """
        results = {"marked": 0, "hard_deleted": 0, "failed": 0}
        
        for record_id in self._pending_deletions:
            if hard_delete_callback:
                try:
                    if hard_delete_callback(record_id):
                        self._create_audit_record(
                            record_id=record_id,
                            action=AuditAction.HARD_DELETE,
                            details={"method": "callback"},
                        )
                        results["hard_deleted"] += 1
                    else:
                        results["failed"] += 1
                except Exception as e:
                    logger.error(f"Hard delete failed for {record_id}: {e}")
                    self._create_audit_record(
                        record_id=record_id,
                        action=AuditAction.HARD_DELETE,
                        details={"method": "callback"},
                        success=False,
                        error_message=str(e),
                    )
                    results["failed"] += 1
            else:
                # Soft delete only
                results["marked"] += 1
        
        self._pending_deletions.clear()
        return results
    
    def get_pending_deletions(self) -> List[str]:
        """Get list of records pending deletion."""
        return self._pending_deletions.copy()
    
    def get_pending_migrations(self) -> List[Dict[str, Any]]:
        """Get list of pending tier migrations."""
        return self._pending_migrations.copy()


# ============================================================
# RETENTION SCHEDULER
# ============================================================

@dataclass
class RetentionJob:
    """A scheduled retention job."""
    job_id: str
    job_type: str  # "deletion", "migration"
    target_category: Optional[DataCategory] = None
    schedule: str = "daily"  # "hourly", "daily", "weekly"
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    is_enabled: bool = True


class RetentionScheduler:
    """
    Schedules retention jobs.
    
    Retention logic must be deterministic.
    """
    
    def __init__(self, executor: RetentionExecutor):
        self._executor = executor
        self._jobs: Dict[str, RetentionJob] = {}
        self._job_history: List[Dict[str, Any]] = []
    
    def register_job(self, job: RetentionJob) -> None:
        """Register a retention job."""
        self._jobs[job.job_id] = job
        logger.info(f"Registered retention job: {job.job_id}")
    
    def get_due_jobs(self) -> List[RetentionJob]:
        """Get jobs that are due for execution."""
        now = datetime.utcnow()
        due_jobs = []
        
        for job in self._jobs.values():
            if not job.is_enabled:
                continue
            
            if job.next_run is None or now >= job.next_run:
                due_jobs.append(job)
        
        return due_jobs
    
    def execute_job(
        self,
        job: RetentionJob,
        records: List[DataRecord],
    ) -> Dict[str, Any]:
        """Execute a retention job."""
        logger.info(f"Executing retention job: {job.job_id}")
        
        results = {
            "job_id": job.job_id,
            "job_type": job.job_type,
            "started_at": datetime.utcnow().isoformat(),
            "records_processed": 0,
            "actions_taken": 0,
        }
        
        for record in records:
            if job.target_category and record.category != job.target_category:
                continue
            
            results["records_processed"] += 1
            
            if job.job_type == "deletion":
                if self._executor._evaluator.is_eligible_for_deletion(record):
                    if self._executor.mark_for_deletion(record, "Scheduled retention"):
                        results["actions_taken"] += 1
            
            elif job.job_type == "migration":
                next_tier = self._executor._evaluator.get_next_tier(record)
                if next_tier:
                    if self._executor.migrate_tier(record, next_tier, "Scheduled migration"):
                        results["actions_taken"] += 1
        
        results["completed_at"] = datetime.utcnow().isoformat()
        
        # Update job timing
        job.last_run = datetime.utcnow()
        job.next_run = self._calculate_next_run(job.schedule)
        
        # Record history
        self._job_history.append(results)
        
        logger.info(
            f"Job {job.job_id} completed: "
            f"{results['records_processed']} processed, "
            f"{results['actions_taken']} actions"
        )
        
        return results
    
    def _calculate_next_run(self, schedule: str) -> datetime:
        """Calculate next run time based on schedule."""
        now = datetime.utcnow()
        
        if schedule == "hourly":
            return now + timedelta(hours=1)
        elif schedule == "daily":
            return now + timedelta(days=1)
        elif schedule == "weekly":
            return now + timedelta(weeks=1)
        else:
            return now + timedelta(days=1)
    
    def get_job_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get job execution history."""
        return self._job_history[-limit:]


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_policy_registry() -> PolicyRegistry:
    """Create a PolicyRegistry with default policies."""
    return PolicyRegistry()


def create_retention_evaluator(
    registry: Optional[PolicyRegistry] = None,
) -> RetentionEvaluator:
    """Create a RetentionEvaluator."""
    return RetentionEvaluator(registry or create_policy_registry())


def create_retention_executor(
    registry: Optional[PolicyRegistry] = None,
    audit_callback: Optional[Callable[[AuditRecord], None]] = None,
) -> RetentionExecutor:
    """Create a RetentionExecutor."""
    return RetentionExecutor(
        policy_registry=registry or create_policy_registry(),
        audit_callback=audit_callback,
    )


def create_retention_scheduler(
    executor: Optional[RetentionExecutor] = None,
) -> RetentionScheduler:
    """Create a RetentionScheduler."""
    return RetentionScheduler(
        executor=executor or create_retention_executor()
    )
