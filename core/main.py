#!/usr/bin/env python3
"""
Drift-Binance Arbitrage Bot - Main Entry Point
"""
import os
import sys
import time
import json
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.price_feed import PriceFeed
from modules.arb_detector import ArbitrageDetector

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('data/logs/bot.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class DriftArbBot:
    def __init__(self):
        self.webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        self.mode = os.getenv('MODE', 'SIMULATION')
        self.env = os.getenv('ENV', 'development')
        
        # Load settings
        with open('config/settings.json', 'r') as f:
            self.settings = json.load(f)
        
        # Initialize modules
        self.price_feed = PriceFeed(self.settings)
        self.arb_detector = ArbitrageDetector(self.settings)
        
        # Get pairs to monitor
        self.pairs_to_monitor = self.settings['TRADING_CONFIG']['PAIRS_TO_MONITOR']
        
        logger.info(f"Bot initialized in {self.mode} mode ({self.env} environment)")
    
    def send_startup_message(self):
        """Send startup notification to Discord"""
        if not self.webhook_url:
            logger.warning("No Discord webhook URL configured")
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="🚀 Drift Arbitrage Bot Started",
                description=f"Mode: **{self.mode}**\nEnvironment: **{self.env}**",
                color="03b2f8"
            )
            
            embed.add_embed_field(
                name="Configuration",
                value=f"Spread Threshold: {self.settings['TRADING_CONFIG']['SPREAD_THRESHOLD']:.1%}\n" +
                      f"Min Profit: {self.settings['TRADING_CONFIG']['MIN_PROFIT_AFTER_FEES']:.1%}\n" +
                      f"Trade Size: ${self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']}\n" +
                      f"Pairs: {', '.join(self.pairs_to_monitor)}",
                inline=False
            )
            
            embed.set_timestamp()
            embed.set_footer(text="Drift Arb Bot v1.0")
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            if response.status_code == 200:
                logger.info("Startup message sent to Discord")
            else:
                logger.error(f"Failed to send Discord message: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
    
    def send_opportunity_alert(self, opportunity: dict):
        """Send arbitrage opportunity alert to Discord"""
        if not self.webhook_url:
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="🎯 Arbitrage Opportunity Detected!",
                description=f"**{opportunity['pair']}** - Profitable spread found",
                color="00ff00"
            )
            
            embed.add_embed_field(
                name="Prices",
                value=f"Binance Spot: ${opportunity['spot_price']:.4f}\n" +
                      f"Drift Perp: ${opportunity['perp_price']:.4f}",
                inline=True
            )
            
            embed.add_embed_field(
                name="Opportunity",
                value=f"Spread: {opportunity['spread']:.2%}\n" +
                      f"Profit/Trade: ${opportunity['potential_profit_usdc']:.2f}",
                inline=True
            )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
        except Exception as e:
            logger.error(f"Error sending opportunity alert: {e}")
    
    async def price_callback(self, pair: str, spot_price: float, perp_price: float):
        """Callback for when new prices are received"""
        # Check for arbitrage opportunity
        opportunity = self.arb_detector.check_arbitrage_opportunity(
            pair, spot_price, perp_price
        )
        
        if opportunity:
            self.send_opportunity_alert(opportunity)
    
    async def run_async(self):
        """Async main loop"""
        logger.info("Starting price monitoring...")
        
        # Start price monitoring
        await self.price_feed.start_price_monitoring(
            self.pairs_to_monitor,
            callback=self.price_callback
        )
    
    def run(self):
        """Main bot loop"""
        self.send_startup_message()
        
        try:
            # Run async event loop
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            self.shutdown()
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            self.shutdown()
    
    def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down bot...")
        
        if self.webhook_url:
            webhook = DiscordWebhook(
                url=self.webhook_url,
                content="🛑 Bot shutting down"
            )
            webhook.execute()

def main():
    """Entry point"""
    try:
        # Create necessary directories
        os.makedirs('data/logs', exist_ok=True)
        
        bot = DriftArbBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
