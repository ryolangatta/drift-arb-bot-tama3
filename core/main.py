#!/usr/bin/env python3
"""
Drift-Binance Arbitrage Bot - Complete Test Network Trading
"""
import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed

# Add parent directory to path for module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.price_feed import PriceFeed
from modules.arb_detector import ArbitrageDetector
from modules.binance_testnet_simple import BinanceTestnetSimple
from modules.drift_devnet_simple import DriftDevnetSimple
from modules.drift_integration import DriftIntegration

# Load environment variables
load_dotenv()

# Setup logging - works for both Codespaces and Render
log_dir = 'data/logs'
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(log_dir, 'bot.log'), mode='a')
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
        
        # Initialize testnet connections if enabled
        self.binance_testnet = None
        self.drift_devnet = None
        self.drift_integration = None
        if self.enable_testnet:
            logger.info("Initializing test network connections...")
            self.binance_testnet = BinanceTestnetSimple()
            
            # Use real Drift integration if configured
            use_real_drift = os.getenv('USE_REAL_DRIFT', 'false').lower() == 'true'
            if use_real_drift:
                self.drift_integration = DriftIntegration()
                # We'll connect async later
            else:
                self.drift_devnet = DriftDevnetSimple()
        
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
                title="🚀 Drift-Binance Arbitrage Bot Started",
                description=f"Mode: **{self.mode}**\nTestnet: **{'ENABLED' if self.enable_testnet else 'DISABLED'}**",
                color="03b2f8"
            )
            
            embed.add_embed_field(
                name="Configuration",
                value=f"Spread Threshold: {self.settings['TRADING_CONFIG']['SPREAD_THRESHOLD']:.1%}\n" +
                      f"Trade Size: ${self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']}",
                inline=False
            )
            
            if self.enable_testnet:
                binance_status = "✅ Connected" if self.binance_testnet and self.binance_testnet.connected else "❌ Not Connected"
                
                if self.drift_integration:
                    drift_status = "✅ Connected (Real)" if self.drift_integration and self.drift_integration.connected else "❌ Not Connected"
                else:
                    drift_status = "✅ Connected (Simulated)" if self.drift_devnet and self.drift_devnet.connected else "❌ Not Connected"
                
                embed.add_embed_field(
                    name="Test Networks",
                    value=f"Binance Testnet: {binance_status}\n" +
                          f"Drift Devnet: {drift_status}",
                    inline=False
                )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
    
    def send_arbitrage_alert(self, opportunity: dict, binance_order=None, drift_order=None):
        """Send arbitrage execution alert to Discord"""
        if not self.webhook_url:
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="🎯 ARBITRAGE EXECUTED - TEST NETWORKS",
                description=f"Complete arbitrage trade placed on both exchanges",
                color="9b59b6"
            )
            
            # Opportunity details
            embed.add_embed_field(
                name="Opportunity",
                value=f"Pair: {opportunity['pair']}\n" +
                      f"Spread: {opportunity['spread']:.2%}\n" +
                      f"Expected Profit: ${opportunity['potential_profit_usdc']:.2f}",
                inline=False
            )
            
            # Binance order
            if binance_order:
                embed.add_embed_field(
                    name="✅ Binance Testnet",
                    value=f"Order ID: `{binance_order['orderId']}`\n" +
                          f"Status: {binance_order['status']}\n" +
                          f"Executed: {binance_order['executedQty']} SOL",
                    inline=True
                )
            
            # Drift order
            if drift_order:
                embed.add_embed_field(
                    name="✅ Drift Devnet",
                    value=f"Order ID: `{drift_order['orderId']}`\n" +
                          f"Side: {drift_order['side']}\n" +
                          f"Size: {drift_order['size']} SOL",
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
            # Execute test orders if enabled
            if self.enable_testnet and self.binance_testnet:
                # Check which Drift connection we're using
                drift_connected = False
                if self.drift_integration and self.drift_integration.connected:
                    drift_connected = True
                elif self.drift_devnet and self.drift_devnet.connected:
                    drift_connected = True
                
                # Only execute if both are connected
                if self.binance_testnet.connected and drift_connected:
                    # Calculate quantity
                    trade_size_usd = self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']
                    quantity = trade_size_usd / spot_price
                    
                    # 1. Buy spot on Binance
                    symbol = pair.replace("/USDC", "USDT").replace("/", "")
                    binance_order = self.binance_testnet.place_test_order(symbol, "BUY", quantity)
                    
                    # 2. Short perp on Drift
                    drift_market = pair.split("/")[0] + "-PERP"
                    drift_order = None
                    if binance_order:
                        if self.drift_integration:
                            # Use real Drift integration
                            drift_order = await self.drift_integration.place_perp_order(
                                drift_market, 
                                float(binance_order['executedQty']), 
                                perp_price
                            )
                        else:
                            # Use simulated Drift
                            drift_order = self.drift_devnet.place_perp_order(
                                drift_market, 
                                float(binance_order['executedQty']), 
                                perp_price
                            )
                    
                    # Send alert if both orders successful
                    if binance_order and drift_order:
                        self.send_arbitrage_alert(opportunity, binance_order, drift_order)
                        
                        # Store position
                        position_id = f"{pair}_{binance_order['orderId']}_{drift_order['orderId']}"
                        self.open_positions[position_id] = {
                            'binance_order': binance_order,
                            'drift_order': drift_order,
                            'entry_spread': opportunity['spread'],
                            'timestamp': datetime.now()
                        }
                else:
                    logger.warning("Test networks not fully connected")
            else:
                # Just send opportunity alert
                self.send_opportunity_alert(opportunity)
    
    def send_opportunity_alert(self, opportunity: dict):
        """Send simple opportunity alert"""
        if not self.webhook_url:
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="🎯 Arbitrage Opportunity",
                description=f"{opportunity['pair']} - Spread: {opportunity['spread']:.2%}",
                color="00ff00"
            )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
    
    async def run_async(self):
        """Async main loop"""
        # Initialize Drift if using real integration
        if self.drift_integration:
            logger.info("Connecting to Drift Protocol...")
            connected = await self.drift_integration.connect()
            if connected:
                # Check account info
                info = await self.drift_integration.get_account_info()
                if info:
                    logger.info(f"Drift Account - Collateral: ${info['total_collateral']:.2f}, Free: ${info['free_collateral']:.2f}")
                    if info['total_collateral'] < 10:
                        logger.warning("Low collateral! Please deposit USDC to your Drift account on devnet")
        
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
            message = f"🛑 Bot shutting down\nOpen arbitrage positions: {positions}"
            
            webhook = DiscordWebhook(url=self.webhook_url, content=message)
            webhook.execute()

def main():
    """Entry point"""
    try:
        # Create log directory
        os.makedirs('data/logs', exist_ok=True)
        
        bot = DriftArbBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()