"""
Test the event bus implementation
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.event_bus import EventBus, Event, EventType, on_event

# Create test event bus
test_bus = EventBus()

# Test handler using decorator
@on_event(EventType.BINANCE_PRICE_UPDATE)
async def handle_price_update(event: Event):
    print(f"Price update: {event.data['symbol']} = ${event.data['price']}")

# Another handler for the same event
@on_event(EventType.BINANCE_PRICE_UPDATE)
async def analyze_price(event: Event):
    print(f"Analyzing price change for {event.data['symbol']}")

async def test_event_bus():
    """Test basic event bus functionality"""
    print("Starting event bus test...")
    
    # Start the event bus
    await test_bus.start()
    
    # Publish some test events
    for i in range(5):
        event = Event(
            type=EventType.BINANCE_PRICE_UPDATE,
            data={
                "symbol": "SOLUSDT",
                "price": 100.0 + i,
                "volume": 1000000
            },
            source="test",
            priority=0
        )
        await test_bus.publish(event)
        print(f"Published event {i+1}")
    
    # Give handlers time to process
    await asyncio.sleep(1)
    
    # Check stats
    stats = test_bus.get_stats()
    print("\nEvent Bus Stats:")
    print(f"Events processed: {stats['events_processed']}")
    print(f"Avg queue latency: {stats['avg_queue_latency_ms']:.2f}ms")
    print(f"Avg process time: {stats['avg_process_time_ms']:.2f}ms")
    
    # Stop the event bus
    await test_bus.stop()
    print("\nTest completed!")

if __name__ == "__main__":
    asyncio.run(test_event_bus())# [Paste the test_event_bus.py content from the artifact above]
