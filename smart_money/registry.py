"""
Wallet Registry Manager - CRUD operations for curated wallet list.

Wallets are manually sourced from Arkham UI and other intelligence sources.
DO NOT scrape Arkham programmatically - this is human-curated intelligence.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import SmartMoneyConfig, get_config
from .exceptions import StorageError, WalletNotFoundError
from .models import Chain, EntityType, WalletInfo


logger = logging.getLogger(__name__)


class WalletRegistryManager:
    """
    Manages the curated smart money wallet registry.
    
    Wallets are stored in SQLite for persistence.
    The registry is human-curated from sources like Arkham UI.
    """
    
    def __init__(
        self,
        config: Optional[SmartMoneyConfig] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self.config = config or get_config()
        self.db_path = db_path or self.config.db_path
        
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_db()
        
        # In-memory cache
        self._cache: dict[str, WalletInfo] = {}
        self._cache_loaded = False
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS wallets (
                        address TEXT NOT NULL,
                        chain TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        entity_name TEXT,
                        source TEXT DEFAULT 'arkham_ui',
                        confidence_level REAL DEFAULT 0.5,
                        tags TEXT DEFAULT '[]',
                        notes TEXT DEFAULT '',
                        first_seen TEXT NOT NULL,
                        last_activity TEXT,
                        is_active INTEGER DEFAULT 1,
                        avg_transaction_value_usd REAL DEFAULT 0,
                        transaction_count_30d INTEGER DEFAULT 0,
                        total_volume_30d_usd REAL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (address, chain)
                    )
                """)
                
                # Index for efficient queries
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_wallets_chain 
                    ON wallets(chain)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_wallets_entity_type 
                    ON wallets(entity_type)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_wallets_active 
                    ON wallets(is_active)
                """)
                
                conn.commit()
                logger.info(f"Wallet registry initialized at {self.db_path}")
                
        except sqlite3.Error as e:
            raise StorageError(f"Failed to initialize wallet database: {e}")
    
    def _load_cache(self) -> None:
        """Load all wallets into memory cache."""
        if self._cache_loaded:
            return
        
        try:
            wallets = self.get_all_wallets()
            self._cache = {
                self._cache_key(w.address, w.chain): w
                for w in wallets
            }
            self._cache_loaded = True
            logger.debug(f"Loaded {len(self._cache)} wallets into cache")
        except Exception as e:
            logger.warning(f"Failed to load wallet cache: {e}")
    
    def _cache_key(self, address: str, chain: Chain) -> str:
        """Generate cache key for wallet."""
        return f"{chain.value}:{address.lower()}"
    
    def add_wallet(self, wallet: WalletInfo) -> bool:
        """
        Add a wallet to the registry.
        
        Returns True if added, False if already exists.
        """
        now = datetime.utcnow().isoformat()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO wallets (
                        address, chain, entity_type, entity_name,
                        source, confidence_level, tags, notes,
                        first_seen, last_activity, is_active,
                        avg_transaction_value_usd, transaction_count_30d,
                        total_volume_30d_usd, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wallet.address.lower(),
                    wallet.chain.value,
                    wallet.entity_type.value,
                    wallet.entity_name,
                    wallet.source,
                    wallet.confidence_level,
                    json.dumps(wallet.tags),
                    wallet.notes,
                    wallet.first_seen.isoformat(),
                    wallet.last_activity.isoformat() if wallet.last_activity else None,
                    1 if wallet.is_active else 0,
                    wallet.avg_transaction_value_usd,
                    wallet.transaction_count_30d,
                    wallet.total_volume_30d_usd,
                    now,
                    now,
                ))
                conn.commit()
            
            # Update cache
            key = self._cache_key(wallet.address, wallet.chain)
            self._cache[key] = wallet
            
            logger.info(f"Added wallet: {wallet.address[:10]}... ({wallet.chain.value})")
            return True
            
        except sqlite3.IntegrityError:
            logger.debug(f"Wallet already exists: {wallet.address[:10]}...")
            return False
        except sqlite3.Error as e:
            logger.error(f"Failed to add wallet: {e}")
            raise StorageError(f"Failed to add wallet: {e}")
    
    def update_wallet(self, wallet: WalletInfo) -> bool:
        """Update an existing wallet."""
        now = datetime.utcnow().isoformat()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    UPDATE wallets SET
                        entity_type = ?,
                        entity_name = ?,
                        source = ?,
                        confidence_level = ?,
                        tags = ?,
                        notes = ?,
                        last_activity = ?,
                        is_active = ?,
                        avg_transaction_value_usd = ?,
                        transaction_count_30d = ?,
                        total_volume_30d_usd = ?,
                        updated_at = ?
                    WHERE address = ? AND chain = ?
                """, (
                    wallet.entity_type.value,
                    wallet.entity_name,
                    wallet.source,
                    wallet.confidence_level,
                    json.dumps(wallet.tags),
                    wallet.notes,
                    wallet.last_activity.isoformat() if wallet.last_activity else None,
                    1 if wallet.is_active else 0,
                    wallet.avg_transaction_value_usd,
                    wallet.transaction_count_30d,
                    wallet.total_volume_30d_usd,
                    now,
                    wallet.address.lower(),
                    wallet.chain.value,
                ))
                conn.commit()
                
                if cursor.rowcount > 0:
                    # Update cache
                    key = self._cache_key(wallet.address, wallet.chain)
                    self._cache[key] = wallet
                    return True
                return False
                
        except sqlite3.Error as e:
            logger.error(f"Failed to update wallet: {e}")
            raise StorageError(f"Failed to update wallet: {e}")
    
    def get_wallet(self, address: str, chain: Chain) -> Optional[WalletInfo]:
        """Get a wallet by address and chain."""
        # Check cache first
        key = self._cache_key(address, chain)
        if key in self._cache:
            return self._cache[key]
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM wallets 
                    WHERE address = ? AND chain = ?
                """, (address.lower(), chain.value))
                
                row = cursor.fetchone()
                if row:
                    wallet = self._row_to_wallet(row)
                    self._cache[key] = wallet
                    return wallet
                return None
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get wallet: {e}")
            return None
    
    def get_wallets_by_chain(self, chain: Chain) -> list[WalletInfo]:
        """Get all wallets for a specific chain."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM wallets 
                    WHERE chain = ? AND is_active = 1
                    ORDER BY confidence_level DESC
                """, (chain.value,))
                
                return [self._row_to_wallet(row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get wallets by chain: {e}")
            return []
    
    def get_wallets_by_entity_type(
        self,
        entity_type: EntityType,
        chain: Optional[Chain] = None,
    ) -> list[WalletInfo]:
        """Get wallets by entity type."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                if chain:
                    cursor = conn.execute("""
                        SELECT * FROM wallets 
                        WHERE entity_type = ? AND chain = ? AND is_active = 1
                    """, (entity_type.value, chain.value))
                else:
                    cursor = conn.execute("""
                        SELECT * FROM wallets 
                        WHERE entity_type = ? AND is_active = 1
                    """, (entity_type.value,))
                
                return [self._row_to_wallet(row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get wallets by entity type: {e}")
            return []
    
    def get_all_wallets(self, active_only: bool = True) -> list[WalletInfo]:
        """Get all wallets in registry."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                if active_only:
                    cursor = conn.execute("""
                        SELECT * FROM wallets WHERE is_active = 1
                        ORDER BY chain, confidence_level DESC
                    """)
                else:
                    cursor = conn.execute("""
                        SELECT * FROM wallets
                        ORDER BY chain, confidence_level DESC
                    """)
                
                return [self._row_to_wallet(row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get all wallets: {e}")
            return []
    
    def get_cex_wallets(self, chain: Optional[Chain] = None) -> list[WalletInfo]:
        """Get all CEX wallets (hot + cold)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                if chain:
                    cursor = conn.execute("""
                        SELECT * FROM wallets 
                        WHERE entity_type IN ('cex_hot', 'cex_cold')
                        AND chain = ? AND is_active = 1
                    """, (chain.value,))
                else:
                    cursor = conn.execute("""
                        SELECT * FROM wallets 
                        WHERE entity_type IN ('cex_hot', 'cex_cold')
                        AND is_active = 1
                    """)
                
                return [self._row_to_wallet(row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get CEX wallets: {e}")
            return []
    
    def is_cex_wallet(self, address: str, chain: Chain) -> bool:
        """Check if address is a known CEX wallet."""
        wallet = self.get_wallet(address, chain)
        if wallet:
            return wallet.entity_type in (EntityType.CEX_HOT, EntityType.CEX_COLD)
        return False
    
    def update_last_activity(
        self,
        address: str,
        chain: Chain,
        timestamp: datetime,
    ) -> bool:
        """Update the last activity timestamp for a wallet."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    UPDATE wallets SET
                        last_activity = ?,
                        updated_at = ?
                    WHERE address = ? AND chain = ?
                """, (
                    timestamp.isoformat(),
                    datetime.utcnow().isoformat(),
                    address.lower(),
                    chain.value,
                ))
                conn.commit()
                
                # Update cache
                key = self._cache_key(address, chain)
                if key in self._cache:
                    wallet = self._cache[key]
                    # Create new instance with updated activity
                    self._cache[key] = WalletInfo(
                        address=wallet.address,
                        chain=wallet.chain,
                        entity_type=wallet.entity_type,
                        entity_name=wallet.entity_name,
                        source=wallet.source,
                        confidence_level=wallet.confidence_level,
                        tags=wallet.tags,
                        notes=wallet.notes,
                        first_seen=wallet.first_seen,
                        last_activity=timestamp,
                        is_active=wallet.is_active,
                        avg_transaction_value_usd=wallet.avg_transaction_value_usd,
                        transaction_count_30d=wallet.transaction_count_30d,
                        total_volume_30d_usd=wallet.total_volume_30d_usd,
                    )
                
                return cursor.rowcount > 0
                
        except sqlite3.Error as e:
            logger.error(f"Failed to update last activity: {e}")
            return False
    
    def deactivate_wallet(self, address: str, chain: Chain) -> bool:
        """Mark a wallet as inactive."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    UPDATE wallets SET
                        is_active = 0,
                        updated_at = ?
                    WHERE address = ? AND chain = ?
                """, (
                    datetime.utcnow().isoformat(),
                    address.lower(),
                    chain.value,
                ))
                conn.commit()
                
                # Remove from cache
                key = self._cache_key(address, chain)
                if key in self._cache:
                    del self._cache[key]
                
                return cursor.rowcount > 0
                
        except sqlite3.Error as e:
            logger.error(f"Failed to deactivate wallet: {e}")
            return False
    
    def count_wallets(
        self,
        chain: Optional[Chain] = None,
        active_only: bool = True,
    ) -> int:
        """Count wallets in registry."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if chain:
                    if active_only:
                        cursor = conn.execute("""
                            SELECT COUNT(*) FROM wallets 
                            WHERE chain = ? AND is_active = 1
                        """, (chain.value,))
                    else:
                        cursor = conn.execute("""
                            SELECT COUNT(*) FROM wallets WHERE chain = ?
                        """, (chain.value,))
                else:
                    if active_only:
                        cursor = conn.execute("""
                            SELECT COUNT(*) FROM wallets WHERE is_active = 1
                        """)
                    else:
                        cursor = conn.execute("SELECT COUNT(*) FROM wallets")
                
                return cursor.fetchone()[0]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to count wallets: {e}")
            return 0
    
    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Total counts
                total = conn.execute(
                    "SELECT COUNT(*) FROM wallets"
                ).fetchone()[0]
                active = conn.execute(
                    "SELECT COUNT(*) FROM wallets WHERE is_active = 1"
                ).fetchone()[0]
                
                # By chain
                by_chain = {}
                for row in conn.execute("""
                    SELECT chain, COUNT(*) FROM wallets 
                    WHERE is_active = 1 GROUP BY chain
                """):
                    by_chain[row[0]] = row[1]
                
                # By entity type
                by_entity = {}
                for row in conn.execute("""
                    SELECT entity_type, COUNT(*) FROM wallets 
                    WHERE is_active = 1 GROUP BY entity_type
                """):
                    by_entity[row[0]] = row[1]
                
                return {
                    "total_wallets": total,
                    "active_wallets": active,
                    "by_chain": by_chain,
                    "by_entity_type": by_entity,
                }
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
    
    def _row_to_wallet(self, row: sqlite3.Row) -> WalletInfo:
        """Convert database row to WalletInfo."""
        return WalletInfo(
            address=row["address"],
            chain=Chain(row["chain"]),
            entity_type=EntityType(row["entity_type"]),
            entity_name=row["entity_name"],
            source=row["source"],
            confidence_level=row["confidence_level"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            notes=row["notes"] or "",
            first_seen=datetime.fromisoformat(row["first_seen"]),
            last_activity=datetime.fromisoformat(row["last_activity"]) if row["last_activity"] else None,
            is_active=bool(row["is_active"]),
            avg_transaction_value_usd=row["avg_transaction_value_usd"],
            transaction_count_30d=row["transaction_count_30d"],
            total_volume_30d_usd=row["total_volume_30d_usd"],
        )
    
    def seed_default_wallets(self) -> int:
        """
        Seed registry with well-known wallets.
        
        These are publicly known addresses from Arkham UI.
        Returns count of wallets added.
        """
        default_wallets = [
            # Ethereum - CEX Hot Wallets (publicly known)
            WalletInfo(
                address="0x28c6c06298d514db089934071355e5743bf21d60",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.CEX_HOT,
                entity_name="Binance",
                source="arkham_ui",
                confidence_level=0.95,
                tags=["cex", "binance", "hot_wallet"],
            ),
            WalletInfo(
                address="0x21a31ee1afc51d94c2efccaa2092ad1028285549",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.CEX_HOT,
                entity_name="Binance",
                source="arkham_ui",
                confidence_level=0.95,
                tags=["cex", "binance", "hot_wallet"],
            ),
            WalletInfo(
                address="0xdfd5293d8e347dfe59e90efd55b2956a1343963d",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.CEX_HOT,
                entity_name="Coinbase",
                source="arkham_ui",
                confidence_level=0.95,
                tags=["cex", "coinbase", "hot_wallet"],
            ),
            WalletInfo(
                address="0x71660c4005ba85c37ccec55d0c4493e66fe775d3",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.CEX_HOT,
                entity_name="Coinbase",
                source="arkham_ui",
                confidence_level=0.95,
                tags=["cex", "coinbase", "hot_wallet"],
            ),
            # Market Makers
            WalletInfo(
                address="0x9507c04b10486547584c37bcbd931b2a4fee9a41",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.MARKET_MAKER,
                entity_name="Wintermute",
                source="arkham_ui",
                confidence_level=0.9,
                tags=["mm", "wintermute"],
            ),
            WalletInfo(
                address="0x2faf487a4414fe77e2327f0bf4ae2a264a776ad2",
                chain=Chain.ETHEREUM,
                entity_type=EntityType.CEX_HOT,
                entity_name="FTX (Defunct)",
                source="arkham_ui",
                confidence_level=0.9,
                tags=["cex", "ftx", "defunct"],
                is_active=False,
            ),
        ]
        
        added = 0
        for wallet in default_wallets:
            if self.add_wallet(wallet):
                added += 1
        
        logger.info(f"Seeded {added} default wallets")
        return added
    
    def import_from_json(self, json_path: str) -> int:
        """Import wallets from JSON file."""
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            added = 0
            for item in data.get("wallets", []):
                try:
                    wallet = WalletInfo.from_dict(item)
                    if self.add_wallet(wallet):
                        added += 1
                except Exception as e:
                    logger.warning(f"Failed to import wallet: {e}")
            
            return added
            
        except Exception as e:
            logger.error(f"Failed to import from JSON: {e}")
            return 0
    
    def export_to_json(self, json_path: str) -> bool:
        """Export all wallets to JSON file."""
        try:
            wallets = self.get_all_wallets(active_only=False)
            data = {
                "exported_at": datetime.utcnow().isoformat(),
                "wallet_count": len(wallets),
                "wallets": [w.to_dict() for w in wallets],
            }
            
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to export to JSON: {e}")
            return False
