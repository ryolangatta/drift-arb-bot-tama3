#!/usr/bin/env python3
"""
Drift-Binance Arbitrage Bot - Fixed Direction Logic
Now properly handles both buying and selling based on price differences
"""
import os
import sys
import json
import logging
import asyncio
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed

# Add parent directory to path for module imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Setup logging
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

# Debug environment variables
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
    sys.exit(1)

try:
    from modules.arb_detector import ArbitrageDetector  
    logger.info("✅ Successfully imported ArbitrageDetector")
except Exception as e:
    logger.error(f"❌ Failed to import ArbitrageDetector: {e}")
    sys.exit(1)

try:
    from modules.binance_testnet_simple import BinanceTestnetSimple
    logger.info("✅ Successfully imported BinanceTestnetSimple")
except Exception as e:
    logger.error(f"❌ Failed to import BinanceTestnetSimple: {e}")
    sys.exit(1)

try:
    from modules.drift_devnet_simple import DriftDevnetSimple
    logger.info("✅ Successfully imported DriftDevnetSimple")
except Exception as e:
    logger.error(f"❌ Failed to import DriftDevnetSimple: {e}")
    sys.exit(1)

try:
    from modules.drift_integration import DriftIntegration
    logger.info("✅ Successfully imported DriftIntegration")
except Exception as e:
    logger.error(f"❌ Failed to import DriftIntegration: {e}")
    sys.exit(1)

try:
    from modules.trade_tracker import TradeTracker
    logger.info("✅ Successfully imported TradeTracker")
except Exception as e:
    logger.error(f"❌ Failed to import TradeTracker: {e}")
    sys.exit(1)

class ArbitrageExecutor:
    """Fixed arbitrage executor that handles both buy and sell directions"""
    
    def __init__(self, binance_testnet, drift_integration):
        self.binance = binance_testnet
        self.drift = drift_integration
    
    def determine_arbitrage_direction(self, opportunity: dict) -> dict:
        """Determine whether to buy or sell based on price difference"""
        spot_price = opportunity['spot_price']
        perp_price = opportunity['perp_price']
        
        if perp_price > spot_price:
            # Perp is more expensive - buy cheap spot, sell expensive perp
            return {
                'action': 'BUY_SPOT_SELL_PERP',
                'binance_side': 'BUY',
                'drift_side': 'SHORT',
                'reasoning': f'Perp (${perp_price:.4f}) > Spot (${spot_price:.4f}) - Buy spot, Short perp'
            }
        else:
            # Spot is more expensive - sell expensive spot, buy cheap perp  
            return {
                'action': 'SELL_SPOT_BUY_PERP',
                'binance_side': 'SELL', 
                'drift_side': 'LONG',
                'reasoning': f'Spot (${spot_price:.4f}) > Perp (${perp_price:.4f}) - Sell spot, Long perp'
            }
    
    def check_required_balances(self, direction: dict, trade_size_usd: float, spot_price: float) -> dict:
        """Check if we have sufficient balances for the trade"""
        try:
            # Get current balances
            balances = self.binance.get_all_balances()
            usdt_balance = balances.get('USDT', 0)
            sol_balance = balances.get('SOL', 0)
            
            # Calculate required amounts
            sol_quantity = trade_size_usd / spot_price
            
            if direction['binance_side'] == 'BUY':
                # Need USDT to buy SOL
                required_usdt = trade_size_usd * 1.001  # Add 0.1% buffer for fees
                available = usdt_balance >= required_usdt
                
                return {
                    'sufficient': available,
                    'required': f'${required_usdt:.2f} USDT',
                    'available': f'${usdt_balance:.2f} USDT',
                    'action': 'Buy SOL with USDT'
                }
            
            else:  # SELL
                # Need SOL to sell for USDT
                required_sol = sol_quantity * 1.001  # Add 0.1% buffer
                available = sol_balance >= required_sol
                
                return {
                    'sufficient': available,
                    'required': f'{required_sol:.4f} SOL',
                    'available': f'{sol_balance:.4f} SOL', 
                    'action': 'Sell SOL for USDT'
                }
                
        except Exception as e:
            logger.error(f"Error checking balances: {e}")
            return {
                'sufficient': False,
                'error': str(e)
            }
    
    async def execute_arbitrage(self, opportunity: dict, trade_size_usd: float) -> dict:
        """Execute arbitrage trade in the correct direction"""
        try:
            # Determine trade direction
            direction = self.determine_arbitrage_direction(opportunity)
            logger.info(f"📊 Trade Direction: {direction['reasoning']}")
            
            # Check balances
            balance_check = self.check_required_balances(
                direction, trade_size_usd, opportunity['spot_price']
            )
            
            if not balance_check['sufficient']:
                logger.warning(f"❌ Insufficient balance for {direction['action']}")
                logger.warning(f"   Required: {balance_check['required']}")
                logger.warning(f"   Available: {balance_check['available']}")
                
                return {
                    'success': False,
                    'error': 'Insufficient balance',
                    'direction': direction,
                    'balance_check': balance_check
                }
            
            logger.info(f"✅ Balance check passed: {balance_check['action']}")
            logger.info(f"   Required: {balance_check['required']}")
            logger.info(f"   Available: {balance_check['available']}")
            
            # Calculate quantities
            base_asset = opportunity['pair'].split('/')[0]
            sol_quantity = trade_size_usd / opportunity['spot_price']
            
            # Execute Binance trade
            binance_symbol = f"{base_asset}USDT"
            logger.info(f"🔄 Executing Binance {direction['binance_side']}: {sol_quantity:.4f} {base_asset}")
            
            binance_order = self.binance.place_test_order(
                binance_symbol, 
                direction['binance_side'], 
                sol_quantity
            )
            
            if not binance_order:
                return {
                    'success': False,
                    'error': 'Binance order failed',
                    'direction': direction
                }
            
            logger.info(f"✅ Binance {direction['binance_side']} successful: {binance_order['orderId']}")
            
            # Execute Drift trade (opposite direction)
            drift_market = f"{base_asset}-PERP"
            logger.info(f"🔄 Executing Drift {direction['drift_side']}: {sol_quantity:.4f} {base_asset}")
            
            # Use the drift integration to place the order
            if direction['drift_side'] == 'SHORT':
                drift_order = await self.drift.place_perp_order(
                    drift_market, sol_quantity, opportunity['perp_price'], 'SHORT'
                )
            else:  # LONG
                drift_order = await self.drift.place_perp_order(
                    drift_market, sol_quantity, opportunity['perp_price'], 'LONG'
                )
            
            if not drift_order:
                logger.error("❌ Drift order failed")
                return {
                    'success': False,
                    'error': 'Drift order failed',
                    'direction': direction,
                    'binance_order': binance_order
                }
            
            logger.info(f"✅ Drift {direction['drift_side']} successful: {drift_order['orderId']}")
            
            # Calculate actual profit
            if direction['binance_side'] == 'BUY':
                # Bought spot at lower price, sold perp at higher price
                profit_per_unit = opportunity['perp_price'] - opportunity['spot_price']
            else:
                # Sold spot at higher price, bought perp at lower price  
                profit_per_unit = opportunity['spot_price'] - opportunity['perp_price']
            
            gross_profit = profit_per_unit * sol_quantity
            # Estimate fees (actual fees would come from order responses)
            estimated_fees = trade_size_usd * 0.002  # ~0.2% total fees
            net_profit = gross_profit - estimated_fees
            
            return {
                'success': True,
                'direction': direction,
                'binance_order': binance_order,
                'drift_order': drift_order,
                'trade_details': {
                    'sol_quantity': sol_quantity,
                    'trade_size_usd': trade_size_usd,
                    'spot_price': opportunity['spot_price'],
                    'perp_price': opportunity['perp_price'],
                    'profit_per_unit': profit_per_unit,
                    'gross_profit': gross_profit,
                    'estimated_fees': estimated_fees,
                    'net_profit': net_profit,
                    'roi_percent': (net_profit / trade_size_usd) * 100
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error executing arbitrage: {e}")
            return {
                'success': False,
                'error': str(e),
                'direction': direction if 'direction' in locals() else None
            }

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
        
        # Load settings
        with open('config/settings.json', 'r') as f:
            self.settings = json.load(f)
        logger.info("✅ Settings loaded")
        
        # Override with Render environment variables
        if os.getenv('TRADE_SIZE_USDC'):
            self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC'] = float(os.getenv('TRADE_SIZE_USDC'))
            logger.info(f"🔧 Trade size overridden to: ${os.getenv('TRADE_SIZE_USDC')}")
        
        # Initialize core modules
        self.price_feed = PriceFeed(self.settings)
        self.arb_detector = ArbitrageDetector(self.settings)
        logger.info("✅ Core modules initialized")

        # Initialize core modules
        self.price_feed = PriceFeed(self.settings)
        self.arb_detector = ArbitrageDetector(self.settings)
        logger.info("✅ Core modules initialized")
        
        # Initialize testnet connections if enabled
        self.binance_testnet = None
        self.drift_devnet = None
        self.drift_integration = None
        
        if self.enable_testnet:
            logger.info("🔧 Initializing test network connections...")
            
            # Initialize Binance testnet
            self.binance_testnet = BinanceTestnetSimple()
            logger.info("✅ Binance testnet initialized")
            
            # Check if we should use real Drift integration
            use_real_drift = os.getenv('USE_REAL_DRIFT', 'false').lower() == 'true'
            logger.info(f"USE_REAL_DRIFT check: '{os.getenv('USE_REAL_DRIFT')}' -> {use_real_drift}")
            
            if use_real_drift:
                logger.info("🚀 Using REAL Drift integration...")
                self.drift_integration = DriftIntegration()
                logger.info("✅ DriftIntegration object created")
            else:
                logger.info("🔄 Using simulated Drift...")
                self.drift_devnet = DriftDevnetSimple()
        
        # Get pairs to monitor
        self.pairs_to_monitor = self.settings['TRADING_CONFIG']['PAIRS_TO_MONITOR']
        
        # Track positions and trades
        self.open_positions = {}
        self.trade_tracker = TradeTracker(initial_balance=500.0)
        self.last_report_time = datetime.now()
        
        # Statistics
        self.opportunities_found = 0
        self.trades_attempted = 0
        self.trades_successful = 0
        
        logger.info(f"✅ Bot initialized - Mode: {self.mode} | Testnet: {'ENABLED' if self.enable_testnet else 'DISABLED'}")
        logger.info("=== BOT INITIALIZATION COMPLETE ===")
    
    def send_startup_message(self):
        """Send startup notification to Discord"""
        if not self.webhook_url:
            logger.warning("⚠️ No Discord webhook URL configured")
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="🚀 Drift-Binance Arbitrage Bot Started (FIXED DIRECTION LOGIC)",
                description=f"Mode: **{self.mode}**\nTestnet: **{'ENABLED' if self.enable_testnet else 'DISABLED'}**",
                color="03b2f8"
            )
            
            # Get current balances
            if self.binance_testnet and self.binance_testnet.connected:
                balances = self.binance_testnet.get_all_balances()
                usdt_balance = balances.get('USDT', 0)
                sol_balance = balances.get('SOL', 0)
                
                embed.add_embed_field(
                    name="💰 Current Balances",
                    value=f"USDT: ${usdt_balance:.2f}\nSOL: {sol_balance:.2f}",
                    inline=True
                )
                
                # Indicate which trades are possible
                can_buy = usdt_balance >= 20
                can_sell = sol_balance >= 0.1
                
                trade_capability = []
                if can_buy:
                    trade_capability.append("✅ Can buy SOL (when perp > spot)")
                else:
                    trade_capability.append("❌ Cannot buy SOL (low USDT)")
                    
                if can_sell:
                    trade_capability.append("✅ Can sell SOL (when spot > perp)")
                else:
                    trade_capability.append("❌ Cannot sell SOL (no SOL)")
                
                embed.add_embed_field(
                    name="🔄 Trading Capability", 
                    value="\n".join(trade_capability),
                    inline=True
                )
            
            # Configuration details
            config_text = (
                f"Spread Threshold: {self.settings['TRADING_CONFIG']['SPREAD_THRESHOLD']:.3%}\n"
                f"Trade Size: ${self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']}\n"
                f"Pairs: {', '.join(self.pairs_to_monitor)}"
            )
            
            embed.add_embed_field(
                name="📊 Configuration",
                value=config_text,
                inline=False
            )
            
            # Key fixes
            embed.add_embed_field(
                name="🔧 Key Fixes Applied",
                value="• ✅ Fixed buy/sell direction logic\n• ✅ Balance checking for both directions\n• ✅ Proper arbitrage execution\n• ✅ Real Drift integration",
                inline=False
            )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
            logger.info("📱 Startup message sent to Discord")
            
        except Exception as e:
            logger.error(f"❌ Error sending Discord notification: {e}")
    
    async def price_callback(self, pair: str, spot_price: float, perp_price: float):
        """Enhanced callback for when new prices are received"""
        try:
            # Check for arbitrage opportunity
            opportunity = self.arb_detector.check_arbitrage_opportunity(
                pair, spot_price, perp_price
            )
            
            if opportunity:
                self.opportunities_found += 1
                logger.info(f"🎯 ARBITRAGE OPPORTUNITY DETECTED: {pair} - {opportunity['spread']:.2%}")
                
                # Log current balances
                if self.binance_testnet and self.binance_testnet.connected:
                    balances = self.binance_testnet.get_all_balances()
                    usdt_balance = balances.get('USDT', 0)
                    sol_balance = balances.get('SOL', 0)
                    logger.info(f"💰 Current balances - USDT: ${usdt_balance:.2f}, SOL: {sol_balance:.2f}")
                
                execution_result = None
                
                # Execute test orders if enabled
                if self.enable_testnet and self.binance_testnet:
                    execution_result = await self._execute_testnet_arbitrage(opportunity)
                
                # Send alert
                self.send_opportunity_alert(opportunity, execution_result)
                
                # Send periodic report every 10 minutes
                if datetime.now() - self.last_report_time > timedelta(minutes=10):
                    self.send_periodic_report()
                    self.last_report_time = datetime.now()
        
        except Exception as e:
            logger.error(f"❌ Error in price callback: {e}")
            logger.error(traceback.format_exc())
    
    async def _execute_testnet_arbitrage(self, opportunity: dict):
        """Execute arbitrage with fixed direction logic"""
        try:
            self.trades_attempted += 1
            trade_size_usd = self.settings['TRADING_CONFIG']['TRADE_SIZE_USDC']
            
            logger.info(f"🔄 Attempting arbitrage #{self.trades_attempted}...")
            
            # Determine which direction to trade
            if opportunity['perp_price'] > opportunity['spot_price']:
                logger.info(f"🔵 BUYING on Binance (cheaper): ${trade_size_usd} worth of SOL")
                logger.info(f"🔴 SHORTING on Drift (expensive): equivalent amount")
            else:
                logger.info(f"🔴 SELLING on Binance (expensive): ${trade_size_usd} worth of SOL") 
                logger.info(f"🔵 LONGING on Drift (cheaper): equivalent amount")
            
            # Create arbitrage executor with fixed logic
            if self.drift_integration:
                executor = ArbitrageExecutor(self.binance_testnet, self.drift_integration)
                result = await executor.execute_arbitrage(opportunity, trade_size_usd)
            else:
                # Fallback to simulated approach
                logger.warning("⚠️ Using simulated Drift - no real orders placed")
                result = {'success': False, 'error': 'Real Drift not available'}
            
            if result['success']:
                self.trades_successful += 1
                logger.info(f"🎉 ARBITRAGE EXECUTED SUCCESSFULLY! Trade #{self.trades_successful}")
                logger.info(f"   Direction: {result['direction']['action']}")
                logger.info(f"   Net Profit: ${result['trade_details']['net_profit']:.2f}")
                logger.info(f"   ROI: {result['trade_details']['roi_percent']:.2f}%")
            else:
                logger.error(f"❌ Arbitrage execution failed: {result.get('error', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in arbitrage execution: {e}")
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    def send_opportunity_alert(self, opportunity: dict, execution_result=None):
        """Send arbitrage opportunity alert to Discord"""
        if not self.webhook_url:
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            if execution_result and execution_result.get('success'):
                # Successful execution
                embed = DiscordEmbed(
                    title="✅ ARBITRAGE EXECUTED - FIXED DIRECTION",
                    description=f"Successfully executed arbitrage with correct buy/sell logic",
                    color="00ff00"
                )
                
                direction = execution_result['direction']
                trade_details = execution_result['trade_details']
                
                embed.add_embed_field(
                    name="📊 Trade Direction",
                    value=direction['reasoning'],
                    inline=False
                )
                
                embed.add_embed_field(
                    name="💰 Trade Results",
                    value=f"Quantity: {trade_details['sol_quantity']:.4f} SOL\n"
                          f"Net Profit: ${trade_details['net_profit']:.2f}\n"
                          f"ROI: {trade_details['roi_percent']:.2f}%",
                    inline=True
                )
                
                if execution_result.get('binance_order'):
                    bo = execution_result['binance_order']
                    embed.add_embed_field(
                        name=f"🟡 Binance {direction['binance_side']}",
                        value=f"Order ID: `{bo['orderId']}`\n"
                              f"Status: {bo['status']}",
                        inline=True
                    )
                
                if execution_result.get('drift_order'):
                    do = execution_result['drift_order']
                    embed.add_embed_field(
                        name=f"🟣 Drift {direction['drift_side']}",
                        value=f"Order ID: `{do['orderId']}`\n"
                              f"Status: {do.get('status', 'PLACED')}",
                        inline=True
                    )
            
            else:
                # Opportunity detected but not executed or failed
                color = "ff0000" if execution_result and execution_result.get('error') else "ffff00"
                
                embed = DiscordEmbed(
                    title="🎯 Arbitrage Opportunity Detected",
                    description=f"**{opportunity['pair']}** - Spread: {opportunity['spread']:.3%}",
                    color=color
                )
                
                # Show what the bot would do
                if opportunity['perp_price'] > opportunity['spot_price']:
                    action_plan = "📈 Would BUY spot (cheaper) and SHORT perp (expensive)"
                else:
                    action_plan = "📉 Would SELL spot (expensive) and LONG perp (cheaper)"
                
                embed.add_embed_field(
                    name="🔄 Action Plan",
                    value=action_plan,
                    inline=False
                )
                
                embed.add_embed_field(
                    name="📊 Prices",
                    value=f"Binance Spot: ${opportunity['spot_price']:.4f}\n"
                          f"Drift Perp: ${opportunity['perp_price']:.4f}\n"
                          f"Expected Profit: ${opportunity['potential_profit_usdc']:.2f}",
                    inline=True
                )
                
                if execution_result and execution_result.get('error'):
                    embed.add_embed_field(
                        name="⚠️ Execution Error",
                        value=execution_result['error'],
                        inline=True
                    )
            
            # Add session statistics
            success_rate = (self.trades_successful / max(1, self.trades_attempted)) * 100
            embed.add_embed_field(
                name="📈 Session Stats",
                value=f"Opportunities: {self.opportunities_found}\n"
                      f"Attempts: {self.trades_attempted}\n"
                      f"Success Rate: {success_rate:.1f}%",
                inline=False
            )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
        except Exception as e:
            logger.error(f"❌ Error sending opportunity alert: {e}")
    
    def send_periodic_report(self):
        """Send periodic status report"""
        if not self.webhook_url:
            return
        
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            success_rate = (self.trades_successful / max(1, self.trades_attempted)) * 100
            
            embed = DiscordEmbed(
                title="📊 10-Minute Status Report",
                description="Fixed direction logic performance",
                color="1f8b4c"
            )
            
            embed.add_embed_field(
                name="📈 Performance",
                value=f"Opportunities: {self.opportunities_found}\n"
                      f"Attempts: {self.trades_attempted}\n"
                      f"Successful: {self.trades_successful}\n" 
                      f"Success Rate: {success_rate:.1f}%",
                inline=True
            )
            
            # Current balances
            if self.binance_testnet and self.binance_testnet.connected:
                balances = self.binance_testnet.get_all_balances()
                usdt_balance = balances.get('USDT', 0)
                sol_balance = balances.get('SOL', 0)
                
                embed.add_embed_field(
                    name="💰 Current Balances",
                    value=f"USDT: ${usdt_balance:.2f}\nSOL: {sol_balance:.2f}",
                    inline=True
                )
            
            embed.set_timestamp()
            webhook.add_embed(embed)
            webhook.execute()
            
            logger.info("📊 Periodic report sent to Discord")
            
        except Exception as e:
            logger.error(f"❌ Error sending periodic report: {e}")
    
    async def run_async(self):
        """Main async loop"""
        # Initialize Drift if using real integration
        if self.drift_integration:
            logger.info("🚀 Connecting to REAL Drift Protocol...")
            connected = await self.drift_integration.connect()
            if connected:
                # Check account info
                info = await self.drift_integration.get_account_info()
                if info:
                    logger.info(f"✅ REAL Drift connection successful!")
                    logger.info(f"💰 Drift Account - Collateral: ${info['total_collateral']:.2f}, Free: ${info['free_collateral']:.2f}")
                    if info['total_collateral'] < 10:
                        logger.warning("⚠️ Low collateral! Please deposit USDC to your Drift account on devnet")
        
        logger.info("📡 Starting price monitoring...")
        
        # Start price monitoring
        await self.price_feed.start_price_monitoring(
            self.pairs_to_monitor,
            callback=self.price_callback
        )
    
    def run(self):
        """Main bot loop"""
        try:
            # Send startup message
            self.send_startup_message()
            
            # Run the async event loop
            asyncio.run(self.run_async())
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
            self.shutdown()
        except Exception as e:
            logger.error(f"💥 Unexpected error in main loop: {e}")
            logger.error(traceback.format_exc())
            self.shutdown()
    
    def shutdown(self):
        """Graceful shutdown"""
        logger.info("🔄 Shutting down bot...")
        
        if self.webhook_url:
            try:
                success_rate = (self.trades_successful / max(1, self.trades_attempted)) * 100
                
                final_message = (
                    f"🛑 **Bot Shutdown - Fixed Direction Logic**\n\n"
                    f"📊 **Final Statistics:**\n"
                    f"• Opportunities Found: {self.opportunities_found}\n"
                    f"• Trades Attempted: {self.trades_attempted}\n"
                    f"• Successful Trades: {self.trades_successful}\n"
                    f"• Success Rate: {success_rate:.1f}%\n\n"
                    f"🔧 **Key Fix Applied:**\n"
                    f"• ✅ Proper buy/sell direction logic\n"
                    f"• ✅ Balance checking for both directions\n"
                    f"• ✅ Real Drift Protocol integration"
                )
                
                webhook = DiscordWebhook(url=self.webhook_url, content=final_message)
                webhook.execute()
                
            except Exception as e:
                logger.error(f"❌ Error sending shutdown message: {e}")
        
        logger.info("✅ Bot shutdown complete")

def main():
    """Entry point"""
    try:
        # Create necessary directories
        os.makedirs('data/logs', exist_ok=True)
        
        # Initialize and run bot
        bot = DriftArbBot()
        bot.run()
        
    except Exception as e:
        logger.error(f"💥 Failed to start bot: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()