"""
Simplified Binance WebSocket client for direct stream connections
"""
import json
import logging
import asyncio
import websockets
from typing import List, Dict, Any
import time
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from infrastructure.event_bus import Event, EventType, event_bus

logger = logging.getLogger(__name__)


class BinanceWebSocketSimple:
    """Simple Binance WebSocket client that connects directly to streams"""
    
    def __init__(self, testnet: bool = False):
        self.testnet = testnet
        self.base_url = (
            "wss://testnet.binance.vision" if testnet
            else "wss://stream.binance.com:9443"
        )
        self.ws = None
        self.running = False
        
    async def connect_and_subscribe(self, symbols: List[str], streams: List[str]):
        """Connect to specific streams"""
        # Build stream names
        stream_names = []
        for symbol in symbols:
            for stream in streams:
                stream_names.append(f"{symbol.lower()}@{stream}")
        
        # Create combined stream URL
        streams_path = "/".join(stream_names)
        url = f"{self.base_url}/stream?streams={streams_path}"
        
        logger.info(f"Connecting to: {url}")
        
        try:
            self.ws = await websockets.connect(url)
            self.running = True
            
            # Send connected event
            await event_bus.publish(Event(
                type=EventType.WEBSOCKET_CONNECTED,
                data={"client": "BinanceWS", "url": url},
                source="BinanceWS"
            ))
            
            # Start receiving messages
            await self._receive_messages()
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            raise
    
    async def _receive_messages(self):
        """Receive and process messages"""
        while self.running and self.ws:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                
                # Combined stream format
                if "stream" in data and "data" in data:
                    stream_type = data["stream"].split('@')[1]
                    stream_data = data["data"]
                    
                    if stream_type == "bookTicker":
                        await self._handle_book_ticker(stream_data)
                    elif stream_type == "aggTrade":
                        await self._handle_trade(stream_data)
                        
            except websockets.ConnectionClosed:
                logger.info("WebSocket connection closed")
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def _handle_book_ticker(self, data: Dict[str, Any]):
        """Handle bookTicker updates"""
        event = Event(
            type=EventType.BINANCE_PRICE_UPDATE,
            data={
                "symbol": data["s"],
                "bid_price": float(data["b"]),
                "bid_qty": float(data["B"]),
                "ask_price": float(data["a"]),
                "ask_qty": float(data["A"]),
                "update_id": data["u"],
                "timestamp": time.time() * 1000
            },
            source="BinanceWS",
            priority=0
        )
        
        await event_bus.publish(event)
    
    async def _handle_trade(self, data: Dict[str, Any]):
        """Handle trade updates"""
        event = Event(
            type=EventType.BINANCE_PRICE_UPDATE,
            data={
                "symbol": data["s"],
                "price": float(data["p"]),
                "quantity": float(data["q"]),
                "trade_time": data["T"],
                "is_buyer_maker": data["m"]
            },
            source="BinanceWS",
            priority=1
        )
        
        await event_bus.publish(event)
    
    async def close(self):
        """Close the WebSocket connection"""
        self.running = False
        if self.ws:
            await self.ws.close()


async def test_simple_client():
    """Test the simple WebSocket client"""
    print("Testing simplified Binance WebSocket client...\n")
    
    # Track updates
    updates = []
    
    async def handle_price(event: Event):
        updates.append(event.data)
        print(f"Update #{len(updates)}: {event.data['symbol']} - "
              f"Bid: ${event.data.get('bid_price', 'N/A'):.2f}, "
              f"Ask: ${event.data.get('ask_price', 'N/A'):.2f}")
        
    # Register handler
    event_bus.subscribe(EventType.BINANCE_PRICE_UPDATE, handle_price)
    
    # Start event bus
    await event_bus.start()
    
    # Create and connect client
    client = BinanceWebSocketSimple(testnet=False)
    
    try:
        # Connect and subscribe
        task = asyncio.create_task(
            client.connect_and_subscribe(
                symbols=["SOLUSDT", "BTCUSDT"],
                streams=["bookTicker"]
            )
        )
        
        # Wait for some updates
        await asyncio.sleep(5)
        
        print(f"\nReceived {len(updates)} updates")
        
        # Close connection
        await client.close()
        task.cancel()
        
    finally:
        await event_bus.stop()
    
    print("\nTest completed!")


if __name__ == "__main__":
    asyncio.run(test_simple_client())