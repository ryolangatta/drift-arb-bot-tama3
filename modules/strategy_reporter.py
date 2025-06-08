"""
Generate detailed strategy reports for Discord
"""
import logging
from typing import Dict, List
from discord_webhook import DiscordWebhook, DiscordEmbed
from datetime import datetime

logger = logging.getLogger(__name__)

class StrategyReporter:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def send_ai_analysis_report(self, analysis: Dict, strategy: Dict):
        """Send comprehensive AI analysis report to Discord"""
        if not self.webhook_url:
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            # Main analysis embed
            embed = DiscordEmbed(
                title="🤖 AI Strategy Analysis Report",
                description="Machine Learning Analysis of Trading Performance",
                color="9b59b6"
            )
            
            # Performance summary
            if 'performance' in analysis:
                perf = analysis['performance']
                embed.add_embed_field(
                    name="📊 Performance Metrics",
                    value=f"Win Rate: {perf['win_rate']*100:.1f}%\n"
                          f"Sharpe Ratio: {perf['sharpe_ratio']:.2f}\n"
                          f"Profit Factor: {perf['profit_factor']:.2f}\n"
                          f"Max Drawdown: {perf['max_drawdown']*100:.1f}%",
                    inline=True
                )
            
            # Optimal parameters
            if 'spread_analysis' in analysis:
                spread = analysis['spread_analysis']
                embed.add_embed_field(
                    name="🎯 Optimal Parameters",
                    value=f"Entry Spread: {spread['optimal_entry_spread']*100:.3f}%\n"
                          f"Exit Ratio: {spread['optimal_exit_ratio']*100:.1f}%\n"
                          f"Current Threshold: {strategy['spread_threshold']*100:.3f}%",
                    inline=True
                )
            
            # Time analysis
            if 'time_analysis' in analysis:
                time_data = analysis['time_analysis']
                best_hours = time_data.get('best_hours', [])[:3]
                worst_hours = time_data.get('worst_hours', [])[:3]
                
                time_str = f"Avg Hold: {time_data['avg_hold_time_seconds']:.0f}s\n"
                if best_hours:
                    time_str += f"Best Hours: {', '.join(f'{h}:00' for h in best_hours)}\n"
                if worst_hours:
                    time_str += f"Avoid Hours: {', '.join(f'{h}:00' for h in worst_hours)}"
                
                embed.add_embed_field(
                    name="⏰ Time Analysis",
                    value=time_str,
                    inline=False
                )
            
            # Pattern insights
            if 'patterns' in analysis:
                patterns = analysis['patterns']
                insights = []
                
                if 'winning_patterns' in patterns and patterns['winning_patterns']:
                    win_p = patterns['winning_patterns']
                    insights.append(f"✅ Winners avg spread: {win_p.get('avg_entry_spread', 0)*100:.3f}%")
                
                if 'losing_patterns' in patterns and patterns['losing_patterns']:
                    lose_p = patterns['losing_patterns']
                    insights.append(f"❌ Losers avg spread: {lose_p.get('avg_entry_spread', 0)*100:.3f}%")
                
                if insights:
                    embed.add_embed_field(
                        name="🔍 Pattern Recognition",
                        value='\n'.join(insights),
                        inline=False
                    )
            
            # Strategy adjustments
            if strategy:
                adj_str = f"Spread Threshold: {strategy['spread_threshold']*100:.3f}%\n"
                adj_str += f"Exit Ratio: {strategy['exit_spread_ratio']*100:.1f}%\n"
                adj_str += f"Max Hold Time: {strategy['max_hold_time']}s\n"
                
                if strategy.get('time_based_entry', {}).get('enabled'):
                    adj_str += "📅 Time-based filtering: ENABLED"
                
                embed.add_embed_field(
                    name="🔧 Active Strategy Settings",
                    value=adj_str,
                    inline=False
                )
            
            embed.set_timestamp()
            embed.set_footer(text=f"Based on {analysis.get('total_trades_analyzed', 0)} trades")
            
            webhook.add_embed(embed)
            webhook.execute()
            
            logger.info("AI analysis report sent to Discord")
            
        except Exception as e:
            logger.error(f"Error sending AI analysis report: {e}")
    
    def send_trade_recommendation(self, opportunity: Dict, recommendation: Dict):
        """Send AI trade recommendation to Discord"""
        if not self.webhook_url:
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            # Color based on recommendation
            color = "00ff00" if recommendation['should_trade'] else "ff0000"
            
            embed = DiscordEmbed(
                title=f"🤖 AI Trade Recommendation: {opportunity['pair']}",
                description=f"Confidence: {recommendation['confidence']*100:.1f}%",
                color=color
            )
            
            # Opportunity details
            embed.add_embed_field(
                name="📊 Opportunity",
                value=f"Spread: {opportunity['spread']*100:.3f}%\n"
                      f"Potential Profit: ${opportunity['potential_profit_usdc']:.2f}",
                inline=True
            )
            
            # AI decision
            decision = "✅ TRADE" if recommendation['should_trade'] else "❌ SKIP"
            size_mult = recommendation['trade_size_multiplier']
            
            embed.add_embed_field(
                name="🎯 AI Decision",
                value=f"Action: {decision}\n"
                      f"Size Multiplier: {size_mult}x",
                inline=True
            )
            
            # Reasons
            if recommendation['reasons']:
                embed.add_embed_field(
                    name="✅ Positive Factors",
                    value='\n'.join(f"• {r}" for r in recommendation['reasons'][:3]),
                    inline=False
                )
            
            # Warnings
            if recommendation['warnings']:
                embed.add_embed_field(
                    name="⚠️ Risk Factors",
                    value='\n'.join(f"• {w}" for w in recommendation['warnings'][:3]),
                    inline=False
                )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
        except Exception as e:
            logger.error(f"Error sending trade recommendation: {e}")
