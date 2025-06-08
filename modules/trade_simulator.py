"""
Trade simulator for paper trading with realistic fees and slippage
"""
import json
import logging
from datetime import datetime
from typing import Dict, Optional
import os
import random

logger = logging.getLogger(__name__)

class TradeSimulator:
    def __init__(self, config: dict):
        self.config = config
        self.trading_config = config.get('TRADING_CONFIG', {})
        self.start_balance = 1000  # Starting with $1,000
        self.trade_size = self.trading_config.get('TRADE_SIZE_USDC', 100)
        
        # Initialize balances
        self.balance = self.start_balance
        self.trades = []
        self.open_position = None
        
        # Fee structure
        self.fees = {
            'binance_taker': 0.001,  # 0.1%
            'drift_taker': 0.0005,   # 0.05%
            'network_fee': 0.10      # $0.10 fixed
        }
        
        # Load existing trades if any
        self.trades_file = 'data/paper_trades.json'
        self.load_trades()
        
    def load_trades(self):
        """Load existing trades from file"""
        try:
            if os.path.exists(self.trades_file):
                with open(self.trades_file, 'r') as f:
                    data = json.load(f)
                    self.trades = data.get('trades', [])
                    self.balance = data.get('balance', self.start_balance)
                    logger.info(f"Loaded {len(self.trades)} existing trades, Balance: ${self.balance:.2f}")
        except Exception as e:
            logger.error(f"Error loading trades: {e}")
    
    def save_trades(self):
        """Save trades to file"""
        try:
            data = {
                'trades': self.trades,
                'balance': self.balance,
                'last_updated': datetime.now().isoformat(),
                'total_trades': len(self.trades),
                'start_balance': self.start_balance
            }
            os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)
            with open(self.trades_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving trades: {e}")
    
    def calculate_slippage(self, price: float, is_entry: bool) -> float:
        """Calculate realistic slippage based on market conditions"""
        # Base slippage: 0.05-0.1%
        base_slippage = random.uniform(0.0005, 0.001)
        
        # Exit slippage is usually worse (urgency)
        if not is_entry:
            base_slippage *= 1.5
        
        # Add volatility factor (simplified)
        volatility_factor = random.uniform(0.8, 1.2)
        
        return price * base_slippage * volatility_factor
    
    def calculate_total_fees(self, trade_size: float) -> dict:
        """Calculate all trading fees"""
        binance_fee = trade_size * self.fees['binance_taker']
        drift_fee = trade_size * self.fees['drift_taker']
        network_fee = self.fees['network_fee']
        
        total_fees = binance_fee + drift_fee + network_fee
        
        return {
            'binance_fee': binance_fee,
            'drift_fee': drift_fee,
            'network_fee': network_fee,
            'total_fees': total_fees,
            'fee_percentage': total_fees / trade_size
        }
    
    def simulate_trade(self, opportunity: dict) -> Optional[dict]:
        """Simulate a trade with realistic execution"""
        try:
            # Check if we have an open position
            if self.open_position:
                logger.warning("Already have an open position")
                return None
            
            # Check if we have enough balance
            if self.balance < self.trade_size:
                logger.warning(f"Insufficient balance: ${self.balance:.2f} < ${self.trade_size}")
                return None
            
            # Calculate entry slippage
            spot_slippage = self.calculate_slippage(opportunity['spot_price'], True)
            perp_slippage = self.calculate_slippage(opportunity['perp_price'], True)
            
            # Adjust prices for slippage (worse execution)
            actual_spot_price = opportunity['spot_price'] + spot_slippage
            actual_perp_price = opportunity['perp_price'] - perp_slippage
            
            # Recalculate actual spread after slippage
            actual_spread = (actual_perp_price - actual_spot_price) / actual_spot_price
            
            # Calculate fees
            fees = self.calculate_total_fees(self.trade_size)
            
            # Create trade record
            trade = {
                'id': len(self.trades) + 1,
                'timestamp': datetime.now().isoformat(),
                'pair': opportunity['pair'],
                'type': 'PAPER',
                
                # Original opportunity
                'signal_spot_price': opportunity['spot_price'],
                'signal_perp_price': opportunity['perp_price'],
                'signal_spread': opportunity['spread'],
                
                # Actual execution
                'entry_spot_price': actual_spot_price,
                'entry_perp_price': actual_perp_price,
                'entry_spread': actual_spread,
                'entry_slippage': spot_slippage + perp_slippage,
                
                # Position details
                'trade_size': self.trade_size,
                'fees': fees,
                'status': 'OPEN',
                'entry_balance': self.balance
            }
            
            # Deduct fees from balance
            self.balance -= fees['total_fees']
            
            # Set as open position
            self.open_position = trade
            self.trades.append(trade)
            self.save_trades()
            
            logger.info(
                f"📝 PAPER TRADE OPENED #{trade['id']}: {trade['pair']} "
                f"Size: ${self.trade_size} | "
                f"Spread: {actual_spread:.3%} (after slippage) | "
                f"Fees: ${fees['total_fees']:.2f}"
            )
            
            return trade
            
        except Exception as e:
            logger.error(f"Error simulating trade: {e}")
            return None
    
    def close_position(self, current_spot: float, current_perp: float) -> Optional[dict]:
        """Close position with realistic execution"""
        if not self.open_position:
            return None
        
        try:
            # Calculate exit slippage (usually worse)
            spot_slippage = self.calculate_slippage(current_spot, False)
            perp_slippage = self.calculate_slippage(current_perp, False)
            
            # Adjust prices for slippage
            actual_exit_spot = current_spot - spot_slippage
            actual_exit_perp = current_perp + perp_slippage
            
            # Calculate exit spread
            exit_spread = (actual_exit_perp - actual_exit_spot) / actual_exit_spot
            
            # Calculate P&L components
            # Profit = (Entry Spread - Exit Spread) * Trade Size
            spread_captured = self.open_position['entry_spread'] - exit_spread
            gross_profit = spread_captured * self.trade_size
            
            # Calculate exit fees
            exit_fees = self.calculate_total_fees(self.trade_size)
            
            # Total costs
            total_costs = (
                self.open_position['fees']['total_fees'] + 
                exit_fees['total_fees'] +
                self.open_position['entry_slippage'] +
                spot_slippage + perp_slippage
            )
            
            # Net P&L
            net_profit = gross_profit - total_costs
            
            # Update trade record
            self.open_position.update({
                'exit_timestamp': datetime.now().isoformat(),
                'exit_spot_price': actual_exit_spot,
                'exit_perp_price': actual_exit_perp,
                'exit_spread': exit_spread,
                'exit_slippage': spot_slippage + perp_slippage,
                'exit_fees': exit_fees,
                
                # P&L breakdown
                'spread_captured': spread_captured,
                'gross_profit': gross_profit,
                'total_costs': total_costs,
                'net_profit': net_profit,
                'roi_percent': (net_profit / self.trade_size) * 100,
                
                # Timing
                'hold_time_seconds': (
                    datetime.now() - datetime.fromisoformat(self.open_position['timestamp'])
                ).total_seconds(),
                
                'status': 'CLOSED'
            })
            
            # Update balance
            self.balance += self.trade_size + net_profit
            
            # Update in trades list
            for i, trade in enumerate(self.trades):
                if trade['id'] == self.open_position['id']:
                    self.trades[i] = self.open_position
                    break
            
            self.save_trades()
            
            # Log results
            emoji = "🟢" if net_profit > 0 else "🔴"
            logger.info(
                f"{emoji} TRADE CLOSED #{self.open_position['id']}: "
                f"P&L: ${net_profit:.2f} ({self.open_position['roi_percent']:.2f}%) | "
                f"Costs: ${total_costs:.2f} | "
                f"Balance: ${self.balance:.2f}"
            )
            
            result = self.open_position
            self.open_position = None
            return result
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return None
    
    def get_performance_stats(self) -> dict:
        """Calculate detailed performance statistics"""
        closed_trades = [t for t in self.trades if t['status'] == 'CLOSED']
        
        if not closed_trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'average_pnl': 0,
                'roi': 0,
                'current_balance': self.balance,
                'total_fees_paid': 0,
                'average_slippage': 0
            }
        
        winning_trades = [t for t in closed_trades if t['net_profit'] > 0]
        losing_trades = [t for t in closed_trades if t['net_profit'] <= 0]
        total_pnl = sum(t['net_profit'] for t in closed_trades)
        total_fees = sum(t['fees']['total_fees'] + t.get('exit_fees', {}).get('total_fees', 0) for t in closed_trades)
        avg_slippage = sum(t.get('entry_slippage', 0) + t.get('exit_slippage', 0) for t in closed_trades) / len(closed_trades)
        
        return {
            'total_trades': len(closed_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(closed_trades) if closed_trades else 0,
            'total_pnl': total_pnl,
            'average_pnl': total_pnl / len(closed_trades) if closed_trades else 0,
            'roi': (self.balance - self.start_balance) / self.start_balance,
            'current_balance': self.balance,
            'best_trade': max(closed_trades, key=lambda x: x['net_profit'])['net_profit'] if closed_trades else 0,
            'worst_trade': min(closed_trades, key=lambda x: x['net_profit'])['net_profit'] if closed_trades else 0,
            'total_fees_paid': total_fees,
            'average_slippage': avg_slippage,
            'average_hold_time': sum(t.get('hold_time_seconds', 0) for t in closed_trades) / len(closed_trades) if closed_trades else 0
        }
