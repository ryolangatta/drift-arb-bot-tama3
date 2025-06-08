#!/usr/bin/env python3
"""
Drift-Binance Arbitrage Bot - With Test Network Trading
"""
import os
import sys
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
from modules.binance_testnet_simple import BinanceTestnetSimple

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
        self.enable_testnet = os.getenv('ENABLE_TESTNET_TRADING', 'false').lower() == 'true'
        
        # Load settings
        with open('config/settings.json', 'r') as f:
            self.settings = json.load(f)
        
        # Initialize modules
        self.price_feed = PriceFeed(self.settings)
        self.arb_detector = ArbitrageDetector(self.settings)
        
        # Initialize testnet if enabled
        self.testnet = None
        if self.enable_testnet:
            logger.info("Initializing Binance Testnet connection...")
            self.testnet = BinanceTestnetSimple()
        
        # Get pairs to monitor
        self.pairs_to_monitor = self.settings['TRADING_CONFIG']['PAIRS_TO_MONITOR']
        
        # Track positions
        self.open_positions = {}
        
        logger.info(f"Bot initialized - Mode: {self.mode} | Testnet: {'ENABLED' if self.enable_testnet else 'DISABLED'}")
    
    def send_startup_message(self):
        """Send startup notification to Discord"""
        if not self.webhook_url:
            logger.warning("No Discord webhook URL configured")
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="🚀 Drift Arbitrage Bot Started",
                description=f"Mode: **{self.mode}**\nTestnet: **{'ENABLED' if self.enable_testnet else 'DISABLED'}**",
                color="03b2f8"
            )
            
            embed.add_embed_field(
                name="Configuration",
                value=f"Spread Threshold: {self.settings['TRADING_CONFIG']['SPREAD_THRESHOLD']:.1%}\n" +
                      f"Trade Size: ${self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']}\n" +
                      f"Testnet Connected: {'✅' if self.testnet and self.testnet.connected else '❌'}",
                inline=False
            )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
    
    def send_opportunity_alert(self, opportunity: dict, order=None):
        """Send arbitrage opportunity alert to Discord"""
        if not self.webhook_url:
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            if order:
                # Real order executed
                embed = DiscordEmbed(
                    title="🧪 TESTNET ORDER EXECUTED!",
                    description=f"Real order placed on Binance Testnet",
                    color="9b59b6"
                )
                
                embed.add_embed_field(
                    name="Order Details",
                    value=f"Order ID: `{order['orderId']}`\n" +
                          f"Symbol: {order['symbol']}\n" +
                          f"Status: {order['status']}\n" +
                          f"Executed Qty: {order['executedQty']}",
                    inline=False
                )
            else:
                # Just opportunity detected
                embed = DiscordEmbed(
                    title="🎯 Arbitrage Opportunity Detected!",
                    description=f"**{opportunity['pair']}** - Profitable spread found",
                    color="00ff00"
                )
            
            embed.add_embed_field(
                name="Opportunity",
                value=f"Spread: {opportunity['spread']:.2%}\n" +
                      f"Expected Profit: ${opportunity['potential_profit_usdc']:.2f}",
                inline=True
            )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
    
    async def price_callback(self, pair: str, spot_price: float, perp_price: float):
        """Callback for when new prices are received"""
        # Check for arbitrage opportunity
        opportunity = self.arb_detector.check_arbitrage_opportunity(
            pair, spot_price, perp_price
        )
        
        if opportunity:
            self.send_opportunity_alert(opportunity)
            
            # Execute test order if enabled
            if self.enable_testnet and self.testnet and self.testnet.connected:
                # Calculate quantity
                trade_size_usd = self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']
                quantity = trade_size_usd / spot_price
                
                # Convert symbol (SOL/USDC -> SOLUSDT for testnet)
                symbol = pair.replace("/USDC", "USDT").replace("/", "")
                
                # Place real testnet order
                order = self.testnet.place_test_order(symbol, "BUY", quantity)
                
                if order:
                    # Store position
                    position_id = f"{pair}_{order['orderId']}"
                    self.open_positions[position_id] = {
                        'order': order,
                        'entry_price': spot_price,
                        'quantity': float(order['executedQty']),
                        'timestamp': datetime.now()
                    }
                    
                    # Send alert with order details
                    self.send_opportunity_alert(opportunity, order)
    
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
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            self.shutdown()
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            self.shutdown()
    
    def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down bot...")
        
        if self.webhook_url:
            positions = len(self.open_positions)
            message = f"🛑 Bot shutting down\nOpen positions: {positions}"
            
            if self.enable_testnet:
                message += "\nTestnet orders were REAL (test money)"
            
            webhook = DiscordWebhook(url=self.webhook_url, content=message)
            webhook.execute()

def main():
    """Entry point"""
    try:
        os.makedirs('data/logs', exist_ok=True)
        
        bot = DriftArbBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
