"""
PnL Logger - Comprehensive profit/loss tracking and reporting
Logs all trade data in CSV and JSON formats with detailed analytics
"""
import os
import csv
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import statistics

logger = logging.getLogger(__name__)

class TradeStatus(Enum):
    """Trade status enumeration"""
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"

class TradeType(Enum):
    """Trade type enumeration"""
    ARBITRAGE = "ARBITRAGE"
    MANUAL = "MANUAL"
    TEST = "TEST"
    SIMULATION = "SIMULATION"

@dataclass
class TradeRecord:
    """Comprehensive trade record structure - all required fields first"""
    # Basic info (required)
    trade_id: str
    timestamp: str
    trade_type: TradeType
    status: TradeStatus
    pair: str
    spot_price: float
    perp_price: float
    spread_entry: float
    position_size: float
    
    # Optional fields with defaults
    spread_exit: Optional[float] = None
    entry_time: str = ""
    exit_time: Optional[str] = None
    hold_duration_seconds: Optional[float] = None
    
    # Exchange details
    binance_order_id: Optional[str] = None
    drift_order_id: Optional[str] = None
    binance_fill_price: Optional[float] = None
    drift_fill_price: Optional[float] = None
    
    # Costs and fees
    binance_fee: float = 0.0
    drift_fee: float = 0.0
    network_fee: float = 0.0
    slippage_cost: float = 0.0
    total_costs: float = 0.0
    
    # P&L calculation
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    roi_percent: float = 0.0
    
    # Risk metrics
    max_exposure: float = 0.0
    drawdown: float = 0.0
    
    # Market conditions
    volatility: Optional[float] = None
    volume_24h: Optional[float] = None
    market_state: Optional[str] = None
    
    # Notes and metadata
    execution_notes: str = ""
    filter_results: str = ""
    error_message: str = ""

class PnLLogger:
    def __init__(self, config: dict):
        self.config = config
        
        # File paths
        self.data_dir = config.get('DATA_DIR', 'data/trades')
        self.csv_file = os.path.join(self.data_dir, 'trades.csv')
        self.json_file = os.path.join(self.data_dir, 'trades.json')
        self.summary_file = os.path.join(self.data_dir, 'daily_summary.json')
        
        # Logging settings
        self.log_to_csv = config.get('LOG_TO_CSV', True)
        self.log_to_json = config.get('LOG_TO_JSON', True)
        self.backup_enabled = config.get('BACKUP_ENABLED', True)
        self.backup_interval_hours = config.get('BACKUP_INTERVAL_HOURS', 24)
        
        # Performance tracking
        self.starting_balance = float(config.get('STARTING_BALANCE', 1000.0))
        self.current_balance = self.starting_balance
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # In-memory storage for quick access
        self.trade_records: List[TradeRecord] = []
        self.daily_summaries = {}
        
        # Initialize
        self._initialize_files()
        self._load_existing_data()
        
        logger.info(f"PnL Logger initialized - Data dir: {self.data_dir}")
        logger.info(f"Starting balance: ${self.starting_balance:,.2f}")
    
    def _initialize_files(self):
        """Create necessary directories and files"""
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Create CSV with headers if it doesn't exist
        if self.log_to_csv and not os.path.exists(self.csv_file):
            self._create_csv_headers()
        
        # Create JSON file if it doesn't exist
        if self.log_to_json and not os.path.exists(self.json_file):
            self._create_json_file()
    
    def _create_csv_headers(self):
        """Create CSV file with proper headers"""
        headers = [
            'trade_id', 'timestamp', 'trade_type', 'status',
            'pair', 'spot_price', 'perp_price', 'spread_entry', 'spread_exit',
            'position_size', 'entry_time', 'exit_time', 'hold_duration_seconds',
            'binance_order_id', 'drift_order_id', 'binance_fill_price', 'drift_fill_price',
            'binance_fee', 'drift_fee', 'network_fee', 'slippage_cost', 'total_costs',
            'gross_pnl', 'net_pnl', 'roi_percent',
            'max_exposure', 'drawdown',
            'volatility', 'volume_24h', 'market_state',
            'execution_notes', 'filter_results', 'error_message'
        ]
        
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        
        logger.info(f"Created CSV file: {self.csv_file}")
    
    def _create_json_file(self):
        """Create JSON file with initial structure"""
        initial_data = {
            'metadata': {
                'created': datetime.now().isoformat(),
                'starting_balance': self.starting_balance,
                'version': '1.0'
            },
            'trades': [],
            'daily_summaries': {}
        }
        
        with open(self.json_file, 'w') as f:
            json.dump(initial_data, f, indent=2)
        
        logger.info(f"Created JSON file: {self.json_file}")
    
    def _load_existing_data(self):
        """Load existing trade data from files"""
        # Load from JSON if available
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, 'r') as f:
                    data = json.load(f)
                
                # Load trade records
                for trade_data in data.get('trades', []):
                    # Convert enum strings back to enums
                    if 'trade_type' in trade_data:
                        trade_data['trade_type'] = TradeType(trade_data['trade_type'])
                    if 'status' in trade_data:
                        trade_data['status'] = TradeStatus(trade_data['status'])
                    
                    trade_record = TradeRecord(**trade_data)
                    self.trade_records.append(trade_record)
                
                # Load daily summaries
                self.daily_summaries = data.get('daily_summaries', {})
                
                # Update counters
                self.total_trades = len(self.trade_records)
                self.winning_trades = len([t for t in self.trade_records if t.net_pnl > 0])
                self.losing_trades = len([t for t in self.trade_records if t.net_pnl < 0])
                
                # Calculate current balance
                total_pnl = sum(t.net_pnl for t in self.trade_records)
                self.current_balance = self.starting_balance + total_pnl
                
                logger.info(f"Loaded {self.total_trades} existing trades")
                
            except Exception as e:
                logger.error(f"Error loading existing data: {e}")
    
    def log_trade(self, trade_data: Dict) -> str:
        """
        Log a new trade record
        Returns: trade_id
        """
        # Generate trade ID
        trade_id = f"trade_{int(datetime.now().timestamp() * 1000)}"
        
        # Create trade record with proper enum conversion
        trade_type = trade_data.get('trade_type', 'ARBITRAGE')
        if isinstance(trade_type, str):
            trade_type = TradeType(trade_type)
        
        status = trade_data.get('status', 'EXECUTED')
        if isinstance(status, str):
            status = TradeStatus(status)
        
        trade_record = TradeRecord(
            trade_id=trade_id,
            timestamp=datetime.now().isoformat(),
            trade_type=trade_type,
            status=status,
            
            # Required market data
            pair=trade_data['pair'],
            spot_price=trade_data['spot_price'],
            perp_price=trade_data['perp_price'],
            spread_entry=trade_data['spread_entry'],
            position_size=trade_data['position_size'],
            
            # Optional fields
            spread_exit=trade_data.get('spread_exit'),
            entry_time=trade_data.get('entry_time', datetime.now().isoformat()),
            exit_time=trade_data.get('exit_time'),
            hold_duration_seconds=trade_data.get('hold_duration_seconds'),
            
            # Exchange details
            binance_order_id=trade_data.get('binance_order_id'),
            drift_order_id=trade_data.get('drift_order_id'),
            binance_fill_price=trade_data.get('binance_fill_price'),
            drift_fill_price=trade_data.get('drift_fill_price'),
            
            # Costs
            binance_fee=trade_data.get('binance_fee', 0.0),
            drift_fee=trade_data.get('drift_fee', 0.0),
            network_fee=trade_data.get('network_fee', 0.0),
            slippage_cost=trade_data.get('slippage_cost', 0.0),
            total_costs=trade_data.get('total_costs', 0.0),
            
            # P&L
            gross_pnl=trade_data.get('gross_pnl', 0.0),
            net_pnl=trade_data.get('net_pnl', 0.0),
            roi_percent=trade_data.get('roi_percent', 0.0),
            
            # Risk
            max_exposure=trade_data.get('max_exposure', 0.0),
            drawdown=trade_data.get('drawdown', 0.0),
            
            # Market conditions
            volatility=trade_data.get('volatility'),
            volume_24h=trade_data.get('volume_24h'),
            market_state=trade_data.get('market_state'),
            
            # Metadata
            execution_notes=trade_data.get('execution_notes', ''),
            filter_results=trade_data.get('filter_results', ''),
            error_message=trade_data.get('error_message', '')
        )
        
        # Add to in-memory storage
        self.trade_records.append(trade_record)
        
        # Update counters
        self.total_trades += 1
        if trade_record.net_pnl > 0:
            self.winning_trades += 1
        elif trade_record.net_pnl < 0:
            self.losing_trades += 1
        
        # Update balance
        self.current_balance += trade_record.net_pnl
        
        # Write to files
        if self.log_to_csv:
            self._write_to_csv(trade_record)
        
        if self.log_to_json:
            self._write_to_json()
        
        # Update daily summary
        self._update_daily_summary(trade_record)
        
        logger.info(f"Logged trade {trade_id}: {trade_record.pair} "
                   f"P&L: ${trade_record.net_pnl:.2f} "
                   f"Balance: ${self.current_balance:.2f}")
        
        return trade_id
    
    def _write_to_csv(self, trade_record: TradeRecord):
        """Write trade record to CSV file"""
        try:
            with open(self.csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                
                # Convert trade record to list of values
                values = [
                    trade_record.trade_id, trade_record.timestamp,
                    trade_record.trade_type.value, trade_record.status.value,
                    trade_record.pair, trade_record.spot_price, trade_record.perp_price,
                    trade_record.spread_entry, trade_record.spread_exit,
                    trade_record.position_size, trade_record.entry_time,
                    trade_record.exit_time, trade_record.hold_duration_seconds,
                    trade_record.binance_order_id, trade_record.drift_order_id,
                    trade_record.binance_fill_price, trade_record.drift_fill_price,
                    trade_record.binance_fee, trade_record.drift_fee,
                    trade_record.network_fee, trade_record.slippage_cost, trade_record.total_costs,
                    trade_record.gross_pnl, trade_record.net_pnl, trade_record.roi_percent,
                    trade_record.max_exposure, trade_record.drawdown,
                    trade_record.volatility, trade_record.volume_24h, trade_record.market_state,
                    trade_record.execution_notes, trade_record.filter_results, trade_record.error_message
                ]
                
                writer.writerow(values)
                
        except Exception as e:
            logger.error(f"Error writing to CSV: {e}")
    
    def _write_to_json(self):
        """Write all trade data to JSON file"""
        try:
            data = {
                'metadata': {
                    'created': datetime.now().isoformat(),
                    'starting_balance': self.starting_balance,
                    'current_balance': self.current_balance,
                    'total_trades': self.total_trades,
                    'version': '1.0'
                },
                'trades': [asdict(trade) for trade in self.trade_records],
                'daily_summaries': self.daily_summaries
            }
            
            # Convert enums to strings for JSON serialization
            for trade in data['trades']:
                if 'trade_type' in trade and hasattr(trade['trade_type'], 'value'):
                    trade['trade_type'] = trade['trade_type'].value
                elif 'trade_type' in trade and isinstance(trade['trade_type'], TradeType):
                    trade['trade_type'] = trade['trade_type'].value
                    
                if 'status' in trade and hasattr(trade['status'], 'value'):
                    trade['status'] = trade['status'].value
                elif 'status' in trade and isinstance(trade['status'], TradeStatus):
                    trade['status'] = trade['status'].value
            
            with open(self.json_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Error writing to JSON: {e}")
    
    def _update_daily_summary(self, trade_record: TradeRecord):
        """Update daily summary statistics"""
        trade_date = trade_record.timestamp[:10]  # YYYY-MM-DD
        
        if trade_date not in self.daily_summaries:
            self.daily_summaries[trade_date] = {
                'date': trade_date,
                'trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0.0,
                'total_fees': 0.0,
                'total_volume': 0.0,
                'avg_spread': 0.0,
                'avg_hold_time': 0.0,
                'pairs_traded': set(),
                'best_trade': 0.0,
                'worst_trade': 0.0
            }
        
        summary = self.daily_summaries[trade_date]
        summary['trades'] += 1
        summary['total_pnl'] += trade_record.net_pnl
        summary['total_fees'] += trade_record.total_costs
        summary['total_volume'] += trade_record.position_size
        
        # Handle pairs_traded as both set and list (for loaded data)
        if isinstance(summary['pairs_traded'], list):
            # Convert list back to set for processing
            summary['pairs_traded'] = set(summary['pairs_traded'])
        
        summary['pairs_traded'].add(trade_record.pair)
        
        if trade_record.net_pnl > 0:
            summary['winning_trades'] += 1
        elif trade_record.net_pnl < 0:
            summary['losing_trades'] += 1
        
        # Update best/worst trades
        if trade_record.net_pnl > summary['best_trade']:
            summary['best_trade'] = trade_record.net_pnl
        if trade_record.net_pnl < summary['worst_trade']:
            summary['worst_trade'] = trade_record.net_pnl
        
        # Calculate averages
        all_spreads = [t.spread_entry for t in self.trade_records if t.timestamp.startswith(trade_date)]
        summary['avg_spread'] = statistics.mean(all_spreads) if all_spreads else 0.0
        
        all_hold_times = [t.hold_duration_seconds for t in self.trade_records 
                         if t.timestamp.startswith(trade_date) and t.hold_duration_seconds]
        summary['avg_hold_time'] = statistics.mean(all_hold_times) if all_hold_times else 0.0
        
        # Convert set to list for JSON serialization
        summary['pairs_traded'] = list(summary['pairs_traded'])
    
    def get_performance_stats(self, days: int = 30) -> Dict:
        """Get comprehensive performance statistics"""
        # Filter trades by timeframe
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_trades = [
            t for t in self.trade_records 
            if datetime.fromisoformat(t.timestamp) > cutoff_date
        ]
        
        if not recent_trades:
            return self._get_empty_stats()
        
        # Calculate basic metrics
        total_pnl = sum(t.net_pnl for t in recent_trades)
        winning_trades = [t for t in recent_trades if t.net_pnl > 0]
        losing_trades = [t for t in recent_trades if t.net_pnl < 0]
        
        # Risk metrics
        pnl_values = [t.net_pnl for t in recent_trades]
        total_fees = sum(t.total_costs for t in recent_trades)
        total_volume = sum(t.position_size for t in recent_trades)
        
        stats = {
            # Basic performance
            'timeframe_days': days,
            'total_trades': len(recent_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(recent_trades) if recent_trades else 0,
            
            # P&L metrics
            'total_pnl': total_pnl,
            'avg_pnl_per_trade': total_pnl / len(recent_trades) if recent_trades else 0,
            'best_trade': max(pnl_values) if pnl_values else 0,
            'worst_trade': min(pnl_values) if pnl_values else 0,
            'avg_winning_trade': statistics.mean([t.net_pnl for t in winning_trades]) if winning_trades else 0,
            'avg_losing_trade': statistics.mean([t.net_pnl for t in losing_trades]) if losing_trades else 0,
            
            # Risk metrics
            'sharpe_ratio': self._calculate_sharpe_ratio(pnl_values),
            'max_drawdown': self._calculate_max_drawdown(recent_trades),
            'profit_factor': self._calculate_profit_factor(winning_trades, losing_trades),
            'volatility': statistics.stdev(pnl_values) if len(pnl_values) > 1 else 0,
            
            # Cost analysis
            'total_fees': total_fees,
            'avg_fee_per_trade': total_fees / len(recent_trades) if recent_trades else 0,
            'fee_percentage': total_fees / total_volume if total_volume > 0 else 0,
            
            # Trading activity
            'total_volume': total_volume,
            'avg_position_size': total_volume / len(recent_trades) if recent_trades else 0,
            'pairs_traded': len(set(t.pair for t in recent_trades)),
            'avg_hold_time_seconds': statistics.mean([t.hold_duration_seconds for t in recent_trades 
                                                     if t.hold_duration_seconds]) if recent_trades else 0,
            
            # Balance tracking
            'starting_balance': self.starting_balance,
            'current_balance': self.current_balance,
            'total_return': (self.current_balance - self.starting_balance) / self.starting_balance,
            'roi_percentage': ((self.current_balance - self.starting_balance) / self.starting_balance) * 100,
            
            # Timestamps
            'last_updated': datetime.now().isoformat(),
            'first_trade': recent_trades[0].timestamp if recent_trades else None,
            'last_trade': recent_trades[-1].timestamp if recent_trades else None
        }
        
        return stats
    
    def _get_empty_stats(self) -> Dict:
        """Return empty statistics structure"""
        return {
            'total_trades': 0,
            'total_pnl': 0.0,
            'win_rate': 0.0,
            'current_balance': self.current_balance,
            'roi_percentage': 0.0,
            'last_updated': datetime.now().isoformat()
        }
    
    def _calculate_sharpe_ratio(self, pnl_values: List[float]) -> float:
        """Calculate Sharpe ratio"""
        if len(pnl_values) < 2:
            return 0.0
        
        mean_return = statistics.mean(pnl_values)
        std_return = statistics.stdev(pnl_values)
        
        if std_return == 0:
            return 0.0
        
        # Annualized Sharpe ratio (assuming daily trades)
        return (mean_return / std_return) * (365 ** 0.5)
    
    def _calculate_max_drawdown(self, trades: List[TradeRecord]) -> float:
        """Calculate maximum drawdown"""
        if not trades:
            return 0.0
        
        cumulative_pnl = []
        running_total = 0
        
        for trade in trades:
            running_total += trade.net_pnl
            cumulative_pnl.append(running_total)
        
        if not cumulative_pnl:
            return 0.0
        
        # Calculate drawdown
        peak = cumulative_pnl[0]
        max_drawdown = 0.0
        
        for value in cumulative_pnl:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak if peak != 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown
    
    def _calculate_profit_factor(self, winning_trades: List[TradeRecord], losing_trades: List[TradeRecord]) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        gross_profit = sum(t.net_pnl for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl for t in losing_trades))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    def get_daily_summary(self, date: str = None) -> Dict:
        """Get daily summary for specific date"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        return self.daily_summaries.get(date, {})
    
    def export_data(self, start_date: str = None, end_date: str = None, format: str = 'json') -> str:
        """Export trade data for specified date range"""
        filtered_trades = self.trade_records
        
        # Apply date filters
        if start_date:
            filtered_trades = [t for t in filtered_trades if t.timestamp >= start_date]
        if end_date:
            filtered_trades = [t for t in filtered_trades if t.timestamp <= end_date]
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"trades_export_{timestamp}.{format}"
        filepath = os.path.join(self.data_dir, filename)
        
        if format.lower() == 'csv':
            self._export_to_csv(filtered_trades, filepath)
        else:
            self._export_to_json(filtered_trades, filepath)
        
        logger.info(f"Exported {len(filtered_trades)} trades to {filepath}")
        return filepath
    
    def _export_to_csv(self, trades: List[TradeRecord], filepath: str):
        """Export trades to CSV file"""
        with open(filepath, 'w', newline='') as f:
            if trades:
                # Convert dataclass to dict and handle enums
                trade_dicts = []
                for trade in trades:
                    trade_dict = asdict(trade)
                    trade_dict['trade_type'] = trade.trade_type.value
                    trade_dict['status'] = trade.status.value
                    trade_dicts.append(trade_dict)
                
                writer = csv.DictWriter(f, fieldnames=trade_dicts[0].keys())
                writer.writeheader()
                writer.writerows(trade_dicts)
    
    def _export_to_json(self, trades: List[TradeRecord], filepath: str):
        """Export trades to JSON file"""
        trade_dicts = []
        for trade in trades:
            trade_dict = asdict(trade)
            trade_dict['trade_type'] = trade.trade_type.value
            trade_dict['status'] = trade.status.value
            trade_dicts.append(trade_dict)
        
        data = {
            'export_date': datetime.now().isoformat(),
            'total_trades': len(trades),
            'trades': trade_dicts
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def get_trade_by_id(self, trade_id: str) -> Optional[TradeRecord]:
        """Get specific trade by ID"""
        for trade in self.trade_records:
            if trade.trade_id == trade_id:
                return trade
        return None
    
    def update_trade(self, trade_id: str, updates: Dict) -> bool:
        """Update existing trade record"""
        for i, trade in enumerate(self.trade_records):
            if trade.trade_id == trade_id:
                # Update fields
                for key, value in updates.items():
                    if hasattr(trade, key):
                        setattr(trade, key, value)
                
                # Rewrite files
                if self.log_to_json:
                    self._write_to_json()
                
                logger.info(f"Updated trade {trade_id}")
                return True
        
        return False
