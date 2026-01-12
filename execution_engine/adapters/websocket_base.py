"""
Exchange Adapter - WebSocket Base.

============================================================
PURPOSE
============================================================
Base class for WebSocket connections to exchanges.

FEATURES:
- Persistent connection management
- Automatic reconnection with backoff
- Heartbeat/ping handling
- Message parsing and routing
- Stream subscription management

============================================================
USAGE
============================================================
```python
class BinanceWebSocket(WebSocketBase):
    async def _on_message(self, data: Dict):
        # Handle message
        pass

ws = BinanceWebSocket("wss://fstream.binance.com/ws")
await ws.connect()
await ws.subscribe(["btcusdt@aggTrade"])
```

============================================================
"""

import asyncio
import logging
import time
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Set
from enum import Enum
from dataclasses import dataclass

import aiohttp


logger = logging.getLogger(__name__)


# ============================================================
# CONNECTION STATE
# ============================================================

class ConnectionState(Enum):
    """WebSocket connection states."""
    
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    CLOSING = "CLOSING"


@dataclass
class WebSocketConfig:
    """WebSocket configuration."""
    
    # Connection
    url: str
    reconnect: bool = True
    max_reconnect_attempts: int = 10
    reconnect_interval_ms: int = 1000
    max_reconnect_interval_ms: int = 30000
    
    # Heartbeat
    ping_interval_ms: int = 20000
    pong_timeout_ms: int = 10000
    
    # Message handling
    message_timeout_ms: int = 60000


# ============================================================
# WEBSOCKET BASE
# ============================================================

class WebSocketBase(ABC):
    """
    Abstract base class for WebSocket connections.
    
    Provides:
    - Connection lifecycle management
    - Automatic reconnection with exponential backoff
    - Heartbeat handling
    - Subscription management
    """
    
    def __init__(
        self,
        url: str,
        config: WebSocketConfig = None,
    ):
        """
        Initialize WebSocket base.
        
        Args:
            url: WebSocket URL
            config: Connection configuration
        """
        self._url = url
        self._config = config or WebSocketConfig(url=url)
        
        # Connection state
        self._state = ConnectionState.DISCONNECTED
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        
        # Reconnection
        self._reconnect_count = 0
        self._last_connect_time = 0.0
        
        # Heartbeat
        self._last_ping_time = 0.0
        self._last_pong_time = 0.0
        self._ping_task: Optional[asyncio.Task] = None
        
        # Message handling
        self._receive_task: Optional[asyncio.Task] = None
        self._last_message_time = 0.0
        
        # Subscriptions
        self._subscriptions: Set[str] = set()
        
        # Callbacks
        self._callbacks: Dict[str, List[Callable]] = {}
    
    # --------------------------------------------------------
    # PROPERTIES
    # --------------------------------------------------------
    
    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._state == ConnectionState.CONNECTED and self._ws is not None
    
    @property
    def url(self) -> str:
        """WebSocket URL."""
        return self._url
    
    # --------------------------------------------------------
    # CONNECTION
    # --------------------------------------------------------
    
    async def connect(self) -> None:
        """
        Establish WebSocket connection.
        
        Raises:
            ConnectionError: If connection fails
        """
        if self._state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
            return
        
        self._state = ConnectionState.CONNECTING
        
        try:
            # Create session if needed
            if self._session is None:
                self._session = aiohttp.ClientSession()
            
            # Connect
            self._ws = await self._session.ws_connect(
                self._url,
                heartbeat=self._config.ping_interval_ms / 1000,
            )
            
            self._state = ConnectionState.CONNECTED
            self._reconnect_count = 0
            self._last_connect_time = time.time()
            self._last_message_time = time.time()
            
            logger.info(f"WebSocket connected: {self._url}")
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            # Start heartbeat
            self._ping_task = asyncio.create_task(self._heartbeat_loop())
            
            # Resubscribe if reconnecting
            if self._subscriptions:
                await self._resubscribe()
            
            # Callback
            await self._on_connect()
            
        except Exception as e:
            self._state = ConnectionState.DISCONNECTED
            logger.error(f"WebSocket connection failed: {e}")
            
            if self._config.reconnect:
                await self._schedule_reconnect()
            else:
                raise ConnectionError(f"WebSocket connection failed: {e}")
    
    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._state = ConnectionState.CLOSING
        
        # Cancel tasks
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None
        
        # Close WebSocket
        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None
        
        # Close session
        if self._session:
            await self._session.close()
            self._session = None
        
        self._state = ConnectionState.DISCONNECTED
        logger.info("WebSocket disconnected")
        
        await self._on_disconnect()
    
    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection with backoff."""
        if not self._config.reconnect:
            return
        
        if self._reconnect_count >= self._config.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            await self._on_max_reconnect()
            return
        
        self._state = ConnectionState.RECONNECTING
        self._reconnect_count += 1
        
        # Exponential backoff
        delay_ms = min(
            self._config.reconnect_interval_ms * (2 ** (self._reconnect_count - 1)),
            self._config.max_reconnect_interval_ms,
        )
        
        logger.info(f"Reconnecting in {delay_ms}ms (attempt {self._reconnect_count})")
        await asyncio.sleep(delay_ms / 1000)
        
        await self.connect()
    
    # --------------------------------------------------------
    # MESSAGE HANDLING
    # --------------------------------------------------------
    
    async def _receive_loop(self) -> None:
        """Main receive loop."""
        try:
            async for msg in self._ws:
                self._last_message_time = time.time()
                
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self._handle_binary(msg.data)
                
                elif msg.type == aiohttp.WSMsgType.PING:
                    await self._ws.pong(msg.data)
                
                elif msg.type == aiohttp.WSMsgType.PONG:
                    self._last_pong_time = time.time()
                
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    logger.warning(f"WebSocket closed: {msg.data}")
                    break
                
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self._ws.exception()}")
                    break
        
        except asyncio.CancelledError:
            return
        
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
        
        finally:
            if self._state == ConnectionState.CONNECTED:
                self._state = ConnectionState.DISCONNECTED
                if self._config.reconnect:
                    await self._schedule_reconnect()
    
    async def _handle_message(self, data: str) -> None:
        """Handle text message."""
        try:
            parsed = json.loads(data)
            await self._on_message(parsed)
            
            # Route to stream callbacks
            stream = self._get_stream_from_message(parsed)
            if stream and stream in self._callbacks:
                for callback in self._callbacks[stream]:
                    try:
                        await callback(parsed)
                    except Exception as e:
                        logger.error(f"Callback error for {stream}: {e}")
        
        except json.JSONDecodeError:
            await self._on_raw_message(data)
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_binary(self, data: bytes) -> None:
        """Handle binary message."""
        # Default: decompress and parse as JSON
        try:
            import gzip
            decompressed = gzip.decompress(data)
            parsed = json.loads(decompressed)
            await self._on_message(parsed)
        except Exception:
            await self._on_binary(data)
    
    def _get_stream_from_message(self, data: Dict) -> Optional[str]:
        """Extract stream name from message (override per exchange)."""
        return data.get("stream") or data.get("e")
    
    # --------------------------------------------------------
    # HEARTBEAT
    # --------------------------------------------------------
    
    async def _heartbeat_loop(self) -> None:
        """Heartbeat loop."""
        while self._state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self._config.ping_interval_ms / 1000)
                
                if not self.is_connected:
                    break
                
                # Check message timeout
                if time.time() - self._last_message_time > self._config.message_timeout_ms / 1000:
                    logger.warning("Message timeout, reconnecting")
                    await self._schedule_reconnect()
                    break
                
                # Send ping
                await self.send_ping()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def send_ping(self) -> None:
        """Send ping message."""
        if self._ws and not self._ws.closed:
            self._last_ping_time = time.time()
            await self._ws.ping()
    
    # --------------------------------------------------------
    # SENDING
    # --------------------------------------------------------
    
    async def send(self, message: Dict[str, Any]) -> None:
        """
        Send JSON message.
        
        Args:
            message: Message to send
        """
        if not self.is_connected:
            raise ConnectionError("Not connected")
        
        await self._ws.send_json(message)
    
    async def send_raw(self, data: str) -> None:
        """
        Send raw string message.
        
        Args:
            data: String data to send
        """
        if not self.is_connected:
            raise ConnectionError("Not connected")
        
        await self._ws.send_str(data)
    
    # --------------------------------------------------------
    # SUBSCRIPTIONS
    # --------------------------------------------------------
    
    async def subscribe(
        self,
        streams: List[str],
        callback: Callable = None,
    ) -> None:
        """
        Subscribe to streams.
        
        Args:
            streams: List of stream names
            callback: Optional callback for stream messages
        """
        for stream in streams:
            self._subscriptions.add(stream)
            
            if callback:
                if stream not in self._callbacks:
                    self._callbacks[stream] = []
                self._callbacks[stream].append(callback)
        
        if self.is_connected:
            await self._send_subscribe(streams)
    
    async def unsubscribe(self, streams: List[str]) -> None:
        """
        Unsubscribe from streams.
        
        Args:
            streams: List of stream names
        """
        for stream in streams:
            self._subscriptions.discard(stream)
            self._callbacks.pop(stream, None)
        
        if self.is_connected:
            await self._send_unsubscribe(streams)
    
    async def _resubscribe(self) -> None:
        """Resubscribe to all streams after reconnection."""
        if self._subscriptions:
            await self._send_subscribe(list(self._subscriptions))
    
    @abstractmethod
    async def _send_subscribe(self, streams: List[str]) -> None:
        """Send subscription message (exchange-specific)."""
        pass
    
    @abstractmethod
    async def _send_unsubscribe(self, streams: List[str]) -> None:
        """Send unsubscription message (exchange-specific)."""
        pass
    
    # --------------------------------------------------------
    # CALLBACKS (OVERRIDE)
    # --------------------------------------------------------
    
    @abstractmethod
    async def _on_message(self, data: Dict[str, Any]) -> None:
        """Handle parsed message (override)."""
        pass
    
    async def _on_raw_message(self, data: str) -> None:
        """Handle raw message."""
        logger.debug(f"Raw message: {data[:100]}")
    
    async def _on_binary(self, data: bytes) -> None:
        """Handle binary message."""
        logger.debug(f"Binary message: {len(data)} bytes")
    
    async def _on_connect(self) -> None:
        """Called on connection."""
        pass
    
    async def _on_disconnect(self) -> None:
        """Called on disconnection."""
        pass
    
    async def _on_max_reconnect(self) -> None:
        """Called when max reconnection attempts reached."""
        pass


# ============================================================
# BINANCE WEBSOCKET
# ============================================================

class BinanceWebSocket(WebSocketBase):
    """
    Binance Futures WebSocket.
    
    Streams:
    - {symbol}@aggTrade: Aggregate trades
    - {symbol}@markPrice: Mark price
    - {symbol}@kline_{interval}: Candlesticks
    - {symbol}@depth{levels}: Order book
    - {symbol}@ticker: 24hr ticker
    """
    
    MAINNET_URL = "wss://fstream.binance.com/ws"
    TESTNET_URL = "wss://stream.binancefuture.com/ws"
    
    def __init__(self, testnet: bool = False):
        """Initialize Binance WebSocket."""
        url = self.TESTNET_URL if testnet else self.MAINNET_URL
        super().__init__(url)
        
        self._message_id = 0
    
    async def _send_subscribe(self, streams: List[str]) -> None:
        """Send subscribe message."""
        self._message_id += 1
        await self.send({
            "method": "SUBSCRIBE",
            "params": streams,
            "id": self._message_id,
        })
    
    async def _send_unsubscribe(self, streams: List[str]) -> None:
        """Send unsubscribe message."""
        self._message_id += 1
        await self.send({
            "method": "UNSUBSCRIBE",
            "params": streams,
            "id": self._message_id,
        })
    
    async def _on_message(self, data: Dict[str, Any]) -> None:
        """Handle Binance message."""
        # Handle subscription responses
        if "result" in data:
            return
        
        # Handle stream data
        event_type = data.get("e")
        logger.debug(f"Binance event: {event_type}")


# ============================================================
# OKX WEBSOCKET
# ============================================================

class OKXWebSocket(WebSocketBase):
    """
    OKX WebSocket.
    
    Channels:
    - tickers: Ticker data
    - trades: Trade data
    - candle{interval}: Candlesticks
    - books{depth}: Order book
    - positions: Position updates (private)
    - orders: Order updates (private)
    """
    
    PUBLIC_URL = "wss://ws.okx.com:8443/ws/v5/public"
    PRIVATE_URL = "wss://ws.okx.com:8443/ws/v5/private"
    
    def __init__(self, private: bool = False):
        """Initialize OKX WebSocket."""
        url = self.PRIVATE_URL if private else self.PUBLIC_URL
        super().__init__(url)
    
    async def _send_subscribe(self, streams: List[str]) -> None:
        """Send subscribe message."""
        # Parse streams into OKX format
        args = []
        for stream in streams:
            parts = stream.split(":")
            if len(parts) == 2:
                args.append({"channel": parts[0], "instId": parts[1]})
            else:
                args.append({"channel": stream})
        
        await self.send({
            "op": "subscribe",
            "args": args,
        })
    
    async def _send_unsubscribe(self, streams: List[str]) -> None:
        """Send unsubscribe message."""
        args = []
        for stream in streams:
            parts = stream.split(":")
            if len(parts) == 2:
                args.append({"channel": parts[0], "instId": parts[1]})
            else:
                args.append({"channel": stream})
        
        await self.send({
            "op": "unsubscribe",
            "args": args,
        })
    
    async def _on_message(self, data: Dict[str, Any]) -> None:
        """Handle OKX message."""
        event = data.get("event")
        if event:
            logger.debug(f"OKX event: {event}")


# ============================================================
# BYBIT WEBSOCKET
# ============================================================

class BybitWebSocket(WebSocketBase):
    """
    Bybit V5 WebSocket.
    
    Topics:
    - orderbook.{depth}.{symbol}: Order book
    - publicTrade.{symbol}: Trades
    - tickers.{symbol}: Tickers
    - kline.{interval}.{symbol}: Candlesticks
    - position: Position updates (private)
    - order: Order updates (private)
    """
    
    PUBLIC_URL = "wss://stream.bybit.com/v5/public/linear"
    PRIVATE_URL = "wss://stream.bybit.com/v5/private"
    TESTNET_PUBLIC_URL = "wss://stream-testnet.bybit.com/v5/public/linear"
    TESTNET_PRIVATE_URL = "wss://stream-testnet.bybit.com/v5/private"
    
    def __init__(self, testnet: bool = False, private: bool = False):
        """Initialize Bybit WebSocket."""
        if testnet:
            url = self.TESTNET_PRIVATE_URL if private else self.TESTNET_PUBLIC_URL
        else:
            url = self.PRIVATE_URL if private else self.PUBLIC_URL
        super().__init__(url)
    
    async def _send_subscribe(self, streams: List[str]) -> None:
        """Send subscribe message."""
        await self.send({
            "op": "subscribe",
            "args": streams,
        })
    
    async def _send_unsubscribe(self, streams: List[str]) -> None:
        """Send unsubscribe message."""
        await self.send({
            "op": "unsubscribe",
            "args": streams,
        })
    
    async def _on_message(self, data: Dict[str, Any]) -> None:
        """Handle Bybit message."""
        topic = data.get("topic")
        if topic:
            logger.debug(f"Bybit topic: {topic}")
