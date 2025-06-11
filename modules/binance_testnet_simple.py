"""
Complete Binance Testnet connection with all required methods
"""
import os
import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException
from decimal import Decimal, ROUND_DOWN
import time

logger = logging.getLogger(__name__)

class BinanceTestnetSimple:
    def __init__(self):
        self.client = None
        self.connected = False
        self.available_symbols = set()
        self._connect()
    
    def _connect(self):
        """Connect to Binance Testnet with improved error handling"""
        api_key = os.getenv('BINANCE_TESTNET_API_KEY', '')
        api_secret = os.getenv('BINANCE_TESTNET_SECRET', '')
        
        try:
            if api_key and api_secret:
                # Initialize with credentials for trading
                self.client = Client(api_key, api_secret, testnet=True)
                logger.info("Binance testnet client initialized with trading credentials")
                
                # Test connection and get account info
                account = self.client.get_account()
                self.connected = True
                
                # Show balances
                balances = {b['asset']: float(b['free']) for b in account['balances'] if float(b['free']) > 0}
                logger.info(f"Connected to Binance Testnet! Balances: {balances}")
                
            else:
                # Use public client for price data only
                self.client = Client("", "", testnet=True)
                self.connected = False
                logger.warning("⚠️ No Binance testnet credentials - using public access only")
            
            # Load available symbols for validation
            self._load_available_symbols()
            
        except Exception as e:
            logger.error(f"❌ Cannot connect to Binance Testnet: {e}")
            logger.info("💡 Get free testnet API keys from: https://testnet.binance.vision")
            # Fallback to public client
            try:
                self.client = Client("", "", testnet=True)
                self._load_available_symbols()
            except Exception as e2:
                logger.error(f"❌ Even public access failed: {e2}")
    
    def _load_available_symbols(self):
        """Load and cache available trading symbols"""
        try:
            exchange_info = self.client.get_exchange_info()
            self.available_symbols = {
                symbol['symbol'] for symbol in exchange_info['symbols']
                if symbol['status'] == 'TRADING'
            }
            logger.info(f"📊 Loaded {len(self.available_symbols)} available symbols")
            
            # Log some common symbols for debugging
            common_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'BNBUSDT']
            available_common = [s for s in common_symbols if s in self.available_symbols]
            logger.info(f"🔍 Common symbols available: {available_common}")
            
        except Exception as e:
            logger.error(f"❌ Failed to load symbols: {e}")
            # Fallback with common symbols
            self.available_symbols = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT'}
    
    def is_symbol_available(self, symbol: str) -> bool:
        """Check if a symbol is available for trading"""
        return symbol.upper() in self.available_symbols
    
    def get_alternative_symbol(self, base_asset: str) -> str:
        """Get alternative symbol if primary not available"""
        # Try different quote currencies
        alternatives = [
            f"{base_asset}USDT",
            f"{base_asset}BUSD", 
            f"{base_asset}BTC",
            f"{base_asset}ETH"
        ]
        
        for alt in alternatives:
            if self.is_symbol_available(alt):
                logger.info(f"🔄 Using alternative symbol: {alt}")
                return alt
        
        logger.warning(f"⚠️ No alternatives found for {base_asset}")
        return f"{base_asset}USDT"  # Return default
    
    def get_symbol_info(self, symbol: str):
        """Get trading rules for a symbol with validation"""
        try:
            if not self.is_symbol_available(symbol):
                logger.error(f"❌ Symbol {symbol} not available on testnet")
                return None
            
            exchange_info = self.client.get_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    # Extract trading rules
                    lot_size_filter = next((f for f in s['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                    price_filter = next((f for f in s['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
                    notional_filter = next((f for f in s['filters'] if f['filterType'] == 'NOTIONAL'), None)
                    
                    return {
                        'symbol': symbol,
                        'status': s['status'],
                        'baseAsset': s['baseAsset'],
                        'quoteAsset': s['quoteAsset'],
                        'minQty': float(lot_size_filter['minQty']) if lot_size_filter else 0.001,
                        'stepSize': float(lot_size_filter['stepSize']) if lot_size_filter else 0.001,
                        'minPrice': float(price_filter['minPrice']) if price_filter else 0.01,
                        'tickSize': float(price_filter['tickSize']) if price_filter else 0.01,
                        'minNotional': float(notional_filter['minNotional']) if notional_filter else 10.0,
                        'baseAssetPrecision': s['baseAssetPrecision'],
                        'quoteAssetPrecision': s['quotePrecision']
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting symbol info for {symbol}: {e}")
            return None
    
    def round_quantity(self, quantity: float, step_size: float) -> float:
        """Round quantity to valid step size"""
        if step_size == 0:
            return quantity
        
        precision = max(0, len(str(step_size).split('.')[-1]))
        factor = 1 / step_size
        rounded = float(Decimal(str(int(quantity * factor) / factor)).quantize(
            Decimal(str(step_size)), rounding=ROUND_DOWN
        ))
        return rounded
    
    def place_test_order(self, symbol: str, side: str, quantity: float):
        """Place a REAL order on testnet with proper validation"""
        if not self.connected:
            logger.error("❌ Not connected to Binance Testnet with trading credentials")
            return None
        
        try:
            # Validate symbol first
            if not self.is_symbol_available(symbol):
                logger.error(f"❌ Symbol {symbol} not available. Checking alternatives...")
                
                # Try to get base asset and find alternative
                if symbol.endswith('USDT'):
                    base_asset = symbol[:-4]  # Remove USDT
                elif symbol.endswith('USDC'):
                    base_asset = symbol[:-4]  # Remove USDC
                else:
                    base_asset = symbol[:3]  # Assume 3-letter base
                
                alternative = self.get_alternative_symbol(base_asset)
                if not self.is_symbol_available(alternative):
                    logger.error(f"❌ No valid symbols found for {base_asset}")
                    return None
                
                symbol = alternative
                logger.info(f"✅ Using symbol: {symbol}")
            
            # Get symbol info and validate
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                logger.error(f"❌ Could not get symbol info for {symbol}")
                return None
            
            # Round quantity properly
            rounded_qty = self.round_quantity(quantity, symbol_info['stepSize'])
            
            # Check minimum quantity
            if rounded_qty < symbol_info['minQty']:
                logger.error(f"❌ Quantity {rounded_qty} below minimum {symbol_info['minQty']}")
                return None
            
            # Get current price for notional check
            ticker = self.client.get_ticker(symbol=symbol)
            current_price = float(ticker['lastPrice'])
            notional_value = rounded_qty * current_price
            
            # Check minimum notional
            if notional_value < symbol_info['minNotional']:
                logger.error(f"❌ Order value ${notional_value:.2f} below minimum ${symbol_info['minNotional']}")
                return None
            
            logger.info(f"🔄 Placing REAL TESTNET order: {side} {rounded_qty} {symbol} @ ${current_price:.4f}")
            
            # Place the order
            if side.upper() == "BUY":
                order = self.client.order_market_buy(symbol=symbol, quantity=rounded_qty)
            else:
                order = self.client.order_market_sell(symbol=symbol, quantity=rounded_qty)
            
            logger.info(f"✅ TESTNET ORDER PLACED! Order ID: {order['orderId']}, Status: {order['status']}")
            
            return {
                'orderId': order['orderId'],
                'symbol': symbol,
                'side': side,
                'type': order['type'],
                'quantity': float(order['executedQty']),
                'status': order['status'],
                'fills': order.get('fills', []),
                'testnet': True,
                'timestamp': time.time()
            }
            
        except BinanceAPIException as e:
            logger.error(f"❌ Binance API error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to place testnet order: {e}")
            return None
    
    def get_balance(self, asset: str) -> float:
        """Get testnet balance for an asset"""
        try:
            if not self.connected:
                return 0.0
            
            balance = self.client.get_asset_balance(asset=asset)
            return float(balance['free']) if balance else 0.0
            
        except Exception as e:
            logger.error(f"❌ Error getting balance for {asset}: {e}")
            return 0.0
    
    def get_all_balances(self):
        """Get all non-zero testnet balances"""
        try:
            if not self.connected:
                return {}
            
            account = self.client.get_account()
            balances = {}
            for b in account['balances']:
                free_balance = float(b['free'])
                if free_balance > 0:
                    balances[b['asset']] = free_balance
            
            return balances
            
        except Exception as e:
            logger.error(f"❌ Error getting balances: {e}")
            return {}