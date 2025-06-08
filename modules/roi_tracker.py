"""
ROI tracking with detailed history
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

class ROITracker:
    def __init__(self, config: dict):
        self.config = config
        self.roi_history_file = 'data/roi_history.json'
        self.roi_history = []
        self.load_history()
    
    def load_history(self):
        """Load ROI history from file"""
        try:
            if os.path.exists(self.roi_history_file):
                with open(self.roi_history_file, 'r') as f:
                    self.roi_history = json.load(f)
                logger.info(f"Loaded {len(self.roi_history)} ROI data points")
        except Exception as e:
            logger.error(f"Error loading ROI history: {e}")
    
    def save_history(self):
        """Save ROI history to file"""
        try:
            os.makedirs(os.path.dirname(self.roi_history_file), exist_ok=True)
            with open(self.roi_history_file, 'w') as f:
                json.dump(self.roi_history, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving ROI history: {e}")
    
    def record_datapoint(self, stats: dict):
        """Record comprehensive performance datapoint"""
        datapoint = {
            'timestamp': datetime.now().isoformat(),
            'balance': stats['current_balance'],
            'roi_percent': stats['roi'] * 100,
            'total_pnl': stats['total_pnl'],
            'total_trades': stats['total_trades'],
            'win_rate': stats['win_rate'] * 100,
            'total_fees': stats.get('total_fees_paid', 0),
            'avg_slippage': stats.get('average_slippage', 0)
        }
        
        self.roi_history.append(datapoint)
        self.save_history()
        
        # Keep only last 7 days of 10-minute data
        if len(self.roi_history) > 1008:
            self.roi_history = self.roi_history[-1008:]
    
    def get_history_for_period(self, hours: int = 24) -> List[dict]:
        """Get ROI history for specified period"""
        if not self.roi_history:
            return []
        
        cutoff = datetime.now().timestamp() - (hours * 3600)
        
        return [
            point for point in self.roi_history
            if datetime.fromisoformat(point['timestamp']).timestamp() > cutoff
        ]
