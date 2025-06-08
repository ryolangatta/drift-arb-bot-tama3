"""
Simple Drift Devnet connection
"""
import os
import logging
import base58
from solders.keypair import Keypair

logger = logging.getLogger(__name__)

class DriftDevnetSimple:
    def __init__(self):
        self.keypair = None
        self.connected = False
        self._connect()
    
    def _connect(self):
        """Connect to Drift on Solana Devnet"""
        private_key_str = os.getenv('SOLANA_DEVNET_PRIVATE_KEY', '')
        
        if private_key_str:
            try:
                # Handle JSON array format (with or without spaces)
                if private_key_str.startswith('['):
                    # Remove brackets and spaces, then split by comma
                    cleaned = private_key_str.strip('[]').replace(' ', '')
                    key_array = [int(x) for x in cleaned.split(',')]
                    
                    # Solana keypairs are 64 bytes (32 secret + 32 public)
                    if len(key_array) == 64:
                        secret_key = bytes(key_array[:32])
                    elif len(key_array) == 32:
                        secret_key = bytes(key_array)
                    else:
                        raise ValueError(f"Expected 32 or 64 bytes, got {len(key_array)}")
                
                # Handle base58 format
                elif len(private_key_str) > 50:
                    secret_bytes = base58.b58decode(private_key_str)
                    secret_key = secret_bytes[:32]
                
                # Handle other formats
                else:
                    raise ValueError("Unknown private key format")
                
                self.keypair = Keypair.from_bytes(secret_key)
                self.connected = True
                
                logger.info(f"Connected to Drift Devnet! Wallet: {self.keypair.pubkey()}")
                
            except Exception as e:
                logger.error(f"Cannot connect to Drift Devnet: {e}")
                logger.info("Check SOLANA_DEVNET_PRIVATE_KEY format")
        else:
            logger.warning("No Solana Devnet credentials found")
    
    def place_perp_order(self, market, size, price):
        """Simulate Drift perp order for now"""
        if not self.connected:
            logger.error("Not connected to Drift Devnet")
            return None
        
        try:
            # For now, simulate the order
            # In production, this would use Drift SDK
            logger.info(f"Simulating DRIFT DEVNET order: SHORT {size} {market} @ ${price}")
            
            # Return simulated order
            return {
                'orderId': f'drift_sim_{os.urandom(4).hex()}',
                'market': market,
                'side': 'SHORT',
                'size': size,
                'price': price,
                'status': 'SIMULATED'
            }
            
        except Exception as e:
            logger.error(f"Failed to place Drift order: {e}")
            return None