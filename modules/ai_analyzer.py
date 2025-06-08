"""
AI-powered trade analysis and strategy optimization
"""
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import os

logger = logging.getLogger(__name__)

class AITradeAnalyzer:
    def __init__(self, config: dict):
        self.config = config
        self.analysis_file = 'data/ai_analysis.json'
        self.strategy_file = 'data/ai_strategy.json'
        self.current_strategy = self.load_strategy()
        
    def load_strategy(self) -> dict:
        """Load current AI strategy parameters"""
        try:
            if os.path.exists(self.strategy_file):
                with open(self.strategy_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading strategy: {e}")
        
        # Default strategy
        return {
            'spread_threshold': self.config['TRADING_CONFIG']['SPREAD_THRESHOLD'],
            'min_profit_after_fees': self.config['TRADING_CONFIG']['MIN_PROFIT_AFTER_FEES'],
            'exit_spread_ratio': 0.5,  # Exit when spread reduces to 50%
            'max_hold_time': 300,  # 5 minutes max hold
            'confidence_threshold': 0.7,
            'adaptive_sizing': False,
            'time_based_entry': {
                'enabled': False,
                'best_hours': [],
                'avoid_hours': []
            },
            'volatility_filter': {
                'enabled': False,
                'min_volatility': 0.001,
                'max_volatility': 0.05
            },
            'momentum_filter': {
                'enabled': False,
                'use_rsi': False,
                'use_trend': False
            }
        }
    
    def analyze_trades(self, trades: List[dict]) -> Dict:
        """Comprehensive analysis of all trades"""
        if not trades:
            return {}
        
        try:
            # Convert to DataFrame for easier analysis
            df = pd.DataFrame(trades)
            closed_trades = df[df['status'] == 'CLOSED'].copy()
            
            if closed_trades.empty:
                return {}
            
            # Calculate additional metrics
            closed_trades['hold_time'] = pd.to_datetime(closed_trades['exit_timestamp']) - pd.to_datetime(closed_trades['timestamp'])
            closed_trades['hold_seconds'] = closed_trades['hold_time'].dt.total_seconds()
            closed_trades['hour'] = pd.to_datetime(closed_trades['timestamp']).dt.hour
            closed_trades['weekday'] = pd.to_datetime(closed_trades['timestamp']).dt.dayofweek
            closed_trades['profit_percent'] = closed_trades['net_profit'] / closed_trades['trade_size'] * 100
            
            analysis = {
                'timestamp': datetime.now().isoformat(),
                'total_trades_analyzed': len(closed_trades),
                
                # Performance metrics
                'performance': {
                    'win_rate': (closed_trades['net_profit'] > 0).mean(),
                    'average_profit': closed_trades['net_profit'].mean(),
                    'median_profit': closed_trades['net_profit'].median(),
                    'std_profit': closed_trades['net_profit'].std(),
                    'sharpe_ratio': self._calculate_sharpe_ratio(closed_trades),
                    'max_drawdown': self._calculate_max_drawdown(closed_trades),
                    'profit_factor': self._calculate_profit_factor(closed_trades)
                },
                
                # Spread analysis
                'spread_analysis': {
                    'avg_entry_spread': closed_trades['entry_spread'].mean(),
                    'avg_exit_spread': closed_trades['exit_spread'].mean(),
                    'optimal_entry_spread': self._find_optimal_spread(closed_trades, 'entry'),
                    'optimal_exit_ratio': self._find_optimal_exit_ratio(closed_trades)
                },
                
                # Time analysis
                'time_analysis': {
                    'avg_hold_time_seconds': closed_trades['hold_seconds'].mean(),
                    'best_hours': self._find_best_trading_hours(closed_trades),
                    'worst_hours': self._find_worst_trading_hours(closed_trades),
                    'optimal_hold_time': self._find_optimal_hold_time(closed_trades)
                },
                
                # Pattern recognition
                'patterns': {
                    'winning_patterns': self._identify_winning_patterns(closed_trades),
                    'losing_patterns': self._identify_losing_patterns(closed_trades),
                    'market_conditions': self._analyze_market_conditions(closed_trades)
                },
                
                # Risk metrics
                'risk_metrics': {
                    'value_at_risk': self._calculate_var(closed_trades),
                    'expected_shortfall': self._calculate_expected_shortfall(closed_trades),
                    'risk_adjusted_return': self._calculate_risk_adjusted_return(closed_trades)
                }
            }
            
            # Save analysis
            self._save_analysis(analysis)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing trades: {e}")
            return {}
    
    def optimize_strategy(self, analysis: Dict) -> Dict:
        """Optimize strategy based on analysis"""
        if not analysis:
            return self.current_strategy
        
        try:
            new_strategy = self.current_strategy.copy()
            
            # Optimize spread threshold
            if 'spread_analysis' in analysis:
                optimal_spread = analysis['spread_analysis']['optimal_entry_spread']
                if optimal_spread and optimal_spread > 0:
                    # Gradually adjust (20% weight to new value)
                    new_strategy['spread_threshold'] = (
                        0.8 * new_strategy['spread_threshold'] + 
                        0.2 * optimal_spread
                    )
            
            # Optimize exit ratio
            if 'spread_analysis' in analysis:
                optimal_exit = analysis['spread_analysis']['optimal_exit_ratio']
                if optimal_exit and 0.1 < optimal_exit < 0.9:
                    new_strategy['exit_spread_ratio'] = (
                        0.8 * new_strategy['exit_spread_ratio'] + 
                        0.2 * optimal_exit
                    )
            
            # Optimize hold time
            if 'time_analysis' in analysis:
                optimal_hold = analysis['time_analysis']['optimal_hold_time']
                if optimal_hold and optimal_hold > 0:
                    new_strategy['max_hold_time'] = int(optimal_hold)
            
            # Enable time-based trading if clear patterns
            if 'time_analysis' in analysis:
                best_hours = analysis['time_analysis']['best_hours']
                worst_hours = analysis['time_analysis']['worst_hours']
                
                if len(best_hours) >= 2 and len(worst_hours) >= 2:
                    new_strategy['time_based_entry']['enabled'] = True
                    new_strategy['time_based_entry']['best_hours'] = best_hours[:5]
                    new_strategy['time_based_entry']['avoid_hours'] = worst_hours[:3]
            
            # Adjust confidence based on performance
            if 'performance' in analysis:
                win_rate = analysis['performance']['win_rate']
                if win_rate > 0.7:
                    new_strategy['confidence_threshold'] = max(0.6, new_strategy['confidence_threshold'] - 0.05)
                elif win_rate < 0.5:
                    new_strategy['confidence_threshold'] = min(0.9, new_strategy['confidence_threshold'] + 0.05)
            
            # Enable adaptive sizing if consistent profits
            if analysis.get('total_trades_analyzed', 0) > 20:
                if analysis['performance']['win_rate'] > 0.65:
                    new_strategy['adaptive_sizing'] = True
            
            # Save optimized strategy
            self._save_strategy(new_strategy)
            self.current_strategy = new_strategy
            
            # Log improvements
            self._log_strategy_changes(self.current_strategy, new_strategy, analysis)
            
            return new_strategy
            
        except Exception as e:
            logger.error(f"Error optimizing strategy: {e}")
            return self.current_strategy
    
    def get_trade_recommendation(self, opportunity: Dict) -> Dict:
        """Get AI recommendation for a trade opportunity"""
        recommendation = {
            'should_trade': False,
            'confidence': 0.0,
            'trade_size_multiplier': 1.0,
            'reasons': [],
            'warnings': []
        }
        
        try:
            # Check basic thresholds
            if opportunity['spread'] >= self.current_strategy['spread_threshold']:
                recommendation['confidence'] += 0.3
                recommendation['reasons'].append(f"Spread {opportunity['spread']:.2%} exceeds threshold")
            
            # Check time-based filters
            current_hour = datetime.now().hour
            if self.current_strategy['time_based_entry']['enabled']:
                if current_hour in self.current_strategy['time_based_entry']['best_hours']:
                    recommendation['confidence'] += 0.2
                    recommendation['reasons'].append(f"Trading in optimal hour ({current_hour}:00)")
                elif current_hour in self.current_strategy['time_based_entry']['avoid_hours']:
                    recommendation['confidence'] -= 0.3
                    recommendation['warnings'].append(f"Poor historical performance at {current_hour}:00")
            
            # Check recent performance
            recent_analysis = self._get_recent_performance()
            if recent_analysis:
                if recent_analysis['recent_win_rate'] > 0.7:
                    recommendation['confidence'] += 0.1
                    recommendation['reasons'].append("Strong recent performance")
                elif recent_analysis['recent_win_rate'] < 0.3:
                    recommendation['confidence'] -= 0.2
                    recommendation['warnings'].append("Poor recent performance")
            
            # Check market conditions
            market_conditions = self._assess_current_market_conditions(opportunity)
            recommendation['confidence'] += market_conditions['confidence_adjustment']
            if market_conditions['favorable']:
                recommendation['reasons'].append(market_conditions['reason'])
            else:
                recommendation['warnings'].append(market_conditions['reason'])
            
            # Final decision
            if recommendation['confidence'] >= self.current_strategy['confidence_threshold']:
                recommendation['should_trade'] = True
                
                # Adjust size based on confidence
                if self.current_strategy['adaptive_sizing']:
                    if recommendation['confidence'] > 0.8:
                        recommendation['trade_size_multiplier'] = 1.5
                    elif recommendation['confidence'] > 0.9:
                        recommendation['trade_size_multiplier'] = 2.0
            
            return recommendation
            
        except Exception as e:
            logger.error(f"Error getting trade recommendation: {e}")
            return recommendation
    
    def _calculate_sharpe_ratio(self, trades: pd.DataFrame) -> float:
        """Calculate Sharpe ratio"""
        if len(trades) < 2:
            return 0.0
        returns = trades['profit_percent'].values
        return np.mean(returns) / (np.std(returns) + 1e-6) * np.sqrt(252)  # Annualized
    
    def _calculate_max_drawdown(self, trades: pd.DataFrame) -> float:
        """Calculate maximum drawdown"""
        cumulative = trades['net_profit'].cumsum()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / (running_max + 1e-6)
        return drawdown.min()
    
    def _calculate_profit_factor(self, trades: pd.DataFrame) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        profits = trades[trades['net_profit'] > 0]['net_profit'].sum()
        losses = abs(trades[trades['net_profit'] < 0]['net_profit'].sum())
        return profits / (losses + 1e-6)
    
    def _find_optimal_spread(self, trades: pd.DataFrame, spread_type: str) -> float:
        """Find optimal entry or exit spread"""
        spread_col = f'{spread_type}_spread'
        
        # Group by spread buckets and calculate win rate
        trades['spread_bucket'] = pd.cut(trades[spread_col], bins=20)
        bucket_performance = trades.groupby('spread_bucket').agg({
            'net_profit': ['mean', 'count', lambda x: (x > 0).mean()]
        })
        
        # Find bucket with best risk-adjusted return
        bucket_performance.columns = ['avg_profit', 'count', 'win_rate']
        bucket_performance = bucket_performance[bucket_performance['count'] >= 3]  # Min samples
        
        if not bucket_performance.empty:
            # Score = win_rate * avg_profit
            bucket_performance['score'] = bucket_performance['win_rate'] * bucket_performance['avg_profit']
            best_bucket = bucket_performance['score'].idxmax()
            return best_bucket.mid
        
        return trades[spread_col].mean()
    
    def _find_optimal_exit_ratio(self, trades: pd.DataFrame) -> float:
        """Find optimal exit spread ratio"""
        trades['exit_ratio'] = trades['exit_spread'] / trades['entry_spread']
        
        # Find ratio that maximizes profit
        ratios = np.linspace(0.1, 0.9, 20)
        profits = []
        
        for ratio in ratios:
            simulated_profits = []
            for _, trade in trades.iterrows():
                # Simulate exit at this ratio
                sim_exit_spread = trade['entry_spread'] * ratio
                spread_captured = trade['entry_spread'] - sim_exit_spread
                sim_profit = spread_captured * trade['trade_size'] - trade['fees']['total_fees']
                simulated_profits.append(sim_profit)
            profits.append(np.mean(simulated_profits))
        
        optimal_idx = np.argmax(profits)
        return ratios[optimal_idx]
    
    def _find_optimal_hold_time(self, trades: pd.DataFrame) -> float:
        """Find optimal holding time in seconds"""
        # Group by hold time buckets
        trades['time_bucket'] = pd.cut(trades['hold_seconds'], bins=10)
        time_performance = trades.groupby('time_bucket').agg({
            'profit_percent': 'mean',
            'net_profit': 'count'
        })
        
        time_performance = time_performance[time_performance['net_profit'] >= 2]
        if not time_performance.empty:
            best_bucket = time_performance['profit_percent'].idxmax()
            return best_bucket.mid
        
        return trades['hold_seconds'].median()
    
    def _find_best_trading_hours(self, trades: pd.DataFrame) -> List[int]:
        """Find most profitable trading hours"""
        hourly_performance = trades.groupby('hour').agg({
            'net_profit': ['mean', 'count', lambda x: (x > 0).mean()]
        })
        hourly_performance.columns = ['avg_profit', 'count', 'win_rate']
        
        # Filter hours with enough samples
        hourly_performance = hourly_performance[hourly_performance['count'] >= 2]
        
        # Score by win rate and average profit
        hourly_performance['score'] = (
            hourly_performance['win_rate'] * 0.6 + 
            hourly_performance['avg_profit'] / hourly_performance['avg_profit'].max() * 0.4
        )
        
        return hourly_performance.nlargest(5, 'score').index.tolist()
    
    def _find_worst_trading_hours(self, trades: pd.DataFrame) -> List[int]:
        """Find least profitable trading hours"""
        hourly_performance = trades.groupby('hour').agg({
            'net_profit': ['mean', 'count', lambda x: (x > 0).mean()]
        })
        hourly_performance.columns = ['avg_profit', 'count', 'win_rate']
        
        # Filter hours with enough samples
        hourly_performance = hourly_performance[hourly_performance['count'] >= 2]
        
        # Score by win rate and average profit
        hourly_performance['score'] = (
            hourly_performance['win_rate'] * 0.6 + 
            hourly_performance['avg_profit'] / (hourly_performance['avg_profit'].max() + 1e-6) * 0.4
        )
        
        return hourly_performance.nsmallest(3, 'score').index.tolist()
    
    def _identify_winning_patterns(self, trades: pd.DataFrame) -> Dict:
        """Identify patterns in winning trades"""
        winning_trades = trades[trades['net_profit'] > 0]
        
        if winning_trades.empty:
            return {}
        
        return {
            'avg_entry_spread': winning_trades['entry_spread'].mean(),
            'avg_hold_time': winning_trades['hold_seconds'].mean(),
            'common_hours': winning_trades['hour'].mode().tolist()[:3],
            'avg_spread_captured': (winning_trades['entry_spread'] - winning_trades['exit_spread']).mean()
        }
    
    def _identify_losing_patterns(self, trades: pd.DataFrame) -> Dict:
        """Identify patterns in losing trades"""
        losing_trades = trades[trades['net_profit'] <= 0]
        
        if losing_trades.empty:
            return {}
        
        return {
            'avg_entry_spread': losing_trades['entry_spread'].mean(),
            'avg_hold_time': losing_trades['hold_seconds'].mean(),
            'common_hours': losing_trades['hour'].mode().tolist()[:3],
            'avg_spread_lost': (losing_trades['entry_spread'] - losing_trades['exit_spread']).mean()
        }
    
    def _analyze_market_conditions(self, trades: pd.DataFrame) -> Dict:
        """Analyze market conditions during trades"""
        # Calculate spread volatility for each trade
        trades['spread_volatility'] = trades.groupby(pd.Grouper(freq='H'))['entry_spread'].transform('std')
        
        return {
            'high_volatility_performance': trades[trades['spread_volatility'] > trades['spread_volatility'].median()]['net_profit'].mean(),
            'low_volatility_performance': trades[trades['spread_volatility'] <= trades['spread_volatility'].median()]['net_profit'].mean(),
            'optimal_volatility_range': self._find_optimal_volatility_range(trades)
        }
    
    def _find_optimal_volatility_range(self, trades: pd.DataFrame) -> Tuple[float, float]:
        """Find optimal volatility range for trading"""
        if 'spread_volatility' not in trades.columns:
            return (0.001, 0.01)
        
        # Quartile analysis
        q1 = trades['spread_volatility'].quantile(0.25)
        q3 = trades['spread_volatility'].quantile(0.75)
        
        # Check performance in different ranges
        mid_vol_trades = trades[(trades['spread_volatility'] >= q1) & (trades['spread_volatility'] <= q3)]
        
        if len(mid_vol_trades) > 5:
            if mid_vol_trades['net_profit'].mean() > trades['net_profit'].mean():
                return (q1, q3)
        
        return (trades['spread_volatility'].min(), trades['spread_volatility'].max())
    
    def _calculate_var(self, trades: pd.DataFrame, confidence: float = 0.95) -> float:
        """Calculate Value at Risk"""
        returns = trades['profit_percent'].values
        return np.percentile(returns, (1 - confidence) * 100)
    
    def _calculate_expected_shortfall(self, trades: pd.DataFrame, confidence: float = 0.95) -> float:
        """Calculate Expected Shortfall (CVaR)"""
        var = self._calculate_var(trades, confidence)
        returns = trades['profit_percent'].values
        return returns[returns <= var].mean()
    
    def _calculate_risk_adjusted_return(self, trades: pd.DataFrame) -> float:
        """Calculate risk-adjusted return"""
        total_return = trades['net_profit'].sum()
        max_drawdown = abs(self._calculate_max_drawdown(trades))
        return total_return / (max_drawdown + 1e-6)
    
    def _get_recent_performance(self, hours: int = 24) -> Optional[Dict]:
        """Get performance for recent period"""
        try:
            # Load recent trades
            with open('data/paper_trades.json', 'r') as f:
                data = json.load(f)
                trades = data.get('trades', [])
            
            if not trades:
                return None
            
            # Filter recent trades
            cutoff = datetime.now() - timedelta(hours=hours)
            recent_trades = [
                t for t in trades 
                if datetime.fromisoformat(t['timestamp']) > cutoff and t['status'] == 'CLOSED'
            ]
            
            if not recent_trades:
                return None
            
            wins = len([t for t in recent_trades if t['net_profit'] > 0])
            
            return {
                'recent_win_rate': wins / len(recent_trades),
                'recent_trades': len(recent_trades),
                'recent_profit': sum(t['net_profit'] for t in recent_trades)
            }
            
        except Exception as e:
            logger.error(f"Error getting recent performance: {e}")
            return None
    
    def _assess_current_market_conditions(self, opportunity: Dict) -> Dict:
        """Assess current market conditions"""
        assessment = {
            'favorable': True,
            'confidence_adjustment': 0.0,
            'reason': ''
        }
        
        # Check if spread is unusually high (might be an error)
        if opportunity['spread'] > 0.02:  # 2%
            assessment['favorable'] = False
            assessment['confidence_adjustment'] = -0.5
            assessment['reason'] = 'Abnormally high spread - possible data error'
        
        # Check if it's a weekend (lower liquidity)
        if datetime.now().weekday() >= 5:
            assessment['confidence_adjustment'] -= 0.1
            assessment['reason'] = 'Weekend - lower liquidity'
        
        return assessment
    
    def _save_analysis(self, analysis: Dict):
        """Save analysis results"""
        try:
            analyses = []
            if os.path.exists(self.analysis_file):
                with open(self.analysis_file, 'r') as f:
                    analyses = json.load(f)
            
            analyses.append(analysis)
            
            # Keep last 100 analyses
            analyses = analyses[-100:]
            
            with open(self.analysis_file, 'w') as f:
                json.dump(analyses, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Error saving analysis: {e}")
    
    def _save_strategy(self, strategy: Dict):
        """Save optimized strategy"""
        try:
            with open(self.strategy_file, 'w') as f:
                json.dump(strategy, f, indent=2)
            logger.info("AI strategy updated and saved")
        except Exception as e:
            logger.error(f"Error saving strategy: {e}")
    
    def _log_strategy_changes(self, old_strategy: Dict, new_strategy: Dict, analysis: Dict):
        """Log strategy changes"""
        changes = []
        
        if old_strategy['spread_threshold'] != new_strategy['spread_threshold']:
            changes.append(
                f"Spread threshold: {old_strategy['spread_threshold']:.3%} → "
                f"{new_strategy['spread_threshold']:.3%}"
            )
        
        if old_strategy['exit_spread_ratio'] != new_strategy['exit_spread_ratio']:
            changes.append(
                f"Exit ratio: {old_strategy['exit_spread_ratio']:.1%} → "
                f"{new_strategy['exit_spread_ratio']:.1%}"
            )
        
        if changes:
            logger.info(f"AI Strategy optimized based on {analysis.get('total_trades_analyzed', 0)} trades:")
            for change in changes:
                logger.info(f"  - {change}")
