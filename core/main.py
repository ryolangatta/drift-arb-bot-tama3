#!/usr/bin/env python3
"""
Drift-Binance Arbitrage Bot - Main Entry Point
"""
import os
import sys
import time
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed

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
                value=f"Spread Threshold: {self.settings['TRADING_CONFIG']['SPREAD_THRESHOLD']}\n" +
                      f"Trade Size: ${self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']}\n" +
                      f"Pairs: {', '.join(self.settings['TRADING_CONFIG']['PAIRS_TO_MONITOR'])}",
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
    
    def run(self):
        """Main bot loop"""
        self.send_startup_message()
        
        logger.info("Starting main bot loop...")
        loop_count = 0
        
        try:
            while True:
                loop_count += 1
                
                # Log heartbeat every 10 loops (10 minutes)
                if loop_count % 10 == 0:
                    logger.info(f"Bot heartbeat - Loop #{loop_count}")
                    
                    # Send periodic update to Discord
                    if self.webhook_url and loop_count % 30 == 0:  # Every 30 minutes
                        webhook = DiscordWebhook(
                            url=self.webhook_url,
                            content=f"💓 Bot is running - Uptime: {loop_count} minutes"
                        )
                        webhook.execute()
                
                # Sleep for 1 minute
                time.sleep(60)
                
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
