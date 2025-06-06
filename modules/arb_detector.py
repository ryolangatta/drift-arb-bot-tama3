"""
Arbitrage detection module
"""
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class ArbitrageDetector:
    def __init__(self, config: dict):
        self.config = config
        self.trading_config = config.get('TRADING_CONFIG', {})
        self.spread_threshold = self.trading_config.get('SPREAD_THRESHOLD', 0.007)
        self.min_profit_after_fees = self.trading_config.get('MIN_PROFIT_AFTER_FEES', 0.003)
        self.opportunities = []
        
    def calculate_spread(self, spot_price: float, perp_price: float) -> float:
        """Calculate spread percentage between spot and perp"""
        if spot_price <= 0:
            return 0
        return (perp_price - spot_price) / spot_price
    
    def calculate_profit_after_fees(self, spread: float) -> float:
        """Calculate potential profit after fees"""
        # Fee structure (from config or defaults)
        binance_fee = 0.001  # 0.1%
        drift_taker_fee = 0.0005  # 0.05%
        total_fees = binance_fee + drift_taker_fee
        
        return spread - total_fees
    
    def check_arbitrage_opportunity(
        self, 
        pair: str, 
        spot_price: float, 
        perp_price: float
    ) -> Optional[Dict]:
        """Check if there's an arbitrage opportunity"""
        try:
            spread = self.calculate_spread(spot_price, perp_price)
            profit_after_fees = self.calculate_profit_after_fees(spread)
            
            # Log current spread
            logger.debug(
                f"{pair} - Spot: ${spot_price:.4f}, Perp: ${perp_price:.4f}, "
                f"Spread: {spread:.4%}, Profit: {profit_after_fees:.4%}"
            )
            
            # Check if opportunity exists
            if spread >= self.spread_threshold and profit_after_fees >= self.min_profit_after_fees:
                opportunity = {
                    'timestamp': datetime.now(),
                    'pair': pair,
                    'spot_price': spot_price,
                    'perp_price': perp_price,
                    'spread': spread,
                    'profit_after_fees': profit_after_fees,
                    'trade_size': self.trading_config.get('TRADE_SIZE_USDC', 100),
                    'potential_profit_usdc': profit_after_fees * self.trading_config.get('TRADE_SIZE_USDC', 100)
                }
                
                self.opportunities.append(opportunity)
                logger.info(
                    f"�� ARBITRAGE OPPORTUNITY: {pair} - Spread: {spread:.4%}, "
                    f"Profit: ${opportunity['potential_profit_usdc']:.2f}"
                )
                
                return opportunity
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking arbitrage for {pair}: {e}")
            return None
    
    def get_recent_opportunities(self, minutes: int = 60) -> list:
        """Get opportunities from the last N minutes"""
        cutoff_time = datetime.now().timestamp() - (minutes * 60)
        recent = [
            opp for opp in self.opportunities 
            if opp['timestamp'].timestamp() > cutoff_time
        ]
        return recent
