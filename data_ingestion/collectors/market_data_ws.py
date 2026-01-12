"""
Data Ingestion - Market Data WebSocket Collector.

============================================================
RESPONSIBILITY
============================================================
Collects real-time market data via WebSocket connections.

- Maintains persistent WebSocket connections
- Receives real-time price and order book updates
- Handles reconnection automatically
- Stores raw data via RawMarketDataRepository

============================================================
DESIGN PRINCIPLES
============================================================
- No business logic - collection only
- Connection resilience is critical
- Raw data is immutable
- Heartbeat monitoring required

============================================================
DATA FLOW
============================================================
1. Connect to exchange WebSocket
2. Subscribe to market streams
3. Parse incoming messages to RawMarketItem
4. Store via RawMarketDataRepository
5. Handle disconnects with automatic reconnection

============================================================
"""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from data_ingestion.types import (
    DataType,
    IngestionSource,
    IngestionResult,
    IngestionStatus,
    WebSocketConfig,
    RawMarketItem,
    FetchError,
    ParseError,
    StorageError,
)
from storage.repositories import RawMarketDataRepository
from storage.repositories.exceptions import RepositoryException, DuplicateRecordError


class MarketDataWebSocketCollector:
    """
    Collector for real-time market data via WebSocket.
    
    ============================================================
    WIRING
    ============================================================
    Source: Exchange WebSocket (e.g., Binance, Coinbase)
    Repository: RawMarketDataRepository
    Processing Stage: RAW
    
    ============================================================
    NOTE
    ============================================================
    This collector operates differently from REST collectors:
    - It maintains a persistent connection
    - Messages are processed as they arrive
    - Collection is continuous, not batch-based
    
    ============================================================
    """
    
    def __init__(
        self,
        config: WebSocketConfig,
        session_factory,  # Callable that returns a new Session
    ) -> None:
        """
        Initialize the WebSocket collector.
        
        Args:
            config: WebSocket configuration
            session_factory: Factory function to create database sessions
        """
        self._config = config
        self._session_factory = session_factory
        self._logger = logging.getLogger("collector.market_data_ws")
        
        # Connection state
        self._websocket = None
        self._connected = False
        self._running = False
        self._subscriptions: Set[str] = set()
        self._reconnect_count = 0
        
        # Metrics
        self._messages_received = 0
        self._messages_stored = 0
        self._messages_failed = 0
        self._last_message_at: Optional[datetime] = None
        
        # Batch tracking
        self._current_batch_id: UUID = uuid4()
        self._sequence_number = 0
        
        # Collector instance ID
        self._collector_instance = f"ws_{config.exchange_name}_{uuid4().hex[:8]}"
    
    @property
    def source_name(self) -> str:
        """Get the source name."""
        return f"{IngestionSource.MARKET_DATA_WS.value}_{self._config.exchange_name}"
    
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected
    
    @property
    def version(self) -> str:
        """Get collector version."""
        return self._config.version
    
    # =========================================================
    # CONNECTION MANAGEMENT
    # =========================================================
    
    async def connect(self) -> None:
        """
        Establish WebSocket connection.
        
        Raises:
            FetchError: On connection failure
        """
        import websockets
        
        if self._connected:
            self._logger.warning("Already connected")
            return
        
        try:
            self._websocket = await websockets.connect(
                self._config.ws_url,
                ping_interval=self._config.heartbeat_interval_seconds,
            )
            self._connected = True
            self._reconnect_count = 0
            self._logger.info(f"Connected to {self._config.ws_url}")
            
            # Resubscribe if we had active subscriptions
            if self._subscriptions:
                await self._send_subscriptions(list(self._subscriptions))
                
        except Exception as e:
            raise FetchError(
                message=f"WebSocket connection failed: {e}",
                source=self.source_name,
                recoverable=True,
            )
    
    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception as e:
                self._logger.warning(f"Error closing WebSocket: {e}")
            finally:
                self._websocket = None
                self._connected = False
                
        self._logger.info("Disconnected from WebSocket")
    
    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        if self._reconnect_count >= self._config.reconnect_attempts:
            self._logger.error("Max reconnection attempts reached")
            raise FetchError(
                message="Max reconnection attempts reached",
                source=self.source_name,
                recoverable=False,
            )
        
        backoff = min(2 ** self._reconnect_count, 60)  # Max 60 seconds
        self._reconnect_count += 1
        
        self._logger.info(
            f"Reconnecting in {backoff}s (attempt {self._reconnect_count})"
        )
        await asyncio.sleep(backoff)
        
        try:
            await self.connect()
        except FetchError:
            await self._reconnect()
    
    # =========================================================
    # SUBSCRIPTION MANAGEMENT
    # =========================================================
    
    async def subscribe(self, symbols: List[str]) -> None:
        """
        Subscribe to market data streams.
        
        Args:
            symbols: List of trading symbols to subscribe to
        """
        new_symbols = set(symbols) - self._subscriptions
        
        if not new_symbols:
            return
        
        if self._connected:
            await self._send_subscriptions(list(new_symbols))
        
        self._subscriptions.update(new_symbols)
        self._logger.info(f"Subscribed to: {new_symbols}")
    
    async def unsubscribe(self, symbols: List[str]) -> None:
        """
        Unsubscribe from market data streams.
        
        Args:
            symbols: List of trading symbols to unsubscribe from
        """
        remove_symbols = set(symbols) & self._subscriptions
        
        if not remove_symbols:
            return
        
        if self._connected:
            await self._send_unsubscriptions(list(remove_symbols))
        
        self._subscriptions -= remove_symbols
        self._logger.info(f"Unsubscribed from: {remove_symbols}")
    
    async def _send_subscriptions(self, symbols: List[str]) -> None:
        """
        Send subscription message to WebSocket.
        
        Args:
            symbols: Symbols to subscribe to
            
        TODO: Implement exchange-specific subscription format
        """
        if not self._websocket:
            return
        
        # TODO: Adjust message format based on exchange
        # Example for Binance-like format:
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [f"{s.lower()}@trade" for s in symbols],
            "id": 1,
        }
        
        await self._websocket.send(json.dumps(subscribe_msg))
    
    async def _send_unsubscriptions(self, symbols: List[str]) -> None:
        """
        Send unsubscription message to WebSocket.
        
        Args:
            symbols: Symbols to unsubscribe from
        """
        if not self._websocket:
            return
        
        # TODO: Adjust message format based on exchange
        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": [f"{s.lower()}@trade" for s in symbols],
            "id": 2,
        }
        
        await self._websocket.send(json.dumps(unsubscribe_msg))
    
    # =========================================================
    # MESSAGE PROCESSING
    # =========================================================
    
    async def start(self) -> None:
        """
        Start the WebSocket collector.
        
        This runs continuously, processing messages as they arrive.
        """
        self._running = True
        await self.connect()
        
        # Subscribe to configured symbols
        if self._config.subscriptions:
            await self.subscribe(list(self._config.subscriptions))
        
        self._logger.info(f"WebSocket collector started for {self.source_name}")
        
        while self._running:
            try:
                await self._process_messages()
            except Exception as e:
                self._logger.error(f"Message processing error: {e}")
                
                if self._running:
                    self._connected = False
                    await self._reconnect()
    
    async def stop(self) -> None:
        """Stop the WebSocket collector."""
        self._running = False
        await self.disconnect()
        self._logger.info(f"WebSocket collector stopped for {self.source_name}")
    
    async def _process_messages(self) -> None:
        """Process incoming WebSocket messages."""
        import websockets
        
        if not self._websocket:
            return
        
        try:
            async for message in self._websocket:
                if not self._running:
                    break
                
                self._messages_received += 1
                self._last_message_at = datetime.utcnow()
                
                try:
                    await self._handle_message(message)
                except Exception as e:
                    self._messages_failed += 1
                    self._logger.warning(f"Failed to handle message: {e}")
                    
        except websockets.ConnectionClosed:
            self._connected = False
            raise
    
    async def _handle_message(self, message: str) -> None:
        """
        Handle a single WebSocket message.
        
        Args:
            message: Raw message string
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            raise ParseError(
                message=f"Invalid JSON: {e}",
                source=self.source_name,
            )
        
        # Skip non-data messages (subscriptions confirmations, pings, etc.)
        if not self._is_data_message(data):
            return
        
        # Parse and store
        item = self._parse_message(data)
        stored = await self._store_item(item)
        
        if stored:
            self._messages_stored += 1
    
    def _is_data_message(self, data: Dict[str, Any]) -> bool:
        """
        Check if message is a data message (vs control message).
        
        Args:
            data: Parsed message data
            
        Returns:
            True if this is a data message
            
        TODO: Adjust based on exchange message format
        """
        # Skip subscription confirmations, errors, etc.
        if "result" in data or "error" in data or "id" in data:
            return False
        
        return True
    
    def _parse_message(self, data: Dict[str, Any]) -> RawMarketItem:
        """
        Parse WebSocket message to RawMarketItem.
        
        Args:
            data: Parsed message data
            
        Returns:
            RawMarketItem ready for storage
        """
        collected_at = datetime.utcnow()
        
        # Compute hash for deduplication
        payload_hash = self._compute_hash(data)
        
        # Extract symbol - adjust based on exchange format
        symbol = (
            data.get("s") or  # Binance format
            data.get("symbol") or
            data.get("product_id") or  # Coinbase format
            "UNKNOWN"
        )
        
        # Determine data type
        data_type = self._detect_data_type(data)
        
        # Extract source timestamp
        source_timestamp = None
        ts = data.get("E") or data.get("T") or data.get("time") or data.get("timestamp")
        if ts:
            try:
                if isinstance(ts, (int, float)):
                    # Assume milliseconds
                    source_timestamp = datetime.utcfromtimestamp(ts / 1000)
                elif isinstance(ts, str):
                    source_timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, OSError):
                pass
        
        self._sequence_number += 1
        
        return RawMarketItem(
            source=self.source_name,
            symbol=symbol,
            data_type=data_type,
            collected_at=collected_at,
            raw_payload=data,
            payload_hash=payload_hash,
            version=self.version,
            source_timestamp=source_timestamp,
            sequence_number=self._sequence_number,
            confidence_score=Decimal("1.0"),
            collection_batch_id=self._current_batch_id,
        )
    
    def _detect_data_type(self, data: Dict[str, Any]) -> str:
        """
        Detect the type of market data message.
        
        Args:
            data: Parsed message data
            
        Returns:
            Data type string
        """
        # Check for common type indicators
        if "e" in data:  # Binance event type
            event_type = data["e"]
            if event_type in ("trade", "aggTrade"):
                return "trade"
            elif "depth" in event_type.lower():
                return "orderbook"
            elif event_type == "24hrTicker":
                return "ticker"
        
        # Check for trade-like fields
        if "price" in data and "quantity" in data:
            return "trade"
        
        # Check for orderbook-like fields
        if "bids" in data or "asks" in data:
            return "orderbook"
        
        return "unknown"
    
    @staticmethod
    def _compute_hash(data: Dict[str, Any]) -> str:
        """Compute hash for deduplication."""
        import hashlib
        payload_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(payload_str.encode()).hexdigest()
    
    async def _store_item(self, item: RawMarketItem) -> bool:
        """
        Store a market item via RawMarketDataRepository.
        
        Args:
            item: Parsed RawMarketItem
            
        Returns:
            True if stored, False if skipped
        """
        # Create new session for each store operation
        session = self._session_factory()
        
        try:
            repository = RawMarketDataRepository(session)
            
            # Check for duplicates
            if repository.exists_by_hash(item.payload_hash):
                return False
            
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
                collection_batch_id=item.collection_batch_id,
                processing_stage="raw",
            )
            
            session.add(entity)
            session.commit()
            
            return True
            
        except DuplicateRecordError:
            return False
            
        except Exception as e:
            session.rollback()
            self._logger.error(f"Storage error: {e}")
            return False
            
        finally:
            session.close()
    
    # =========================================================
    # HEALTH & METRICS
    # =========================================================
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get collector health status."""
        return {
            "source": self.source_name,
            "connected": self._connected,
            "running": self._running,
            "subscriptions": list(self._subscriptions),
            "reconnect_count": self._reconnect_count,
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get collector metrics."""
        return {
            "source": self.source_name,
            "messages_received": self._messages_received,
            "messages_stored": self._messages_stored,
            "messages_failed": self._messages_failed,
            "last_message_at": self._last_message_at.isoformat() if self._last_message_at else None,
        }
    
    def get_ingestion_result(self) -> IngestionResult:
        """Get current ingestion result snapshot."""
        return IngestionResult(
            batch_id=self._current_batch_id,
            source=self.source_name,
            data_type=DataType.MARKET,
            status=IngestionStatus.SUCCESS if self._connected else IngestionStatus.FAILED,
            records_fetched=self._messages_received,
            records_stored=self._messages_stored,
            records_failed=self._messages_failed,
        )
