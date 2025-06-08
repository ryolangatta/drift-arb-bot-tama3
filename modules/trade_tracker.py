"""
Trade tracking and reporting module
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64

logger = logging.getLogger(__name__)

class TradeTracker:
    def __init__(self, initial_balance: float = 500.0):
        self.initial_balance = initial_balance
        self.trades = []
        self.balance_history = []
        self.start_time = datetime.now()
        
        # Initialize balances
        self.balances = {
            'binance': initial_balance,
            'drift': initial_balance,
            'total': initial_balance * 2
        }
        
        # Track initial balance
        self.balance_history.append({
            'timestamp': self.start_time,
            'binance': self.balances['binance'],
            'drift': self.balances['drift'],
            'total': self.balances['total']
        })
        
        # Load existing data if available
        self.data_file = 'data/trade_history.json'
        self.load_data()
    
    def load_data(self):
        """Load existing trade data"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.trades = data.get('trades', [])
                    self.balance_history = data.get('balance_history', [])
                    # Convert string timestamps back to datetime
                    for trade in self.trades:
                        trade['timestamp'] = datetime.fromisoformat(trade['timestamp'])
                    for balance in self.balance_history:
                        balance['timestamp'] = datetime.fromisoformat(balance['timestamp'])
        except Exception as e:
            logger.error(f"Error loading trade data: {e}")
    
    def save_data(self):
        """Save trade data"""
        try:
            os.makedirs('data', exist_ok=True)
            data = {
                'trades': [{**t, 'timestamp': t['timestamp'].isoformat()} for t in self.trades],
                'balance_history': [{**b, 'timestamp': b['timestamp'].isoformat()} for b in self.balance_history]
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving trade data: {e}")
    
    def record_trade(self, opportunity: dict, binance_order: dict, drift_order: dict):
        """Record a completed arbitrage trade"""
        trade = {
            'timestamp': datetime.now(),
            'pair': opportunity['pair'],
            'spread': opportunity['spread'],
            'expected_profit': opportunity['potential_profit_usdc'],
            'binance_order': binance_order,
            'drift_order': drift_order,
            'status': 'completed'
        }
        
        self.trades.append(trade)
        
        # Update balances (simplified - assumes profit is realized)
        profit = opportunity['potential_profit_usdc']
        self.balances['total'] += profit
        self.balances['binance'] += profit / 2  # Split profit
        self.balances['drift'] += profit / 2
        
        # Record balance update
        self.balance_history.append({
            'timestamp': datetime.now(),
            'binance': self.balances['binance'],
            'drift': self.balances['drift'],
            'total': self.balances['total']
        })
        
        self.save_data()
        logger.info(f"Trade recorded - Profit: ${profit:.2f}, New Balance: ${self.balances['total']:.2f}")
    
    def get_summary(self) -> dict:
        """Get trading summary"""
        if not self.trades:
            return {
                'total_trades': 0,
                'total_profit': 0,
                'roi': 0,
                'avg_spread': 0,
                'runtime': str(datetime.now() - self.start_time).split('.')[0]
            }
        
        total_profit = sum(t['expected_profit'] for t in self.trades)
        roi = (total_profit / (self.initial_balance * 2)) * 100
        avg_spread = sum(t['spread'] for t in self.trades) / len(self.trades)
        
        return {
            'total_trades': len(self.trades),
            'total_profit': total_profit,
            'roi': roi,
            'avg_spread': avg_spread,
            'runtime': str(datetime.now() - self.start_time).split('.')[0],
            'current_balance': self.balances['total'],
            'binance_balance': self.balances['binance'],
            'drift_balance': self.balances['drift']
        }
    
    def generate_roi_chart(self) -> Optional[str]:
        """Generate ROI chart and return as base64 string"""
        try:
            if len(self.balance_history) < 2:
                return None
            
            # Create DataFrame
            df = pd.DataFrame(self.balance_history)
            df['roi'] = ((df['total'] - self.initial_balance * 2) / (self.initial_balance * 2)) * 100
            
            # Create figure
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
            
            # Plot 1: Balance over time
            ax1.plot(df['timestamp'], df['total'], 'b-', label='Total Balance', linewidth=2)
            ax1.plot(df['timestamp'], df['binance'], 'g--', label='Binance', alpha=0.7)
            ax1.plot(df['timestamp'], df['drift'], 'r--', label='Drift', alpha=0.7)
            ax1.axhline(y=self.initial_balance * 2, color='gray', linestyle=':', label='Initial')
            ax1.set_ylabel('Balance (USDC)')
            ax1.set_title('Balance History')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Plot 2: ROI over time
            ax2.plot(df['timestamp'], df['roi'], 'purple', linewidth=2)
            ax2.fill_between(df['timestamp'], df['roi'], alpha=0.3, color='purple')
            ax2.set_ylabel('ROI (%)')
            ax2.set_xlabel('Time')
            ax2.set_title('Return on Investment')
            ax2.grid(True, alpha=0.3)
            
            # Format x-axis
            for ax in [ax1, ax2]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax.xaxis.set_major_locator(mdates.AutoDateLocator())
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
            
            plt.tight_layout()
            
            # Convert to base64
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100)
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            return image_base64
            
        except Exception as e:
            logger.error(f"Error generating ROI chart: {e}")
            return None
    
    def get_recent_trades(self, minutes: int = 10) -> List[dict]:
        """Get trades from the last N minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [t for t in self.trades if t['timestamp'] > cutoff_time]