"""
Access Control for Data Retention.

============================================================
PURPOSE
============================================================
Controls access to retained data.

Access rules:
- Internal system has full access
- External access must be read-only
- Data exports must be logged
- No module may alter retained historical data

============================================================
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from .models import (
    DataCategory,
    AccessLevel,
    DataSensitivity,
    AuditAction,
    AuditRecord,
    DataRecord,
)


logger = logging.getLogger(__name__)


# ============================================================
# ACCESS POLICY
# ============================================================

@dataclass
class AccessPolicy:
    """Access policy for a data category or actor."""
    policy_id: str
    actor: str  # Module name, user ID, or "*" for default
    actor_type: str  # "system", "user", "export", "external"
    allowed_categories: Set[DataCategory] = field(default_factory=set)
    denied_categories: Set[DataCategory] = field(default_factory=set)
    access_level: AccessLevel = AccessLevel.NONE
    can_export: bool = False
    requires_audit: bool = True
    max_records_per_query: int = 1000
    description: str = ""


# ============================================================
# ACCESS CONTROLLER
# ============================================================

class AccessController:
    """
    Controls access to data records.
    
    All access decisions are logged.
    """
    
    def __init__(
        self,
        audit_callback: Optional[Callable[[AuditRecord], None]] = None,
    ):
        self._policies: Dict[str, AccessPolicy] = {}
        self._actor_policies: Dict[str, List[str]] = {}  # actor -> [policy_ids]
        self._audit_callback = audit_callback
        self._access_log: List[Dict[str, Any]] = []
        
        # Load default policies
        self._load_default_policies()
    
    def _load_default_policies(self) -> None:
        """Load default access policies."""
        # System internal - full access
        self.add_policy(AccessPolicy(
            policy_id="pol_system_internal",
            actor="*",
            actor_type="system",
            allowed_categories=set(DataCategory),
            access_level=AccessLevel.INTERNAL_FULL,
            can_export=False,
            requires_audit=True,
            description="Internal system components - full read access",
        ))
        
        # External read-only
        self.add_policy(AccessPolicy(
            policy_id="pol_external_read",
            actor="*",
            actor_type="external",
            allowed_categories={
                DataCategory.RAW_DATA,
                DataCategory.PROCESSED_DATA,
                DataCategory.DERIVED_SCORES,
            },
            denied_categories={
                DataCategory.DECISION_LOGS,
                DataCategory.EXECUTION_RECORDS,
            },
            access_level=AccessLevel.EXTERNAL_READ,
            can_export=False,
            requires_audit=True,
            max_records_per_query=100,
            description="External access - limited read-only",
        ))
        
        # Export permission
        self.add_policy(AccessPolicy(
            policy_id="pol_export",
            actor="*",
            actor_type="export",
            allowed_categories={
                DataCategory.RAW_DATA,
                DataCategory.PROCESSED_DATA,
                DataCategory.DERIVED_SCORES,
            },
            denied_categories={
                DataCategory.DECISION_LOGS,
                DataCategory.EXECUTION_RECORDS,
                DataCategory.SYSTEM_METADATA,
            },
            access_level=AccessLevel.EXPORT,
            can_export=True,
            requires_audit=True,
            max_records_per_query=10000,
            description="Export permission for monetization-eligible data",
        ))
    
    def add_policy(self, policy: AccessPolicy) -> None:
        """Add an access policy."""
        self._policies[policy.policy_id] = policy
        
        # Map actor to policies
        if policy.actor not in self._actor_policies:
            self._actor_policies[policy.actor] = []
        self._actor_policies[policy.actor].append(policy.policy_id)
        
        logger.info(f"Added access policy: {policy.policy_id}")
    
    def get_applicable_policy(
        self,
        actor: str,
        actor_type: str,
    ) -> Optional[AccessPolicy]:
        """Get the applicable policy for an actor."""
        # Check specific actor policies first
        if actor in self._actor_policies:
            for policy_id in self._actor_policies[actor]:
                policy = self._policies.get(policy_id)
                if policy and policy.actor_type == actor_type:
                    return policy
        
        # Fall back to wildcard policies
        if "*" in self._actor_policies:
            for policy_id in self._actor_policies["*"]:
                policy = self._policies.get(policy_id)
                if policy and policy.actor_type == actor_type:
                    return policy
        
        return None
    
    def check_access(
        self,
        actor: str,
        actor_type: str,
        record: DataRecord,
        action: AuditAction,
    ) -> tuple:
        """
        Check if access is allowed.
        
        Returns (allowed, reason).
        """
        policy = self.get_applicable_policy(actor, actor_type)
        
        if not policy:
            self._log_access_denied(actor, actor_type, record, "No policy found")
            return False, "No access policy found"
        
        # Check category restrictions
        if record.category in policy.denied_categories:
            self._log_access_denied(actor, actor_type, record, "Category denied")
            return False, f"Access to {record.category.value} is denied"
        
        if policy.allowed_categories and record.category not in policy.allowed_categories:
            self._log_access_denied(actor, actor_type, record, "Category not allowed")
            return False, f"Access to {record.category.value} not allowed"
        
        # Check access level
        if policy.access_level == AccessLevel.NONE:
            self._log_access_denied(actor, actor_type, record, "No access level")
            return False, "No access granted"
        
        # Check for write attempts on read-only
        if action in [AuditAction.HARD_DELETE, AuditAction.POLICY_CHANGE]:
            if policy.access_level in [AccessLevel.INTERNAL_READ, AccessLevel.EXTERNAL_READ]:
                self._log_access_denied(actor, actor_type, record, "Write not allowed")
                return False, "Write operations not allowed"
        
        # Check export permission
        if action == AuditAction.EXPORT:
            if not policy.can_export:
                self._log_access_denied(actor, actor_type, record, "Export not allowed")
                return False, "Export not permitted"
        
        # Log successful access check
        if policy.requires_audit:
            self._log_access_allowed(actor, actor_type, record, action)
        
        return True, "Access granted"
    
    def _log_access_allowed(
        self,
        actor: str,
        actor_type: str,
        record: DataRecord,
        action: AuditAction,
    ) -> None:
        """Log allowed access."""
        audit = AuditRecord(
            audit_id=f"audit_{uuid.uuid4().hex}",
            record_id=record.record_id,
            action=action,
            timestamp=datetime.utcnow(),
            actor=actor,
            actor_type=actor_type,
            details={"category": record.category.value},
            success=True,
        )
        
        if self._audit_callback:
            self._audit_callback(audit)
        
        self._access_log.append(audit.to_dict())
    
    def _log_access_denied(
        self,
        actor: str,
        actor_type: str,
        record: DataRecord,
        reason: str,
    ) -> None:
        """Log denied access."""
        audit = AuditRecord(
            audit_id=f"audit_{uuid.uuid4().hex}",
            record_id=record.record_id,
            action=AuditAction.ACCESS_DENIED,
            timestamp=datetime.utcnow(),
            actor=actor,
            actor_type=actor_type,
            details={"category": record.category.value, "reason": reason},
            success=False,
            error_message=reason,
        )
        
        if self._audit_callback:
            self._audit_callback(audit)
        
        self._access_log.append(audit.to_dict())
        logger.warning(f"Access denied: {actor} ({actor_type}) -> {record.record_id}: {reason}")
    
    def get_access_log(
        self,
        since: Optional[datetime] = None,
        actor: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get access log entries."""
        log = self._access_log
        
        if since:
            log = [
                entry for entry in log
                if datetime.fromisoformat(entry["timestamp"]) >= since
            ]
        
        if actor:
            log = [entry for entry in log if entry["actor"] == actor]
        
        return log[-limit:]


# ============================================================
# EXPORT CONTROLLER
# ============================================================

class ExportController:
    """
    Controls data exports.
    
    All exports must be logged.
    """
    
    def __init__(
        self,
        access_controller: AccessController,
        audit_callback: Optional[Callable[[AuditRecord], None]] = None,
    ):
        self._access_controller = access_controller
        self._audit_callback = audit_callback
        self._export_log: List[Dict[str, Any]] = []
    
    def can_export(
        self,
        actor: str,
        records: List[DataRecord],
    ) -> tuple:
        """
        Check if export is allowed.
        
        Returns (allowed, denied_records, reason).
        """
        denied = []
        
        for record in records:
            allowed, reason = self._access_controller.check_access(
                actor=actor,
                actor_type="export",
                record=record,
                action=AuditAction.EXPORT,
            )
            if not allowed:
                denied.append((record.record_id, reason))
        
        if denied:
            return False, denied, "Some records cannot be exported"
        
        return True, [], "Export allowed"
    
    def log_export(
        self,
        actor: str,
        records: List[DataRecord],
        destination: str,
        format: str,
    ) -> str:
        """
        Log an export operation.
        
        Returns export ID.
        """
        export_id = f"export_{uuid.uuid4().hex}"
        
        export_entry = {
            "export_id": export_id,
            "actor": actor,
            "timestamp": datetime.utcnow().isoformat(),
            "record_count": len(records),
            "record_ids": [r.record_id for r in records],
            "categories": list(set(r.category.value for r in records)),
            "destination": destination,
            "format": format,
        }
        
        self._export_log.append(export_entry)
        
        logger.info(
            f"Export logged: {export_id}, {len(records)} records by {actor}"
        )
        
        return export_id
    
    def get_export_log(
        self,
        since: Optional[datetime] = None,
        actor: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get export log entries."""
        log = self._export_log
        
        if since:
            log = [
                entry for entry in log
                if datetime.fromisoformat(entry["timestamp"]) >= since
            ]
        
        if actor:
            log = [entry for entry in log if entry["actor"] == actor]
        
        return log


# ============================================================
# IMMUTABILITY ENFORCER
# ============================================================

class ImmutabilityEnforcer:
    """
    Enforces data immutability.
    
    No module may alter retained historical data.
    """
    
    def __init__(
        self,
        audit_callback: Optional[Callable[[AuditRecord], None]] = None,
    ):
        self._audit_callback = audit_callback
        self._sealed_records: Set[str] = set()
        self._violation_log: List[Dict[str, Any]] = []
    
    def seal_record(self, record: DataRecord) -> None:
        """
        Seal a record to prevent modifications.
        
        Sealed records cannot be modified, only marked for deletion.
        """
        self._sealed_records.add(record.record_id)
        logger.debug(f"Sealed record: {record.record_id}")
    
    def is_sealed(self, record_id: str) -> bool:
        """Check if a record is sealed."""
        return record_id in self._sealed_records
    
    def check_modification(
        self,
        record: DataRecord,
        actor: str,
        modification_type: str,
    ) -> tuple:
        """
        Check if modification is allowed.
        
        Returns (allowed, reason).
        """
        if not self.is_sealed(record.record_id):
            return True, "Record not sealed"
        
        # Sealed records can only be marked for deletion, not modified
        if modification_type == "delete":
            return True, "Deletion of sealed record allowed"
        
        # Log violation attempt
        violation = {
            "record_id": record.record_id,
            "actor": actor,
            "modification_type": modification_type,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._violation_log.append(violation)
        
        logger.warning(
            f"Immutability violation attempt: {actor} tried to {modification_type} "
            f"sealed record {record.record_id}"
        )
        
        return False, "Cannot modify sealed/historical data"
    
    def get_violation_log(self) -> List[Dict[str, Any]]:
        """Get immutability violation log."""
        return self._violation_log.copy()


# ============================================================
# AUDIT LOGGER
# ============================================================

class AuditLogger:
    """
    Comprehensive audit logging.
    
    All retention, deletion, and access actions must be logged.
    """
    
    def __init__(self):
        self._records: List[AuditRecord] = []
    
    def log(self, record: AuditRecord) -> None:
        """Log an audit record."""
        self._records.append(record)
        
        level = logging.INFO if record.success else logging.WARNING
        logger.log(
            level,
            f"Audit: {record.action.value} on {record.record_id} by "
            f"{record.actor} ({record.actor_type})"
        )
    
    def get_records(
        self,
        since: Optional[datetime] = None,
        action: Optional[AuditAction] = None,
        actor: Optional[str] = None,
        record_id: Optional[str] = None,
        success_only: bool = False,
        limit: int = 1000,
    ) -> List[AuditRecord]:
        """Query audit records."""
        records = self._records
        
        if since:
            records = [r for r in records if r.timestamp >= since]
        
        if action:
            records = [r for r in records if r.action == action]
        
        if actor:
            records = [r for r in records if r.actor == actor]
        
        if record_id:
            records = [r for r in records if r.record_id == record_id]
        
        if success_only:
            records = [r for r in records if r.success]
        
        return records[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get audit statistics."""
        action_counts = {}
        success_count = 0
        failure_count = 0
        
        for record in self._records:
            action = record.action.value
            action_counts[action] = action_counts.get(action, 0) + 1
            
            if record.success:
                success_count += 1
            else:
                failure_count += 1
        
        return {
            "total_records": len(self._records),
            "success_count": success_count,
            "failure_count": failure_count,
            "action_breakdown": action_counts,
        }


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_access_controller(
    audit_callback: Optional[Callable[[AuditRecord], None]] = None,
) -> AccessController:
    """Create an AccessController."""
    return AccessController(audit_callback)


def create_export_controller(
    access_controller: Optional[AccessController] = None,
) -> ExportController:
    """Create an ExportController."""
    return ExportController(
        access_controller=access_controller or create_access_controller()
    )


def create_immutability_enforcer() -> ImmutabilityEnforcer:
    """Create an ImmutabilityEnforcer."""
    return ImmutabilityEnforcer()


def create_audit_logger() -> AuditLogger:
    """Create an AuditLogger."""
    return AuditLogger()
