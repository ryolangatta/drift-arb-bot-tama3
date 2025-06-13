"""
Advanced Filters - Sophisticated opportunity filtering based on market conditions
Filters arbitrage opportunities using multiple criteria for better trade quality
"""
import logging
import time
import statistics
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)

class FilterResult(Enum):
    """Filter result enumeration"""
    PASS = "PASS"
    FAIL_SPREAD = "FAIL_SPREAD"
    FAIL_VOLATILITY = "FAIL_VOLATILITY"
    FAIL_VOLUME = "FAIL_VOLUME"
    FAIL_MARKET_HOURS = "FAIL_MARKET_HOURS"
    FAIL_PRICE_STABILITY = "FAIL_PRICE_STABILITY"
    FAIL_BLACKLIST = "FAIL_BLACKLIST"
    FAIL_COOLDOWN = "FAIL_COOLDOWN"

class MarketState(Enum):
    """Market state enumeration"""
    NORMAL = "NORMAL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    UNSTABLE = "UNSTABLE"

class AdvancedFilters:
    def __init__(self, config: dict):
        self.config = config
        
        # Filter thresholds - research-backed values
        self.min_spread_threshold = float(config.get('MIN_SPREAD_THRESHOLD', 0.004))  # 0.4%
        self.max_spread_threshold = float(config.get('MAX_SPREAD_THRESHOLD', 0.05))   # 5% (suspicious)
        self.min_volatility = float(config.get('MIN_VOLATILITY', 0.002))             # 0.2%
        self.max_volatility = float(config.get('MAX_VOLATILITY', 0.1))               # 10%
        self.min_volume_24h = float(config.get('MIN_VOLUME_24H', 1000000))           # $1M
        self.price_stability_window = int(config.get('PRICE_STABILITY_WINDOW', 30))   # 30 seconds
        self.max_price_deviation = float(config.get('MAX_PRICE_DEVIATION', 0.02))    # 2%
        
        # Market hours filtering (UTC)
        self.market_hours_enabled = config.get('MARKET_HOURS_ENABLED', True)
        self.allowed_hours = config.get('ALLOWED_HOURS', list(range(6, 22)))  # 6 AM - 10 PM UTC
        self.blackout_hours = config.get('BLACKOUT_HOURS', [])  # Additional blackout periods
        
        # Pair management
        self.pair_blacklist = set(config.get('PAIR_BLACKLIST', []))
        self.pair_cooldowns = {}  # Track recent rejections
        self.cooldown_duration = int(config.get('COOLDOWN_DURATION', 300))  # 5 minutes
        
        # Historical data storage
        self.price_history = {}  # Store recent price data for volatility calculation
        self.volume_cache = {}   # Cache volume data
        self.filter_stats = {
            'total_opportunities': 0,
            'passed_filters': 0,
            'rejected_by_filter': {},
            'last_reset': datetime.now()
        }
        
        logger.info(f"Advanced Filters initialized - Min spread: {self.min_spread_threshold:.3%}, "
                   f"Min volatility: {self.min_volatility:.3%}, Min volume: ${self.min_volume_24h:,.0f}")
    
    def update_price_history(self, pair: str, spot_price: float, perp_price: float, timestamp: float = None):
        """Update price history for volatility calculation"""
        if timestamp is None:
            timestamp = time.time()
        
        if pair not in self.price_history:
            self.price_history[pair] = {
                'spot': [],
                'perp': [],
                'spreads': [],
                'timestamps': []
            }
        
        history = self.price_history[pair]
        
        # Calculate spread
        spread = (perp_price - spot_price) / spot_price if spot_price > 0 else 0
        
        # Add new data point
        history['spot'].append(spot_price)
        history['perp'].append(perp_price)
        history['spreads'].append(spread)
        history['timestamps'].append(timestamp)
        
        # Keep only recent data (last 10 minutes)
        cutoff_time = timestamp - 600
        while history['timestamps'] and history['timestamps'][0] < cutoff_time:
            history['spot'].pop(0)
            history['perp'].pop(0)
            history['spreads'].pop(0)
            history['timestamps'].pop(0)
    
    def calculate_volatility(self, pair: str) -> float:
        """Calculate recent price volatility using spread standard deviation"""
        if pair not in self.price_history:
            return 0.0
        
        spreads = self.price_history[pair]['spreads']
        
        if len(spreads) < 2:  # Need minimum 2 data points
            return 0.0
        
        # Calculate standard deviation of spreads
        try:
            if len(spreads) == 2:
                # For 2 points, calculate simple difference
                volatility = abs(spreads[1] - spreads[0])
            else:
                # For 3+ points, use standard deviation
                volatility = statistics.stdev(spreads)
            
            return volatility
        except (statistics.StatisticsError, ValueError, ZeroDivisionError):
            # Fallback: calculate range-based volatility
            if len(spreads) >= 2:
                return max(spreads) - min(spreads)
            return 0.0
    
    def check_price_stability(self, pair: str, current_spot: float, current_perp: float) -> bool:
        """Check if prices are stable (not erratic)"""
        if pair not in self.price_history:
            return True  # No history, assume stable
        
        history = self.price_history[pair]
        
        if len(history['spot']) < 2:
            return True  # Insufficient data
        
        # Check recent price movements
        recent_spot = history['spot'][-2:]
        recent_perp = history['perp'][-2:]
        
        # Calculate price change over stability window
        if len(recent_spot) >= 2 and recent_spot[0] > 0 and recent_perp[0] > 0:
            spot_change = abs(current_spot - recent_spot[0]) / recent_spot[0]
            perp_change = abs(current_perp - recent_perp[0]) / recent_perp[0]
            
            # Check if changes are within acceptable range
            stable = spot_change <= self.max_price_deviation and perp_change <= self.max_price_deviation
            
            if not stable:
                logger.debug(f"Price instability detected for {pair}: "
                            f"Spot change: {spot_change:.3%}, Perp change: {perp_change:.3%}")
            
            return stable
        
        return True  # Default to stable if calculation fails
    
    def check_market_hours(self) -> bool:
        """Check if current time is within allowed trading hours"""
        if not self.market_hours_enabled:
            return True
        
        current_hour = datetime.utcnow().hour
        
        # Check allowed hours
        if current_hour not in self.allowed_hours:
            return False
        
        # Check blackout periods
        if current_hour in self.blackout_hours:
            return False
        
        return True
    
    def check_volume_requirements(self, pair: str, volume_24h: Optional[float] = None) -> bool:
        """Check if pair meets minimum volume requirements"""
        if volume_24h is None:
            # Try to get from cache or use default
            volume_24h = self.volume_cache.get(pair, self.min_volume_24h)
        
        # Update cache
        self.volume_cache[pair] = volume_24h
        
        meets_requirement = volume_24h >= self.min_volume_24h
        
        if not meets_requirement:
            logger.debug(f"Volume too low for {pair}: ${volume_24h:,.0f} < ${self.min_volume_24h:,.0f}")
        
        return meets_requirement
    
    def check_spread_validity(self, spread: float) -> bool:
        """Check if spread is within valid range"""
        if spread < self.min_spread_threshold:
            logger.debug(f"Spread too low: {spread:.3%} < {self.min_spread_threshold:.3%}")
            return False
        
        if spread > self.max_spread_threshold:
            logger.warning(f"Spread suspiciously high: {spread:.3%} > {self.max_spread_threshold:.3%}")
            return False
        
        return True
    
    def check_pair_cooldown(self, pair: str) -> bool:
        """Check if pair is in cooldown period"""
        if pair not in self.pair_cooldowns:
            return True
        
        cooldown_end = self.pair_cooldowns[pair]
        current_time = time.time()
        
        if current_time >= cooldown_end:
            # Cooldown expired, remove it
            del self.pair_cooldowns[pair]
            return True
        
        remaining = cooldown_end - current_time
        logger.debug(f"Pair {pair} in cooldown for {remaining:.0f}s")
        return False
    
    def add_pair_cooldown(self, pair: str, reason: str):
        """Add pair to cooldown list"""
        cooldown_end = time.time() + self.cooldown_duration
        self.pair_cooldowns[pair] = cooldown_end
        logger.info(f"Added {pair} to cooldown for {self.cooldown_duration}s - Reason: {reason}")
    
    def get_market_state(self, pair: str) -> MarketState:
        """Assess current market state for the pair"""
        volatility = self.calculate_volatility(pair)
        volume_24h = self.volume_cache.get(pair, 0)
        
        # Determine market state
        if volatility > 0.05:  # 5%
            return MarketState.HIGH_VOLATILITY
        elif volume_24h < self.min_volume_24h * 0.5:  # Half minimum volume
            return MarketState.LOW_LIQUIDITY
        elif not self.check_price_stability(pair, 0, 0):  # Dummy prices for stability check
            return MarketState.UNSTABLE
        else:
            return MarketState.NORMAL
    
    def apply_filters(self, 
                     opportunity: Dict,
                     spot_price: float,
                     perp_price: float,
                     volume_24h: Optional[float] = None) -> Tuple[bool, FilterResult, str]:
        """
        Apply all filters to an arbitrage opportunity
        Returns: (passed: bool, result: FilterResult, reason: str)
        """
        pair = opportunity['pair']
        spread = opportunity['spread']
        
        self.filter_stats['total_opportunities'] += 1
        
        # Update price history for this opportunity
        self.update_price_history(pair, spot_price, perp_price)
        
        # Filter 1: Pair blacklist check
        if pair in self.pair_blacklist:
            reason = f"Pair {pair} is blacklisted"
            self._record_rejection(FilterResult.FAIL_BLACKLIST, reason)
            return False, FilterResult.FAIL_BLACKLIST, reason
        
        # Filter 2: Cooldown check
        if not self.check_pair_cooldown(pair):
            reason = f"Pair {pair} is in cooldown period"
            self._record_rejection(FilterResult.FAIL_COOLDOWN, reason)
            return False, FilterResult.FAIL_COOLDOWN, reason
        
        # Filter 3: Spread validity
        if not self.check_spread_validity(spread):
            reason = f"Spread {spread:.3%} outside valid range [{self.min_spread_threshold:.3%}, {self.max_spread_threshold:.3%}]"
            self._record_rejection(FilterResult.FAIL_SPREAD, reason)
            self.add_pair_cooldown(pair, "Invalid spread")
            return False, FilterResult.FAIL_SPREAD, reason
        
        # Filter 4: Market hours
        if not self.check_market_hours():
            current_hour = datetime.utcnow().hour
            reason = f"Outside trading hours: {current_hour}:00 UTC"
            self._record_rejection(FilterResult.FAIL_MARKET_HOURS, reason)
            return False, FilterResult.FAIL_MARKET_HOURS, reason
        
        # Filter 5: Volume requirements
        if not self.check_volume_requirements(pair, volume_24h):
            vol = volume_24h or 0
            reason = f"Volume too low: ${vol:,.0f} < ${self.min_volume_24h:,.0f}"
            self._record_rejection(FilterResult.FAIL_VOLUME, reason)
            self.add_pair_cooldown(pair, "Low volume")
            return False, FilterResult.FAIL_VOLUME, reason
        
        # Filter 6: Volatility check
        volatility = self.calculate_volatility(pair)
        if volatility < self.min_volatility:
            reason = f"Volatility too low: {volatility:.3%} < {self.min_volatility:.3%}"
            self._record_rejection(FilterResult.FAIL_VOLATILITY, reason)
            return False, FilterResult.FAIL_VOLATILITY, reason
        
        if volatility > self.max_volatility:
            reason = f"Volatility too high: {volatility:.3%} > {self.max_volatility:.3%}"
            self._record_rejection(FilterResult.FAIL_VOLATILITY, reason)
            self.add_pair_cooldown(pair, "High volatility")
            return False, FilterResult.FAIL_VOLATILITY, reason
        
        # Filter 7: Price stability
        if not self.check_price_stability(pair, spot_price, perp_price):
            reason = f"Price instability detected for {pair}"
            self._record_rejection(FilterResult.FAIL_PRICE_STABILITY, reason)
            return False, FilterResult.FAIL_PRICE_STABILITY, reason
        
        # All filters passed!
        self.filter_stats['passed_filters'] += 1
        
        # Add market state info to opportunity
        market_state = self.get_market_state(pair)
        opportunity['market_state'] = market_state.value
        opportunity['volatility'] = volatility
        opportunity['volume_24h'] = volume_24h or 0
        
        logger.info(f"✅ Opportunity passed all filters: {pair} - "
                   f"Spread: {spread:.3%}, Volatility: {volatility:.3%}, State: {market_state.value}")
        
        return True, FilterResult.PASS, "All filters passed"
    
    def _record_rejection(self, filter_result: FilterResult, reason: str):
        """Record filter rejection for statistics"""
        filter_name = filter_result.value
        if filter_name not in self.filter_stats['rejected_by_filter']:
            self.filter_stats['rejected_by_filter'][filter_name] = 0
        self.filter_stats['rejected_by_filter'][filter_name] += 1
        
        logger.debug(f"Filter rejection: {reason}")
    
    def get_filter_statistics(self) -> Dict:
        """Get comprehensive filter statistics"""
        total = self.filter_stats['total_opportunities']
        passed = self.filter_stats['passed_filters']
        rejection_rate = (total - passed) / total if total > 0 else 0
        
        stats = {
            'total_opportunities_analyzed': total,
            'opportunities_passed': passed,
            'opportunities_rejected': total - passed,
            'pass_rate': passed / total if total > 0 else 0,
            'rejection_rate': rejection_rate,
            'rejections_by_filter': self.filter_stats['rejected_by_filter'].copy(),
            'active_cooldowns': len(self.pair_cooldowns),
            'pairs_in_cooldown': list(self.pair_cooldowns.keys()),
            'blacklisted_pairs': list(self.pair_blacklist),
            'market_hours_enabled': self.market_hours_enabled,
            'current_utc_hour': datetime.utcnow().hour,
            'statistics_since': self.filter_stats['last_reset'].isoformat(),
            'filter_config': {
                'min_spread_threshold': self.min_spread_threshold,
                'max_spread_threshold': self.max_spread_threshold,
                'min_volatility': self.min_volatility,
                'max_volatility': self.max_volatility,
                'min_volume_24h': self.min_volume_24h,
                'cooldown_duration': self.cooldown_duration
            }
        }
        
        return stats
    
    def reset_statistics(self):
        """Reset filter statistics"""
        self.filter_stats = {
            'total_opportunities': 0,
            'passed_filters': 0,
            'rejected_by_filter': {},
            'last_reset': datetime.now()
        }
        logger.info("Filter statistics reset")
    
    def update_config(self, new_config: Dict):
        """Update filter configuration dynamically"""
        old_config = {
            'min_spread_threshold': self.min_spread_threshold,
            'min_volatility': self.min_volatility,
            'min_volume_24h': self.min_volume_24h
        }
        
        # Update thresholds
        if 'MIN_SPREAD_THRESHOLD' in new_config:
            self.min_spread_threshold = float(new_config['MIN_SPREAD_THRESHOLD'])
        if 'MIN_VOLATILITY' in new_config:
            self.min_volatility = float(new_config['MIN_VOLATILITY'])
        if 'MIN_VOLUME_24H' in new_config:
            self.min_volume_24h = float(new_config['MIN_VOLUME_24H'])
        
        # Log changes
        changes = []
        for key, old_value in old_config.items():
            new_value = getattr(self, key)
            if old_value != new_value:
                changes.append(f"{key}: {old_value} → {new_value}")
        
        if changes:
            logger.info(f"Filter config updated: {', '.join(changes)}")
        else:
            logger.info("No filter config changes applied")
    
    def add_to_blacklist(self, pair: str, reason: str = "Manual"):
        """Add pair to blacklist"""
        self.pair_blacklist.add(pair)
        logger.warning(f"Added {pair} to blacklist - Reason: {reason}")
    
    def remove_from_blacklist(self, pair: str):
        """Remove pair from blacklist"""
        if pair in self.pair_blacklist:
            self.pair_blacklist.remove(pair)
            logger.info(f"Removed {pair} from blacklist")
    
    def clear_cooldowns(self):
        """Clear all pair cooldowns"""
        cleared_pairs = list(self.pair_cooldowns.keys())
        self.pair_cooldowns.clear()
        logger.info(f"Cleared cooldowns for {len(cleared_pairs)} pairs: {cleared_pairs}")
    
    def get_active_pairs(self) -> List[str]:
        """Get list of pairs that can currently be traded (not blacklisted or in cooldown)"""
        current_time = time.time()
        active_pairs = []
        
        for pair in self.price_history.keys():
            if pair in self.pair_blacklist:
                continue
            if pair in self.pair_cooldowns and current_time < self.pair_cooldowns[pair]:
                continue
            active_pairs.append(pair)
        
        return active_pairs
