"""
Create detailed performance graphs
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import io
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class Plotter:
    def __init__(self):
        plt.style.use('seaborn-v0_8-darkgrid')
        self.figure_size = (12, 8)
    
    def create_roi_graph(self, roi_history: List[dict], stats: dict) -> io.BytesIO:
        """Create comprehensive ROI and performance graph"""
        try:
            # Create figure with multiple subplots
            fig = plt.figure(figsize=(14, 10))
            
            # Define grid
            gs = fig.add_gridspec(3, 2, height_ratios=[2, 1, 1], hspace=0.3, wspace=0.3)
            
            # Main ROI plot
            ax1 = fig.add_subplot(gs[0, :])
            
            # Balance plot
            ax2 = fig.add_subplot(gs[1, 0])
            
            # Win rate plot
            ax3 = fig.add_subplot(gs[1, 1])
            
            # Costs breakdown
            ax4 = fig.add_subplot(gs[2, 0])
            
            # Trade distribution
            ax5 = fig.add_subplot(gs[2, 1])
            
            # Prepare data
            if roi_history:
                timestamps = [datetime.fromisoformat(p['timestamp']) for p in roi_history]
                roi_values = [p['roi_percent'] for p in roi_history]
                balances = [p['balance'] for p in roi_history]
                win_rates = [p.get('win_rate', 0) for p in roi_history]
            else:
                timestamps = [datetime.now()]
                roi_values = [0]
                balances = [1000]
                win_rates = [0]
            
            # 1. ROI Chart
            ax1.plot(timestamps, roi_values, 'b-', linewidth=2.5, label='ROI %')
            ax1.fill_between(timestamps, roi_values, alpha=0.3)
            ax1.set_title('📈 Paper Trading ROI Performance ($1,000 Start)', fontsize=16, fontweight='bold')
            ax1.set_ylabel('ROI (%)', fontsize=12)
            ax1.grid(True, alpha=0.3)
            ax1.axhline(y=0, color='black', linestyle='-', alpha=0.5)
            
            # Add ROI target lines
            ax1.axhline(y=10, color='g', linestyle='--', alpha=0.3, label='10% Target')
            ax1.axhline(y=-5, color='r', linestyle='--', alpha=0.3, label='-5% Stop Loss')
            
            # Current ROI annotation
            current_roi = roi_values[-1] if roi_values else 0
            roi_color = 'green' if current_roi > 0 else 'red'
            ax1.text(0.02, 0.98, f'Current ROI: {current_roi:.2f}%', 
                    transform=ax1.transAxes, fontsize=14, fontweight='bold',
                    verticalalignment='top', color=roi_color,
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            
            # 2. Balance Chart
            ax2.plot(timestamps, balances, 'g-', linewidth=2)
            ax2.fill_between(timestamps, balances, alpha=0.3, color='green')
            ax2.set_ylabel('Balance ($)', fontsize=11)
            ax2.set_title('Account Balance', fontsize=12)
            ax2.grid(True, alpha=0.3)
            ax2.axhline(y=1000, color='black', linestyle='--', alpha=0.5, label='Start: $1,000')
            
            # 3. Win Rate Chart
            ax3.plot(timestamps, win_rates, 'orange', linewidth=2)
            ax3.fill_between(timestamps, win_rates, alpha=0.3, color='orange')
            ax3.set_ylabel('Win Rate (%)', fontsize=11)
            ax3.set_title('Win Rate Over Time', fontsize=12)
            ax3.set_ylim(0, 100)
            ax3.grid(True, alpha=0.3)
            ax3.axhline(y=50, color='black', linestyle='--', alpha=0.5)
            
            # 4. Costs Breakdown (if we have trades)
            if stats['total_trades'] > 0:
                costs = [
                    stats.get('total_fees_paid', 0),
                    stats.get('average_slippage', 0) * stats['total_trades']
                ]
                labels = ['Fees', 'Slippage']
                ax4.pie(costs, labels=labels, autopct='%1.1f%%', startangle=90)
                ax4.set_title(f'Total Costs: ${sum(costs):.2f}', fontsize=12)
            else:
                ax4.text(0.5, 0.5, 'No trades yet', ha='center', va='center', fontsize=12)
                ax4.set_title('Cost Breakdown', fontsize=12)
            
            # 5. P&L Distribution
            if stats['total_trades'] > 0:
                win_loss = [stats['winning_trades'], stats['losing_trades']]
                labels = [f"Wins ({stats['winning_trades']})", f"Losses ({stats['losing_trades']})"]
                colors = ['lightgreen', 'lightcoral']
                ax5.pie(win_loss, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
                ax5.set_title('Trade Outcomes', fontsize=12)
            else:
                ax5.text(0.5, 0.5, 'No trades yet', ha='center', va='center', fontsize=12)
                ax5.set_title('Trade Distribution', fontsize=12)
            
            # Format x-axis for time-based plots
            for ax in [ax1, ax2, ax3]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
                plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
            
            # Add comprehensive stats box
            stats_text = (
                f"═══ PERFORMANCE SUMMARY ═══\n"
                f"Starting Capital: $1,000\n"
                f"Current Balance: ${stats['current_balance']:.2f}\n"
                f"Total P&L: ${stats['total_pnl']:.2f}\n"
                f"ROI: {stats['roi']*100:.2f}%\n"
                f"\n"
                f"Total Trades: {stats['total_trades']}\n"
                f"Win Rate: {stats['win_rate']*100:.1f}%\n"
                f"Avg P&L per Trade: ${stats.get('average_pnl', 0):.2f}\n"
                f"Best Trade: ${stats.get('best_trade', 0):.2f}\n"
                f"Worst Trade: ${stats.get('worst_trade', 0):.2f}\n"
                f"\n"
                f"Total Fees Paid: ${stats.get('total_fees_paid', 0):.2f}\n"
                f"Avg Slippage Cost: ${stats.get('average_slippage', 0):.2f}\n"
                f"Avg Hold Time: {stats.get('average_hold_time', 0):.0f}s"
            )
            
            fig.text(0.02, 0.02, stats_text, fontsize=10, family='monospace',
                    bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
            
            plt.suptitle(f'Paper Trading Performance Report - {datetime.now().strftime("%Y-%m-%d %H:%M")}', 
                        fontsize=16, fontweight='bold')
            
            # Save to bytes
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            plt.close()
            
            buf.seek(0)
            return buf
            
        except Exception as e:
            logger.error(f"Error creating ROI graph: {e}")
            return None
