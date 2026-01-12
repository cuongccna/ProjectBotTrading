"""
Data Ingestion - On-Chain Free Sources Collector.

============================================================
RESPONSIBILITY
============================================================
Collects on-chain data from free blockchain data sources.

- Fetches transaction data, whale movements, etc.
- Aggregates from multiple free sources
- Handles source-specific rate limits
- Stores raw data via RawOnChainRepository

============================================================
DESIGN PRINCIPLES
============================================================
- No business logic - collection only
- Aggregate multiple sources for redundancy
- Raw data is immutable
- Document source limitations

============================================================
DATA FLOW
============================================================
1. Fetch on-chain data from free sources
2. Parse to RawOnChainItem
3. Store via RawOnChainRepository
4. Return ingestion metrics

============================================================
FREE DATA SOURCES (CANDIDATES)
============================================================
- Blockchain explorers (public APIs)
- Free tier API providers
- Public mempool data
- DEX aggregator public endpoints

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from data_ingestion.collectors.base import BaseCollector
from data_ingestion.types import (
    DataType,
    IngestionSource,
    OnChainConfig,
    RawOnChainItem,
    FetchError,
    ParseError,
    StorageError,
)
from storage.repositories import RawOnChainRepository
from storage.repositories.exceptions import RepositoryException, DuplicateRecordError


class OnChainCollector(BaseCollector[RawOnChainItem]):
    """
    Collector for on-chain data from free sources.
    
    ============================================================
    WIRING
    ============================================================
    Source: Free blockchain data sources
    Repository: RawOnChainRepository
    Processing Stage: RAW
    
    ============================================================
    """
    
    def __init__(
        self,
        config: OnChainConfig,
        session: Session,
    ) -> None:
        """
        Initialize the on-chain collector.
        
        Args:
            config: On-chain source configuration
            session: Database session for repository
        """
        super().__init__(
            config=config,
            source=IngestionSource.ONCHAIN_FREE,
            data_type=DataType.ONCHAIN,
        )
        self._oc_config = config
        self._session = session
        self._repository = RawOnChainRepository(session)
        self._logger = logging.getLogger("collector.onchain_free")
    
    # =========================================================
    # FETCH - External API Call
    # =========================================================
    
    async def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Fetch on-chain data from free sources.
        
        This method aggregates data from multiple free sources.
        
        Returns:
            List of raw on-chain data dictionaries
            
        Raises:
            FetchError: On network or API errors
        """
        import httpx
        
        all_data: List[Dict[str, Any]] = []
        
        # Fetch from each supported chain
        for chain in self._oc_config.supported_chains:
            try:
                chain_data = await self._fetch_chain_data(chain)
                all_data.extend(chain_data)
            except FetchError as e:
                # Log but continue with other chains
                self._logger.warning(
                    f"Failed to fetch data for chain {chain}: {e}"
                )
        
        if not all_data:
            # If all chains failed, raise error
            raise FetchError(
                message="All chain data fetches failed",
                source=self.source_name,
                recoverable=True,
            )
        
        return all_data
    
    async def _fetch_chain_data(self, chain: str) -> List[Dict[str, Any]]:
        """
        Fetch data for a specific chain.
        
        Args:
            chain: Blockchain identifier (ethereum, bitcoin, etc.)
            
        Returns:
            List of raw on-chain data dictionaries
        """
        import httpx
        
        # TODO: Configure actual endpoints per chain
        # This is a placeholder implementation
        endpoints = self._get_chain_endpoints(chain)
        
        if not endpoints:
            return []
        
        all_chain_data: List[Dict[str, Any]] = []
        
        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            for endpoint_info in endpoints:
                try:
                    response = await client.get(
                        endpoint_info["url"],
                        params=endpoint_info.get("params", {}),
                        headers=endpoint_info.get("headers", {}),
                    )
                    response.raise_for_status()
                    
                    data = response.json()
                    
                    # Normalize response to list
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        # Try common response wrapper patterns
                        items = (
                            data.get("data") or 
                            data.get("result") or 
                            data.get("transactions") or
                            [data]
                        )
                    else:
                        items = []
                    
                    # Add chain and data_type metadata
                    for item in items:
                        if isinstance(item, dict):
                            item["_chain"] = chain
                            item["_data_type"] = endpoint_info.get("data_type", "unknown")
                            item["_source_endpoint"] = endpoint_info["name"]
                            all_chain_data.append(item)
                            
                except httpx.HTTPStatusError as e:
                    self._logger.warning(
                        f"HTTP error fetching {endpoint_info['name']}: {e}"
                    )
                except Exception as e:
                    self._logger.warning(
                        f"Error fetching {endpoint_info['name']}: {e}"
                    )
        
        return all_chain_data
    
    def _get_chain_endpoints(self, chain: str) -> List[Dict[str, Any]]:
        """
        Get API endpoints for a specific chain.
        
        Args:
            chain: Blockchain identifier
            
        Returns:
            List of endpoint configurations
            
        TODO: Move to configuration file
        """
        # TODO: Configure actual free API endpoints
        # These are placeholder endpoints - replace with actual free APIs
        endpoints: Dict[str, List[Dict[str, Any]]] = {
            "ethereum": [
                # Placeholder - replace with actual free Ethereum data sources
                # Examples: Etherscan public API, free tier providers
            ],
            "bitcoin": [
                # Placeholder - replace with actual free Bitcoin data sources
                # Examples: Blockchain.com public API
            ],
        }
        
        return endpoints.get(chain, [])
    
    # =========================================================
    # PARSE - Normalize to RawOnChainItem
    # =========================================================
    
    def parse_item(self, raw_data: Dict[str, Any]) -> RawOnChainItem:
        """
        Parse raw on-chain data to RawOnChainItem.
        
        Args:
            raw_data: Raw on-chain data from source
            
        Returns:
            RawOnChainItem ready for storage
            
        Raises:
            ParseError: On parsing errors
        """
        try:
            collected_at = datetime.utcnow()
            
            # Remove internal metadata before hashing
            clean_data = {
                k: v for k, v in raw_data.items() 
                if not k.startswith("_")
            }
            payload_hash = self.compute_payload_hash(clean_data)
            
            # Extract chain and data type from metadata
            chain = raw_data.get("_chain", "unknown")
            data_type = raw_data.get("_data_type", "transaction")
            
            # Extract block info if available
            block_number = None
            block_timestamp = None
            tx_hash = None
            
            # Try common field names
            block_number = (
                raw_data.get("blockNumber") or
                raw_data.get("block_number") or
                raw_data.get("height")
            )
            if block_number and isinstance(block_number, str):
                try:
                    block_number = int(block_number, 16) if block_number.startswith("0x") else int(block_number)
                except ValueError:
                    block_number = None
            
            tx_hash = (
                raw_data.get("hash") or
                raw_data.get("txHash") or
                raw_data.get("tx_hash") or
                raw_data.get("transactionHash")
            )
            
            # Parse block timestamp if available
            ts = raw_data.get("timeStamp") or raw_data.get("timestamp") or raw_data.get("time")
            if ts:
                try:
                    if isinstance(ts, (int, float)):
                        block_timestamp = datetime.utcfromtimestamp(ts)
                    elif isinstance(ts, str):
                        block_timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except (ValueError, OSError):
                    pass
            
            return RawOnChainItem(
                source=self.source_name,
                chain=chain,
                data_type=data_type,
                collected_at=collected_at,
                raw_payload=clean_data,
                payload_hash=payload_hash,
                version=self.version,
                block_timestamp=block_timestamp,
                block_number=block_number,
                tx_hash=tx_hash,
                confidence_score=Decimal("1.0"),
            )
            
        except Exception as e:
            raise ParseError(
                message=f"Failed to parse on-chain item: {e}",
                source=self.source_name,
                details={"raw_data_keys": list(raw_data.keys()) if raw_data else []},
            )
    
    # =========================================================
    # STORE - Persist via Repository
    # =========================================================
    
    async def store_item(self, item: RawOnChainItem, batch_id: UUID) -> bool:
        """
        Store an on-chain item via RawOnChainRepository.
        
        Args:
            item: Parsed RawOnChainItem
            batch_id: Collection batch ID
            
        Returns:
            True if stored, False if skipped (duplicate)
            
        Raises:
            StorageError: On storage errors
        """
        try:
            # Check for duplicates by hash
            if self._repository.exists_by_hash(item.payload_hash):
                self._logger.debug(
                    f"Skipping duplicate on-chain item: {item.chain}/{item.payload_hash[:16]}..."
                )
                return False
            
            # Store via repository
            from storage.models.raw_data import RawOnChainData
            
            entity = RawOnChainData(
                source=item.source,
                chain=item.chain,
                data_type=item.data_type,
                collected_at=item.collected_at,
                raw_payload=item.raw_payload,
                payload_hash=item.payload_hash,
                version=item.version,
                block_timestamp=item.block_timestamp,
                block_number=item.block_number,
                tx_hash=item.tx_hash,
                confidence_score=item.confidence_score,
                collection_batch_id=batch_id,
                processing_stage="raw",
            )
            
            self._session.add(entity)
            self._session.flush()
            
            self._logger.debug(
                f"Stored on-chain item: {item.chain}/{entity.raw_onchain_id}"
            )
            return True
            
        except DuplicateRecordError:
            self._logger.debug(
                f"Duplicate on-chain item detected: {item.payload_hash[:16]}..."
            )
            return False
            
        except RepositoryException as e:
            self._session.rollback()
            raise StorageError(
                message=f"Repository error: {e}",
                source=self.source_name,
                recoverable=True,
            )
        except Exception as e:
            self._session.rollback()
            raise StorageError(
                message=f"Storage error: {e}",
                source=self.source_name,
                recoverable=False,
            )
    
    def commit(self) -> None:
        """Commit the current transaction."""
        self._session.commit()
    
    def rollback(self) -> None:
        """Rollback the current transaction."""
        self._session.rollback()
