"""
Test Binance WebSocket client
"""
import asyncio
import sys
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from exchanges.binance.ws_client import BinanceWebSocketClient
from infrastructure.event_bus import event_bus, on_event, EventType, Event

# Price update counter
price_updates = 0

@on_event(EventType.BINANCE_PRICE_UPDATE)
async def handle_price_update(event: Event):
    """Handle Binance price updates"""
    global price_updates
    price_updates += 1
    
    data = event.data
    print(f"Price Update #{price_updates}: {data['symbol']} - Bid: ${data.get('bid_price', 'N/A')}, Ask: ${data.get('ask_price', 'N/A')}")
    
    # Stop after 5 updates
    if price_updates >= 5:
        print("\nReceived 5 price updates, stopping test...")

@on_event(EventType.WEBSOCKET_CONNECTED)
async def handle_connected(event: Event):
    """Handle connection events"""
    print(f"✅ {event.data['client']} connected!")

@on_event(EventType.WEBSOCKET_DISCONNECTED)
async def handle_disconnected(event: Event):
    """Handle disconnection events"""
    print(f"❌ {event.data['client']} disconnected!")

async def test_binance_websocket():
    """Test Binance WebSocket connection"""
    print("Starting Binance WebSocket test...")
    print("Expecting 5 price updates from SOL and BTC...\n")
    
    # Start event bus AFTER handlers are registered
    await event_bus.start()
    
    # Create Binance WebSocket client
    client = BinanceWebSocketClient(testnet=False)  # Using mainnet for real data
    
    # Start the client
    await client.start()
    
    # Wait for connection
    await asyncio.sleep(2)
    
    # Subscribe to SOL and BTC price updates
    print("Subscribing to SOLUSDT and BTCUSDT streams...")
    await client.subscribe_symbols(
        symbols=["SOLUSDT", "BTCUSDT"],
        streams=["bookTicker"]  # Real-time best bid/ask
    )
    
    # Wait for price updates (with timeout)
    timeout = 30  # 30 seconds timeout
    start_time = asyncio.get_event_loop().time()
    
    while price_updates < 5:
        if asyncio.get_event_loop().time() - start_time > timeout:
            print(f"\nTimeout after {timeout} seconds. Received {price_updates} updates.")
            break
        await asyncio.sleep(0.1)
    
    # Give a moment for final messages
    await asyncio.sleep(1)
    
    # Check metrics
    metrics = client.get_metrics()
    print("\n📊 WebSocket Metrics:")
    print(f"Connected: {metrics['connected']}")
    print(f"Messages received: {metrics['messages_received']}")
    print(f"Messages processed: {metrics['messages_processed']}")
    print(f"Errors: {metrics['errors']}")
    print(f"Reconnects: {metrics['reconnects']}")
    if 'avg_latency_ms' in metrics:
        print(f"Avg latency: {metrics['avg_latency_ms']:.2f}ms")
    
    # Event bus stats
    bus_stats = event_bus.get_stats()
    print(f"\n📊 Event Bus Stats:")
    print(f"Events processed: {bus_stats['events_processed']}")
    print(f"Queue size: {bus_stats['current_queue_size']}")
    
    # Stop everything
    print("\nStopping WebSocket client...")
    await client.stop()
    await event_bus.stop()
    
    print("\nTest completed!")

if __name__ == "__main__":
    asyncio.run(test_binance_websocket())