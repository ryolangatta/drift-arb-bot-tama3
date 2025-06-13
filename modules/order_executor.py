"""
Order Executor - Reliable order execution with retry logic and confirmations
Handles both Binance and Drift order execution with comprehensive error handling
"""
import asyncio
import logging
import time
import random
from typing import Dict, Optional, Any, Callable, Tuple, List
from enum import Enum
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class OrderStatus(Enum):
    """Order status enumeration"""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    CONFIRMED = "CONFIRMED"

class ExchangeType(Enum):
    """Exchange type enumeration"""
    BINANCE = "BINANCE"
    DRIFT = "DRIFT"
    SIMULATION = "SIMULATION"

class OrderExecutor:
    def __init__(self, config: dict):
        self.config = config
        
        # Retry configuration
        self.max_retries = int(config.get('MAX_RETRIES', 3))
        self.base_delay = float(config.get('BASE_RETRY_DELAY', 0.1))  # 0.1 second
        self.max_delay = float(config.get('MAX_RETRY_DELAY', 30.0))   # 30 seconds
        self.backoff_multiplier = float(config.get('BACKOFF_MULTIPLIER', 2.0))
        
        # Confirmation settings
        self.confirmation_timeout = int(config.get('CONFIRMATION_TIMEOUT', 30))  # 30 seconds
        self.confirmation_check_interval = float(config.get('CONFIRMATION_CHECK_INTERVAL', 2.0))  # 2 seconds
        
        # Order tracking
        self.pending_orders: Dict[str, Dict] = {}
        self.order_history: List[Dict] = []
        
        logger.info(f"Order Executor initialized - Max retries: {self.max_retries}, Base delay: {self.base_delay}s")
    
    def calculate_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        delay = self.base_delay * (self.backoff_multiplier ** attempt)
        delay = min(delay, self.max_delay)
        
        # Add jitter (random variation) to prevent thundering herd
        jitter = delay * 0.1 * random.random()
        return delay + jitter
    
    async def execute_with_retry(self, 
                                operation: Callable,
                                operation_name: str,
                                *args, **kwargs) -> Tuple[bool, Any, str]:
        """
        Execute an operation with exponential backoff retry logic
        Returns: (success: bool, result: Any, error_message: str)
        """
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"Executing {operation_name}, attempt {attempt + 1}/{self.max_retries + 1}")
                
                # Execute the operation
                result = await operation(*args, **kwargs)
                
                logger.info(f"✅ {operation_name} succeeded on attempt {attempt + 1}")
                return True, result, ""
                
            except Exception as e:
                last_error = e
                error_msg = str(e)
                
                if attempt < self.max_retries:
                    delay = self.calculate_retry_delay(attempt)
                    logger.warning(f"⚠️ {operation_name} failed (attempt {attempt + 1}): {error_msg}")
                    logger.info(f"Retrying in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ {operation_name} failed after {self.max_retries + 1} attempts: {error_msg}")
        
        return False, None, str(last_error)
    
    async def place_binance_order(self, 
                                 binance_client,
                                 symbol: str,
                                 side: str,
                                 quantity: float,
                                 order_type: str = "MARKET") -> Dict:
        """Place order on Binance with error handling"""
        try:
            if hasattr(binance_client, 'place_test_order'):
                # Testnet client
                order = binance_client.place_test_order(symbol, side, quantity)
            elif hasattr(binance_client, 'order_market_buy') and side == "BUY":
                order = binance_client.order_market_buy(symbol=symbol, quantity=quantity)
            elif hasattr(binance_client, 'order_market_sell') and side == "SELL":
                order = binance_client.order_market_sell(symbol=symbol, quantity=quantity)
            else:
                # Simulation
                order = {
                    'orderId': f"sim_binance_{int(time.time() * 1000)}",
                    'symbol': symbol,
                    'side': side,
                    'status': 'FILLED',
                    'executedQty': str(quantity),
                    'fills': [],
                    'transactTime': int(time.time() * 1000)
                }
            
            return order
            
        except Exception as e:
            logger.error(f"Binance order error: {e}")
            raise
    
    async def place_drift_order(self,
                               drift_client,
                               market: str,
                               side: str,
                               size: float,
                               price: Optional[float] = None) -> Dict:
        """Place order on Drift with error handling"""
        try:
            if hasattr(drift_client, 'place_perp_order'):
                # Real Drift client
                order = await drift_client.place_perp_order(market, size, price)
            elif hasattr(drift_client, 'place_perp_order'):
                # Simulated Drift client
                order = drift_client.place_perp_order(market, size, price)
            else:
                # Simulation
                order = {
                    'orderId': f"sim_drift_{int(time.time() * 1000)}",
                    'market': market,
                    'side': side,
                    'size': size,
                    'price': price,
                    'status': 'FILLED',
                    'timestamp': time.time()
                }
            
            return order
            
        except Exception as e:
            logger.error(f"Drift order error: {e}")
            raise
    
    async def confirm_binance_order(self, binance_client, order_id: str, symbol: str) -> Tuple[bool, Dict]:
        """Confirm Binance order execution"""
        try:
            if hasattr(binance_client, 'get_order'):
                order_info = binance_client.get_order(symbol=symbol, orderId=order_id)
                
                status = order_info.get('status', 'UNKNOWN')
                is_filled = status in ['FILLED', 'PARTIALLY_FILLED']
                
                return is_filled, order_info
            else:
                # For testnet/simulation, assume immediate fill
                return True, {'status': 'FILLED', 'orderId': order_id}
                
        except Exception as e:
            logger.error(f"Error confirming Binance order {order_id}: {e}")
            return False, {}
    
    async def confirm_drift_order(self, drift_client, order_id: str) -> Tuple[bool, Dict]:
        """Confirm Drift order execution - FIXED VERSION"""
        try:
            if hasattr(drift_client, 'get_user'):
                user = drift_client.get_user()
                if user and hasattr(user, 'get_active_perp_positions'):
                    positions = user.get_active_perp_positions()
                    
                    # Check if we have positions (indicating successful order)
                    active_positions = []
                    for p in positions:
                        # Handle different position data structures
                        if hasattr(p, 'base_asset_amount'):
                            if p.base_asset_amount != 0:
                                active_positions.append(p)
                        elif isinstance(p, dict) and p.get('base_asset_amount', 0) != 0:
                            active_positions.append(p)
                        elif isinstance(p, dict) and p.get('size', 0) != 0:
                            active_positions.append(p)
                    
                    has_positions = len(active_positions) > 0
                    
                    return has_positions, {
                        'confirmed': has_positions,
                        'positions_count': len(active_positions),
                        'order_id': order_id
                    }
            
            # For simulation or when drift_client doesn't have get_user method
            # Check if the client returned a successful order
            if hasattr(drift_client, 'last_order_status'):
                return drift_client.last_order_status == 'FILLED', {'status': 'FILLED', 'orderId': order_id}
            
            # Default to immediate confirmation for simulation
            return True, {'status': 'FILLED', 'orderId': order_id, 'simulation': True}
            
        except Exception as e:
            logger.error(f"Error confirming Drift order {order_id}: {e}")
            return False, {}
    
    async def wait_for_confirmation(self, 
                                   exchange: ExchangeType,
                                   client,
                                   order_id: str,
                                   symbol: str = None) -> Tuple[bool, Dict]:
        """Wait for order confirmation with timeout"""
        start_time = time.time()
        timeout = self.confirmation_timeout
        
        logger.info(f"Waiting for {exchange.value} order {order_id} confirmation...")
        
        while time.time() - start_time < timeout:
            try:
                if exchange == ExchangeType.BINANCE:
                    confirmed, order_info = await self.confirm_binance_order(client, order_id, symbol)
                elif exchange == ExchangeType.DRIFT:
                    confirmed, order_info = await self.confirm_drift_order(client, order_id)
                else:
                    # Simulation - immediate confirmation
                    return True, {'status': 'CONFIRMED', 'orderId': order_id}
                
                if confirmed:
                    elapsed = time.time() - start_time
                    logger.info(f"✅ {exchange.value} order {order_id} confirmed in {elapsed:.2f}s")
                    return True, order_info
                
                await asyncio.sleep(self.confirmation_check_interval)
                
            except Exception as e:
                logger.error(f"Error checking {exchange.value} order confirmation: {e}")
                await asyncio.sleep(self.confirmation_check_interval)
        
        logger.error(f"❌ {exchange.value} order {order_id} confirmation timeout after {timeout}s")
        return False, {}
    
    async def execute_arbitrage_orders(self,
                                     binance_client,
                                     drift_client,
                                     opportunity: Dict,
                                     trade_size: float) -> Tuple[bool, Dict]:
        """
        Execute arbitrage orders on both exchanges with full retry and confirmation
        Returns: (success: bool, execution_result: Dict)
        """
        execution_id = f"arb_{int(time.time() * 1000)}"
        result = {
            'execution_id': execution_id,
            'timestamp': datetime.now().isoformat(),
            'opportunity': opportunity,
            'trade_size': trade_size,
            'binance_order': None,
            'drift_order': None,
            'success': False,
            'error': None,
            'execution_time_seconds': 0
        }
        
        start_time = time.time()
        
        try:
            logger.info(f"🚀 Executing arbitrage orders for {opportunity['pair']} - Size: ${trade_size:.2f}")
            
            # Step 1: Place Binance order with retry
            pair = opportunity['pair']
            symbol = pair.replace("/USDC", "USDT").replace("/", "")
            quantity = trade_size / opportunity['spot_price']
            
            success, binance_order, error = await self.execute_with_retry(
                self.place_binance_order,
                f"Binance {symbol} BUY",
                binance_client, symbol, "BUY", quantity
            )
            
            if not success:
                result['error'] = f"Binance order failed: {error}"
                return False, result
            
            result['binance_order'] = binance_order
            
            # Step 2: Place Drift order with retry
            drift_market = pair.split("/")[0] + "-PERP"
            drift_size = float(binance_order.get('executedQty', quantity))
            
            success, drift_order, error = await self.execute_with_retry(
                self.place_drift_order,
                f"Drift {drift_market} SHORT",
                drift_client, drift_market, "SHORT", drift_size, opportunity['perp_price']
            )
            
            if not success:
                result['error'] = f"Drift order failed: {error}"
                # TODO: Consider reversing Binance order here
                return False, result
            
            result['drift_order'] = drift_order
            
            # Step 3: Confirm both orders
            logger.info("🔍 Confirming order executions...")
            
            # Confirm Binance order
            binance_confirmed, binance_confirmation = await self.wait_for_confirmation(
                ExchangeType.BINANCE,
                binance_client,
                str(binance_order.get('orderId')),
                symbol
            )
            
            # Confirm Drift order
            drift_confirmed, drift_confirmation = await self.wait_for_confirmation(
                ExchangeType.DRIFT,
                drift_client,
                str(drift_order.get('orderId'))
            )
            
            # Check if both orders confirmed
            if binance_confirmed and drift_confirmed:
                result['success'] = True
                result['binance_confirmation'] = binance_confirmation
                result['drift_confirmation'] = drift_confirmation
                
                execution_time = time.time() - start_time
                result['execution_time_seconds'] = execution_time
                
                logger.info(f"✅ Arbitrage execution completed successfully in {execution_time:.2f}s")
                
            else:
                result['error'] = f"Confirmation failed - Binance: {binance_confirmed}, Drift: {drift_confirmed}"
                logger.error(f"❌ Order confirmation failed - Binance: {binance_confirmed}, Drift: {drift_confirmed}")
            
            return result['success'], result
            
        except Exception as e:
            result['error'] = f"Execution error: {str(e)}"
            result['execution_time_seconds'] = time.time() - start_time
            logger.error(f"❌ Arbitrage execution failed: {e}")
            return False, result
    
    async def execute_single_order(self,
                                  exchange: ExchangeType,
                                  client,
                                  order_params: Dict) -> Tuple[bool, Dict]:
        """
        Execute a single order with retry and confirmation
        Returns: (success: bool, order_result: Dict)
        """
        try:
            if exchange == ExchangeType.BINANCE:
                success, order, error = await self.execute_with_retry(
                    self.place_binance_order,
                    f"Binance {order_params.get('symbol')} {order_params.get('side')}",
                    client,
                    order_params['symbol'],
                    order_params['side'],
                    order_params['quantity'],
                    order_params.get('type', 'MARKET')
                )
                
                if success:
                    confirmed, confirmation = await self.wait_for_confirmation(
                        exchange, client, str(order['orderId']), order_params['symbol']
                    )
                    return confirmed, {'order': order, 'confirmation': confirmation}
                    
            elif exchange == ExchangeType.DRIFT:
                success, order, error = await self.execute_with_retry(
                    self.place_drift_order,
                    f"Drift {order_params.get('market')} {order_params.get('side')}",
                    client,
                    order_params['market'],
                    order_params['side'],
                    order_params['size'],
                    order_params.get('price')
                )
                
                if success:
                    confirmed, confirmation = await self.wait_for_confirmation(
                        exchange, client, str(order['orderId'])
                    )
                    return confirmed, {'order': order, 'confirmation': confirmation}
            
            return False, {'error': error if 'error' in locals() else 'Unknown error'}
            
        except Exception as e:
            logger.error(f"Single order execution failed: {e}")
            return False, {'error': str(e)}
    
    def get_execution_stats(self) -> Dict:
        """Get execution statistics"""
        return {
            'total_executions': len(self.order_history),
            'pending_orders': len(self.pending_orders),
            'max_retries': self.max_retries,
            'base_delay': self.base_delay,
            'max_delay': self.max_delay,
            'confirmation_timeout': self.confirmation_timeout,
            'timestamp': datetime.now().isoformat()
        }
