"""
Drift Protocol Integration for Devnet - FIXED VERSION
"""
import os
import logging
import json
from typing import Optional, Dict
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from anchorpy import Wallet

from driftpy.drift_client import DriftClient
from driftpy.constants.numeric_constants import BASE_PRECISION, PRICE_PRECISION
from driftpy.types import PositionDirection, OrderType, OrderParams

logger = logging.getLogger(__name__)

class DriftIntegration:
    def __init__(self):
        self.client = None
        self.drift_client = None
        self.connected = False
        self.wallet = None
        self.connection = None
        
    async def connect(self):
        """Connect to Drift on Solana Devnet"""
        try:
            # Get private key from environment (WORKING METHOD)
            private_key_str = os.getenv('SOLANA_DEVNET_PRIVATE_KEY', '')
            
            if not private_key_str:
                logger.warning("No Solana Devnet credentials found")
                return False
            
            # Parse JSON array format (the method that works)
            key_array = json.loads(private_key_str)
            secret_key = bytes(key_array[:32])
            keypair = Keypair.from_seed(secret_key)
            
            # Create wallet
            self.wallet = Wallet(keypair)
            
            # Connect to Solana devnet
            rpc_url = 'https://api.devnet.solana.com'
            self.connection = AsyncClient(rpc_url)
            
            # Initialize Drift client
            self.drift_client = DriftClient(
                self.connection,
                self.wallet,
                "devnet"
            )
            
            self.connected = True
            logger.info(f"Connected to Drift Devnet! Wallet: {self.wallet.payer.pubkey()}")
            
            return True
            
        except Exception as e:
            logger.error(f"Cannot connect to Drift Devnet: {e}")
            self.connected = False
            return False

    async def place_perp_order(self, market: str, size: float, price: float, direction: str = "SHORT"):
        """Place a real perpetual order on Drift devnet"""
        try:
            if not self.connected:
                logger.error("Not connected to Drift")
                return None
            
            # Get market index (SOL-PERP = 0)
            market_index = 0  # SOL-PERP
            
            # Convert size to BASE_PRECISION (10^9)
            base_asset_amount = int(size * BASE_PRECISION)
            
            # Convert price to PRICE_PRECISION (10^6)
            price_int = int(price * PRICE_PRECISION)
            
            # Create order params
            order_params = OrderParams(
                order_type=OrderType.Limit(),
                market_index=market_index,
                base_asset_amount=base_asset_amount,
                direction=PositionDirection.Short() if direction == "SHORT" else PositionDirection.Long(),
                price=price_int,
            )
            
            logger.info(f"Placing Drift order: {direction} {size} {market} @ ${price}")
            
            # Place the order
            tx_sig = await self.drift_client.place_perp_order(order_params)
            
            logger.info(f"✅ DRIFT ORDER PLACED! Tx: {tx_sig}")
            
            return {
                'orderId': tx_sig,
                'market': market,
                'side': direction,
                'size': size,
                'price': price,
                'status': 'PLACED',
                'tx_signature': tx_sig
            }
            
        except Exception as e:
            logger.error(f"Failed to place Drift order: {e}")
            return None

    async def get_account_info(self):
        """Get Drift account information"""
        try:
            if not self.connected:
                return None
            
            user = self.drift_client.get_user()
            
            # Get collateral
            total_collateral = user.get_total_collateral() / PRICE_PRECISION
            free_collateral = user.get_free_collateral() / PRICE_PRECISION
            
            return {
                'total_collateral': total_collateral,
                'free_collateral': free_collateral,
                'wallet': str(self.wallet.payer.pubkey())
            }
            
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return None
