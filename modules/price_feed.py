"""
Price feed module for fetching prices from Binance and Drift
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

logger = logging.getLogger(__name__)

class PriceFeed:
    def __init__(self, config: dict):
        self.config = config
        self.binance_client = None
        self.last_prices = {}
        self.price_history = {}
        
        # Initialize Binance client (public endpoints don't need API keys)
        try:
            self.binance_client = Client("", "")  # Empty keys for public data
            logger.info("Binance client initialized for public data")
        except Exception as e:
            logger.error(f"Failed to initialize Binance client: {e}")
    
    async def get_binance_price(self, symbol: str) -> Optional[float]:
        """Fetch spot price from Binance"""
        try:
            # Convert symbol format (SOL/USDC -> SOLUSDT for Binance)
            # Note: Binance mainly uses USDT pairs
            if "USDC" in symbol:
                binance_symbol = symbol.replace("/", "").replace("/", "")
            else:
                binance_symbol = symbol.replace("/", "")
            
            # Get ticker price
            ticker = self.binance_client.get_ticker(symbol=binance_symbol)
            price = float(ticker['lastPrice'])
            
            # Store price
            self.last_prices[f"binance_{symbol}"] = {
                'price': price,
                'timestamp': datetime.now(),
                'bid': float(ticker['bidPrice']),
                'ask': float(ticker['askPrice'])
            }
            
            logger.debug(f"Binance {symbol}: ${price:.4f}")
            return price
            
        except BinanceAPIException as e:
            logger.error(f"Binance API error for {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching Binance price for {symbol}: {e}")
            return None
    
    async def get_drift_price(self, symbol: str) -> Optional[float]:
        """Fetch perpetual price from Drift"""
        try:
            # For now, simulate Drift prices (since Drift integration is complex)
            # In production, this would connect to Drift's Solana program
            
            # Simulate with a small spread from Binance price
            base_symbol = symbol.replace("-PERP", "/USDC")
            binance_price = await self.get_binance_price(base_symbol)
            
            if binance_price:
                # Simulate Drift price with random spread (0.1% to 0.5%)
                import random
                spread_percent = random.uniform(0.001, 0.005)
                drift_price = binance_price * (1 + spread_percent)
                
                self.last_prices[f"drift_{symbol}"] = {
                    'price': drift_price,
                    'timestamp': datetime.now(),
                    'simulated': True
                }
                
                logger.debug(f"Drift {symbol}: ${drift_price:.4f} (simulated)")
                return drift_price
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching Drift price for {symbol}: {e}")
            return None
    
    async def get_prices_for_pair(self, pair: str) -> Tuple[Optional[float], Optional[float]]:
        """Get both Binance spot and Drift perp prices for a pair"""
        try:
            # Pair format: "SOL/USDC"
            spot_task = self.get_binance_price(pair)
            perp_symbol = pair.split("/")[0] + "-PERP"
            perp_task = self.get_drift_price(perp_symbol)
            
            spot_price, perp_price = await asyncio.gather(spot_task, perp_task)
            
            return spot_price, perp_price
            
        except Exception as e:
            logger.error(f"Error fetching prices for {pair}: {e}")
            return None, None
    
    def get_last_price(self, exchange: str, symbol: str) -> Optional[dict]:
        """Get last cached price for a symbol"""
        key = f"{exchange}_{symbol}"
        return self.last_prices.get(key)
    
    async def start_price_monitoring(self, pairs: list, callback=None):
        """Start monitoring prices for multiple pairs"""
        logger.info(f"Starting price monitoring for pairs: {pairs}")
        
        while True:
            try:
                for pair in pairs:
                    spot_price, perp_price = await self.get_prices_for_pair(pair)
                    
                    if spot_price and perp_price and callback:
                        await callback(pair, spot_price, perp_price)
                
                # Wait before next price check
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in price monitoring: {e}")
                await asyncio.sleep(10)  # Wait longer on error
