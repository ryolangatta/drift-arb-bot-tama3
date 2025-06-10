#!/usr/bin/env python3
"""
Drift-Binance Arbitrage Bot - Complete Version with Debug Logging
"""
import os
import sys
import json
import logging
import asyncio
import base64
from datetime import datetime, timedelta
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed

# Add parent directory to path for module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging FIRST
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

# Debug: Check environment variables first
logger.info("=== ENVIRONMENT VARIABLE DEBUG ===")
logger.info(f"ENABLE_TESTNET_TRADING: {os.getenv('ENABLE_TESTNET_TRADING')}")
logger.info(f"USE_REAL_DRIFT: {os.getenv('USE_REAL_DRIFT')}")
logger.info(f"SOLANA_DEVNET_PRIVATE_KEY exists: {bool(os.getenv('SOLANA_DEVNET_PRIVATE_KEY'))}")
logger.info("=== END ENVIRONMENT DEBUG ===")

# Import modules with error handling
try:
    from modules.price_feed import PriceFeed
    logger.info("✅ Successfully imported PriceFeed")
except Exception as e:
    logger.error(f"❌ Failed to import PriceFeed: {e}")

try:
    from modules.arb_detector import ArbitrageDetector
    logger.info("✅ Successfully imported ArbitrageDetector")
except Exception as e:
    logger.error(f"❌ Failed to import ArbitrageDetector: {e}")

try:
    from modules.binance_testnet_simple import BinanceTestnetSimple
    logger.info("✅ Successfully imported BinanceTestnetSimple")
except Exception as e:
    logger.error(f"❌ Failed to import BinanceTestnetSimple: {e}")

try:
    from modules.drift_devnet_simple import DriftDevnetSimple
    logger.info("✅ Successfully imported DriftDevnetSimple")
except Exception as e:
    logger.error(f"❌ Failed to import DriftDevnetSimple: {e}")

try:
    from modules.drift_integration import DriftIntegration
    logger.info("✅ Successfully imported DriftIntegration")
except Exception as e:
    logger.error(f"❌ Failed to import DriftIntegration: {e}")

try:
    from modules.trade_tracker import TradeTracker
    logger.info("✅ Successfully imported TradeTracker")
except Exception as e:
    logger.error(f"❌ Failed to import TradeTracker: {e}")

# Load environment variables
load_dotenv()

class DriftArbBot:
    def __init__(self):
        logger.info("=== BOT INITIALIZATION START ===")
        
        self.webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        self.mode = os.getenv('MODE', 'SIMULATION')
        self.env = os.getenv('ENV', 'development')
        self.enable_testnet = os.getenv('ENABLE_TESTNET_TRADING', 'false').lower() == 'true'
        
        logger.info(f"Mode: {self.mode}")
        logger.info(f"Environment: {self.env}")
        logger.info(f"Testnet enabled: {self.enable_testnet}")
        
        # Load settings
        with open('config/settings.json', 'r') as f:
            self.settings = json.load(f)
        logger.info("✅ Settings loaded")
        
        # Initialize modules
        self.price_feed = PriceFeed(self.settings)
        self.arb_detector = ArbitrageDetector(self.settings)
        logger.info("✅ Core modules initialized")
        
        # Initialize testnet connections if enabled
        self.binance_testnet = None
        self.drift_devnet = None
        self.drift_integration = None
        
        if self.enable_testnet:
            logger.info("🔧 Initializing test network connections...")
            
            # Initialize Binance Testnet
            try:
                self.binance_testnet = BinanceTestnetSimple()
                logger.info("✅ Binance testnet initialized")
            except Exception as e:
                logger.error(f"❌ Binance testnet initialization failed: {e}")
            
            # Initialize Drift connection - check which version to use
            use_real_drift = os.getenv('USE_REAL_DRIFT', 'false').lower() == 'true'
            logger.info(f"USE_REAL_DRIFT check: '{os.getenv('USE_REAL_DRIFT')}' -> {use_real_drift}")
            
            if use_real_drift:
                logger.info("🚀 Using REAL Drift integration...")
                try:
                    self.drift_integration = DriftIntegration()
                    logger.info("✅ DriftIntegration object created")
                except Exception as e:
                    logger.error(f"❌ DriftIntegration creation failed: {e}")
            else:
                logger.info("🎯 Using simulated Drift integration...")
                try:
                    self.drift_devnet = DriftDevnetSimple()
                    logger.info("✅ DriftDevnetSimple object created")
                except Exception as e:
                    logger.error(f"❌ DriftDevnetSimple creation failed: {e}")
        else:
            logger.info("⚠️ Testnet trading is DISABLED")
        
        # Get pairs to monitor
        self.pairs_to_monitor = self.settings['TRADING_CONFIG']['PAIRS_TO_MONITOR']
        
        # Track positions and trades
        self.open_positions = {}
        self.trade_tracker = TradeTracker(initial_balance=500.0)
        self.last_report_time = datetime.now()
        
        logger.info(f"✅ Bot initialized - Mode: {self.mode} | Testnet: {'ENABLED' if self.enable_testnet else 'DISABLED'}")
        logger.info("=== BOT INITIALIZATION COMPLETE ===")
    
    def send_startup_message(self):
        """Send startup notification to Discord"""
        if not self.webhook_url:
            logger.warning("No Discord webhook URL configured")
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="🚀 Drift-Binance Arbitrage Bot Started (DEBUG MODE)",
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
                    drift_status = "✅ Real Drift Object Created" if self.drift_integration else "❌ Not Created"
                elif self.drift_devnet:
                    drift_status = "✅ Simulated Drift Object Created" if self.drift_devnet else "❌ Not Created"
                else:
                    drift_status = "❌ No Drift Object"
                
                embed.add_embed_field(
                    name="Test Networks",
                    value=f"Binance Testnet: {binance_status}\n" +
                          f"Drift: {drift_status}",
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
                title="🎯 ARBITRAGE EXECUTED - BOTH EXCHANGES",
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
                    name="✅ Drift",
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
    
    def send_opportunity_alert(self, opportunity: dict):
        """Send simple opportunity alert when orders cannot be placed"""
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
    
    async def price_callback(self, pair: str, spot_price: float, perp_price: float):
        """Callback for when new prices are received"""
        # Check if it's time for periodic report (every 10 minutes)
        if datetime.now() - self.last_report_time > timedelta(minutes=10):
            self.send_periodic_report()
            self.last_report_time = datetime.now()
        
        # Check for arbitrage opportunity
        opportunity = self.arb_detector.check_arbitrage_opportunity(
            pair, spot_price, perp_price
        )
        
        if opportunity:
            logger.info(f"🎯 ARBITRAGE OPPORTUNITY DETECTED: {opportunity['pair']} - {opportunity['spread']:.2%}")
            
            # Execute orders on both exchanges if testnet is enabled
            if self.enable_testnet:
                binance_order = None
                drift_order = None
                
                # 1. Place Binance order first
                if self.binance_testnet and self.binance_testnet.connected:
                    logger.info("🔄 Attempting Binance order...")
                    # Calculate quantity
                    trade_size_usd = self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']
                    quantity = trade_size_usd / spot_price
                    
                    # Convert symbol (SOL/USDC -> SOLUSDT for testnet)
                    symbol = pair.replace("/USDC", "USDT").replace("/", "")
                    
                    # Place Binance order
                    binance_order = self.binance_testnet.place_test_order(symbol, "BUY", quantity)
                    
                    if binance_order:
                        logger.info(f"✅ Binance order placed: {binance_order['orderId']}")
                    else:
                        logger.error("❌ Binance order failed")
                else:
                    logger.warning("⚠️ Binance testnet not connected")
                
                # 2. Place Drift order
                if binance_order:  # Only if Binance order succeeded
                    logger.info("🔄 Attempting Drift order...")
                    drift_market = pair.split("/")[0] + "-PERP"
                    
                    if self.drift_integration:
                        logger.info("🚀 Using REAL Drift integration for order...")
                        # Use real Drift integration
                        try:
                            drift_order = await self.drift_integration.place_perp_order(
                                drift_market, 
                                float(binance_order['executedQty']), 
                                perp_price,
                                "SHORT"  # Short perp when buying spot
                            )
                            if drift_order:
                                logger.info(f"✅ REAL Drift order placed: {drift_order['orderId']}")
                            else:
                                logger.error("❌ REAL Drift order failed")
                        except Exception as e:
                            logger.error(f"❌ REAL Drift order error: {e}")
                    
                    elif self.drift_devnet:
                        logger.info("🎯 Using SIMULATED Drift for order...")
                        # Use simulated Drift
                        drift_order = self.drift_devnet.place_perp_order(
                            drift_market, 
                            float(binance_order['executedQty']), 
                            perp_price
                        )
                        if drift_order:
                            logger.info(f"✅ SIMULATED Drift order: {drift_order['orderId']}")
                    else:
                        logger.error("❌ No Drift integration available!")
                
                # 3. Send alerts and track trade
                if binance_order and drift_order:
                    # Both orders successful - send success alert
                    logger.info("🎉 COMPLETE ARBITRAGE EXECUTED!")
                    self.send_arbitrage_alert(opportunity, binance_order, drift_order)
                    
                    # Record the trade
                    self.trade_tracker.record_trade(opportunity, binance_order, drift_order)
                    
                    # Store position for tracking
                    position_id = f"{pair}_{binance_order['orderId']}_{drift_order['orderId']}"
                    self.open_positions[position_id] = {
                        'binance_order': binance_order,
                        'drift_order': drift_order,
                        'entry_spread': opportunity['spread'],
                        'timestamp': datetime.now()
                    }
                    
                    logger.info(f"📊 Position stored: {position_id}")
                    
                elif binance_order and not drift_order:
                    logger.warning("⚠️ PARTIAL EXECUTION: Only Binance order placed - Drift order failed")
                    
                else:
                    logger.warning("⚠️ NO ORDERS PLACED: Both exchanges failed")
            
            else:
                # Just send opportunity alert if testnet not enabled
                logger.info("📢 Sending opportunity alert (testnet disabled)")
                self.send_opportunity_alert(opportunity)
    
    def send_periodic_report(self):
        """Send periodic trading report"""
        if not self.webhook_url:
            return
        
        try:
            summary = self.trade_tracker.get_summary()
            
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="📊 Trading Report - 10 Minute Update",
                description=f"Runtime: {summary['runtime']}",
                color="1f8b4c"
            )
            
            # Performance metrics
            embed.add_embed_field(
                name="📈 Performance",
                value=f"Total Trades: {summary['total_trades']}\n" +
                      f"Total Profit: ${summary['total_profit']:.2f}\n" +
                      f"ROI: {summary['roi']:.2f}%\n" +
                      f"Avg Spread: {summary['avg_spread']:.4%}",
                inline=True
            )
            
            # Balance information
            embed.add_embed_field(
                name="💰 Balances",
                value=f"Total: ${summary['current_balance']:.2f}\n" +
                      f"Binance: ${summary['binance_balance']:.2f}\n" +
                      f"Drift: ${summary['drift_balance']:.2f}\n" +
                      f"Initial: $1000.00",
                inline=True
            )
            
            # Open positions
            embed.add_embed_field(
                name="🔄 Open Positions",
                value=f"Active: {len(self.open_positions)}\n" +
                      f"Monitoring: {', '.join(self.pairs_to_monitor)}",
                inline=False
            )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
        except Exception as e:
            logger.error(f"Error sending periodic report: {e}")
    
    async def run_async(self):
        """Async main loop"""
        # Initialize Drift if using real integration
        if self.drift_integration:
            logger.info("🚀 Connecting to REAL Drift Protocol...")
            try:
                connected = await self.drift_integration.connect()
                if connected:
                    logger.info("✅ REAL Drift connection successful!")
                    # Check account info
                    info = await self.drift_integration.get_account_info()
                    if info:
                        logger.info(f"💰 Drift Account - Collateral: ${info['total_collateral']:.2f}, Free: ${info['free_collateral']:.2f}")
                        if info['total_collateral'] < 10:
                            logger.warning("⚠️ Low collateral! Please deposit USDC to your Drift account")
                    else:
                        logger.warning("⚠️ Could not retrieve Drift account info")
                else:
                    logger.error("❌ Failed to connect to REAL Drift Protocol")
            except Exception as e:
                logger.error(f"❌ REAL Drift connection error: {e}")
        elif self.drift_devnet:
            logger.info("🎯 Using SIMULATED Drift (no connection needed)")
        else:
            logger.warning("⚠️ No Drift integration configured")
        
        logger.info("📡 Starting price monitoring...")
        
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