"""
Data Processing - Deduplicator.

============================================================
RESPONSIBILITY
============================================================
Identifies and handles duplicate data across all sources.

- Detects exact duplicates via hash comparison
- Detects near-duplicates via similarity scoring
- Maintains deduplication index
- Preserves first occurrence, marks subsequent as duplicates

============================================================
DESIGN PRINCIPLES
============================================================
- Never delete raw data - only mark as duplicate
- Configurable similarity thresholds
- Efficient for high-volume data
- Time-window based deduplication

============================================================
DEDUPLICATION STRATEGIES
============================================================
1. Exact match: Hash-based comparison
2. Near-duplicate: SimHash-based similarity
3. Cross-source: Same story from different sources
4. Temporal: Same source, same story updated

============================================================
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID


# ============================================================
# CONFIGURATION
# ============================================================


@dataclass
class DeduplicatorConfig:
    """Configuration for deduplication."""
    
    # Exact match settings
    exact_match_enabled: bool = True
    
    # Near-duplicate settings
    near_duplicate_enabled: bool = True
    similarity_threshold: float = 0.85
    shingle_size: int = 3  # For SimHash
    
    # Time window
    time_window_hours: int = 168  # 7 days
    
    # Hash algorithm
    hash_algorithm: str = "sha256"
    
    # Version
    version: str = "1.0.0"


# ============================================================
# RESULT TYPES
# ============================================================


@dataclass
class DeduplicationResult:
    """Result of deduplication check."""
    
    item_id: UUID
    is_duplicate: bool
    duplicate_type: Optional[str] = None  # exact, near, cross_source
    original_id: Optional[UUID] = None
    similarity_score: Optional[float] = None
    checked_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================
# DEDUPLICATOR
# ============================================================


class Deduplicator:
    """
    Handles deduplication of content.
    
    ============================================================
    USAGE
    ============================================================
    ```python
    config = DeduplicatorConfig()
    dedup = Deduplicator(config)
    
    result = dedup.check_duplicate(item_id, content, source)
    if result.is_duplicate:
        # Mark as duplicate, link to original
        pass
    ```
    
    ============================================================
    """
    
    def __init__(self, config: DeduplicatorConfig) -> None:
        """
        Initialize the deduplicator.
        
        Args:
            config: Deduplication configuration
        """
        self._config = config
        
        # In-memory hash index (would be backed by DB in production)
        self._hash_index: Dict[str, Tuple[UUID, datetime]] = {}
        self._simhash_index: Dict[int, List[Tuple[UUID, int, datetime]]] = {}
    
    @property
    def version(self) -> str:
        """Get deduplicator version."""
        return self._config.version
    
    # =========================================================
    # PUBLIC API
    # =========================================================
    
    def check_duplicate(
        self,
        item_id: UUID,
        content: str,
        source: str,
        timestamp: Optional[datetime] = None,
    ) -> DeduplicationResult:
        """
        Check if content is a duplicate.
        
        Args:
            item_id: ID of the item being checked
            content: Text content to check
            source: Source identifier
            timestamp: Content timestamp
            
        Returns:
            DeduplicationResult with duplicate info
        """
        timestamp = timestamp or datetime.utcnow()
        
        # Normalize content for comparison
        normalized = self._normalize_content(content)
        
        # Check exact match first
        if self._config.exact_match_enabled:
            exact_result = self._check_exact_match(item_id, normalized, timestamp)
            if exact_result.is_duplicate:
                return exact_result
        
        # Check near-duplicate
        if self._config.near_duplicate_enabled:
            near_result = self._check_near_duplicate(item_id, normalized, timestamp)
            if near_result.is_duplicate:
                return near_result
        
        # Not a duplicate - add to index
        self._add_to_index(item_id, normalized, timestamp)
        
        return DeduplicationResult(
            item_id=item_id,
            is_duplicate=False,
        )
    
    def check_batch(
        self,
        items: List[Tuple[UUID, str, str, Optional[datetime]]],
    ) -> List[DeduplicationResult]:
        """
        Check a batch of items for duplicates.
        
        Args:
            items: List of (item_id, content, source, timestamp) tuples
            
        Returns:
            List of DeduplicationResult
        """
        results = []
        for item_id, content, source, timestamp in items:
            result = self.check_duplicate(item_id, content, source, timestamp)
            results.append(result)
        return results
    
    def compute_hash(self, content: str) -> str:
        """
        Compute hash of content.
        
        Args:
            content: Text content
            
        Returns:
            Hash string
        """
        normalized = self._normalize_content(content)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    def clear_expired(self) -> int:
        """
        Clear expired entries from the index.
        
        Returns:
            Number of entries cleared
        """
        cutoff = datetime.utcnow() - timedelta(hours=self._config.time_window_hours)
        cleared = 0
        
        # Clear exact hash index
        expired_hashes = [
            h for h, (_, ts) in self._hash_index.items()
            if ts < cutoff
        ]
        for h in expired_hashes:
            del self._hash_index[h]
            cleared += 1
        
        # Clear simhash index
        for bucket_key in list(self._simhash_index.keys()):
            self._simhash_index[bucket_key] = [
                (id_, sh, ts) for id_, sh, ts in self._simhash_index[bucket_key]
                if ts >= cutoff
            ]
            if not self._simhash_index[bucket_key]:
                del self._simhash_index[bucket_key]
        
        return cleared
    
    # =========================================================
    # EXACT MATCH
    # =========================================================
    
    def _check_exact_match(
        self,
        item_id: UUID,
        normalized_content: str,
        timestamp: datetime,
    ) -> DeduplicationResult:
        """Check for exact hash match."""
        content_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        
        if content_hash in self._hash_index:
            original_id, original_ts = self._hash_index[content_hash]
            return DeduplicationResult(
                item_id=item_id,
                is_duplicate=True,
                duplicate_type="exact",
                original_id=original_id,
                similarity_score=1.0,
            )
        
        return DeduplicationResult(
            item_id=item_id,
            is_duplicate=False,
        )
    
    # =========================================================
    # NEAR-DUPLICATE DETECTION
    # =========================================================
    
    def _check_near_duplicate(
        self,
        item_id: UUID,
        normalized_content: str,
        timestamp: datetime,
    ) -> DeduplicationResult:
        """Check for near-duplicate using SimHash."""
        content_simhash = self._compute_simhash(normalized_content)
        
        # Get candidate buckets (LSH-style)
        bucket_key = content_simhash >> 32  # Use high 32 bits as bucket
        
        if bucket_key in self._simhash_index:
            for original_id, original_simhash, original_ts in self._simhash_index[bucket_key]:
                similarity = self._hamming_similarity(content_simhash, original_simhash)
                
                if similarity >= self._config.similarity_threshold:
                    return DeduplicationResult(
                        item_id=item_id,
                        is_duplicate=True,
                        duplicate_type="near",
                        original_id=original_id,
                        similarity_score=similarity,
                    )
        
        return DeduplicationResult(
            item_id=item_id,
            is_duplicate=False,
        )
    
    def _compute_simhash(self, content: str) -> int:
        """
        Compute SimHash of content.
        
        Uses shingle-based approach for text similarity.
        """
        # Generate shingles
        words = content.split()
        shingles = set()
        for i in range(len(words) - self._config.shingle_size + 1):
            shingle = " ".join(words[i:i + self._config.shingle_size])
            shingles.add(shingle)
        
        if not shingles:
            return 0
        
        # Compute SimHash
        v = [0] * 64  # 64-bit hash
        
        for shingle in shingles:
            # Hash each shingle
            h = int(hashlib.md5(shingle.encode()).hexdigest(), 16) % (2 ** 64)
            
            for i in range(64):
                if h & (1 << i):
                    v[i] += 1
                else:
                    v[i] -= 1
        
        # Generate final hash
        fingerprint = 0
        for i in range(64):
            if v[i] > 0:
                fingerprint |= (1 << i)
        
        return fingerprint
    
    def _hamming_similarity(self, hash1: int, hash2: int) -> float:
        """
        Compute similarity based on Hamming distance.
        
        Returns:
            Similarity score between 0 and 1
        """
        xor = hash1 ^ hash2
        distance = bin(xor).count("1")
        similarity = 1 - (distance / 64)
        return similarity
    
    # =========================================================
    # INDEX MANAGEMENT
    # =========================================================
    
    def _add_to_index(
        self,
        item_id: UUID,
        normalized_content: str,
        timestamp: datetime,
    ) -> None:
        """Add item to deduplication indices."""
        # Add to exact hash index
        content_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        self._hash_index[content_hash] = (item_id, timestamp)
        
        # Add to simhash index
        if self._config.near_duplicate_enabled:
            content_simhash = self._compute_simhash(normalized_content)
            bucket_key = content_simhash >> 32
            
            if bucket_key not in self._simhash_index:
                self._simhash_index[bucket_key] = []
            
            self._simhash_index[bucket_key].append((item_id, content_simhash, timestamp))
    
    def _normalize_content(self, content: str) -> str:
        """
        Normalize content for comparison.
        
        - Lowercase
        - Remove extra whitespace
        - Remove punctuation
        """
        # Lowercase
        normalized = content.lower()
        
        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        
        # Remove common punctuation (keep alphanumeric and spaces)
        normalized = re.sub(r"[^\w\s]", "", normalized)
        
        return normalized
    
    # =========================================================
    # PERSISTENCE HELPERS
    # =========================================================
    
    def load_index_from_records(
        self,
        records: List[Tuple[UUID, str, datetime]],
    ) -> None:
        """
        Load index from existing records.
        
        Args:
            records: List of (id, content_hash or content, timestamp)
        """
        for record_id, content, timestamp in records:
            # Check if content looks like a hash (64 hex chars)
            if len(content) == 64 and all(c in "0123456789abcdef" for c in content.lower()):
                # It's already a hash
                self._hash_index[content] = (record_id, timestamp)
            else:
                # It's content, compute hash
                self._add_to_index(record_id, self._normalize_content(content), timestamp)
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the deduplication index."""
        return {
            "exact_hash_count": len(self._hash_index),
            "simhash_bucket_count": len(self._simhash_index),
            "simhash_entry_count": sum(
                len(entries) for entries in self._simhash_index.values()
            ),
            "version": self._config.version,
        }
