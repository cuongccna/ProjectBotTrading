"""
Data Lineage Tracking.

============================================================
PURPOSE
============================================================
Tracks the complete lineage of every data record.

Every derived data point must be traceable back to raw inputs.

Lineage includes:
- Source information
- Processing steps
- Timestamp tracking
- Correlation IDs for related records

============================================================
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .models import (
    DataCategory,
    DataLineage,
    DataSource,
    ProcessingStep,
    generate_record_id,
    generate_correlation_id,
)


logger = logging.getLogger(__name__)


# ============================================================
# LINEAGE BUILDER
# ============================================================

class LineageBuilder:
    """Builder for constructing data lineage."""
    
    def __init__(self, record_id: str):
        self._record_id = record_id
        self._source: Optional[DataSource] = None
        self._processing_steps: List[ProcessingStep] = []
        self._parent_record_ids: List[str] = []
        self._correlation_id: Optional[str] = None
    
    def with_source(
        self,
        source_type: str,
        source_name: str,
        source_version: str = "1.0.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "LineageBuilder":
        """Set the data source."""
        self._source = DataSource(
            source_id=f"src_{uuid.uuid4().hex[:12]}",
            source_type=source_type,
            source_name=source_name,
            source_version=source_version,
            metadata=metadata or {},
        )
        return self
    
    def with_processing_step(
        self,
        step_name: str,
        module_name: str,
        module_version: str,
        input_record_ids: List[str],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> "LineageBuilder":
        """Add a processing step."""
        step = ProcessingStep(
            step_id=f"step_{uuid.uuid4().hex[:12]}",
            step_name=step_name,
            module_name=module_name,
            module_version=module_version,
            timestamp=datetime.utcnow(),
            input_record_ids=input_record_ids,
            parameters=parameters or {},
        )
        self._processing_steps.append(step)
        return self
    
    def with_parent_records(self, parent_ids: List[str]) -> "LineageBuilder":
        """Set parent record IDs."""
        self._parent_record_ids = parent_ids
        return self
    
    def with_correlation_id(self, correlation_id: str) -> "LineageBuilder":
        """Set correlation ID."""
        self._correlation_id = correlation_id
        return self
    
    def build(self) -> DataLineage:
        """Build the lineage object."""
        if not self._source:
            raise ValueError("Source must be set before building lineage")
        
        return DataLineage(
            lineage_id=f"lin_{uuid.uuid4().hex}",
            record_id=self._record_id,
            source=self._source,
            processing_steps=self._processing_steps,
            parent_record_ids=self._parent_record_ids,
            correlation_id=self._correlation_id,
        )


# ============================================================
# LINEAGE TRACKER
# ============================================================

class LineageTracker:
    """
    Tracks data lineage across the system.
    
    Ensures every derived data point can be traced back to raw inputs.
    """
    
    def __init__(self):
        self._lineages: Dict[str, DataLineage] = {}
        self._correlation_groups: Dict[str, Set[str]] = {}
        self._parent_to_children: Dict[str, Set[str]] = {}
    
    def register_lineage(self, lineage: DataLineage) -> None:
        """Register a lineage record."""
        self._lineages[lineage.record_id] = lineage
        
        # Track correlation groups
        if lineage.correlation_id:
            if lineage.correlation_id not in self._correlation_groups:
                self._correlation_groups[lineage.correlation_id] = set()
            self._correlation_groups[lineage.correlation_id].add(lineage.record_id)
        
        # Track parent-child relationships
        for parent_id in lineage.parent_record_ids:
            if parent_id not in self._parent_to_children:
                self._parent_to_children[parent_id] = set()
            self._parent_to_children[parent_id].add(lineage.record_id)
        
        logger.debug(f"Registered lineage for record: {lineage.record_id}")
    
    def get_lineage(self, record_id: str) -> Optional[DataLineage]:
        """Get lineage for a record."""
        return self._lineages.get(record_id)
    
    def get_root_records(self, record_id: str) -> List[str]:
        """
        Trace back to root source records.
        
        Returns list of record IDs that are the ultimate sources.
        """
        visited: Set[str] = set()
        roots: List[str] = []
        
        def trace_back(rid: str) -> None:
            if rid in visited:
                return
            visited.add(rid)
            
            lineage = self._lineages.get(rid)
            if not lineage:
                # Record not found, might be external source
                roots.append(rid)
                return
            
            if not lineage.parent_record_ids:
                # No parents, this is a root
                roots.append(rid)
            else:
                for parent_id in lineage.parent_record_ids:
                    trace_back(parent_id)
        
        trace_back(record_id)
        return roots
    
    def get_derived_records(self, record_id: str) -> List[str]:
        """
        Get all records derived from this record.
        
        Returns list of record IDs that use this as source.
        """
        children = self._parent_to_children.get(record_id, set())
        return list(children)
    
    def get_all_descendants(self, record_id: str) -> List[str]:
        """Get all descendants (children, grandchildren, etc.)."""
        visited: Set[str] = set()
        descendants: List[str] = []
        
        def collect_descendants(rid: str) -> None:
            children = self._parent_to_children.get(rid, set())
            for child_id in children:
                if child_id not in visited:
                    visited.add(child_id)
                    descendants.append(child_id)
                    collect_descendants(child_id)
        
        collect_descendants(record_id)
        return descendants
    
    def get_correlated_records(self, correlation_id: str) -> List[str]:
        """Get all records with the same correlation ID."""
        records = self._correlation_groups.get(correlation_id, set())
        return list(records)
    
    def get_processing_history(self, record_id: str) -> List[ProcessingStep]:
        """Get the full processing history for a record."""
        lineage = self._lineages.get(record_id)
        if not lineage:
            return []
        return lineage.processing_steps
    
    def validate_lineage_chain(self, record_id: str) -> bool:
        """
        Validate that lineage chain is complete.
        
        Returns True if all parents exist in tracker.
        """
        lineage = self._lineages.get(record_id)
        if not lineage:
            return False
        
        for parent_id in lineage.parent_record_ids:
            if parent_id not in self._lineages:
                logger.warning(
                    f"Broken lineage chain: {record_id} -> {parent_id} (not found)"
                )
                return False
        
        return True
    
    def export_lineage_graph(
        self,
        record_id: str,
        max_depth: int = 10,
    ) -> Dict[str, Any]:
        """
        Export lineage as a graph structure.
        
        Useful for visualization and analysis.
        """
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, str]] = []
        visited: Set[str] = set()
        
        def build_graph(rid: str, depth: int) -> None:
            if rid in visited or depth > max_depth:
                return
            visited.add(rid)
            
            lineage = self._lineages.get(rid)
            if lineage:
                nodes[rid] = {
                    "record_id": rid,
                    "source_type": lineage.source.source_type,
                    "source_name": lineage.source.source_name,
                    "processing_steps": len(lineage.processing_steps),
                }
                
                for parent_id in lineage.parent_record_ids:
                    edges.append({"from": parent_id, "to": rid})
                    build_graph(parent_id, depth + 1)
        
        build_graph(record_id, 0)
        
        return {
            "root_record": record_id,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }


# ============================================================
# LINEAGE REGISTRY
# ============================================================

class LineageRegistry:
    """
    Persistent registry for data lineage.
    
    Supports database storage for production use.
    """
    
    def __init__(self, db_connection: Any = None):
        self._db = db_connection
        self._in_memory_tracker = LineageTracker()
    
    async def save_lineage(self, lineage: DataLineage) -> None:
        """Save lineage to database."""
        # Register in memory tracker
        self._in_memory_tracker.register_lineage(lineage)
        
        # Save to database (placeholder)
        # await self._db.execute(
        #     "INSERT INTO data_lineage (...) VALUES (...)",
        #     lineage.to_dict()
        # )
        
        logger.debug(f"Saved lineage: {lineage.lineage_id}")
    
    async def get_lineage(self, record_id: str) -> Optional[DataLineage]:
        """Get lineage from database."""
        # Try in-memory first
        lineage = self._in_memory_tracker.get_lineage(record_id)
        if lineage:
            return lineage
        
        # Load from database (placeholder)
        # row = await self._db.fetchone(
        #     "SELECT * FROM data_lineage WHERE record_id = ?",
        #     (record_id,)
        # )
        # if row:
        #     return self._deserialize_lineage(row)
        
        return None
    
    async def trace_to_root(self, record_id: str) -> List[str]:
        """Trace record to root sources."""
        return self._in_memory_tracker.get_root_records(record_id)
    
    async def find_derived(self, record_id: str) -> List[str]:
        """Find all records derived from this one."""
        return self._in_memory_tracker.get_derived_records(record_id)
    
    async def get_by_correlation(self, correlation_id: str) -> List[str]:
        """Get records by correlation ID."""
        return self._in_memory_tracker.get_correlated_records(correlation_id)
    
    async def export_lineage_report(
        self,
        record_id: str,
    ) -> Dict[str, Any]:
        """Export a comprehensive lineage report."""
        lineage = await self.get_lineage(record_id)
        if not lineage:
            return {"error": f"Lineage not found for {record_id}"}
        
        roots = await self.trace_to_root(record_id)
        derived = await self.find_derived(record_id)
        graph = self._in_memory_tracker.export_lineage_graph(record_id)
        
        return {
            "record_id": record_id,
            "lineage": lineage.to_dict(),
            "root_sources": roots,
            "derived_records": derived,
            "graph": graph,
            "generated_at": datetime.utcnow().isoformat(),
        }


# ============================================================
# CORRELATION MANAGER
# ============================================================

class CorrelationManager:
    """
    Manages correlation IDs for linking related records.
    """
    
    def __init__(self):
        self._active_correlations: Dict[str, Dict[str, Any]] = {}
    
    def create_correlation(
        self,
        context: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new correlation ID."""
        correlation_id = generate_correlation_id()
        
        self._active_correlations[correlation_id] = {
            "created_at": datetime.utcnow(),
            "context": context,
            "metadata": metadata or {},
            "record_count": 0,
        }
        
        logger.debug(f"Created correlation: {correlation_id} for {context}")
        return correlation_id
    
    def increment_record_count(self, correlation_id: str) -> None:
        """Increment record count for a correlation."""
        if correlation_id in self._active_correlations:
            self._active_correlations[correlation_id]["record_count"] += 1
    
    def get_correlation_info(
        self,
        correlation_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get information about a correlation."""
        return self._active_correlations.get(correlation_id)
    
    def close_correlation(self, correlation_id: str) -> None:
        """Mark a correlation as closed."""
        if correlation_id in self._active_correlations:
            self._active_correlations[correlation_id]["closed_at"] = datetime.utcnow()
            logger.debug(f"Closed correlation: {correlation_id}")


# ============================================================
# FACTORY FUNCTIONS
# ============================================================

def create_lineage_builder(record_id: str) -> LineageBuilder:
    """Create a LineageBuilder."""
    return LineageBuilder(record_id)


def create_lineage_tracker() -> LineageTracker:
    """Create a LineageTracker."""
    return LineageTracker()


def create_lineage_registry(db_connection: Any = None) -> LineageRegistry:
    """Create a LineageRegistry."""
    return LineageRegistry(db_connection)


def create_correlation_manager() -> CorrelationManager:
    """Create a CorrelationManager."""
    return CorrelationManager()


def build_simple_lineage(
    record_id: str,
    source_type: str,
    source_name: str,
    parent_record_ids: Optional[List[str]] = None,
    correlation_id: Optional[str] = None,
) -> DataLineage:
    """Build a simple lineage with minimal configuration."""
    builder = LineageBuilder(record_id)
    builder.with_source(source_type, source_name)
    
    if parent_record_ids:
        builder.with_parent_records(parent_record_ids)
    
    if correlation_id:
        builder.with_correlation_id(correlation_id)
    
    return builder.build()
