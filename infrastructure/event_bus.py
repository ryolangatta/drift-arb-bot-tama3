"""
Event Bus for WebSocket Architecture
Handles all real-time events with ultra-low latency
"""
import asyncio
import time
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging
import orjson
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventType(Enum):
    """All possible event types in the system"""
    # Price events
    BINANCE_PRICE_UPDATE = "binance_price_update"
    DRIFT_PRICE_UPDATE = "drift_price_update"
    
    # Order book events
    BINANCE_ORDERBOOK_UPDATE = "binance_orderbook_update"
    DRIFT_ORDERBOOK_UPDATE = "drift_orderbook_update"
    
    # Trade events
    TRADE_SIGNAL = "trade_signal"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    
    # System events
    WEBSOCKET_CONNECTED = "websocket_connected"
    WEBSOCKET_DISCONNECTED = "websocket_disconnected"
    WEBSOCKET_ERROR = "websocket_error"
    
    # Risk events
    RISK_LIMIT_BREACHED = "risk_limit_breached"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"


@dataclass
class Event:
    """Event data structure with timing information"""
    type: EventType
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    priority: int = 0  # 0 = highest priority
    
    def to_json(self) -> bytes:
        """Serialize to JSON bytes for Redis/Kafka"""
        return orjson.dumps({
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
            "priority": self.priority
        })
    
    @classmethod
    def from_json(cls, data: bytes) -> 'Event':
        """Deserialize from JSON bytes"""
        obj = orjson.loads(data)
        return cls(
            type=EventType(obj["type"]),
            data=obj["data"],
            timestamp=obj["timestamp"],
            source=obj["source"],
            priority=obj["priority"]
        )


class EventBus:
    """
    High-performance event bus for WebSocket architecture
    Features:
    - Async event processing
    - Priority queues
    - Event filtering
    - Performance metrics
    """
    
    def __init__(self, max_queue_size: int = 10000):
        self.handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self.event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self.running = False
        self.stats = {
            "events_processed": 0,
            "events_dropped": 0,
            "processing_times": [],
            "queue_sizes": []
        }
        self._worker_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the event processing worker"""
        if self.running:
            return
        
        self.running = True
        self._worker_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")
        
    async def stop(self):
        """Stop the event processing worker"""
        self.running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus stopped")
        
    def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe a handler to an event type"""
        if not asyncio.iscoroutinefunction(handler):
            raise ValueError(f"Handler {handler.__name__} must be async")
        
        self.handlers[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__name__} to {event_type.value}")
        
    def unsubscribe(self, event_type: EventType, handler: Callable):
        """Unsubscribe a handler from an event type"""
        if handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
            logger.debug(f"Unsubscribed {handler.__name__} from {event_type.value}")
            
    async def publish(self, event: Event):
        """
        Publish an event to the bus
        Non-blocking - returns immediately
        """
        try:
            # Use priority as first element for priority queue
            await self.event_queue.put((event.priority, time.time(), event))
        except asyncio.QueueFull:
            self.stats["events_dropped"] += 1
            logger.warning(f"Event queue full, dropping event: {event.type.value}")
            
    async def _process_events(self):
        """Worker coroutine that processes events"""
        while self.running:
            try:
                # Wait for event with timeout
                priority, enqueue_time, event = await asyncio.wait_for(
                    self.event_queue.get(), 
                    timeout=0.1
                )
                
                # Calculate queue latency
                queue_latency = time.time() - enqueue_time
                
                # Process the event
                start_time = time.time()
                await self._handle_event(event)
                
                # Update stats
                process_time = time.time() - start_time
                self.stats["events_processed"] += 1
                self.stats["processing_times"].append({
                    "queue_latency": queue_latency * 1000,  # ms
                    "process_time": process_time * 1000,    # ms
                    "event_type": event.type.value
                })
                
                # Keep only last 1000 timing samples
                if len(self.stats["processing_times"]) > 1000:
                    self.stats["processing_times"] = self.stats["processing_times"][-1000:]
                    
            except asyncio.TimeoutError:
                # No events to process
                continue
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                
    async def _handle_event(self, event: Event):
        """Handle a single event by calling all subscribed handlers"""
        handlers = self.handlers.get(event.type, [])
        
        if not handlers:
            logger.debug(f"No handlers for event type: {event.type.value}")
            return
            
        # Run all handlers concurrently
        tasks = [
            asyncio.create_task(self._run_handler(handler, event))
            for handler in handlers
        ]
        
        # Wait for all handlers to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log any handler errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"Handler {handlers[i].__name__} failed for {event.type.value}: {result}"
                )
                
    async def _run_handler(self, handler: Callable, event: Event):
        """Run a single handler with error handling"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Handler {handler.__name__} error: {e}")
            raise
            
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        processing_times = self.stats["processing_times"]
        
        if processing_times:
            queue_latencies = [t["queue_latency"] for t in processing_times]
            process_times = [t["process_time"] for t in processing_times]
            
            return {
                "events_processed": self.stats["events_processed"],
                "events_dropped": self.stats["events_dropped"],
                "current_queue_size": self.event_queue.qsize(),
                "avg_queue_latency_ms": sum(queue_latencies) / len(queue_latencies),
                "max_queue_latency_ms": max(queue_latencies),
                "avg_process_time_ms": sum(process_times) / len(process_times),
                "max_process_time_ms": max(process_times),
            }
        else:
            return {
                "events_processed": 0,
                "events_dropped": 0,
                "current_queue_size": 0,
                "avg_queue_latency_ms": 0,
                "max_queue_latency_ms": 0,
                "avg_process_time_ms": 0,
                "max_process_time_ms": 0,
            }


# Global event bus instance
event_bus = EventBus()


# Decorator for easy event handling
def on_event(event_type: EventType):
    """Decorator to subscribe a function to an event type"""
    def decorator(func):
        event_bus.subscribe(event_type, func)
        return func
    return decorator# [Paste the event_bus.py content from the artifact above]
