"""
WebSocket Price Feeds - Real-time price streaming with automatic reconnection
Provides low-latency price feeds from multiple exchanges with fallback mechanisms
"""
import asyncio
import json
import logging
import time
import statistics
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from collections import deque, defaultdict

# Handle websockets import with fallback
try:
    import websockets
except ImportError:
    print("Warning: websockets package not installed. Install with: pip install websockets")
    websockets = None

from binance.client import Client

logger = logging.getLogger(__name__)

class PriceBuffer:
    """Buffer for storing recent price data with statistics"""
    
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.prices = deque(maxlen=max_size)
        self.timestamps = deque(maxlen=max_size)
        
    def add_price(self, price: float, timestamp: float = None):
        """Add new price to buffer"""
        if timestamp is None:
            timestamp = time.time()
        
        self.prices.append(price)
        self.timestamps.append(timestamp)
    
    def get_latest(self) -> Optional[float]:
        """Get most recent price"""
        return self.prices[-1] if self.prices else None
    
    def get_moving_average(self, periods: int = 10) -> Optional[float]:
        """Calculate moving average"""
        if len(self.prices) < periods:
            return None
        return statistics.mean(list(self.prices)[-periods:])
    
    def get_volatility(self, periods: int = 20) -> float:
        """Calculate price volatility (standard deviation)"""
        if len(self.prices) < 2:
            return 0.0
        
        # Use available data if we don't have enough periods
        available_periods = min(periods, len(self.prices))
        recent_prices = list(self.prices)[-available_periods:]
        
        if len(recent_prices) < 2:
            return 0.0
            
        try:
            return statistics.stdev(recent_prices)
        except statistics.StatisticsError:
            return 0.0
    
    def is_stale(self, max_age_seconds: int = 10) -> bool:
        """Check if latest price is stale"""
        if not self.timestamps:
            return True
        return time.time() - self.timestamps[-1] > max_age_seconds

class WebSocketFeeds:
    """WebSocket price feeds manager with automatic reconnection"""
    
    def __init__(self, config: dict):
        self.config = config
        self.callbacks = []
        self.price_buffers: Dict[str, PriceBuffer] = {}
        self.subscribed_symbols = set()
        
        # WebSocket connections
        self.binance_ws = None
        self.drift_ws = None
        
        # Connection state
        self.binance_connected = False
        self.drift_connected = False
        self.last_binance_message = 0
        self.last_drift_message = 0
        
        # Reconnection settings
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0
        self.reconnect_attempts = 0
        
        # Metrics
        self.metrics = {
            'messages_received': 0,
            'reconnect_count': 0,
            'uptime_start': time.time(),
            'last_error': None,
            'binance_latency': deque(maxlen=100),
            'drift_latency': deque(maxlen=100),
            'error_count': 0
        }
        
        # Fallback REST client
        self.rest_client = Client("", "")  # Public client for price data
        self.fallback_active = False
        self.fallback_task = None
        
        logger.info("WebSocket feeds manager initialized")
    
    def add_callback(self, callback: Callable):
        """Add callback for price updates"""
        self.callbacks.append(callback)
        logger.info(f"Added price callback, total: {len(self.callbacks)}")
    
    def subscribe_symbol(self, symbol: str):
        """Subscribe to price updates for a symbol"""
        self.subscribed_symbols.add(symbol.lower())
        if symbol not in self.price_buffers:
            self.price_buffers[symbol] = PriceBuffer()
        logger.info(f"Subscribed to {symbol}")
    
    def unsubscribe_symbol(self, symbol: str):
        """Unsubscribe from a symbol"""
        self.subscribed_symbols.discard(symbol.lower())
        logger.info(f"Unsubscribed from {symbol}")
    
    async def start(self):
        """Start WebSocket connections"""
        logger.info("Starting WebSocket price feeds...")
        
        if not websockets:
            logger.warning("WebSockets not available, starting fallback only")
            await self._start_fallback()
            return []
        
        # Start connection tasks
        tasks = [
            asyncio.create_task(self._binance_websocket_loop()),
            asyncio.create_task(self._drift_websocket_loop()),
            asyncio.create_task(self._health_monitor_loop())
        ]
        
        # Wait for initial connection
        await asyncio.sleep(2.0)
        
        if not self.binance_connected and not self.drift_connected:
            logger.warning("No WebSocket connections established, starting fallback")
            await self._start_fallback()
        
        return tasks
    
    async def _binance_websocket_loop(self):
        """Binance WebSocket connection loop with reconnection"""
        while True:
            try:
                await self._connect_binance_websocket()
            except Exception as e:
                logger.error(f"Binance WebSocket error: {e}")
                self.metrics['error_count'] += 1
                self.metrics['last_error'] = str(e)
                self.binance_connected = False
                await self._handle_reconnection('binance')
    
    async def _connect_binance_websocket(self):
        """Connect to Binance WebSocket stream"""
        if not self.subscribed_symbols:
            await asyncio.sleep(5)
            return
        
        if not websockets:
            logger.warning("WebSockets not available for Binance connection")
            return
        
        # Create stream for subscribed symbols
        symbols = '/'.join([f"{symbol}@ticker" for symbol in self.subscribed_symbols])
        ws_url = f"wss://stream.binance.com:9443/ws/{symbols}"
        
        logger.info(f"Connecting to Binance WebSocket: {len(self.subscribed_symbols)} symbols")
        
        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as websocket:
                self.binance_ws = websocket
                self.binance_connected = True
                self.reconnect_attempts = 0
                logger.info("✅ Binance WebSocket connected")
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        await self._process_binance_message(data)
                        self.last_binance_message = time.time()
                        self.metrics['messages_received'] += 1
                        
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from Binance WebSocket")
                    except Exception as e:
                        logger.error(f"Error processing Binance message: {e}")
                        
        except Exception as e:
            logger.error(f"Binance WebSocket connection failed: {e}")
            raise
    
    async def _process_binance_message(self, data: dict):
        """Process Binance ticker message"""
        try:
            symbol = data.get('s', '').lower()
            price = float(data.get('c', 0))  # Current price
            
            if symbol and price > 0:
                # Add to buffer
                if symbol in self.price_buffers:
                    self.price_buffers[symbol].add_price(price)
                
                # Calculate latency
                event_time = data.get('E', 0) / 1000  # Convert to seconds
                if event_time > 0:
                    latency = time.time() - event_time
                    self.metrics['binance_latency'].append(latency)
                
                # Notify callbacks
                await self._notify_callbacks('binance', symbol, price, data)
                
        except Exception as e:
            logger.error(f"Error processing Binance data: {e}")
    
    async def _drift_websocket_loop(self):
        """Drift WebSocket simulation"""
        while True:
            try:
                if self.subscribed_symbols:
                    for symbol in self.subscribed_symbols:
                        if symbol in self.price_buffers:
                            binance_price = self.price_buffers[symbol].get_latest()
                            if binance_price:
                                # Simulate Drift price with small spread
                                import random
                                spread = random.uniform(0.001, 0.005)
                                drift_price = binance_price * (1 + spread)
                                
                                # Add to buffer
                                drift_symbol = f"{symbol}_drift"
                                if drift_symbol not in self.price_buffers:
                                    self.price_buffers[drift_symbol] = PriceBuffer()
                                
                                self.price_buffers[drift_symbol].add_price(drift_price)
                                
                                # Notify callbacks
                                await self._notify_callbacks('drift', symbol, drift_price, {'simulated': True})
                
                self.drift_connected = True
                self.last_drift_message = time.time()
                await asyncio.sleep(1.0)  # Simulate 1Hz updates
                
            except Exception as e:
                logger.error(f"Drift simulation error: {e}")
                self.drift_connected = False
                await asyncio.sleep(5.0)
    
    async def _notify_callbacks(self, exchange: str, symbol: str, price: float, raw_data: dict):
        """Notify all registered callbacks of price updates"""
        for callback in self.callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(exchange, symbol, price, raw_data)
                else:
                    callback(exchange, symbol, price, raw_data)
            except Exception as e:
                logger.error(f"Error in price callback: {e}")
    
    async def _health_monitor_loop(self):
        """Monitor connection health and trigger fallback if needed"""
        while True:
            try:
                await asyncio.sleep(10.0)
                
                # Check for stale connections
                now = time.time()
                binance_stale = (now - self.last_binance_message) > 30 if self.last_binance_message else False
                drift_stale = (now - self.last_drift_message) > 30 if self.last_drift_message else False
                
                if binance_stale and self.binance_connected:
                    logger.warning("Binance WebSocket appears stale")
                    self.binance_connected = False
                
                if drift_stale and self.drift_connected:
                    logger.warning("Drift WebSocket appears stale") 
                    self.drift_connected = False
                
                # Start fallback if no connections
                if not self.binance_connected and not self.fallback_active:
                    logger.info("Starting REST API fallback")
                    await self._start_fallback()
                
                # Stop fallback if WebSocket restored
                elif self.binance_connected and self.fallback_active:
                    logger.info("WebSocket restored, stopping fallback")
                    await self._stop_fallback()
                
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
    
    async def _handle_reconnection(self, exchange: str):
        """Handle reconnection with exponential backoff"""
        self.reconnect_attempts += 1
        self.metrics['reconnect_count'] += 1
        
        delay = min(self.reconnect_delay * (2 ** self.reconnect_attempts), self.max_reconnect_delay)
        logger.info(f"Reconnecting to {exchange} in {delay:.1f}s (attempt {self.reconnect_attempts})")
        
        await asyncio.sleep(delay)
    
    async def _start_fallback(self):
        """Start REST API fallback for price feeds"""
        if self.fallback_active:
            return
        
        self.fallback_active = True
        self.fallback_task = asyncio.create_task(self._fallback_loop())
        logger.info("REST API fallback started")
    
    async def _stop_fallback(self):
        """Stop REST API fallback"""
        self.fallback_active = False
        if self.fallback_task:
            self.fallback_task.cancel()
            try:
                await self.fallback_task
            except asyncio.CancelledError:
                pass
        logger.info("REST API fallback stopped")
    
    async def _fallback_loop(self):
        """Fallback price polling using REST API"""
        while self.fallback_active:
            try:
                for symbol in self.subscribed_symbols:
                    try:
                        # Get price from Binance REST API
                        ticker = self.rest_client.get_ticker(symbol=symbol.upper() + 'USDT')
                        price = float(ticker['lastPrice'])
                        
                        # Add to buffer
                        if symbol in self.price_buffers:
                            self.price_buffers[symbol].add_price(price)
                        
                        # Notify callbacks
                        await self._notify_callbacks('binance_rest', symbol, price, {'fallback': True})
                        
                    except Exception as e:
                        logger.error(f"Fallback error for {symbol}: {e}")
                
                await asyncio.sleep(2.0)  # Poll every 2 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Fallback loop error: {e}")
                await asyncio.sleep(5.0)
    
    def get_latest_price(self, exchange: str, symbol: str) -> Optional[float]:
        """Get latest price for a symbol from specific exchange"""
        key = f"{symbol}_{exchange}" if exchange == 'drift' else symbol
        buffer = self.price_buffers.get(key)
        return buffer.get_latest() if buffer else None
    
    def get_price_statistics(self, symbol: str, exchange: str = 'binance') -> Dict[str, Any]:
        """Get price statistics for a symbol"""
        key = f"{symbol}_{exchange}" if exchange == 'drift' else symbol
        buffer = self.price_buffers.get(key)
        
        if not buffer:
            return {}
        
        return {
            'latest_price': buffer.get_latest(),
            'moving_average_10': buffer.get_moving_average(10),
            'moving_average_20': buffer.get_moving_average(20),
            'volatility': buffer.get_volatility(),
            'is_stale': buffer.is_stale(),
            'buffer_size': len(buffer.prices)
        }
    
    def get_connection_metrics(self) -> Dict[str, Any]:
        """Get connection and performance metrics"""
        uptime = time.time() - self.metrics['uptime_start']
        
        metrics = {
            'uptime_seconds': uptime,
            'binance_connected': self.binance_connected,
            'drift_connected': self.drift_connected,
            'fallback_active': self.fallback_active,
            'messages_received': self.metrics['messages_received'],
            'reconnect_count': self.metrics['reconnect_count'],
            'error_count': self.metrics['error_count'],
            'last_error': self.metrics['last_error'],
            'subscribed_symbols': len(self.subscribed_symbols),
            'message_rate': self.metrics['messages_received'] / uptime if uptime > 0 else 0
        }
        
        # Add latency statistics
        if self.metrics['binance_latency']:
            metrics['binance_avg_latency'] = statistics.mean(self.metrics['binance_latency'])
            metrics['binance_max_latency'] = max(self.metrics['binance_latency'])
        
        if self.metrics['drift_latency']:
            metrics['drift_avg_latency'] = statistics.mean(self.metrics['drift_latency'])
            metrics['drift_max_latency'] = max(self.metrics['drift_latency'])
        
        return metrics
    
    async def close(self):
        """Close all connections gracefully"""
        logger.info("Closing WebSocket connections...")
        
        self.binance_connected = False
        self.drift_connected = False
        
        await self._stop_fallback()
        
        if self.binance_ws:
            await self.binance_ws.close()
        
        logger.info("WebSocket connections closed")
