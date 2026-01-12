"""
Raw Data Repositories.

============================================================
PURPOSE
============================================================
Repositories for raw data ingestion. These handle the first
stage of data: unprocessed news, market, and on-chain data.

============================================================
DATA LIFECYCLE
============================================================
- Stage: RAW
- Mutability: IMMUTABLE (append-only)
- Never update or delete raw data

============================================================
REPOSITORIES
============================================================
- RawNewsRepository: Raw news article data
- RawMarketDataRepository: Raw market/price data
- RawOnChainRepository: Raw blockchain data

============================================================
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from storage.models.raw_data import (
    RawNewsData,
    RawMarketData,
    RawOnChainData,
)
from storage.repositories.base import BaseRepository
from storage.repositories.exceptions import (
    RecordNotFoundError,
    RepositoryException,
    ImmutableRecordError,
)


class RawNewsRepository(BaseRepository[RawNewsData]):
    """
    Repository for raw news data.
    
    ============================================================
    SCOPE
    ============================================================
    Manages RawNewsData records. Raw news is collected from
    various sources (RSS, APIs, scrapers) and stored as-is
    for downstream processing.
    
    ============================================================
    IMMUTABILITY
    ============================================================
    Raw news data is APPEND-ONLY. Once created, records cannot
    be updated or deleted. This ensures data lineage integrity.
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, RawNewsData, "RawNewsRepository")
    
    # =========================================================
    # CREATE OPERATIONS
    # =========================================================
    
    def create_raw_news(
        self,
        source: str,
        collected_at: datetime,
        payload: dict,
        payload_hash: str,
        version: str,
        original_id: Optional[str] = None,
        source_url: Optional[str] = None,
        published_at: Optional[datetime] = None,
        confidence_score: Decimal = Decimal("1.0"),
    ) -> RawNewsData:
        """
        Create a new raw news record.
        
        Args:
            source: News source identifier
            collected_at: When the news was collected
            payload: Raw payload as JSON
            payload_hash: Hash for deduplication
            version: Collector version
            original_id: Original ID from source
            source_url: Source URL if available
            published_at: Publication timestamp if available
            confidence_score: Source confidence score
            
        Returns:
            Created RawNewsData record
        """
        entity = RawNewsData(
            source=source,
            collected_at=collected_at,
            payload=payload,
            payload_hash=payload_hash,
            version=version,
            original_id=original_id,
            source_url=source_url,
            published_at=published_at,
            confidence_score=confidence_score,
            processing_stage="raw",
        )
        return self._add(entity)
    
    # =========================================================
    # READ OPERATIONS
    # =========================================================
    
    def get_by_id(self, raw_news_id: UUID) -> Optional[RawNewsData]:
        """
        Get raw news by ID.
        
        Args:
            raw_news_id: The record UUID
            
        Returns:
            RawNewsData or None
        """
        return self._get_by_id(raw_news_id)
    
    def get_by_id_or_raise(self, raw_news_id: UUID) -> RawNewsData:
        """
        Get raw news by ID, raising if not found.
        
        Args:
            raw_news_id: The record UUID
            
        Returns:
            RawNewsData
            
        Raises:
            RecordNotFoundError: If not found
        """
        return self._get_by_id_or_raise(raw_news_id, "raw_news_id")
    
    def get_by_payload_hash(self, payload_hash: str) -> Optional[RawNewsData]:
        """
        Get raw news by payload hash (for deduplication).
        
        Args:
            payload_hash: The payload hash
            
        Returns:
            RawNewsData or None
        """
        stmt = select(RawNewsData).where(
            RawNewsData.payload_hash == payload_hash
        )
        return self._execute_scalar(stmt)
    
    def list_by_source(
        self,
        source: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[RawNewsData]:
        """
        List raw news by source.
        
        Args:
            source: Source identifier
            limit: Maximum records to return
            offset: Number of records to skip
            
        Returns:
            List of RawNewsData
        """
        stmt = (
            select(RawNewsData)
            .where(RawNewsData.source == source)
            .order_by(desc(RawNewsData.collected_at))
            .limit(limit)
            .offset(offset)
        )
        return self._execute_query(stmt)
    
    def list_by_collected_range(
        self,
        start_time: datetime,
        end_time: datetime,
        source: Optional[str] = None,
        limit: int = 1000
    ) -> List[RawNewsData]:
        """
        List raw news within a time range.
        
        Args:
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            source: Optional source filter
            limit: Maximum records to return
            
        Returns:
            List of RawNewsData
        """
        conditions = [
            RawNewsData.collected_at >= start_time,
            RawNewsData.collected_at < end_time,
        ]
        if source:
            conditions.append(RawNewsData.source == source)
        
        stmt = (
            select(RawNewsData)
            .where(and_(*conditions))
            .order_by(RawNewsData.collected_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_unprocessed(
        self,
        limit: int = 100
    ) -> List[RawNewsData]:
        """
        List raw news that hasn't been processed yet.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            List of RawNewsData with processing_stage='raw'
        """
        stmt = (
            select(RawNewsData)
            .where(RawNewsData.processing_stage == "raw")
            .order_by(RawNewsData.collected_at)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def count_by_source(self, source: str) -> int:
        """
        Count raw news by source.
        
        Args:
            source: Source identifier
            
        Returns:
            Record count
        """
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(RawNewsData)
            .where(RawNewsData.source == source)
        )
        try:
            result = self._session.execute(stmt)
            return result.scalar() or 0
        except SQLAlchemyError as e:
            self._handle_db_error(e, "count_by_source", {"source": source})
            raise
    
    def exists_by_hash(self, payload_hash: str) -> bool:
        """
        Check if a record with the given hash exists.
        
        Args:
            payload_hash: The payload hash
            
        Returns:
            True if exists
        """
        from sqlalchemy import exists
        stmt = select(exists().where(RawNewsData.payload_hash == payload_hash))
        try:
            result = self._session.execute(stmt)
            return result.scalar() or False
        except SQLAlchemyError as e:
            self._handle_db_error(e, "exists_by_hash", {"hash": payload_hash})
            raise


class RawMarketDataRepository(BaseRepository[RawMarketData]):
    """
    Repository for raw market data.
    
    ============================================================
    SCOPE
    ============================================================
    Manages RawMarketData records. Raw market data includes
    OHLCV, order book snapshots, and trade data from exchanges.
    
    ============================================================
    IMMUTABILITY
    ============================================================
    Raw market data is APPEND-ONLY. Historical market data
    must be preserved exactly as received.
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, RawMarketData, "RawMarketDataRepository")
    
    # =========================================================
    # CREATE OPERATIONS
    # =========================================================
    
    def create_raw_market_data(
        self,
        exchange: str,
        symbol: str,
        data_type: str,
        collected_at: datetime,
        exchange_timestamp: datetime,
        payload: dict,
        payload_hash: str,
        version: str,
        confidence_score: Decimal = Decimal("1.0"),
    ) -> RawMarketData:
        """
        Create a new raw market data record.
        
        Args:
            exchange: Exchange identifier
            symbol: Trading symbol
            data_type: Data type (ohlcv, orderbook, trades)
            collected_at: When data was collected
            exchange_timestamp: Exchange timestamp
            payload: Raw payload as JSON
            payload_hash: Hash for deduplication
            version: Collector version
            confidence_score: Data confidence score
            
        Returns:
            Created RawMarketData record
        """
        entity = RawMarketData(
            exchange=exchange,
            symbol=symbol,
            data_type=data_type,
            collected_at=collected_at,
            exchange_timestamp=exchange_timestamp,
            payload=payload,
            payload_hash=payload_hash,
            version=version,
            confidence_score=confidence_score,
            processing_stage="raw",
        )
        return self._add(entity)
    
    # =========================================================
    # READ OPERATIONS
    # =========================================================
    
    def get_by_id(self, raw_market_id: UUID) -> Optional[RawMarketData]:
        """Get raw market data by ID."""
        return self._get_by_id(raw_market_id)
    
    def get_by_id_or_raise(self, raw_market_id: UUID) -> RawMarketData:
        """Get raw market data by ID, raising if not found."""
        return self._get_by_id_or_raise(raw_market_id, "raw_market_id")
    
    def list_by_symbol(
        self,
        exchange: str,
        symbol: str,
        data_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[RawMarketData]:
        """
        List raw market data by exchange and symbol.
        
        Args:
            exchange: Exchange identifier
            symbol: Trading symbol
            data_type: Optional data type filter
            limit: Maximum records to return
            offset: Number of records to skip
            
        Returns:
            List of RawMarketData
        """
        conditions = [
            RawMarketData.exchange == exchange,
            RawMarketData.symbol == symbol,
        ]
        if data_type:
            conditions.append(RawMarketData.data_type == data_type)
        
        stmt = (
            select(RawMarketData)
            .where(and_(*conditions))
            .order_by(desc(RawMarketData.exchange_timestamp))
            .limit(limit)
            .offset(offset)
        )
        return self._execute_query(stmt)
    
    def list_by_time_range(
        self,
        exchange: str,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        data_type: Optional[str] = None,
        limit: int = 1000
    ) -> List[RawMarketData]:
        """
        List raw market data within a time range.
        
        Args:
            exchange: Exchange identifier
            symbol: Trading symbol
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            data_type: Optional data type filter
            limit: Maximum records to return
            
        Returns:
            List of RawMarketData
        """
        conditions = [
            RawMarketData.exchange == exchange,
            RawMarketData.symbol == symbol,
            RawMarketData.exchange_timestamp >= start_time,
            RawMarketData.exchange_timestamp < end_time,
        ]
        if data_type:
            conditions.append(RawMarketData.data_type == data_type)
        
        stmt = (
            select(RawMarketData)
            .where(and_(*conditions))
            .order_by(RawMarketData.exchange_timestamp)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def get_latest_by_symbol(
        self,
        exchange: str,
        symbol: str,
        data_type: str
    ) -> Optional[RawMarketData]:
        """
        Get the most recent market data for a symbol.
        
        Args:
            exchange: Exchange identifier
            symbol: Trading symbol
            data_type: Data type
            
        Returns:
            Most recent RawMarketData or None
        """
        stmt = (
            select(RawMarketData)
            .where(and_(
                RawMarketData.exchange == exchange,
                RawMarketData.symbol == symbol,
                RawMarketData.data_type == data_type,
            ))
            .order_by(desc(RawMarketData.exchange_timestamp))
            .limit(1)
        )
        return self._execute_scalar(stmt)
    
    def exists_by_hash(self, payload_hash: str) -> bool:
        """Check if a record with the given hash exists."""
        from sqlalchemy import exists
        stmt = select(exists().where(RawMarketData.payload_hash == payload_hash))
        try:
            result = self._session.execute(stmt)
            return result.scalar() or False
        except SQLAlchemyError as e:
            self._handle_db_error(e, "exists_by_hash", {"hash": payload_hash})
            raise


class RawOnChainRepository(BaseRepository[RawOnChainData]):
    """
    Repository for raw on-chain data.
    
    ============================================================
    SCOPE
    ============================================================
    Manages RawOnChainData records. On-chain data includes
    blockchain transactions, contract events, and address data.
    
    ============================================================
    IMMUTABILITY
    ============================================================
    Raw on-chain data is APPEND-ONLY. Blockchain data is
    inherently immutable and must be preserved.
    
    ============================================================
    """
    
    def __init__(self, session: Session) -> None:
        super().__init__(session, RawOnChainData, "RawOnChainRepository")
    
    # =========================================================
    # CREATE OPERATIONS
    # =========================================================
    
    def create_raw_onchain_data(
        self,
        chain: str,
        data_type: str,
        collected_at: datetime,
        block_number: Optional[int],
        block_timestamp: Optional[datetime],
        payload: dict,
        payload_hash: str,
        version: str,
        transaction_hash: Optional[str] = None,
        address: Optional[str] = None,
        confidence_score: Decimal = Decimal("1.0"),
    ) -> RawOnChainData:
        """
        Create a new raw on-chain data record.
        
        Args:
            chain: Blockchain identifier
            data_type: Data type (transaction, event, balance)
            collected_at: When data was collected
            block_number: Block number if applicable
            block_timestamp: Block timestamp if applicable
            payload: Raw payload as JSON
            payload_hash: Hash for deduplication
            version: Collector version
            transaction_hash: Transaction hash if applicable
            address: Related address if applicable
            confidence_score: Data confidence score
            
        Returns:
            Created RawOnChainData record
        """
        entity = RawOnChainData(
            chain=chain,
            data_type=data_type,
            collected_at=collected_at,
            block_number=block_number,
            block_timestamp=block_timestamp,
            payload=payload,
            payload_hash=payload_hash,
            version=version,
            transaction_hash=transaction_hash,
            address=address,
            confidence_score=confidence_score,
            processing_stage="raw",
        )
        return self._add(entity)
    
    # =========================================================
    # READ OPERATIONS
    # =========================================================
    
    def get_by_id(self, raw_onchain_id: UUID) -> Optional[RawOnChainData]:
        """Get raw on-chain data by ID."""
        return self._get_by_id(raw_onchain_id)
    
    def get_by_id_or_raise(self, raw_onchain_id: UUID) -> RawOnChainData:
        """Get raw on-chain data by ID, raising if not found."""
        return self._get_by_id_or_raise(raw_onchain_id, "raw_onchain_id")
    
    def get_by_transaction_hash(
        self,
        chain: str,
        transaction_hash: str
    ) -> Optional[RawOnChainData]:
        """
        Get raw on-chain data by transaction hash.
        
        Args:
            chain: Blockchain identifier
            transaction_hash: Transaction hash
            
        Returns:
            RawOnChainData or None
        """
        stmt = select(RawOnChainData).where(and_(
            RawOnChainData.chain == chain,
            RawOnChainData.transaction_hash == transaction_hash,
        ))
        return self._execute_scalar(stmt)
    
    def list_by_chain(
        self,
        chain: str,
        data_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[RawOnChainData]:
        """
        List raw on-chain data by chain.
        
        Args:
            chain: Blockchain identifier
            data_type: Optional data type filter
            limit: Maximum records to return
            offset: Number of records to skip
            
        Returns:
            List of RawOnChainData
        """
        conditions = [RawOnChainData.chain == chain]
        if data_type:
            conditions.append(RawOnChainData.data_type == data_type)
        
        stmt = (
            select(RawOnChainData)
            .where(and_(*conditions))
            .order_by(desc(RawOnChainData.collected_at))
            .limit(limit)
            .offset(offset)
        )
        return self._execute_query(stmt)
    
    def list_by_address(
        self,
        chain: str,
        address: str,
        limit: int = 100
    ) -> List[RawOnChainData]:
        """
        List raw on-chain data by address.
        
        Args:
            chain: Blockchain identifier
            address: Blockchain address
            limit: Maximum records to return
            
        Returns:
            List of RawOnChainData
        """
        stmt = (
            select(RawOnChainData)
            .where(and_(
                RawOnChainData.chain == chain,
                RawOnChainData.address == address,
            ))
            .order_by(desc(RawOnChainData.block_number))
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def list_by_block_range(
        self,
        chain: str,
        start_block: int,
        end_block: int,
        data_type: Optional[str] = None,
        limit: int = 1000
    ) -> List[RawOnChainData]:
        """
        List raw on-chain data within a block range.
        
        Args:
            chain: Blockchain identifier
            start_block: Start block (inclusive)
            end_block: End block (inclusive)
            data_type: Optional data type filter
            limit: Maximum records to return
            
        Returns:
            List of RawOnChainData
        """
        conditions = [
            RawOnChainData.chain == chain,
            RawOnChainData.block_number >= start_block,
            RawOnChainData.block_number <= end_block,
        ]
        if data_type:
            conditions.append(RawOnChainData.data_type == data_type)
        
        stmt = (
            select(RawOnChainData)
            .where(and_(*conditions))
            .order_by(RawOnChainData.block_number)
            .limit(limit)
        )
        return self._execute_query(stmt)
    
    def exists_by_hash(self, payload_hash: str) -> bool:
        """Check if a record with the given hash exists."""
        from sqlalchemy import exists
        stmt = select(exists().where(RawOnChainData.payload_hash == payload_hash))
        try:
            result = self._session.execute(stmt)
            return result.scalar() or False
        except SQLAlchemyError as e:
            self._handle_db_error(e, "exists_by_hash", {"hash": payload_hash})
            raise
