"""
Binance Testnet trading implementation
"""
import os
import logging
from typing import Dict, Optional, Tuple
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from decimal import Decimal, ROUND_DOWN
import asyncio

logger = logging.getLogger(__name__)

class BinanceTestnet:
    def __init__(self, config: dict):
        self.config = config
        self.client = None
        self.testnet_url = "https://testnet.binance.vision/api"
        self.is_testnet = True
        
        # Initialize client
        self._init_client()
        
    def _init_client(self):
        """Initialize Binance testnet client"""
        try:
            api_key = os.getenv('BINANCE_TESTNET_API_KEY')
            api_secret = os.getenv('BINANCE_TESTNET_SECRET')
            
            if not api_key or not api_secret:
                logger.warning("Binance testnet credentials not found - running in view-only mode")
                self.client = Client("", "")
            else:
                self.client = Client(api_key, api_secret, testnet=True)
                self.client.API_URL = self.testnet_url
                logger.info("Binance testnet client initialized with credentials")
                
                # Test connection
                self._test_connection()
                
        except Exception as e:
            logger.error(f"Failed to initialize Binance testnet client: {e}")
            self.client = Client("", "")
    
    def _test_connection(self):
        """Test API connection and get account info"""
        try:
            # Get account information
            account = self.client.get_account()
            logger.info(f"Connected to Binance Testnet - Account status: {account['accountType']}")
            
            # Log testnet balances
            balances = {b['asset']: b['free'] for b in account['balances'] if float(b['free']) > 0}
            if balances:
                logger.info(f"Testnet balances: {balances}")
            else:
                logger.warning("No testnet balances found - get free tokens from testnet.binance.vision")
                
        except Exception as e:
            logger.error(f"Testnet connection test failed: {e}")
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get trading rules for a symbol"""
        try:
            info = self.client.get_symbol_info(symbol)
            return {
                'min_qty': float(next(f['minQty'] for f in info['filters'] if f['filterType'] == 'LOT_SIZE')),
                'step_size': float(next(f['stepSize'] for f in info['filters'] if f['filterType'] == 'LOT_SIZE')),
                'min_notional': float(next(f['minNotional'] for f in info['filters'] if f['filterType'] == 'MIN_NOTIONAL')),
                'price_precision': info['quotePrecision'],
                'qty_precision': info['baseAssetPrecision']
            }
        except Exception as e:
            logger.error(f"Failed to get symbol info for {symbol}: {e}")
            return None
    
    def round_quantity(self, quantity: float, step_size: float) -> float:
        """Round quantity to valid step size"""
        precision = len(str(step_size).split('.')[-1])
        factor = 1 / step_size
        return float(Decimal(str(int(quantity * factor) / factor)).quantize(
            Decimal(str(step_size)), rounding=ROUND_DOWN
        ))
    
    async def place_market_buy(self, symbol: str, quote_amount: float) -> Optional[Dict]:
        """Place market buy order on testnet"""
        try:
            if not self.client.API_KEY:
                logger.warning("Cannot place orders without API credentials")
                return None
            
            # Get current price
            ticker = self.client.get_ticker(symbol=symbol)
            current_price = float(ticker['lastPrice'])
            
            # Calculate quantity
            quantity = quote_amount / current_price
            
            # Get symbol info and round quantity
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                return None
            
            quantity = self.round_quantity(quantity, symbol_info['step_size'])
            
            # Check minimum notional
            if quantity * current_price < symbol_info['min_notional']:
                logger.error(f"Order value below minimum: {quantity * current_price} < {symbol_info['min_notional']}")
                return None
            
            # Place order
            logger.info(f"Placing TESTNET BUY order: {quantity} {symbol} @ market")
            
            order = self.client.order_market_buy(
                symbol=symbol,
                quantity=quantity
            )
            
            logger.info(f"Testnet order placed: {order['orderId']} - Status: {order['status']}")
            
            # Get order details
            fills = order.get('fills', [])
            avg_price = sum(float(f['price']) * float(f['qty']) for f in fills) / sum(float(f['qty']) for f in fills) if fills else current_price
            total_commission = sum(float(f['commission']) for f in fills)
            
            return {
                'order_id': order['orderId'],
                'symbol': symbol,
                'side': 'BUY',
                'type': order['type'],
                'quantity': float(order['executedQty']),
                'avg_price': avg_price,
                'status': order['status'],
                'commission': total_commission,
                'testnet': True
            }
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error placing order: {e}")
            return None
        except Exception as e:
            logger.error(f"Error placing market buy: {e}")
            return None
    
    async def place_market_sell(self, symbol: str, quantity: float) -> Optional[Dict]:
        """Place market sell order on testnet"""
        try:
            if not self.client.API_KEY:
                logger.warning("Cannot place orders without API credentials")
                return None
            
            # Get symbol info and round quantity
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                return None
            
            quantity = self.round_quantity(quantity, symbol_info['step_size'])
            
            # Place order
            logger.info(f"Placing TESTNET SELL order: {quantity} {symbol} @ market")
            
            order = self.client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )
            
            logger.info(f"Testnet order placed: {order['orderId']} - Status: {order['status']}")
            
            # Get order details
            fills = order.get('fills', [])
            avg_price = sum(float(f['price']) * float(f['qty']) for f in fills) / sum(float(f['qty']) for f in fills) if fills else 0
            total_commission = sum(float(f['commission']) for f in fills)
            
            return {
                'order_id': order['orderId'],
                'symbol': symbol,
                'side': 'SELL',
                'type': order['type'],
                'quantity': float(order['executedQty']),
                'avg_price': avg_price,
                'status': order['status'],
                'commission': total_commission,
                'testnet': True
            }
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error placing order: {e}")
            return None
        except Exception as e:
            logger.error(f"Error placing market sell: {e}")
            return None
    
    def get_balance(self, asset: str) -> float:
        """Get testnet balance for an asset"""
        try:
            if not self.client.API_KEY:
                return 0.0
            
            balance = self.client.get_asset_balance(asset=asset)
            return float(balance['free']) if balance else 0.0
            
        except Exception as e:
            logger.error(f"Error getting balance for {asset}: {e}")
            return 0.0
    
    def get_all_balances(self) -> Dict[str, float]:
        """Get all non-zero testnet balances"""
        try:
            if not self.client.API_KEY:
                return {}
            
            account = self.client.get_account()
            return {
                b['asset']: float(b['free']) 
                for b in account['balances'] 
                if float(b['free']) > 0
            }
            
        except Exception as e:
            logger.error(f"Error getting balances: {e}")
            return {}
