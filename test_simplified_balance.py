#!/usr/bin/env python3
"""
Test script for Simplified Balance Manager
Tests the new research-backed approach in Codespaces
"""
import asyncio
import sys
import os
import json
import logging

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.balance_manager import BalanceManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MockBinanceClient:
    """Mock Binance client for testing"""
    def __init__(self, usdt_balance=500.0):
        self.usdt_balance = usdt_balance
    
    def get_account(self):
        return {
            'balances': [
                {'asset': 'USDT', 'free': str(self.usdt_balance)},
                {'asset': 'BTC', 'free': '0.01'},
                {'asset': 'SOL', 'free': '10.0'}
            ]
        }
    
    def get_all_balances(self):
        return {
            'USDT': self.usdt_balance,
            'BTC': 0.01,
            'SOL': 10.0
        }

class MockDriftUser:
    """Mock Drift user for testing"""
    def __init__(self, free_collateral=750.0, positions=0):
        self.free_collateral = free_collateral * 1e6  # Convert to precision
        self.positions_count = positions
    
    def get_free_collateral(self):
        return self.free_collateral
    
    def get_active_perp_positions(self):
        # Return mock positions based on count
        return [{'base_asset_amount': 1e9} for _ in range(self.positions_count)]

class MockDriftClient:
    """Mock Drift client for testing"""
    def __init__(self, free_collateral=750.0, positions=0):
        self.user = MockDriftUser(free_collateral, positions)
    
    def get_user(self):
        return self.user
    
    async def get_collateral_balance(self):
        return self.user.free_collateral / 1e6

async def test_simplified_balance_manager():
    """Test the simplified balance manager"""
    try:
        print("🧪 Testing Simplified Balance Manager")
        print("=" * 50)
        
        # Load config
        config_path = 'config/settings.json'
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            # Default config for testing
            config = {
                'TRADING_CONFIG': {
                    'TRADE_SIZE_USDC': 100,
                    'SPREAD_THRESHOLD': 0.002
                }
            }
        
        # Initialize balance manager
        balance_manager = BalanceManager(config)
        print("✅ Balance Manager initialized")
        
        # Test 1: Normal balances, no positions
        print("\n📊 Test 1: Normal Balances, No Positions")
        binance_client = MockBinanceClient(usdt_balance=500.0)
        drift_client = MockDriftClient(free_collateral=750.0, positions=0)
        
        can_trade, reason, trade_size = await balance_manager.validate_trade_feasibility(
            binance_client, drift_client, 100.0
        )
        
        print(f"Can trade: {can_trade}")
        print(f"Reason: {reason}")
        print(f"Trade size: ${trade_size:.2f}")
        
        # Test 2: Low balances - should use dynamic sizing
        print("\n📊 Test 2: Low Balances - Dynamic Sizing")
        binance_client = MockBinanceClient(usdt_balance=150.0)
        drift_client = MockDriftClient(free_collateral=150.0, positions=0)
        
        can_trade, reason, trade_size = await balance_manager.validate_trade_feasibility(
            binance_client, drift_client, 100.0
        )
        
        print(f"Can trade: {can_trade}")
        print(f"Reason: {reason}")
        print(f"Trade size: ${trade_size:.2f}")
        
        # Test 3: Maximum positions reached
        print("\n📊 Test 3: Maximum Positions Reached")
        binance_client = MockBinanceClient(usdt_balance=500.0)
        drift_client = MockDriftClient(free_collateral=750.0, positions=3)  # Max positions
        
        can_trade, reason, trade_size = await balance_manager.validate_trade_feasibility(
            binance_client, drift_client, 100.0
        )
        
        print(f"Can trade: {can_trade}")
        print(f"Reason: {reason}")
        print(f"Trade size: ${trade_size:.2f}")
        
        # Test 4: Insufficient funds
        print("\n📊 Test 4: Insufficient Funds")
        binance_client = MockBinanceClient(usdt_balance=50.0)
        drift_client = MockDriftClient(free_collateral=50.0, positions=0)
        
        can_trade, reason, trade_size = await balance_manager.validate_trade_feasibility(
            binance_client, drift_client, 100.0
        )
        
        print(f"Can trade: {can_trade}")
        print(f"Reason: {reason}")
        print(f"Trade size: ${trade_size:.2f}")
        
        # Test 5: Dynamic sizing with existing positions
        print("\n📊 Test 5: Dynamic Sizing with 1 Existing Position")
        binance_client = MockBinanceClient(usdt_balance=300.0)
        drift_client = MockDriftClient(free_collateral=300.0, positions=1)
        
        dynamic_size = balance_manager.calculate_dynamic_trade_size(300.0, 1)
        print(f"Dynamic trade size with 1 position: ${dynamic_size:.2f}")
        
        # Test 6: Status summary
        print("\n📊 Test 6: Status Summary")
        status = balance_manager.get_status_summary()
        for key, value in status.items():
            print(f"{key}: {value}")
        
        print("\n🎉 All tests completed successfully!")
        
        # Test integration with existing modules
        print("\n🔗 Testing Integration with Existing Modules")
        try:
            from modules.price_feed import PriceFeed
            price_feed = PriceFeed(config)
            print("✅ Price feed integration works")
        except Exception as e:
            print(f"⚠️  Price feed integration issue: {e}")
        
        try:
            from modules.arb_detector import ArbitrageDetector
            arb_detector = ArbitrageDetector(config)
            print("✅ Arbitrage detector integration works")
        except Exception as e:
            print(f"⚠️  Arbitrage detector integration issue: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_simplified_balance_manager())
    print(f"\n{'✅ SUCCESS' if success else '❌ FAILURE'}")
    sys.exit(0 if success else 1)
