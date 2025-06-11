"""
Fixed price feed module with proper symbol handling and validation
"""
import os
import logging
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
import aiohttp
import json
import random

logger = logging.getLogger(__name__)

class PriceFeed:
    def __init__(self, config: dict):
        self.config = config
        self.binance_client = None
        self.last_prices = {}
        self.price_history = {}
        self.available_symbols = set()
        
        # Initialize Binance client (public endpoints don't need API keys)
        self._init_binance_client()
    
    def _init_binance_client(self):
        """Initialize Binance client with proper error handling"""
        try:
            # Use testnet for consistency with trading module
            self.binance_client = Client("", "", testnet=True)
            logger.info("✅ Binance price feed client initialized")
            
            # Load available symbols
            self._load_available_symbols()
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Binance client: {e}")
    
    def _load_available_symbols(self):
        """Load available symbols for validation"""
        try:
            exchange_info = self.binance_client.get_exchange_info()
            self.available_symbols = {
                symbol['symbol'] for symbol in exchange_info['symbols']
                if symbol['status'] == 'TRADING'
            }
            logger.info(f"📊 Price feed loaded {len(self.available_symbols)} symbols")
            
        except Exception as e:
            logger.error(f"❌ Failed to load symbols for price feed: {e}")
            # Fallback symbols
            self.available_symbols = {'BTCUSDT', 'ETHUSDT', 'BNBUSDT'}
    
    def get_valid_binance_symbol(self, pair: str) -> Optional[str]:
        """Convert trading pair to valid Binance symbol"""
        # Handle different pair formats
        if "/" in pair:
            base, quote = pair.split("/")
        else:
            # Assume it's already in Binance format
            return pair if pair in self.available_symbols else None
        
        # Try different combinations
        symbol_attempts = [
            f"{base}{quote}",  # SOLUSDC
            f"{base}USDT",     # SOLUSDT (most common)
            f"{base}BUSD",     # SOLBUSD
            f"{base}BTC",      # SOLBTC
            f"{base}ETH"       # SOLETH
        ]
        
        for symbol in symbol_attempts:
            if symbol in self.available_symbols:
                logger.debug(f"✅ Found valid Binance symbol: {symbol} for pair {pair}")
                return symbol
        
        logger.warning(f"⚠️ No valid Binance symbol found for pair {pair}")
        return None
    
    async def get_binance_price(self, symbol: str) -> Optional[float]:
        """Fetch spot price from Binance with validation"""
        try:
            # Convert to valid Binance symbol
            binance_symbol = self.get_valid_binance_symbol(symbol)
            if not binance_symbol:
                logger.error(f"❌ Cannot find valid Binance symbol for {symbol}")
                return None
            
            # Get ticker price
            ticker = self.binance_client.get_ticker(symbol=binance_symbol)
            price = float(ticker['lastPrice'])
            
            # Store price with metadata
            self.last_prices[f"binance_{symbol}"] = {
                'price': price,
                'symbol_used': binance_symbol,
                'timestamp': datetime.now(),
                'bid': float(ticker['bidPrice']),
                'ask': float(ticker['askPrice']),
                'volume': float(ticker['volume'])
            }
            
            logger.debug(f"📈 Binance {symbol} ({binance_symbol}): ${price:.4f}")
            return price
            
        except BinanceAPIException as e:
            logger.error(f"❌ Binance API error for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching Binance price for {symbol}: {e}")
            return None
    
    async def get_drift_price(self, symbol: str) -> Optional[float]:
        """Fetch perpetual price from Drift (enhanced simulation)"""
        try:
            # For now, simulate Drift prices with more realistic spreads
            # In production, this would connect to Drift's Solana program
            
            # Get the base pair for reference
            base_symbol = symbol.replace("-PERP", "/USDC")
            binance_price = await self.get_binance_price(base_symbol)
            
            if binance_price is None:
                logger.error(f"❌ Could not get reference price for {base_symbol}")
                return None
            
            # Simulate more realistic Drift pricing
            # Real perpetual futures often trade at premium/discount to spot
            
            # Add market sentiment simulation
            market_hour = datetime.now().hour
            if 14 <= market_hour <= 16:  # US market hours - higher activity
                spread_range = (0.0001, 0.004)  # 0.01% to 0.4%
            elif 22 <= market_hour or market_hour <= 2:  # Low activity
                spread_range = (0.0005, 0.008)  # 0.05% to 0.8%
            else:
                spread_range = (0.0002, 0.006)  # 0.02% to 0.6%
            
            # Random spread with bias toward premium (perpetuals often trade higher)
            if random.random() < 0.6:  # 60% chance of premium
                spread_percent = random.uniform(spread_range[0], spread_range[1])
            else:  # 40% chance of discount
                spread_percent = -random.uniform(spread_range[0], spread_range[1] * 0.5)
            
            drift_price = binance_price * (1 + spread_percent)
            
            # Store price with simulation metadata
            self.last_prices[f"drift_{symbol}"] = {
                'price': drift_price,
                'reference_price': binance_price,
                'spread_percent': spread_percent,
                'timestamp': datetime.now(),
                'simulated': True,
                'market_hour': market_hour
            }
            
            logger.debug(f"📊 Drift {symbol}: ${drift_price:.4f} (spread: {spread_percent:.4%})")
            return drift_price
            
        except Exception as e:
            logger.error(f"❌ Error fetching Drift price for {symbol}: {e}")
            return None
    
    async def get_prices_for_pair(self, pair: str) -> Tuple[Optional[float], Optional[float]]:
        """Get both Binance spot and Drift perp prices for a pair"""
        try:
            # Convert pair format: "SOL/USDC" -> spot and perp symbols
            base_asset = pair.split("/")[0] if "/" in pair else pair[:3]
            
            # Get spot price from Binance
            spot_task = self.get_binance_price(pair)
            
            # Get perp price from Drift (simulated)
            perp_symbol = f"{base_asset}-PERP"
            perp_task = self.get_drift_price(perp_symbol)
            
            # Execute both requests concurrently
            spot_price, perp_price = await asyncio.gather(
                spot_task, perp_task, return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(spot_price, Exception):
                logger.error(f"❌ Spot price error: {spot_price}")
                spot_price = None
            
            if isinstance(perp_price, Exception):
                logger.error(f"❌ Perp price error: {perp_price}")
                perp_price = None
            
            return spot_price, perp_price
            
        except Exception as e:
            logger.error(f"❌ Error fetching prices for {pair}: {e}")
            return None, None
    
    def get_last_price(self, exchange: str, symbol: str) -> Optional[dict]:
        """Get last cached price for a symbol"""
        key = f"{exchange}_{symbol}"
        return self.last_prices.get(key)
    
    def get_price_history(self, exchange: str, symbol: str, minutes: int = 60) -> list:
        """Get price history for analysis"""
        key = f"{exchange}_{symbol}"
        if key not in self.price_history:
            return []
        
        cutoff_time = datetime.now().timestamp() - (minutes * 60)
        return [
            entry for entry in self.price_history[key]
            if entry['timestamp'].timestamp() > cutoff_time
        ]
    
    def _store_price_history(self, exchange: str, symbol: str, price: float):
        """Store price for historical analysis"""
        key = f"{exchange}_{symbol}"
        if key not in self.price_history:
            self.price_history[key] = []
        
        self.price_history[key].append({
            'price': price,
            'timestamp': datetime.now()
        })
        
        # Keep only last 1000 entries per symbol
        if len(self.price_history[key]) > 1000:
            self.price_history[key] = self.price_history[key][-1000:]
    
    async def start_price_monitoring(self, pairs: list, callback=None):
        """Start monitoring prices for multiple pairs with enhanced error handling"""
        logger.info(f"🚀 Starting price monitoring for pairs: {pairs}")
        
        error_count = 0
        max_errors = 10
        
        while error_count < max_errors:
            try:
                for pair in pairs:
                    try:
                        spot_price, perp_price = await self.get_prices_for_pair(pair)
                        
                        if spot_price and perp_price:
                            # Store in history
                            self._store_price_history("binance", pair, spot_price)
                            self._store_price_history("drift", f"{pair.split('/')[0]}-PERP", perp_price)
                            
                            # Call callback if provided
                            if callback:
                                await callback(pair, spot_price, perp_price)
                            
                            # Reset error count on success
                            error_count = 0
                        else:
                            logger.warning(f"⚠️ Failed to get prices for {pair}")
                            error_count += 1
                    
                    except Exception as e:
                        logger.error(f"❌ Error processing pair {pair}: {e}")
                        error_count += 1
                
                # Wait before next price check (5 seconds)
                await asyncio.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("🛑 Price monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Critical error in price monitoring: {e}")
                error_count += 1
                await asyncio.sleep(10)  # Wait longer on critical error
        
        if error_count >= max_errors:
            logger.error(f"💥 Too many errors ({max_errors}), stopping price monitoring")
            raise Exception("Price monitoring failed with too many errors")