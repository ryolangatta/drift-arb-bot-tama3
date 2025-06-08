"""
Test network trading executor
"""
import logging
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime
import json
import os

logger = logging.getLogger(__name__)

class TestTrader:
    def __init__(self, config: dict, binance_testnet, drift_devnet):
        self.config = config
        self.binance = binance_testnet
        self.drift = drift_devnet
        self.trading_config = config.get('TRADING_CONFIG', {})
        
        # Test trading state
        self.test_trades = []
        self.open_positions = {}
        self.test_mode = True
        
        # Load trade history
        self.trades_file = 'data/testnet_trades.json'
        self.load_trades()
    
    def load_trades(self):
        """Load testnet trade history"""
        try:
            if os.path.exists(self.trades_file):
                with open(self.trades_file, 'r') as f:
                    data = json.load(f)
                    self.test_trades = data.get('trades', [])
                    logger.info(f"Loaded {len(self.test_trades)} testnet trades")
        except Exception as e:
            logger.error(f"Error loading testnet trades: {e}")
    
    def save_trades(self):
        """Save testnet trade history"""
        try:
            data = {
                'trades': self.test_trades,
                'last_updated': datetime.now().isoformat()
            }
            os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)
            with open(self.trades_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving testnet trades: {e}")
    
    async def execute_arbitrage(self, opportunity: Dict) -> Optional[Dict]:
        """Execute arbitrage trade on test networks"""
        try:
            trade_size = self.trading_config.get('TRADE_SIZE_USDC', 100)
            pair = opportunity['pair']
            
            # Extract base asset (e.g., SOL from SOL/USDC)
            base_asset = pair.split('/')[0]
            quote_asset = pair.split('/')[1]
            
            # Convert pair for Binance (USDC -> USDT for testnet)
            binance_symbol = f"{base_asset}USDT"
            drift_market = f"{base_asset}-PERP"
            
            logger.info(f"Executing TESTNET arbitrage: {pair}")
            logger.info(f"Binance: Buy {binance_symbol}, Drift: Long {drift_market}")
            
            # Step 1: Buy spot on Binance testnet
            binance_order = await self.binance.place_market_buy(
                symbol=binance_symbol,
                quote_amount=trade_size
            )
            
            if not binance_order:
                logger.error("Failed to execute Binance testnet order")
                return None
            
            # Step 2: Open perp long on Drift devnet
            drift_position = await self.drift.place_perp_long(
                market=drift_market,
                size_usd=trade_size
            )
            
            if not drift_position:
                logger.error("Failed to open Drift devnet position")
                # TODO: Reverse Binance order
                return None
            
            # Record the arbitrage trade
            test_trade = {
                'id': len(self.test_trades) + 1,
                'timestamp': datetime.now().isoformat(),
                'type': 'TESTNET_ARBITRAGE',
                'pair': pair,
                'opportunity': opportunity,
                
                # Binance execution
                'binance': {
                    'order_id': binance_order['order_id'],
                    'symbol': binance_symbol,
                    'quantity': binance_order['quantity'],
                    'avg_price': binance_order['avg_price'],
                    'commission': binance_order['commission']
                },
                
                # Drift execution
                'drift': {
                    'tx_signature': drift_position['tx_signature'],
                    'market': drift_market,
                    'size': drift_position['size'],
                    'price': drift_position['price']
                },
                
                # Status
                'status': 'OPEN',
                'entry_spread': opportunity['spread'],
                'trade_size_usd': trade_size
            }
            
            # Store as open position
            position_key = f"{pair}_{test_trade['id']}"
            self.open_positions[position_key] = test_trade
            
            # Save trade
            self.test_trades.append(test_trade)
            self.save_trades()
            
            logger.info(f"✅ TESTNET trade executed successfully! Trade ID: {test_trade['id']}")
            
            return test_trade
            
        except Exception as e:
            logger.error(f"Error executing testnet arbitrage: {e}")
            return None
    
    async def close_arbitrage(self, position_key: str, current_prices: Dict) -> Optional[Dict]:
        """Close arbitrage position on test networks"""
        try:
            if position_key not in self.open_positions:
                logger.error(f"Position {position_key} not found")
                return None
            
            position = self.open_positions[position_key]
            
            # Extract details
            base_asset = position['pair'].split('/')[0]
            binance_symbol = f"{base_asset}USDT"
            drift_market = f"{base_asset}-PERP"
            
            logger.info(f"Closing TESTNET position: {position_key}")
            
            # Step 1: Close Drift position
            drift_close = await self.drift.close_perp_position(
                market=drift_market,
                size=position['drift']['size']
            )
            
            if not drift_close:
                logger.error("Failed to close Drift position")
                return None
            
            # Step 2: Sell spot on Binance
            binance_sell = await self.binance.place_market_sell(
                symbol=binance_symbol,
                quantity=position['binance']['quantity']
            )
            
            if not binance_sell:
                logger.error("Failed to sell on Binance testnet")
                return None
            
            # Calculate P&L
            # Entry: Bought spot at X, sold perp at Y (spread = Y-X)
            # Exit: Sold spot at A, bought perp at B (spread = B-A)
            # Profit = Entry spread - Exit spread
            
            entry_spread = position['entry_spread']
            exit_spread = (current_prices['perp'] - current_prices['spot']) / current_prices['spot']
            spread_captured = entry_spread - exit_spread
            
            # Calculate costs
            total_commission = (
                position['binance']['commission'] + 
                binance_sell['commission'] +
                0.001  # Estimated Drift fees
            )
            
            # Net P&L
            gross_pnl = spread_captured * position['trade_size_usd']
            net_pnl = gross_pnl - total_commission
            
            # Update position record
            position.update({
                'close_timestamp': datetime.now().isoformat(),
                'status': 'CLOSED',
                
                # Exit details
                'exit_spread': exit_spread,
                'spread_captured': spread_captured,
                
                # Binance close
                'binance_close': {
                    'order_id': binance_sell['order_id'],
                    'avg_price': binance_sell['avg_price'],
                    'commission': binance_sell['commission']
                },
                
                # Drift close
                'drift_close': {
                    'tx_signature': drift_close['tx_signature'],
                    'price': drift_close['price']
                },
                
                # P&L
                'gross_pnl': gross_pnl,
                'total_commission': total_commission,
                'net_pnl': net_pnl,
                'roi_percent': (net_pnl / position['trade_size_usd']) * 100
            })
            
            # Remove from open positions
            del self.open_positions[position_key]
            
            # Update in trades list
            for i, trade in enumerate(self.test_trades):
                if trade['id'] == position['id']:
                    self.test_trades[i] = position
                    break
            
            self.save_trades()
            
            emoji = "🟢" if net_pnl > 0 else "🔴"
            logger.info(
                f"{emoji} TESTNET position closed! "
                f"P&L: ${net_pnl:.2f} ({position['roi_percent']:.2f}%)"
            )
            
            return position
            
        except Exception as e:
            logger.error(f"Error closing testnet position: {e}")
            return None
    
    async def get_testnet_balances(self) -> Dict:
        """Get all testnet balances"""
        try:
            # Binance testnet balances
            binance_balances = self.binance.get_all_balances()
            
            # Drift collateral
            drift_collateral = await self.drift.get_collateral_balance()
            
            return {
                'binance_testnet': binance_balances,
                'drift_devnet': {
                    'USDC': drift_collateral
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting testnet balances: {e}")
            return {}
