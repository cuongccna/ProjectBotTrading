"""
Data Ingestion - Crypto News API Collector.

============================================================
RESPONSIBILITY
============================================================
Collects news data from crypto news API providers.

- Fetches news articles via REST API
- Handles rate limiting and retries
- Timestamps all incoming data
- Stores raw data via RawNewsRepository

============================================================
DESIGN PRINCIPLES
============================================================
- No business logic - collection only
- Raw data is immutable
- All failures are logged and reported
- Supports backfill for historical data

============================================================
DATA FLOW
============================================================
1. Fetch raw news from API
2. Parse to RawNewsItem
3. Store via RawNewsRepository
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
    NewsApiConfig,
    RawNewsItem,
    FetchError,
    ParseError,
    StorageError,
)
from storage.repositories import RawNewsRepository
from storage.repositories.exceptions import RepositoryException, DuplicateRecordError


class CryptoNewsApiCollector(BaseCollector[RawNewsItem]):
    """
    Collector for crypto news API data.
    
    ============================================================
    WIRING
    ============================================================
    Source: Crypto News API (REST)
    Repository: RawNewsRepository
    Processing Stage: RAW
    
    ============================================================
    """
    
    def __init__(
        self,
        config: NewsApiConfig,
        session: Session,
    ) -> None:
        """
        Initialize the crypto news API collector.
        
        Args:
            config: News API configuration
            session: Database session for repository
        """
        super().__init__(
            config=config,
            source=IngestionSource.CRYPTO_NEWS_API,
            data_type=DataType.NEWS,
        )
        self._news_config = config
        self._session = session
        self._repository = RawNewsRepository(session)
        self._logger = logging.getLogger("collector.crypto_news_api")
    
    # =========================================================
    # FETCH - External API Call
    # =========================================================
    
    async def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Fetch news articles from crypto news API.
        
        Returns:
            List of raw news article dictionaries
            
        Raises:
            FetchError: On network or API errors
            
        Note:
            Trial Plan allows max 3 items per request.
            Upgrade plan for up to 100 items.
        """
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                # CryptoNews API uses /category endpoint
                url = f"{self._news_config.base_url}/category"
                
                # Trial Plan limit: max 3 items per request
                batch_size = min(self._news_config.batch_size, 3)
                
                params = {
                    "section": "alltickers",
                    "tickers": "BTC,ETH,SOL,XRP,ADA,DOGE",  # Main crypto assets
                    "items": batch_size,
                }
                
                if self._news_config.api_key:
                    params["token"] = self._news_config.api_key
                
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                # Extract news items from response
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                elif isinstance(data, list):
                    return data
                else:
                    return [data]
                    
        except httpx.HTTPStatusError as e:
            raise FetchError(
                message=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                source=self.source_name,
                recoverable=e.response.status_code >= 500,
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
    # PARSE - Normalize to RawNewsItem
    # =========================================================
    
    def parse_item(self, raw_data: Dict[str, Any]) -> RawNewsItem:
        """
        Parse raw API response to RawNewsItem.
        
        Args:
            raw_data: Raw news data from API
            
        Returns:
            RawNewsItem ready for storage
            
        Raises:
            ParseError: On parsing errors
        """
        try:
            from email.utils import parsedate_to_datetime
            
            collected_at = datetime.utcnow()
            payload_hash = self.compute_payload_hash(raw_data)
            
            # CryptoNews API uses news_url as unique identifier
            source_article_id = raw_data.get("news_url")
            
            # Parse source publication timestamp (RFC 2822 format)
            source_published_at = None
            pub_date_str = raw_data.get("date")
            if pub_date_str:
                try:
                    # CryptoNews API returns dates like "Sun, 11 Jan 2026 07:04:13 -0500"
                    source_published_at = parsedate_to_datetime(pub_date_str)
                except (ValueError, TypeError) as e:
                    self._logger.warning(
                        f"Could not parse publication date: {pub_date_str} - {e}"
                    )
            
            return RawNewsItem(
                source=self.source_name,
                collected_at=collected_at,
                raw_payload=raw_data,
                payload_hash=payload_hash,
                version=self.version,
                source_article_id=str(source_article_id) if source_article_id else None,
                source_published_at=source_published_at,
                confidence_score=Decimal("1.0"),
                collector_instance=self._collector_instance,
            )
            
        except Exception as e:
            raise ParseError(
                message=f"Failed to parse news item: {e}",
                source=self.source_name,
                details={"raw_data_keys": list(raw_data.keys()) if raw_data else []},
            )
    
    # =========================================================
    # STORE - Persist via Repository
    # =========================================================
    
    async def store_item(self, item: RawNewsItem, batch_id: UUID) -> bool:
        """
        Store a news item via RawNewsRepository.
        
        Args:
            item: Parsed RawNewsItem
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
                    f"Skipping duplicate news item: {item.payload_hash[:16]}..."
                )
                return False
            
            # Store via repository
            # Note: Repository method signature adjusted to match actual model
            from storage.models.raw_data import RawNewsData
            
            entity = RawNewsData(
                source=item.source,
                collected_at=item.collected_at,
                raw_payload=item.raw_payload,
                payload_hash=item.payload_hash,
                version=item.version,
                source_article_id=item.source_article_id,
                source_published_at=item.source_published_at,
                confidence_score=item.confidence_score,
                collection_batch_id=batch_id,
                collector_instance=item.collector_instance,
                processing_stage="raw",
            )
            
            self._session.add(entity)
            self._session.flush()
            
            self._logger.debug(
                f"Stored news item: {entity.raw_news_id}"
            )
            return True
            
        except DuplicateRecordError:
            self._logger.debug(
                f"Duplicate news item detected: {item.payload_hash[:16]}..."
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
