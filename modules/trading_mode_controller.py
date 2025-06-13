"""
Trading Mode Controller - DRY_RUN and LIVE_MODE safety controls
Prevents accidental live trading and provides simulation capabilities
"""
import os
import logging
from typing import Dict, Optional, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class TradingMode(Enum):
    """Trading mode enumeration"""
    DRY_RUN = "DRY_RUN"          # Simulate all trades, no real orders
    LIVE_MODE = "LIVE_MODE"      # Execute real trades
    TESTNET = "TESTNET"          # Use test networks only

class TradingModeController:
    def __init__(self, config: dict):
        self.config = config
        
        # Load mode settings from environment variables (primary) or config (fallback)
        self.dry_run = self._get_bool_setting('DRY_RUN', True)  # Default to safe mode
        self.live_mode = self._get_bool_setting('LIVE_MODE', False)  # Default to disabled
        self.testnet_enabled = self._get_bool_setting('ENABLE_TESTNET_TRADING', False)
        
        # Determine active trading mode
        self.trading_mode = self._determine_trading_mode()
        
        # Safety checks
        self._validate_mode_configuration()
        
        # Log the active configuration
        self._log_configuration()
    
    def _get_bool_setting(self, key: str, default: bool) -> bool:
        """Get boolean setting from environment or config"""
        # First check environment variables
        env_value = os.getenv(key)
        if env_value is not None:
            return env_value.lower() in ('true', '1', 'yes', 'on')
        
        # Fallback to config
        return self.config.get(key, default)
    
    def _determine_trading_mode(self) -> TradingMode:
        """Determine the active trading mode based on settings"""
        if self.dry_run:
            return TradingMode.DRY_RUN
        elif self.live_mode and not self.testnet_enabled:
            return TradingMode.LIVE_MODE
        elif self.testnet_enabled:
            return TradingMode.TESTNET
        else:
            # Default to safest mode
            return TradingMode.DRY_RUN
    
    def _validate_mode_configuration(self):
        """Validate mode configuration for safety"""
        # Safety check: Cannot have both DRY_RUN=False and LIVE_MODE=False
        if not self.dry_run and not self.live_mode and not self.testnet_enabled:
            logger.warning("No trading mode enabled! Forcing DRY_RUN mode for safety")
            self.dry_run = True
            self.trading_mode = TradingMode.DRY_RUN
        
        # Safety check: LIVE_MODE requires explicit confirmation
        if self.live_mode and self.dry_run:
            logger.warning("Both DRY_RUN and LIVE_MODE enabled! Prioritizing DRY_RUN for safety")
            self.trading_mode = TradingMode.DRY_RUN
        
        # Safety check: LIVE_MODE requires additional confirmation
        if self.trading_mode == TradingMode.LIVE_MODE:
            confirm_live = os.getenv('CONFIRM_LIVE_TRADING', '').lower()
            if confirm_live != 'yes_i_understand_this_uses_real_money':
                logger.error("LIVE_MODE requires CONFIRM_LIVE_TRADING='yes_i_understand_this_uses_real_money'")
                logger.error("Falling back to DRY_RUN mode for safety")
                self.trading_mode = TradingMode.DRY_RUN
                self.dry_run = True
                self.live_mode = False
    
    def _log_configuration(self):
        """Log the current trading mode configuration"""
        logger.info("=" * 50)
        logger.info("TRADING MODE CONFIGURATION")
        logger.info("=" * 50)
        logger.info(f"Active Mode: {self.trading_mode.value}")
        logger.info(f"DRY_RUN: {self.dry_run}")
        logger.info(f"LIVE_MODE: {self.live_mode}")
        logger.info(f"TESTNET_ENABLED: {self.testnet_enabled}")
        
        if self.trading_mode == TradingMode.DRY_RUN:
            logger.info("🔒 SAFE MODE: All trades will be simulated only")
        elif self.trading_mode == TradingMode.TESTNET:
            logger.info("🧪 TESTNET MODE: Using test networks with test funds")
        elif self.trading_mode == TradingMode.LIVE_MODE:
            logger.warning("⚠️  LIVE MODE: REAL MONEY WILL BE USED!")
        
        logger.info("=" * 50)
    
    def is_dry_run(self) -> bool:
        """Check if in dry run mode"""
        return self.trading_mode == TradingMode.DRY_RUN
    
    def is_live_mode(self) -> bool:
        """Check if in live trading mode"""
        return self.trading_mode == TradingMode.LIVE_MODE
    
    def is_testnet_mode(self) -> bool:
        """Check if in testnet mode"""
        return self.trading_mode == TradingMode.TESTNET
    
    def can_place_real_orders(self) -> bool:
        """Check if real orders can be placed"""
        return self.trading_mode in [TradingMode.LIVE_MODE, TradingMode.TESTNET]
    
    def validate_trade_execution(self, trade_data: Dict) -> Dict:
        """Validate and potentially modify trade execution based on mode"""
        result = {
            'allowed': False,
            'mode': self.trading_mode.value,
            'simulated': True,
            'reason': '',
            'trade_data': trade_data.copy()
        }
        
        if self.trading_mode == TradingMode.DRY_RUN:
            result.update({
                'allowed': True,
                'simulated': True,
                'reason': 'DRY_RUN mode - trade will be simulated only'
            })
        
        elif self.trading_mode == TradingMode.TESTNET:
            result.update({
                'allowed': True,
                'simulated': False,
                'reason': 'TESTNET mode - trade will execute on test networks'
            })
        
        elif self.trading_mode == TradingMode.LIVE_MODE:
            result.update({
                'allowed': True,
                'simulated': False,
                'reason': 'LIVE_MODE - trade will execute with REAL MONEY'
            })
        
        return result
    
    def log_trade_decision(self, trade_validation: Dict):
        """Log trade execution decision"""
        mode = trade_validation['mode']
        allowed = trade_validation['allowed']
        simulated = trade_validation['simulated']
        reason = trade_validation['reason']
        
        if allowed:
            if simulated:
                logger.info(f"🔒 [{mode}] Trade simulation approved: {reason}")
            else:
                if mode == 'TESTNET':
                    logger.info(f"🧪 [{mode}] Testnet trade approved: {reason}")
                else:
                    logger.warning(f"💰 [{mode}] LIVE trade approved: {reason}")
        else:
            logger.error(f"❌ [{mode}] Trade blocked: {reason}")
    
    def get_mode_summary(self) -> Dict:
        """Get summary of current trading mode"""
        return {
            'trading_mode': self.trading_mode.value,
            'dry_run': self.dry_run,
            'live_mode': self.live_mode,
            'testnet_enabled': self.testnet_enabled,
            'can_place_orders': self.can_place_real_orders(),
            'is_simulated': self.is_dry_run(),
            'timestamp': datetime.now().isoformat()
        }
    
    def create_simulation_trade(self, opportunity: Dict) -> Dict:
        """Create a simulated trade record"""
        return {
            'id': f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'type': 'SIMULATED',
            'mode': self.trading_mode.value,
            'timestamp': datetime.now().isoformat(),
            'opportunity': opportunity,
            'pair': opportunity.get('pair', 'UNKNOWN'),
            'spread': opportunity.get('spread', 0),
            'expected_profit': opportunity.get('potential_profit_usdc', 0),
            'trade_size': opportunity.get('trade_size', 0),
            'status': 'SIMULATED_SUCCESS',
            'note': 'This trade was simulated only - no real orders placed'
        }
    
    def should_send_discord_alert(self) -> bool:
        """Determine if Discord alerts should be sent based on mode"""
        # Send alerts for all modes, but with different formatting
        return True
    
    def format_discord_alert_title(self, base_title: str) -> str:
        """Format Discord alert title based on trading mode"""
        if self.trading_mode == TradingMode.DRY_RUN:
            return f"🔒 [SIMULATION] {base_title}"
        elif self.trading_mode == TradingMode.TESTNET:
            return f"🧪 [TESTNET] {base_title}"
        elif self.trading_mode == TradingMode.LIVE_MODE:
            return f"💰 [LIVE] {base_title}"
        else:
            return f"❓ [UNKNOWN] {base_title}"
    
    def get_environment_instructions(self) -> str:
        """Get instructions for setting environment variables"""
        return """
Environment Variable Configuration:

For DRY_RUN mode (safest - simulates all trades):
export DRY_RUN=true
export LIVE_MODE=false

For TESTNET mode (uses test networks):
export DRY_RUN=false
export LIVE_MODE=false
export ENABLE_TESTNET_TRADING=true

For LIVE mode (REAL MONEY - be careful!):
export DRY_RUN=false
export LIVE_MODE=true
export ENABLE_TESTNET_TRADING=false
export CONFIRM_LIVE_TRADING=yes_i_understand_this_uses_real_money

In Render deployment:
- Set these as Environment Variables in Render dashboard
- DRY_RUN defaults to 'true' for safety
"""
