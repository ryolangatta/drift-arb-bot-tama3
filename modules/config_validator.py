"""
Validate configuration from Render environment
"""
import os
import logging

logger = logging.getLogger(__name__)

class ConfigValidator:
    @staticmethod
    def validate_render_config():
        """Validate all required Render environment variables"""
        required = {
            'DISCORD_WEBHOOK_URL': 'Discord webhook for notifications',
            'MODE': 'Trading mode (SIMULATION or LIVE)',
            'ENV': 'Environment (production, staging, development)'
        }
        
        optional = {
            'SPREAD_THRESHOLD': 'Minimum spread threshold',
            'TRADE_SIZE_USDC': 'Trade size in USDC',
            'ENABLE_TESTNET_TRADING': 'Enable test network trading',
            'BINANCE_TESTNET_API_KEY': 'Binance testnet API key',
            'BINANCE_TESTNET_SECRET': 'Binance testnet secret',
            'SOLANA_DEVNET_PRIVATE_KEY': 'Solana devnet private key'
        }
        
        errors = []
        warnings = []
        
        # Check required variables
        for var, description in required.items():
            if not os.getenv(var):
                errors.append(f"Missing required: {var} - {description}")
        
        # Check optional variables
        for var, description in optional.items():
            if not os.getenv(var):
                warnings.append(f"Optional not set: {var} - {description}")
            else:
                logger.info(f"✓ {var} is configured")
        
        # Validate test network setup
        if os.getenv('ENABLE_TESTNET_TRADING', 'false').lower() == 'true':
            if not os.getenv('BINANCE_TESTNET_API_KEY'):
                errors.append("ENABLE_TESTNET_TRADING is true but BINANCE_TESTNET_API_KEY is missing")
            if not os.getenv('BINANCE_TESTNET_SECRET'):
                errors.append("ENABLE_TESTNET_TRADING is true but BINANCE_TESTNET_SECRET is missing")
        
        # Log results
        if errors:
            logger.error("Configuration errors found:")
            for error in errors:
                logger.error(f"  ❌ {error}")
            raise ValueError("Invalid Render configuration")
        
        if warnings:
            logger.warning("Configuration warnings:")
            for warning in warnings:
                logger.warning(f"  ⚠️  {warning}")
        
        logger.info("✅ Render configuration validated successfully")
        
        # Log active configuration
        logger.info("Active configuration from Render:")
        logger.info(f"  MODE: {os.getenv('MODE')}")
        logger.info(f"  ENV: {os.getenv('ENV')}")
        logger.info(f"  SPREAD_THRESHOLD: {os.getenv('SPREAD_THRESHOLD', 'default')}")
        logger.info(f"  TESTNET_TRADING: {os.getenv('ENABLE_TESTNET_TRADING', 'false')}")
        
        return True
