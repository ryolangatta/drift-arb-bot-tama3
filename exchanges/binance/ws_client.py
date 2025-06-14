"""
Binance WebSocket client for real-time market data
"""
import json
import logging
from typing import List, Dict, Any, Set
import time

from infrastructure.websocket_base import WebSocketClient
from infrastructure.event_bus import Event, EventType, event_bus

logger = logging.getLogger(__name__)


class BinanceWebSocketClient(WebSocketClient):
    """
    Binance WebSocket client with support for:
    - Multiple stream subscriptions
    - Order book updates
    - Trade updates
    - Best bid/ask (bookTicker)
    """
    
    def __init__(self, testnet: bool = False):
        base_url = (
            "wss://testnet.binance.vision/ws" if testnet
            else "wss://stream.binance.com:9443/ws"
        )
        
        super().__init__(
            name="BinanceWS",
            url=base_url,
            reconnect_delay=5,
            ping_interval=180  # Binance expects ping every 3 minutes
        )
        
        self.testnet = testnet
        self.subscribed_streams: Set[str] = set()
        self.symbols: Set[str] = set()
        
        # Message handlers by stream type
        self.handlers = {
            "bookTicker": self._handle_book_ticker,
            "aggTrade": self._handle_agg_trade,
            "depth": self._handle_depth_update,
            "depth5": self._handle_depth5,
            "depth10": self._handle_depth10,
            "depth20": self._handle_depth20
        }
        
    async def subscribe_symbols(self, symbols: List[str], streams: List[str]):
        """
        Subscribe to multiple symbols and streams
        symbols: ['SOLUSDT', 'BTCUSDT']
        streams: ['bookTicker', 'aggTrade', 'depth5@100ms']
        """
        self.symbols.update(symbols)
        
        # Build subscription list
        subscriptions = []
        for symbol in symbols:
            for stream in streams:
                # Handle streams with parameters (e.g., depth5@100ms)
                stream_name = stream.split('@')[0]
                
                if '@' in stream:
                    # Stream with parameters
                    subscriptions.append(f"{symbol.lower()}@{stream}")
                else:
                    # Simple stream
                    subscriptions.append(f"{symbol.lower()}@{stream}")
                    
                self.subscribed_streams.add(f"{symbol}:{stream_name}")
        
        # For combined streams, we need to reconnect with the full URL
        if subscriptions:
            # Close current connection
            if self.ws:
                await self.ws.close()
                
            # Build new URL with streams
            stream_names = "/".join(subscriptions)
            self.url = f"{self.url.split('/ws')[0]}/stream?streams={stream_names}"
            
            logger.info(f"Reconnecting to: {self.url}")
            
            # The reconnection will happen automatically in the connection loop
            
    async def unsubscribe_symbols(self, symbols: List[str], streams: List[str]):
        """Unsubscribe from symbols and streams"""
        # Build unsubscription list
        unsubscriptions = []
        for symbol in symbols:
            for stream in streams:
                stream_name = stream.split('@')[0]
                
                if '@' in stream:
                    unsubscriptions.append(f"{symbol.lower()}@{stream}")
                else:
                    unsubscriptions.append(f"{symbol.lower()}@{stream}")
                    
                self.subscribed_streams.discard(f"{symbol}:{stream_name}")
                
        # Send unsubscription message
        if self.connected and unsubscriptions:
            unsub_message = {
                "method": "UNSUBSCRIBE",
                "params": unsubscriptions,
                "id": int(time.time() * 1000)
            }
            
            await self.send(json.dumps(unsub_message))
            logger.info(f"Unsubscribed from {len(unsubscriptions)} Binance streams")
            
    async def on_connect(self):
        """Called when connected - resubscribe to streams"""
        # Resubscribe to all streams
        if self.subscribed_streams:
            # Parse back to symbols and streams
            symbols_to_resubscribe = set()
            streams_to_resubscribe = set()
            
            for item in self.subscribed_streams:
                symbol, stream = item.split(':')
                symbols_to_resubscribe.add(symbol)
                streams_to_resubscribe.add(stream)
                
            await self.subscribe_symbols(
                list(symbols_to_resubscribe),
                list(streams_to_resubscribe)
            )
            
    async def on_message(self, message: str):
        """Process a received message"""
        try:
            data = json.loads(message)
            
            # Debug log first few messages
            if self.metrics["messages_received"] < 5:
                logger.info(f"Raw message: {message[:200]}...")
            
            # Handle subscription responses
            if "result" in data and data["result"] is None:
                logger.info("Subscription confirmed")
                return
                
            # Handle combined stream data (when using /ws)
            if "stream" in data:
                stream_name = data["stream"]
                stream_data = data["data"]
                
                # Extract stream type
                stream_parts = stream_name.split('@')
                if len(stream_parts) >= 2:
                    stream_type = stream_parts[1].split('@')[0]
                    
                    # Call appropriate handler
                    handler = self.handlers.get(stream_type)
                    if handler:
                        await handler(stream_data)
                    else:
                        logger.warning(f"No handler for stream type: {stream_type}")
                        
            # Handle single stream data (direct format)
            else:
                # Check if it's a bookTicker update (most common for our use)
                if "u" in data and "s" in data and "b" in data and "a" in data:
                    # This is a bookTicker update
                    await self._handle_book_ticker(data)
                elif "e" in data:
                    # Event-based message
                    event_type = data["e"]
                    
                    if event_type == "bookTicker":
                        await self._handle_book_ticker(data)
                    elif event_type == "aggTrade":
                        await self._handle_agg_trade(data)
                    elif event_type == "depthUpdate":
                        await self._handle_depth_update(data)
                    else:
                        logger.warning(f"Unknown event type: {event_type}")
                else:
                    # Unknown message format
                    logger.debug(f"Unknown message format: {message[:100]}...")
                    
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            
    async def _handle_book_ticker(self, data: Dict[str, Any]):
        """Handle best bid/ask updates"""
        # bookTicker format can vary, handle both formats
        symbol = data.get("s") or data.get("symbol")
        
        event = Event(
            type=EventType.BINANCE_PRICE_UPDATE,
            data={
                "symbol": symbol,
                "bid_price": float(data.get("b", 0)),
                "bid_qty": float(data.get("B", 0)),
                "ask_price": float(data.get("a", 0)),
                "ask_qty": float(data.get("A", 0)),
                "timestamp": data.get("T", data.get("E", time.time() * 1000))
            },
            source=self.name,
            priority=0  # High priority
        )
        
        await event_bus.publish(event)
        
    async def _handle_agg_trade(self, data: Dict[str, Any]):
        """Handle aggregated trade updates"""
        event = Event(
            type=EventType.BINANCE_PRICE_UPDATE,
            data={
                "symbol": data["s"],
                "price": float(data["p"]),
                "quantity": float(data["q"]),
                "is_buyer_maker": data["m"],
                "trade_time": data["T"],
                "first_trade_id": data["f"],
                "last_trade_id": data["l"]
            },
            source=self.name,
            priority=1
        )
        
        await event_bus.publish(event)
        
    async def _handle_depth_update(self, data: Dict[str, Any]):
        """Handle order book depth updates"""
        event = Event(
            type=EventType.BINANCE_ORDERBOOK_UPDATE,
            data={
                "symbol": data["s"],
                "first_update_id": data["U"],
                "final_update_id": data["u"],
                "bids": [[float(p), float(q)] for p, q in data["b"]],
                "asks": [[float(p), float(q)] for p, q in data["a"]],
                "timestamp": data.get("E", time.time() * 1000)
            },
            source=self.name,
            priority=0
        )
        
        await event_bus.publish(event)
        
    async def _handle_depth5(self, data: Dict[str, Any]):
        """Handle top 5 order book levels"""
        await self._handle_depth_snapshot(data, 5)
        
    async def _handle_depth10(self, data: Dict[str, Any]):
        """Handle top 10 order book levels"""
        await self._handle_depth_snapshot(data, 10)
        
    async def _handle_depth20(self, data: Dict[str, Any]):
        """Handle top 20 order book levels"""
        await self._handle_depth_snapshot(data, 20)
        
    async def _handle_depth_snapshot(self, data: Dict[str, Any], levels: int):
        """Handle order book snapshot"""
        event = Event(
            type=EventType.BINANCE_ORDERBOOK_UPDATE,
            data={
                "symbol": data.get("s", data.get("symbol")),
                "levels": levels,
                "bids": [[float(p), float(q)] for p, q in data["bids"]],
                "asks": [[float(p), float(q)] for p, q in data["asks"]],
                "last_update_id": data.get("lastUpdateId", 0),
                "timestamp": time.time() * 1000
            },
            source=self.name,
            priority=0
        )
        
        await event_bus.publish(event)
        
    async def on_disconnect(self):
        """Called when disconnected"""
        # Send disconnected event
        await event_bus.publish(Event(
            type=EventType.WEBSOCKET_DISCONNECTED,
            data={"client": self.name},
            source=self.name,
            priority=1
        ))