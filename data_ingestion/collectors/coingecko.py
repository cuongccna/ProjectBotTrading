"""
Data Ingestion - CoinGecko Collector.

============================================================
RESPONSIBILITY
============================================================
Collects market data from CoinGecko API.

- Fetches price, volume, and market cap data
- Handles free tier rate limits
- Provides fallback market data source
- Stores raw data via RawMarketDataRepository

============================================================
DESIGN PRINCIPLES
============================================================
- No business logic - collection only
- Respect API rate limits strictly
- Raw data is immutable
- Graceful degradation on errors

============================================================
DATA FLOW
============================================================
1. Fetch market data from CoinGecko
2. Parse to RawMarketItem
3. Store via RawMarketDataRepository
4. Return ingestion metrics

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
    CoinGeckoConfig,
    RawMarketItem,
    FetchError,
    ParseError,
    StorageError,
)
from storage.repositories import RawMarketDataRepository
from storage.repositories.exceptions import RepositoryException, DuplicateRecordError


class CoinGeckoCollector(BaseCollector[RawMarketItem]):
    """
    Collector for CoinGecko market data.
    
    ============================================================
    WIRING
    ============================================================
    Source: CoinGecko API (REST)
    Repository: RawMarketDataRepository
    Processing Stage: RAW
    
    ============================================================
    """
    
    def __init__(
        self,
        config: CoinGeckoConfig,
        session: Session,
    ) -> None:
        """
        Initialize the CoinGecko collector.
        
        Args:
            config: CoinGecko configuration
            session: Database session for repository
        """
        super().__init__(
            config=config,
            source=IngestionSource.COINGECKO,
            data_type=DataType.MARKET,
        )
        self._cg_config = config
        self._session = session
        self._repository = RawMarketDataRepository(session)
        self._logger = logging.getLogger("collector.coingecko")
    
    # =========================================================
    # FETCH - External API Call
    # =========================================================
    
    async def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Fetch market data from CoinGecko API.
        
        Returns:
            List of raw market data dictionaries
            
        Raises:
            FetchError: On network or API errors
        """
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                url = f"{self._cg_config.base_url}/coins/markets"
                params = {
                    "vs_currency": "usd",
                    "ids": ",".join(self._cg_config.tracked_assets),
                    "order": "market_cap_desc",
                    "sparkline": "false",
                }
                
                headers = {}
                if self._cg_config.api_key:
                    # Use x-cg-demo-api-key for Demo API (free tier)
                    # Use x-cg-pro-api-key for Pro API (paid tier)
                    headers["x-cg-demo-api-key"] = self._cg_config.api_key
                
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                
                # CoinGecko returns a list of coin market data
                if isinstance(data, list):
                    return data
                else:
                    return [data]
                    
        except httpx.HTTPStatusError as e:
            # Rate limit (429) is recoverable
            is_rate_limit = e.response.status_code == 429
            raise FetchError(
                message=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                source=self.source_name,
                recoverable=e.response.status_code >= 500 or is_rate_limit,
                details={"status_code": e.response.status_code},
            )
        except httpx.TimeoutException as e:
            raise FetchError(
                message=f"Request timeout: {e}",
                source=self.source_name,
                recoverable=True,
            )
        except httpx.RequestError as e:
            raise FetchError(
                message=f"Request error: {e}",
                source=self.source_name,
                recoverable=True,
            )
        except Exception as e:
            raise FetchError(
                message=f"Unexpected error: {e}",
                source=self.source_name,
                recoverable=False,
            )
    
    # =========================================================
    # PARSE - Normalize to RawMarketItem
    # =========================================================
    
    def parse_item(self, raw_data: Dict[str, Any]) -> RawMarketItem:
        """
        Parse raw CoinGecko response to RawMarketItem.
        
        Args:
            raw_data: Raw market data from CoinGecko
            
        Returns:
            RawMarketItem ready for storage
            
        Raises:
            ParseError: On parsing errors
        """
        try:
            collected_at = datetime.utcnow()
            payload_hash = self.compute_payload_hash(raw_data)
            
            # Extract symbol from CoinGecko data
            symbol = raw_data.get("symbol", "").upper()
            if not symbol:
                symbol = raw_data.get("id", "UNKNOWN")
            
            # CoinGecko provides "last_updated" as ISO timestamp
            source_timestamp = None
            last_updated = raw_data.get("last_updated")
            if last_updated:
                try:
                    source_timestamp = datetime.fromisoformat(
                        last_updated.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass
            
            return RawMarketItem(
                source=self.source_name,
                symbol=symbol,
                data_type="ticker",  # CoinGecko markets endpoint is ticker-like
                collected_at=collected_at,
                raw_payload=raw_data,
                payload_hash=payload_hash,
                version=self.version,
                source_timestamp=source_timestamp,
                confidence_score=Decimal("1.0"),
            )
            
        except Exception as e:
            raise ParseError(
                message=f"Failed to parse market item: {e}",
                source=self.source_name,
                details={"raw_data_keys": list(raw_data.keys()) if raw_data else []},
            )
    
    # =========================================================
    # STORE - Persist via Repository
    # =========================================================
    
    async def store_item(self, item: RawMarketItem, batch_id: UUID) -> bool:
        """
        Store a market item via RawMarketDataRepository.
        
        Args:
            item: Parsed RawMarketItem
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
                    f"Skipping duplicate market item: {item.symbol} - {item.payload_hash[:16]}..."
                )
                return False
            
            # Store via repository - direct entity creation
            from storage.models.raw_data import RawMarketData
            
            entity = RawMarketData(
                source=item.source,
                symbol=item.symbol,
                data_type=item.data_type,
                collected_at=item.collected_at,
                raw_payload=item.raw_payload,
                payload_hash=item.payload_hash,
                version=item.version,
                source_timestamp=item.source_timestamp,
                sequence_number=item.sequence_number,
                confidence_score=item.confidence_score,
                collection_batch_id=batch_id,
                processing_stage="raw",
            )
            
            self._session.add(entity)
            self._session.flush()
            
            self._logger.debug(
                f"Stored market item: {item.symbol} - {entity.raw_market_id}"
            )
            return True
            
        except DuplicateRecordError:
            self._logger.debug(
                f"Duplicate market item detected: {item.payload_hash[:16]}..."
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
