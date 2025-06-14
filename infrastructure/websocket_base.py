"""
Base WebSocket client with automatic reconnection and error handling
"""
import asyncio
import time
import logging
from typing import Optional, Dict, Any, Callable
from abc import ABC, abstractmethod
import websockets
from websockets.client import WebSocketClientProtocol
from tenacity import retry, stop_after_attempt, wait_exponential

from infrastructure.event_bus import Event, EventType, event_bus

logger = logging.getLogger(__name__)


class WebSocketClient(ABC):
    """
    Base WebSocket client with:
    - Automatic reconnection
    - Heartbeat/ping management
    - Error handling
    - Performance metrics
    """
    
    def __init__(
        self,
        name: str,
        url: str,
        reconnect_delay: int = 5,
        ping_interval: int = 30,
        ping_timeout: int = 10
    ):
        self.name = name
        self.url = url
        self.reconnect_delay = reconnect_delay
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        
        self.ws: Optional[WebSocketClientProtocol] = None
        self.running = False
        self.connected = False
        
        # Tasks
        self._connect_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        
        # Metrics
        self.metrics = {
            "messages_received": 0,
            "messages_processed": 0,
            "errors": 0,
            "reconnects": 0,
            "last_message_time": None,
            "connection_start": None,
            "latencies": []  # Rolling window of message latencies
        }
        
        # Callbacks
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        
    async def start(self):
        """Start the WebSocket client"""
        if self.running:
            logger.warning(f"{self.name} already running")
            return
            
        self.running = True
        self._connect_task = asyncio.create_task(self._connection_loop())
        logger.info(f"{self.name} WebSocket client started")
        
    async def stop(self):
        """Stop the WebSocket client"""
        self.running = False
        
        # Cancel tasks
        for task in [self._connect_task, self._receive_task, self._ping_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        # Close WebSocket
        if self.ws:
            await self.ws.close()
            
        logger.info(f"{self.name} WebSocket client stopped")
        
    async def _connection_loop(self):
        """Main connection loop with automatic reconnection"""
        while self.running:
            try:
                await self._connect()
                
                # Start receive and ping tasks
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._ping_task = asyncio.create_task(self._ping_loop())
                
                # Wait for any task to complete (usually due to disconnection)
                done, pending = await asyncio.wait(
                    [self._receive_task, self._ping_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    
            except Exception as e:
                logger.error(f"{self.name} connection error: {e}")
                self.metrics["errors"] += 1
                
            finally:
                self.connected = False
                if self.ws:
                    await self.ws.close()
                    self.ws = None
                    
            if self.running:
                logger.info(f"{self.name} reconnecting in {self.reconnect_delay}s...")
                self.metrics["reconnects"] += 1
                await asyncio.sleep(self.reconnect_delay)
                
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def _connect(self):
        """Connect to WebSocket with retries"""
        logger.info(f"{self.name} connecting to {self.url}")
        
        self.ws = await websockets.connect(
            self.url,
            ping_interval=None,  # We'll handle pings manually
            close_timeout=10,
            max_size=10 * 1024 * 1024  # 10MB max message size
        )
        
        self.connected = True
        self.metrics["connection_start"] = time.time()
        
        # Send connected event
        await event_bus.publish(Event(
            type=EventType.WEBSOCKET_CONNECTED,
            data={"client": self.name, "url": self.url},
            source=self.name
        ))
        
        # Call subclass connection handler
        await self.on_connect()
        
        if self.on_connected:
            await self.on_connected()
            
        logger.info(f"{self.name} connected successfully")
        
    async def _receive_loop(self):
        """Receive messages from WebSocket"""
        while self.running and self.connected and self.ws:
            try:
                message = await asyncio.wait_for(
                    self.ws.recv(),
                    timeout=self.ping_interval + self.ping_timeout
                )
                
                receive_time = time.time()
                self.metrics["messages_received"] += 1
                self.metrics["last_message_time"] = receive_time
                
                # Process message (implemented by subclass)
                process_start = time.time()
                await self.on_message(message)
                process_time = time.time() - process_start
                
                # Update metrics
                self.metrics["messages_processed"] += 1
                self.metrics["latencies"].append(process_time * 1000)  # ms
                
                # Keep only last 1000 latencies
                if len(self.metrics["latencies"]) > 1000:
                    self.metrics["latencies"] = self.metrics["latencies"][-1000:]
                    
            except asyncio.TimeoutError:
                logger.warning(f"{self.name} receive timeout")
                break
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"{self.name} connection closed")
                break
            except Exception as e:
                logger.error(f"{self.name} receive error: {e}")
                self.metrics["errors"] += 1
                
                # Send error event
                await event_bus.publish(Event(
                    type=EventType.WEBSOCKET_ERROR,
                    data={
                        "client": self.name,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    source=self.name,
                    priority=1
                ))
                
    async def _ping_loop(self):
        """Send periodic pings to keep connection alive"""
        while self.running and self.connected and self.ws:
            try:
                await asyncio.sleep(self.ping_interval)
                
                # Send ping
                pong_waiter = await self.ws.ping()
                await asyncio.wait_for(pong_waiter, timeout=self.ping_timeout)
                
                logger.debug(f"{self.name} ping successful")
                
            except asyncio.TimeoutError:
                logger.warning(f"{self.name} ping timeout")
                break
            except Exception as e:
                logger.error(f"{self.name} ping error: {e}")
                break
                
    async def send(self, message: str):
        """Send a message to the WebSocket"""
        if not self.connected or not self.ws:
            raise RuntimeError(f"{self.name} not connected")
            
        await self.ws.send(message)
        
    def get_metrics(self) -> Dict[str, Any]:
        """Get client metrics"""
        latencies = self.metrics["latencies"]
        
        metrics = {
            "name": self.name,
            "connected": self.connected,
            "messages_received": self.metrics["messages_received"],
            "messages_processed": self.metrics["messages_processed"],
            "errors": self.metrics["errors"],
            "reconnects": self.metrics["reconnects"],
            "uptime_seconds": (
                time.time() - self.metrics["connection_start"]
                if self.metrics["connection_start"] else 0
            )
        }
        
        if latencies:
            metrics.update({
                "avg_latency_ms": sum(latencies) / len(latencies),
                "max_latency_ms": max(latencies),
                "min_latency_ms": min(latencies)
            })
            
        return metrics
        
    @abstractmethod
    async def on_connect(self):
        """Called when connected (subscribe to channels, etc.)"""
        pass
        
    @abstractmethod
    async def on_message(self, message: str):
        """Process a received message"""
        pass
        
    @abstractmethod
    async def on_disconnect(self):
        """Called when disconnected"""
        pass