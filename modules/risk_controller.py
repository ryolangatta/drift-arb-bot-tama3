"""
Risk Controller - Position tracking and automated risk management
Tracks open positions, implements timeouts, and manages auto-close logic
"""
import logging
import asyncio
import json
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class PositionStatus(Enum):
    """Position status enumeration"""
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"

@dataclass
class Position:
    """Position data structure"""
    id: str
    pair: str
    timestamp: datetime
    trade_size: float
    entry_spread: float
    binance_order_id: Optional[str] = None
    drift_order_id: Optional[str] = None
    status: PositionStatus = PositionStatus.OPEN
    entry_prices: Optional[Dict] = None
    exit_prices: Optional[Dict] = None
    exit_timestamp: Optional[datetime] = None
    profit_loss: Optional[float] = None
    close_reason: Optional[str] = None
    auto_close_triggered: bool = False
    
    def to_dict(self) -> Dict:
        """Convert position to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        if self.exit_timestamp:
            data['exit_timestamp'] = self.exit_timestamp.isoformat()
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Position':
        """Create position from dictionary"""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        if data.get('exit_timestamp'):
            data['exit_timestamp'] = datetime.fromisoformat(data['exit_timestamp'])
        data['status'] = PositionStatus(data['status'])
        return cls(**data)
    
    def get_age_seconds(self) -> float:
        """Get position age in seconds"""
        return (datetime.now() - self.timestamp).total_seconds()
    
    def is_expired(self, max_age_seconds: int = 180) -> bool:
        """Check if position has exceeded maximum age"""
        return self.get_age_seconds() > max_age_seconds

class RiskController:
    def __init__(self, config: dict):
        self.config = config
        self.risk_config = config.get('RISK_MANAGEMENT', {})
        
        # Risk parameters
        self.max_position_age_seconds = int(os.getenv('MAX_POSITION_AGE_SECONDS', '180'))  # 3 minutes
        self.max_concurrent_positions = int(os.getenv('MAX_CONCURRENT_POSITIONS', '3'))
        self.max_daily_trades = self.risk_config.get('MAX_TRADES_PER_DAY', 50)
        self.max_daily_drawdown = self.risk_config.get('MAX_DAILY_DRAWDOWN', 0.05)
        
        # Position tracking
        self.open_positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        self.daily_trades_count = 0
        self.daily_pnl = 0.0
        self.last_reset_date = datetime.now().date()
        
        # Storage
        self.positions_file = 'data/positions.json'
        self.load_positions()
        
        # Monitoring task
        self.monitoring_task = None
        self.is_monitoring = False
        
        logger.info(f"Risk Controller initialized - Max age: {self.max_position_age_seconds}s, Max positions: {self.max_concurrent_positions}")
    
    def load_positions(self):
        """Load positions from storage"""
        try:
            if os.path.exists(self.positions_file):
                with open(self.positions_file, 'r') as f:
                    data = json.load(f)
                
                # Load open positions
                for pos_data in data.get('open_positions', []):
                    position = Position.from_dict(pos_data)
                    self.open_positions[position.id] = position
                
                # Load closed positions (last 100)
                for pos_data in data.get('closed_positions', [])[-100:]:
                    position = Position.from_dict(pos_data)
                    self.closed_positions.append(position)
                
                # Load daily stats
                self.daily_trades_count = data.get('daily_trades_count', 0)
                self.daily_pnl = data.get('daily_pnl', 0.0)
                
                saved_date = data.get('last_reset_date')
                if saved_date:
                    self.last_reset_date = datetime.fromisoformat(saved_date).date()
                
                logger.info(f"Loaded {len(self.open_positions)} open positions and {len(self.closed_positions)} closed positions")
        except Exception as e:
            logger.error(f"Error loading positions: {e}")
    
    def save_positions(self):
        """Save positions to storage"""
        try:
            os.makedirs(os.path.dirname(self.positions_file), exist_ok=True)
            
            data = {
                'open_positions': [pos.to_dict() for pos in self.open_positions.values()],
                'closed_positions': [pos.to_dict() for pos in self.closed_positions[-100:]],  # Keep last 100
                'daily_trades_count': self.daily_trades_count,
                'daily_pnl': self.daily_pnl,
                'last_reset_date': self.last_reset_date.isoformat(),
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.positions_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving positions: {e}")
    
    def reset_daily_stats_if_needed(self):
        """Reset daily statistics if it's a new day"""
        today = datetime.now().date()
        if today > self.last_reset_date:
            logger.info(f"New day detected, resetting daily stats. Previous: {self.daily_trades_count} trades, ${self.daily_pnl:.2f} P&L")
            self.daily_trades_count = 0
            self.daily_pnl = 0.0
            self.last_reset_date = today
            self.save_positions()
    
    def can_open_new_position(self) -> Tuple[bool, str]:
        """Check if a new position can be opened"""
        self.reset_daily_stats_if_needed()
        
        # Check concurrent position limit
        if len(self.open_positions) >= self.max_concurrent_positions:
            return False, f"Maximum concurrent positions reached: {len(self.open_positions)}/{self.max_concurrent_positions}"
        
        # Check daily trade limit
        if self.daily_trades_count >= self.max_daily_trades:
            return False, f"Daily trade limit reached: {self.daily_trades_count}/{self.max_daily_trades}"
        
        # Check daily drawdown limit
        if self.daily_pnl < 0 and abs(self.daily_pnl) > (self.max_daily_drawdown * 1000):  # Assume $1000 base
            return False, f"Daily drawdown limit exceeded: ${self.daily_pnl:.2f}"
        
        return True, "Position can be opened"
    
    def create_position(self, pair: str, trade_size: float, entry_spread: float, 
                       binance_order_id: str = None, drift_order_id: str = None,
                       entry_prices: Dict = None) -> Position:
        """Create a new position"""
        position_id = f"{pair}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        position = Position(
            id=position_id,
            pair=pair,
            timestamp=datetime.now(),
            trade_size=trade_size,
            entry_spread=entry_spread,
            binance_order_id=binance_order_id,
            drift_order_id=drift_order_id,
            entry_prices=entry_prices or {}
        )
        
        self.open_positions[position_id] = position
        self.daily_trades_count += 1
        self.save_positions()
        
        logger.info(f"Created position {position_id}: {pair} size ${trade_size:.2f} spread {entry_spread:.4%}")
        
        return position
    
    def close_position(self, position_id: str, exit_prices: Dict = None, 
                      profit_loss: float = None, close_reason: str = "Manual close") -> Optional[Position]:
        """Close a position"""
        if position_id not in self.open_positions:
            logger.warning(f"Position {position_id} not found in open positions")
            return None
        
        position = self.open_positions[position_id]
        position.status = PositionStatus.CLOSED
        position.exit_timestamp = datetime.now()
        position.exit_prices = exit_prices or {}
        position.profit_loss = profit_loss or 0.0
        position.close_reason = close_reason
        
        # Move to closed positions
        del self.open_positions[position_id]
        self.closed_positions.append(position)
        
        # Update daily P&L
        if profit_loss is not None:
            self.daily_pnl += profit_loss
        
        self.save_positions()
        
        logger.info(f"Closed position {position_id}: P&L ${profit_loss:.2f} reason: {close_reason}")
        
        return position
    
    def get_expired_positions(self) -> List[Position]:
        """Get positions that have exceeded maximum age"""
        expired = []
        for position in self.open_positions.values():
            if position.is_expired(self.max_position_age_seconds):
                expired.append(position)
        return expired
    
    def mark_position_for_auto_close(self, position_id: str) -> bool:
        """Mark position for auto-close due to timeout"""
        if position_id in self.open_positions:
            position = self.open_positions[position_id]
            position.auto_close_triggered = True
            position.status = PositionStatus.CLOSING
            self.save_positions()
            
            logger.warning(f"Position {position_id} marked for auto-close after {position.get_age_seconds():.0f}s")
            return True
        return False
    
    async def start_monitoring(self):
        """Start the position monitoring task"""
        if self.is_monitoring:
            logger.warning("Position monitoring already running")
            return
        
        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Position monitoring started")
    
    async def stop_monitoring(self):
        """Stop the position monitoring task"""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Position monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        try:
            while self.is_monitoring:
                await self._check_positions()
                await asyncio.sleep(10)  # Check every 10 seconds
        except asyncio.CancelledError:
            logger.info("Position monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
    
    async def _check_positions(self):
        """Check all open positions for timeout or other issues"""
        try:
            expired_positions = self.get_expired_positions()
            
            for position in expired_positions:
                if not position.auto_close_triggered:
                    logger.warning(f"Position {position.id} expired after {position.get_age_seconds():.0f}s - triggering auto-close")
                    self.mark_position_for_auto_close(position.id)
                    
                    # Here you would trigger the actual closing mechanism
                    # This would be connected to your order execution system
                    await self._trigger_position_close(position)
        except Exception as e:
            logger.error(f"Error checking positions: {e}")
    
    async def _trigger_position_close(self, position: Position):
        """Trigger the actual closing of a position (placeholder)"""
        # This is where you'd integrate with your order execution system
        # For now, we'll simulate a close
        
        logger.info(f"Auto-closing position {position.id} due to timeout")
        
        # Simulate close (in real implementation, this would call your order execution)
        simulated_exit_prices = {
            'binance_price': position.entry_prices.get('binance_price', 0) * 0.999,  # Slight loss
            'drift_price': position.entry_prices.get('drift_price', 0) * 1.001
        }
        
        # Calculate simulated P&L (slightly negative due to timeout)
        simulated_pnl = -2.0  # Small loss for timeout
        
        self.close_position(
            position.id,
            exit_prices=simulated_exit_prices,
            profit_loss=simulated_pnl,
            close_reason="Auto-close due to timeout"
        )
    
    def get_position_summary(self) -> Dict:
        """Get summary of current positions and risk metrics"""
        self.reset_daily_stats_if_needed()
        
        # Calculate average position age
        avg_age = 0
        if self.open_positions:
            total_age = sum(pos.get_age_seconds() for pos in self.open_positions.values())
            avg_age = total_age / len(self.open_positions)
        
        # Get recent performance
        recent_closed = [p for p in self.closed_positions if p.exit_timestamp and 
                        (datetime.now() - p.exit_timestamp).days < 1]
        
        recent_pnl = sum(p.profit_loss or 0 for p in recent_closed)
        win_rate = 0
        if recent_closed:
            wins = len([p for p in recent_closed if (p.profit_loss or 0) > 0])
            win_rate = wins / len(recent_closed)
        
        return {
            'open_positions_count': len(self.open_positions),
            'max_concurrent_positions': self.max_concurrent_positions,
            'daily_trades_count': self.daily_trades_count,
            'max_daily_trades': self.max_daily_trades,
            'daily_pnl': self.daily_pnl,
            'max_daily_drawdown': self.max_daily_drawdown,
            'average_position_age_seconds': avg_age,
            'max_position_age_seconds': self.max_position_age_seconds,
            'recent_win_rate': win_rate,
            'recent_pnl': recent_pnl,
            'positions_near_timeout': len(self.get_expired_positions()),
            'can_open_new_position': self.can_open_new_position()[0],
            'timestamp': datetime.now().isoformat()
        }
    
    def get_open_positions(self) -> List[Position]:
        """Get list of open positions"""
        return list(self.open_positions.values())
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get specific position by ID"""
        return self.open_positions.get(position_id)
    
    def force_close_all_positions(self, reason: str = "Emergency close"):
        """Force close all open positions"""
        logger.warning(f"Force closing all {len(self.open_positions)} open positions: {reason}")
        
        positions_to_close = list(self.open_positions.keys())
        for position_id in positions_to_close:
            self.close_position(position_id, close_reason=reason, profit_loss=-1.0)  # Small loss for emergency close
        
        logger.info("All positions force closed")
