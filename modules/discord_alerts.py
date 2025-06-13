"""
Discord Alerts - Comprehensive notification system for trading events
Sends real-time alerts for trades, balance updates, and system status
"""
import os
import json
import logging
import asyncio
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
from enum import Enum
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class AlertType(Enum):
    """Alert type enumeration"""
    TRADE_EXECUTED = "TRADE_EXECUTED"
    TRADE_FAILED = "TRADE_FAILED"
    OPPORTUNITY_DETECTED = "OPPORTUNITY_DETECTED"
    BALANCE_LOW = "BALANCE_LOW"
    BALANCE_UPDATE = "BALANCE_UPDATE"
    SYSTEM_START = "SYSTEM_START"
    SYSTEM_STOP = "SYSTEM_STOP"
    ERROR = "ERROR"
    WARNING = "WARNING"
    DAILY_SUMMARY = "DAILY_SUMMARY"
    PERFORMANCE_UPDATE = "PERFORMANCE_UPDATE"

class AlertPriority(Enum):
    """Alert priority levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

@dataclass
class EmbedField:
    """Discord embed field structure"""
    name: str
    value: str
    inline: bool = True

@dataclass
class DiscordEmbed:
    """Discord embed structure"""
    title: str
    description: str
    color: int
    fields: List[EmbedField]
    footer: Optional[str] = None
    thumbnail_url: Optional[str] = None
    timestamp: Optional[str] = None

class DiscordAlerts:
    def __init__(self, config: dict):
        self.config = config
        
        # Discord webhook configuration
        self.webhook_url = config.get('DISCORD_WEBHOOK_URL')
        self.bot_name = config.get('BOT_NAME', 'Drift-Binance Arbitrage Bot')
        self.environment = config.get('ENVIRONMENT', 'DEVELOPMENT')
        
        # Alert settings
        self.enabled = config.get('ALERTS_ENABLED', True) and bool(self.webhook_url)
        self.rate_limit_enabled = config.get('RATE_LIMIT_ENABLED', True)
        self.max_alerts_per_minute = config.get('MAX_ALERTS_PER_MINUTE', 10)
        self.min_alert_interval = config.get('MIN_ALERT_INTERVAL', 5)  # seconds
        
        # Alert filtering
        self.min_priority = AlertPriority(config.get('MIN_ALERT_PRIORITY', 'LOW'))
        self.enabled_alert_types = set(config.get('ENABLED_ALERT_TYPES', [
            'TRADE_EXECUTED', 'TRADE_FAILED', 'BALANCE_LOW', 'SYSTEM_START', 
            'SYSTEM_STOP', 'ERROR', 'DAILY_SUMMARY'
        ]))
        
        # Rate limiting tracking
        self.alert_timestamps = []
        self.last_alert_time = {}
        self.alert_counts = {}
        
        # Message templates
        self.color_map = {
            AlertType.TRADE_EXECUTED: 0x00FF00,    # Green
            AlertType.TRADE_FAILED: 0xFF0000,      # Red
            AlertType.OPPORTUNITY_DETECTED: 0xFFFF00,  # Yellow
            AlertType.BALANCE_LOW: 0xFF6600,        # Orange
            AlertType.BALANCE_UPDATE: 0x0099FF,     # Blue
            AlertType.SYSTEM_START: 0x00FFFF,       # Cyan
            AlertType.SYSTEM_STOP: 0x9900FF,        # Purple
            AlertType.ERROR: 0xFF0000,              # Red
            AlertType.WARNING: 0xFFCC00,            # Orange-Yellow
            AlertType.DAILY_SUMMARY: 0x6666FF,      # Light Blue
            AlertType.PERFORMANCE_UPDATE: 0x99FF99  # Light Green
        }
        
        # Emoji mapping
        self.emoji_map = {
            AlertType.TRADE_EXECUTED: "✅",
            AlertType.TRADE_FAILED: "❌",
            AlertType.OPPORTUNITY_DETECTED: "🎯",
            AlertType.BALANCE_LOW: "⚠️",
            AlertType.BALANCE_UPDATE: "💰",
            AlertType.SYSTEM_START: "🚀",
            AlertType.SYSTEM_STOP: "🛑",
            AlertType.ERROR: "🚨",
            AlertType.WARNING: "⚠️",
            AlertType.DAILY_SUMMARY: "📊",
            AlertType.PERFORMANCE_UPDATE: "📈"
        }
        
        if self.enabled:
            logger.info(f"Discord alerts enabled - Webhook configured")
        else:
            logger.warning(f"Discord alerts disabled - No webhook URL provided")
    
    def _should_send_alert(self, alert_type: AlertType, priority: AlertPriority) -> bool:
        """Check if alert should be sent based on filters and rate limits"""
        if not self.enabled:
            return False
        
        # Check if alert type is enabled
        if alert_type.value not in self.enabled_alert_types:
            return False
        
        # Check priority filter
        priority_order = {AlertPriority.LOW: 0, AlertPriority.MEDIUM: 1, 
                         AlertPriority.HIGH: 2, AlertPriority.CRITICAL: 3}
        if priority_order[priority] < priority_order[self.min_priority]:
            return False
        
        # Check rate limiting
        if self.rate_limit_enabled:
            current_time = datetime.now().timestamp()
            
            # Clean old timestamps (older than 1 minute)
            self.alert_timestamps = [t for t in self.alert_timestamps if current_time - t < 60]
            
            # Check max alerts per minute
            if len(self.alert_timestamps) >= self.max_alerts_per_minute:
                logger.warning(f"Rate limit reached: {len(self.alert_timestamps)} alerts in last minute")
                return False
            
            # Check minimum interval for this alert type
            alert_key = alert_type.value
            if alert_key in self.last_alert_time:
                time_since_last = current_time - self.last_alert_time[alert_key]
                if time_since_last < self.min_alert_interval:
                    return False
            
            # Update tracking
            self.alert_timestamps.append(current_time)
            self.last_alert_time[alert_key] = current_time
        
        return True
    
    async def send_trade_executed_alert(self, trade_data: Dict, execution_result: Dict) -> bool:
        """Send alert for successful trade execution"""
        if not self._should_send_alert(AlertType.TRADE_EXECUTED, AlertPriority.HIGH):
            return False
        
        pair = trade_data.get('pair', 'Unknown')
        net_pnl = execution_result.get('net_pnl', 0.0)
        spread = trade_data.get('spread', 0.0)
        position_size = trade_data.get('position_size', 0.0)
        
        # Determine profit/loss emoji
        pnl_emoji = "🟢" if net_pnl > 0 else "🔴" if net_pnl < 0 else "⚪"
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.TRADE_EXECUTED]} Trade Executed - {pair}",
            description=f"Arbitrage trade completed successfully",
            color=self.color_map[AlertType.TRADE_EXECUTED],
            fields=[
                EmbedField("💹 P&L", f"{pnl_emoji} ${net_pnl:.2f}", True),
                EmbedField("📊 Spread", f"{spread:.3%}", True),
                EmbedField("💰 Size", f"${position_size:.2f}", True),
                EmbedField("⏱️ Duration", f"{execution_result.get('execution_time_seconds', 0):.1f}s", True),
                EmbedField("🏪 Exchanges", "Binance ↔️ Drift", True),
                EmbedField("🎯 ROI", f"{execution_result.get('roi_percent', 0):.2f}%", True)
            ],
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        # Add order details if available
        if 'binance_order' in execution_result:
            binance_order = execution_result['binance_order']
            embed.fields.append(
                EmbedField("🅱️ Binance Order", 
                          f"ID: `{binance_order.get('orderId', 'N/A')}`\n"
                          f"Status: {binance_order.get('status', 'Unknown')}", False)
            )
        
        if 'drift_order' in execution_result:
            drift_order = execution_result['drift_order']
            embed.fields.append(
                EmbedField("🌊 Drift Order", 
                          f"ID: `{drift_order.get('orderId', 'N/A')}`\n"
                          f"Side: {drift_order.get('side', 'Unknown')}", False)
            )
        
        return await self._send_embed(embed)
    
    async def send_trade_failed_alert(self, trade_data: Dict, error: str) -> bool:
        """Send alert for failed trade execution"""
        if not self._should_send_alert(AlertType.TRADE_FAILED, AlertPriority.HIGH):
            return False
        
        pair = trade_data.get('pair', 'Unknown')
        spread = trade_data.get('spread', 0.0)
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.TRADE_FAILED]} Trade Failed - {pair}",
            description=f"Arbitrage trade execution failed",
            color=self.color_map[AlertType.TRADE_FAILED],
            fields=[
                EmbedField("📊 Spread", f"{spread:.3%}", True),
                EmbedField("💰 Size", f"${trade_data.get('position_size', 0):.2f}", True),
                EmbedField("⏰ Time", datetime.now().strftime('%H:%M:%S'), True),
                EmbedField("❌ Error", error[:1000], False)  # Limit error message length
            ],
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    async def send_opportunity_detected_alert(self, opportunity: Dict) -> bool:
        """Send alert for detected arbitrage opportunity"""
        if not self._should_send_alert(AlertType.OPPORTUNITY_DETECTED, AlertPriority.MEDIUM):
            return False
        
        pair = opportunity.get('pair', 'Unknown')
        spread = opportunity.get('spread', 0.0)
        profit = opportunity.get('potential_profit_usdc', 0.0)
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.OPPORTUNITY_DETECTED]} Opportunity Detected - {pair}",
            description=f"Arbitrage opportunity found",
            color=self.color_map[AlertType.OPPORTUNITY_DETECTED],
            fields=[
                EmbedField("📊 Spread", f"{spread:.3%}", True),
                EmbedField("💰 Potential Profit", f"${profit:.2f}", True),
                EmbedField("💹 Spot Price", f"${opportunity.get('spot_price', 0):.4f}", True),
                EmbedField("🌊 Perp Price", f"${opportunity.get('perp_price', 0):.4f}", True),
                EmbedField("🎯 Entry Threshold", f"{self.config.get('MIN_SPREAD_THRESHOLD', 0.004):.3%}", True),
                EmbedField("⏰ Detected", datetime.now().strftime('%H:%M:%S'), True)
            ],
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    async def send_balance_low_alert(self, current_balance: float, min_balance: float) -> bool:
        """Send alert for low balance warning"""
        if not self._should_send_alert(AlertType.BALANCE_LOW, AlertPriority.CRITICAL):
            return False
        
        percentage_remaining = (current_balance / min_balance) * 100 if min_balance > 0 else 0
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.BALANCE_LOW]} Low Balance Warning",
            description=f"Trading balance is below minimum threshold",
            color=self.color_map[AlertType.BALANCE_LOW],
            fields=[
                EmbedField("💰 Current Balance", f"${current_balance:.2f}", True),
                EmbedField("⚠️ Minimum Required", f"${min_balance:.2f}", True),
                EmbedField("📊 Remaining", f"{percentage_remaining:.1f}%", True),
                EmbedField("🚨 Action Required", "Please top up trading account", False)
            ],
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    async def send_balance_update_alert(self, balance_data: Dict) -> bool:
        """Send balance update alert"""
        if not self._should_send_alert(AlertType.BALANCE_UPDATE, AlertPriority.LOW):
            return False
        
        current = balance_data.get('current_balance', 0.0)
        starting = balance_data.get('starting_balance', 0.0)
        change = current - starting
        roi = (change / starting * 100) if starting > 0 else 0
        
        change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.BALANCE_UPDATE]} Balance Update",
            description=f"Current trading balance status",
            color=self.color_map[AlertType.BALANCE_UPDATE],
            fields=[
                EmbedField("💰 Current Balance", f"${current:.2f}", True),
                EmbedField("📊 Starting Balance", f"${starting:.2f}", True),
                EmbedField(f"{change_emoji} Total Change", f"${change:+.2f}", True),
                EmbedField("🎯 ROI", f"{roi:+.2f}%", True),
                EmbedField("📈 Total Trades", f"{balance_data.get('total_trades', 0)}", True),
                EmbedField("🏆 Win Rate", f"{balance_data.get('win_rate', 0)*100:.1f}%", True)
            ],
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    async def send_system_start_alert(self, config_summary: Dict) -> bool:
        """Send system startup alert"""
        if not self._should_send_alert(AlertType.SYSTEM_START, AlertPriority.MEDIUM):
            return False
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.SYSTEM_START]} Bot Started",
            description=f"Arbitrage bot has started successfully",
            color=self.color_map[AlertType.SYSTEM_START],
            fields=[
                EmbedField("🌍 Environment", self.environment, True),
                EmbedField("💰 Starting Balance", f"${config_summary.get('starting_balance', 0):.2f}", True),
                EmbedField("📊 Spread Threshold", f"{config_summary.get('spread_threshold', 0):.3%}", True),
                EmbedField("💱 Pairs Monitored", f"{config_summary.get('pairs_count', 0)}", True),
                EmbedField("🎯 Trading Mode", config_summary.get('trading_mode', 'Unknown'), True),
                EmbedField("⏰ Started", datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), True)
            ],
            footer=f"{self.bot_name} • Version {config_summary.get('version', '1.0')}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    async def send_system_stop_alert(self, reason: str = "Manual stop") -> bool:
        """Send system shutdown alert"""
        if not self._should_send_alert(AlertType.SYSTEM_STOP, AlertPriority.MEDIUM):
            return False
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.SYSTEM_STOP]} Bot Stopped",
            description=f"Arbitrage bot has been stopped",
            color=self.color_map[AlertType.SYSTEM_STOP],
            fields=[
                EmbedField("🛑 Reason", reason, True),
                EmbedField("⏰ Stopped", datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), True),
                EmbedField("🌍 Environment", self.environment, True)
            ],
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    async def send_error_alert(self, error_message: str, error_type: str = "General Error") -> bool:
        """Send error alert"""
        if not self._should_send_alert(AlertType.ERROR, AlertPriority.HIGH):
            return False
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.ERROR]} Error Detected",
            description=f"System error occurred",
            color=self.color_map[AlertType.ERROR],
            fields=[
                EmbedField("🚨 Error Type", error_type, True),
                EmbedField("⏰ Time", datetime.now().strftime('%H:%M:%S'), True),
                EmbedField("🌍 Environment", self.environment, True),
                EmbedField("📝 Details", error_message[:1000], False)  # Limit length
            ],
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    async def send_daily_summary_alert(self, summary_data: Dict) -> bool:
        """Send daily trading summary"""
        if not self._should_send_alert(AlertType.DAILY_SUMMARY, AlertPriority.MEDIUM):
            return False
        
        total_pnl = summary_data.get('total_pnl', 0.0)
        trades = summary_data.get('total_trades', 0)
        win_rate = summary_data.get('win_rate', 0.0) * 100
        
        pnl_emoji = "🟢" if total_pnl > 0 else "🔴" if total_pnl < 0 else "⚪"
        
        embed = DiscordEmbed(
            title=f"{self.emoji_map[AlertType.DAILY_SUMMARY]} Daily Summary",
            description=f"Trading performance for {datetime.now().strftime('%Y-%m-%d')}",
            color=self.color_map[AlertType.DAILY_SUMMARY],
            fields=[
                EmbedField("📊 Total Trades", f"{trades}", True),
                EmbedField("🏆 Win Rate", f"{win_rate:.1f}%", True),
                EmbedField(f"{pnl_emoji} Total P&L", f"${total_pnl:+.2f}", True),
                EmbedField("💰 Current Balance", f"${summary_data.get('current_balance', 0):.2f}", True),
                EmbedField("📈 Best Trade", f"${summary_data.get('best_trade', 0):.2f}", True),
                EmbedField("📉 Worst Trade", f"${summary_data.get('worst_trade', 0):.2f}", True),
                EmbedField("💸 Total Fees", f"${summary_data.get('total_fees', 0):.2f}", True),
                EmbedField("🎯 Avg Spread", f"{summary_data.get('avg_spread', 0):.3%}", True),
                EmbedField("⏱️ Avg Hold Time", f"{summary_data.get('avg_hold_time', 0):.0f}s", True)
            ],
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    async def _send_embed(self, embed: DiscordEmbed) -> bool:
        """Send embed to Discord webhook"""
        if not self.webhook_url:
            logger.warning("Cannot send Discord alert: No webhook URL configured")
            return False
        
        payload = {
            "embeds": [{
                "title": embed.title,
                "description": embed.description,
                "color": embed.color,
                "fields": [{"name": f.name, "value": f.value, "inline": f.inline} for f in embed.fields],
                "footer": {"text": embed.footer} if embed.footer else None,
                "thumbnail": {"url": embed.thumbnail_url} if embed.thumbnail_url else None,
                "timestamp": embed.timestamp
            }]
        }
        
        # Remove None values
        payload["embeds"][0] = {k: v for k, v in payload["embeds"][0].items() if v is not None}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 204:
                        logger.debug(f"Discord alert sent successfully: {embed.title}")
                        return True
                    elif response.status == 429:
                        logger.warning("Discord rate limit hit")
                        return False
                    else:
                        logger.error(f"Discord webhook error: {response.status}")
                        return False
                        
        except asyncio.TimeoutError:
            logger.error("Discord webhook timeout")
            return False
        except Exception as e:
            logger.error(f"Discord webhook error: {e}")
            return False
    
    async def send_custom_alert(self, 
                               title: str, 
                               description: str, 
                               fields: List[Dict] = None,
                               color: int = 0x0099FF,
                               priority: AlertPriority = AlertPriority.MEDIUM) -> bool:
        """Send custom alert with specified content"""
        # Use a more permissive check for custom alerts - just check if alerts are enabled
        if not self.enabled:
            return False
        
        # For custom alerts, we'll bypass the strict filtering and just check rate limits
        current_time = datetime.now().timestamp()
        
        # Check rate limiting only
        if self.rate_limit_enabled:
            # Clean old timestamps (older than 1 minute)
            self.alert_timestamps = [t for t in self.alert_timestamps if current_time - t < 60]
            
            # Check max alerts per minute
            if len(self.alert_timestamps) >= self.max_alerts_per_minute:
                logger.warning(f"Rate limit reached: {len(self.alert_timestamps)} alerts in last minute")
                return False
            
            # Update tracking
            self.alert_timestamps.append(current_time)
        
        embed_fields = []
        if fields:
            for field in fields:
                embed_fields.append(EmbedField(
                    name=field.get('name', ''),
                    value=field.get('value', ''),
                    inline=field.get('inline', True)
                ))
        
        embed = DiscordEmbed(
            title=title,
            description=description,
            color=color,
            fields=embed_fields,
            footer=f"{self.bot_name} • {self.environment}",
            timestamp=datetime.now().isoformat()
        )
        
        return await self._send_embed(embed)
    
    def get_alert_stats(self) -> Dict:
        """Get alert statistics"""
        current_time = datetime.now().timestamp()
        
        # Clean old timestamps
        self.alert_timestamps = [t for t in self.alert_timestamps if current_time - t < 3600]  # Last hour
        
        return {
            'enabled': self.enabled,
            'webhook_configured': bool(self.webhook_url),
            'alerts_sent_last_hour': len(self.alert_timestamps),
            'rate_limit_enabled': self.rate_limit_enabled,
            'max_alerts_per_minute': self.max_alerts_per_minute,
            'enabled_alert_types': list(self.enabled_alert_types),
            'min_priority': self.min_priority.value,
            'last_alert_times': {k: datetime.fromtimestamp(v).isoformat() 
                               for k, v in self.last_alert_time.items()},
            'environment': self.environment
        }
    
    def update_config(self, new_config: Dict):
        """Update alert configuration"""
        if 'ALERTS_ENABLED' in new_config:
            self.enabled = new_config['ALERTS_ENABLED'] and bool(self.webhook_url)
        
        if 'MAX_ALERTS_PER_MINUTE' in new_config:
            self.max_alerts_per_minute = new_config['MAX_ALERTS_PER_MINUTE']
        
        if 'MIN_ALERT_PRIORITY' in new_config:
            self.min_priority = AlertPriority(new_config['MIN_ALERT_PRIORITY'])
        
        if 'ENABLED_ALERT_TYPES' in new_config:
            self.enabled_alert_types = set(new_config['ENABLED_ALERT_TYPES'])
        
        logger.info("Discord alerts configuration updated")
    
    def enable_alert_type(self, alert_type: str):
        """Enable specific alert type"""
        self.enabled_alert_types.add(alert_type)
        logger.info(f"Enabled alert type: {alert_type}")
    
    def disable_alert_type(self, alert_type: str):
        """Disable specific alert type"""
        self.enabled_alert_types.discard(alert_type)
        logger.info(f"Disabled alert type: {alert_type}")
    
    def reset_rate_limits(self):
        """Reset all rate limiting counters"""
        self.alert_timestamps.clear()
        self.last_alert_time.clear()
        logger.info("Discord alert rate limits reset")
