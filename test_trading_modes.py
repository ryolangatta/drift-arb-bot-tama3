#!/usr/bin/env python3
"""
Test script for Trading Mode Controller
Tests DRY_RUN, LIVE_MODE, and TESTNET controls
"""
import os
import sys
import json
import logging

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.trading_mode_controller import TradingModeController, TradingMode

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def clear_test_env():
    """Clear test environment variables"""
    test_vars = ['DRY_RUN', 'LIVE_MODE', 'ENABLE_TESTNET_TRADING', 'CONFIRM_LIVE_TRADING']
    for var in test_vars:
        if var in os.environ:
            del os.environ[var]

def set_test_env(**kwargs):
    """Set test environment variables"""
    clear_test_env()
    for key, value in kwargs.items():
        os.environ[key] = str(value)

def test_trading_mode_controller():
    """Test the trading mode controller"""
    try:
        print("🧪 Testing Trading Mode Controller")
        print("=" * 60)
        
        # Default config
        config = {
            'TRADING_CONFIG': {
                'TRADE_SIZE_USDC': 100
            }
        }
        
        # Test 1: Default safe mode (DRY_RUN)
        print("\n📊 Test 1: Default Mode (Should be DRY_RUN)")
        clear_test_env()
        controller = TradingModeController(config)
        
        assert controller.is_dry_run(), "Default mode should be DRY_RUN"
        assert not controller.is_live_mode(), "Should not be in live mode by default"
        print("✅ Default mode is DRY_RUN (safe)")
        
        # Test 2: Explicit DRY_RUN mode
        print("\n📊 Test 2: Explicit DRY_RUN Mode")
        set_test_env(DRY_RUN='true', LIVE_MODE='false')
        controller = TradingModeController(config)
        
        assert controller.is_dry_run(), "Should be in DRY_RUN mode"
        assert not controller.can_place_real_orders(), "Should not allow real orders"
        print("✅ DRY_RUN mode working correctly")
        
        # Test 3: TESTNET mode
        print("\n📊 Test 3: TESTNET Mode")
        set_test_env(DRY_RUN='false', LIVE_MODE='false', ENABLE_TESTNET_TRADING='true')
        controller = TradingModeController(config)
        
        assert controller.is_testnet_mode(), "Should be in TESTNET mode"
        assert controller.can_place_real_orders(), "Should allow testnet orders"
        print("✅ TESTNET mode working correctly")
        
        # Test 4: LIVE mode without confirmation (should fail)
        print("\n📊 Test 4: LIVE Mode Without Confirmation (Should Fail)")
        set_test_env(DRY_RUN='false', LIVE_MODE='true')
        controller = TradingModeController(config)
        
        assert controller.is_dry_run(), "Should fallback to DRY_RUN without confirmation"
        assert not controller.is_live_mode(), "Should not enable live mode without confirmation"
        print("✅ LIVE mode properly blocked without confirmation")
        
        # Test 5: LIVE mode with proper confirmation
        print("\n📊 Test 5: LIVE Mode With Proper Confirmation")
        set_test_env(
            DRY_RUN='false', 
            LIVE_MODE='true',
            CONFIRM_LIVE_TRADING='yes_i_understand_this_uses_real_money'
        )
        controller = TradingModeController(config)
        
        assert controller.is_live_mode(), "Should be in LIVE mode with proper confirmation"
        assert controller.can_place_real_orders(), "Should allow real orders"
        print("✅ LIVE mode enabled with proper confirmation")
        
        # Test 6: Trade validation in different modes
        print("\n📊 Test 6: Trade Validation")
        
        # Test DRY_RUN validation
        set_test_env(DRY_RUN='true')
        controller = TradingModeController(config)
        
        test_opportunity = {
            'pair': 'SOL/USDC',
            'spread': 0.005,
            'potential_profit_usdc': 5.0,
            'trade_size': 100
        }
        
        validation = controller.validate_trade_execution(test_opportunity)
        assert validation['allowed'], "DRY_RUN should allow trades"
        assert validation['simulated'], "DRY_RUN should be simulated"
        print("✅ DRY_RUN trade validation working")
        
        # Test TESTNET validation
        set_test_env(DRY_RUN='false', ENABLE_TESTNET_TRADING='true')
        controller = TradingModeController(config)
        
        validation = controller.validate_trade_execution(test_opportunity)
        assert validation['allowed'], "TESTNET should allow trades"
        assert not validation['simulated'], "TESTNET should not be simulated"
        print("✅ TESTNET trade validation working")
        
        # Test 7: Simulation trade creation
        print("\n📊 Test 7: Simulation Trade Creation")
        set_test_env(DRY_RUN='true')
        controller = TradingModeController(config)
        
        sim_trade = controller.create_simulation_trade(test_opportunity)
        assert sim_trade['type'] == 'SIMULATED', "Should create simulated trade"
        assert 'sim_' in sim_trade['id'], "Should have simulation ID prefix"
        print("✅ Simulation trade creation working")
        
        # Test 8: Discord alert formatting
        print("\n📊 Test 8: Discord Alert Formatting")
        
        # DRY_RUN formatting
        set_test_env(DRY_RUN='true')
        controller = TradingModeController(config)
        title = controller.format_discord_alert_title("Trade Executed")
        assert "🔒 [SIMULATION]" in title, "Should format DRY_RUN alerts"
        
        # TESTNET formatting
        set_test_env(DRY_RUN='false', ENABLE_TESTNET_TRADING='true')
        controller = TradingModeController(config)
        title = controller.format_discord_alert_title("Trade Executed")
        assert "🧪 [TESTNET]" in title, "Should format TESTNET alerts"
        
        # LIVE formatting
        set_test_env(
            DRY_RUN='false', 
            LIVE_MODE='true',
            CONFIRM_LIVE_TRADING='yes_i_understand_this_uses_real_money'
        )
        controller = TradingModeController(config)
        title = controller.format_discord_alert_title("Trade Executed")
        assert "💰 [LIVE]" in title, "Should format LIVE alerts"
        
        print("✅ Discord alert formatting working")
        
        # Test 9: Mode summary
        print("\n📊 Test 9: Mode Summary")
        summary = controller.get_mode_summary()
        assert 'trading_mode' in summary, "Should include trading mode"
        assert 'timestamp' in summary, "Should include timestamp"
        print("✅ Mode summary working")
        
        # Test 10: Environment instructions
        print("\n📊 Test 10: Environment Instructions")
        instructions = controller.get_environment_instructions()
        assert 'DRY_RUN' in instructions, "Should include DRY_RUN instructions"
        assert 'LIVE_MODE' in instructions, "Should include LIVE_MODE instructions"
        print("✅ Environment instructions available")
        
        print("\n🎉 All Trading Mode Controller tests passed!")
        
        # Display configuration summary
        print("\n📋 Final Configuration Summary:")
        summary = controller.get_mode_summary()
        for key, value in summary.items():
            print(f"  {key}: {value}")
        
        # Clean up
        clear_test_env()
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        clear_test_env()
        return False

if __name__ == "__main__":
    success = test_trading_mode_controller()
    print(f"\n{'✅ SUCCESS' if success else '❌ FAILURE'}")
    sys.exit(0 if success else 1)
