"""
Configuration loader that merges settings.json with environment variables
"""
import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self):
        self.config = {}
        self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from settings.json and override with env vars"""
        # Load base configuration
        try:
            with open('config/settings.json', 'r') as f:
                self.config = json.load(f)
            logger.info("Loaded base configuration from settings.json")
        except Exception as e:
            logger.error(f"Failed to load settings.json: {e}")
            raise
        
        # Override with environment variables
        self._override_from_env()
        
        return self.config
    
    def _override_from_env(self):
        """Override config values with environment variables"""
        # Simple overrides
        overrides = {
            'MODE': os.getenv('MODE'),
            'DISCORD_WEBHOOK_URL': os.getenv('DISCORD_WEBHOOK_URL'),
            'DATABASE_URL': os.getenv('DATABASE_URL'),
        }
        
        # Trading config overrides
        if os.getenv('SPREAD_THRESHOLD'):
            self.config['TRADING_CONFIG']['SPREAD_THRESHOLD'] = float(os.getenv('SPREAD_THRESHOLD'))
        
        if os.getenv('TRADE_SIZE_USDC'):
            self.config['TRADING_CONFIG']['TRADE_SIZE_USDC'] = float(os.getenv('TRADE_SIZE_USDC'))
        
        # Apply simple overrides
        for key, value in overrides.items():
            if value is not None:
                if key in self.config:
                    self.config[key] = value
                else:
                    # Add to config even if not in settings.json
                    self.config[key] = value
        
        logger.info("Applied environment variable overrides")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)

# Singleton instance
config_loader = ConfigLoader()
get_config = config_loader.get
