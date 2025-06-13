"""
Simplified Balance Manager - Following Drift Protocol Best Practices
Based on research of successful arbitrage bots and Drift's official patterns
"""
import logging
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class BalanceManager:
    def __init__(self, config: dict):
        self.config = config
        self.trading_config = config.get('TRADING_CONFIG', {})
        
        # Core settings
        self.base_trade_size = self.trading_config.get('TRADE_SIZE_USDC', 100)
        self.max_concurrent_trades = 3  # Industry standard
        self.safety_margin = 0.05  # 5% safety buffer
        
        # Fee estimates (simplified)
        self.total_fee_percent = 0.002  # 0.2% total (both exchanges + network)
        
        logger.info(f"Balance Manager initialized - Trade size: ${self.base_trade_size}, Max concurrent: {self.max_concurrent_trades}")
    
    def calculate_dynamic_trade_size(self, available_balance: float, current_positions: int = 0) -> float:
        """Calculate trade size based on balance and position limits"""
        try:
            # Check position limits first
            if current_positions >= self.max_concurrent_trades:
                logger.warning(f"Max concurrent trades reached: {current_positions}/{self.max_concurrent_trades}")
                return 0
            
            # Calculate max size per remaining position slots
            remaining_slots = self.max_concurrent_trades - current_positions
            max_per_slot = available_balance / remaining_slots
            
            # Apply safety margin and fee buffer
            safe_size = max_per_slot * (1 - self.safety_margin)
            fee_buffer = safe_size * self.total_fee_percent
            final_size = safe_size - fee_buffer
            
            # Don't exceed base trade size unless we have excess funds
            if final_size > self.base_trade_size:
                final_size = self.base_trade_size
            
            # Minimum viable trade size
            if final_size < 10:
                logger.warning(f"Trade size too small: ${final_size:.2f}")
                return 0
            
            logger.info(f"Dynamic trade size: ${final_size:.2f} (Available: ${available_balance:.2f}, Positions: {current_positions})")
            return final_size
            
        except Exception as e:
            logger.error(f"Error calculating trade size: {e}")
            return 0
    
    async def validate_binance_balance(self, binance_client, required_usdt: float) -> Tuple[bool, str, float]:
        """Validate Binance USDT balance for trade"""
        try:
            if hasattr(binance_client, 'get_account'):
                account = binance_client.get_account()
                usdt_balance = float(next(
                    (b['free'] for b in account['balances'] if b['asset'] == 'USDT'), 
                    '0'
                ))
            else:
                # For testnet clients
                balances = binance_client.get_all_balances()
                usdt_balance = balances.get('USDT', 0)
            
            if usdt_balance >= required_usdt:
                return True, f"Sufficient USDT: ${usdt_balance:.2f}", usdt_balance
            else:
                return False, f"Insufficient USDT: ${usdt_balance:.2f} < ${required_usdt:.2f}", usdt_balance
                
        except Exception as e:
            logger.error(f"Error checking Binance balance: {e}")
            return False, f"Balance check failed: {e}", 0
    
    async def validate_drift_balance(self, drift_client, required_usdc: float) -> Tuple[bool, str, float]:
        """Validate Drift USDC collateral for trade"""
        try:
            # Use Drift's standard method
            if hasattr(drift_client, 'get_user'):
                user = drift_client.get_user()
                if user:
                    # Get free collateral (available for trading)
                    free_collateral = user.get_free_collateral()
                    usdc_balance = free_collateral / 1e6  # Convert from precision
                else:
                    usdc_balance = 0
            elif hasattr(drift_client, 'get_collateral_balance'):
                usdc_balance = await drift_client.get_collateral_balance()
            else:
                # Fallback for testing
                usdc_balance = 1000.0
            
            if usdc_balance >= required_usdc:
                return True, f"Sufficient USDC: ${usdc_balance:.2f}", usdc_balance
            else:
                return False, f"Insufficient USDC: ${usdc_balance:.2f} < ${required_usdc:.2f}", usdc_balance
                
        except Exception as e:
            logger.error(f"Error checking Drift balance: {e}")
            return False, f"Balance check failed: {e}", 0
    
    def count_active_positions(self, drift_client) -> int:
        """Count active positions using Drift's native methods"""
        try:
            if hasattr(drift_client, 'get_user'):
                user = drift_client.get_user()
                if user:
                    positions = user.get_active_perp_positions()
                    return len([p for p in positions if p.base_asset_amount != 0])
            return 0
        except Exception as e:
            logger.error(f"Error counting positions: {e}")
            return 0
    
    async def validate_trade_feasibility(self, binance_client, drift_client, 
                                       trade_size: float) -> Tuple[bool, str, float]:
        """
        Master validation function - checks everything needed for a trade
        Returns: (can_trade, reason, final_trade_size)
        """
        try:
            # Count current positions
            current_positions = self.count_active_positions(drift_client)
            
            # Check position limits
            if current_positions >= self.max_concurrent_trades:
                return False, f"Max positions reached: {current_positions}/{self.max_concurrent_trades}", 0
            
            # Calculate required amounts (including fees and buffer)
            fee_buffer = trade_size * self.total_fee_percent
            safety_buffer = trade_size * self.safety_margin
            required_amount = trade_size + fee_buffer + safety_buffer
            
            # Check Binance USDT
            binance_ok, binance_msg, usdt_balance = await self.validate_binance_balance(
                binance_client, required_amount
            )
            
            # Check Drift USDC
            drift_ok, drift_msg, usdc_balance = await self.validate_drift_balance(
                drift_client, required_amount
            )
            
            # If either fails, try dynamic sizing
            if not binance_ok or not drift_ok:
                min_balance = min(usdt_balance, usdc_balance)
                dynamic_size = self.calculate_dynamic_trade_size(min_balance, current_positions)
                
                if dynamic_size > 0:
                    return True, f"Reduced size due to balance limits", dynamic_size
                else:
                    reasons = []
                    if not binance_ok:
                        reasons.append(binance_msg)
                    if not drift_ok:
                        reasons.append(drift_msg)
                    return False, "; ".join(reasons), 0
            
            # All checks passed
            logger.info(f"Trade validation passed - Size: ${trade_size:.2f}, Positions: {current_positions}")
            return True, "All validations passed", trade_size
            
        except Exception as e:
            logger.error(f"Error validating trade: {e}")
            return False, f"Validation error: {e}", 0
    
    def get_status_summary(self) -> Dict:
        """Get current balance manager status"""
        return {
            'max_concurrent_trades': self.max_concurrent_trades,
            'base_trade_size': self.base_trade_size,
            'safety_margin': self.safety_margin,
            'total_fee_percent': self.total_fee_percent,
            'timestamp': datetime.now().isoformat()
        }
