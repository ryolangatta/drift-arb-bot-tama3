"""
Simple Binance Testnet connection for real orders
"""
import os
import logging
from binance.client import Client
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)

class BinanceTestnetSimple:
    def __init__(self):
        self.client = None
        self.connected = False
        self._connect()
    
    def _connect(self):
        """Connect to Binance Testnet"""
        api_key = os.getenv('BINANCE_TESTNET_API_KEY', '')
        api_secret = os.getenv('BINANCE_TESTNET_SECRET', '')
        
        if api_key and api_secret:
            try:
                self.client = Client(api_key, api_secret, testnet=True)
                self.client.API_URL = "https://testnet.binance.vision/api"
                
                # Test connection
                account = self.client.get_account()
                self.connected = True
                
                # Show balances
                balances = {b['asset']: float(b['free']) for b in account['balances'] if float(b['free']) > 0}
                logger.info(f"Connected to Binance Testnet! Balances: {balances}")
                
            except Exception as e:
                logger.error(f"Cannot connect to Binance Testnet: {e}")
                logger.info("Get API keys from: https://testnet.binance.vision")
        else:
            logger.warning("No Binance Testnet credentials found")
    
    def place_test_order(self, symbol, side, quantity):
        """Place a REAL order on testnet"""
        if not self.connected:
            logger.error("Not connected to Binance Testnet")
            return None
        
        try:
            # Round quantity properly
            qty = float(Decimal(str(quantity)).quantize(Decimal('0.01'), rounding=ROUND_DOWN))
            
            logger.info(f"Placing REAL TESTNET order: {side} {qty} {symbol}")
            
            if side == "BUY":
                order = self.client.order_market_buy(symbol=symbol, quantity=qty)
            else:
                order = self.client.order_market_sell(symbol=symbol, quantity=qty)
            
            logger.info(f"✅ TESTNET ORDER PLACED! Order ID: {order['orderId']}")
            return order
            
        except Exception as e:
            logger.error(f"Failed to place testnet order: {e}")
            return None
    
    def sell_sol_for_usdt_once(self):
        """One-time function to sell 2 SOL for USDT to fund arbitrage trading"""
        if not self.connected:
            logger.error("Not connected to Binance Testnet")
            return False
        
        try:
            # Check current SOL balance first
            sol_balance = float(self.client.get_asset_balance(asset='SOL')['free'])
            logger.info(f"Current SOL balance: {sol_balance}")
            
            if sol_balance < 2.0:
                logger.warning(f"Insufficient SOL balance: {sol_balance} < 2.0")
                return False
            
            # Sell 2 SOL for USDT (SOLUSDT pair exists on testnet)
            logger.info("💰 Selling 2 SOL for USDT to fund arbitrage trading...")
            order = self.client.order_market_sell(symbol='SOLUSDT', quantity=2.0)
            
            # Check the result
            executed_qty = float(order['executedQty'])
            logger.info(f"✅ SOLD {executed_qty} SOL FOR USDT!")
            logger.info(f"Order ID: {order['orderId']} - Status: {order['status']}")
            
            # Check new USDT balance
            usdt_balance = float(self.client.get_asset_balance(asset='USDT')['free'])
            logger.info(f"New USDT balance: {usdt_balance}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to sell SOL for USDT: {e}")
            return False