#!/usr/bin/env python3
"""
Test script for Risk Controller
Tests position tracking, timeouts, and auto-close functionality
"""
import asyncio
import os
import sys
import json
import logging
import time
from datetime import datetime, timedelta

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.risk_controller import RiskController, Position, PositionStatus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_test_files():
    """Clean up test files"""
    try:
        if os.path.exists('data/positions.json'):
            os.remove('data/positions.json')
    except:
        pass

async def test_risk_controller():
    """Test the risk controller functionality"""
    try:
        print("🧪 Testing Risk Controller")
        print("=" * 50)
        
        # Clean up any existing test data
        cleanup_test_files()
        
        # Test config
        config = {
            'RISK_MANAGEMENT': {
                'MAX_TRADES_PER_DAY': 5,
                'MAX_DAILY_DRAWDOWN': 0.05
            }
        }
        
        # Override environment for testing
        os.environ['MAX_POSITION_AGE_SECONDS'] = '5'  # 5 seconds for testing
        os.environ['MAX_CONCURRENT_POSITIONS'] = '3'
        
        # Test 1: Initialize Risk Controller
        print("\n📊 Test 1: Risk Controller Initialization")
        risk_controller = RiskController(config)
        
        assert risk_controller.max_position_age_seconds == 5, "Should use env variable for max age"
        assert risk_controller.max_concurrent_positions == 3, "Should use env variable for max positions"
        print("✅ Risk Controller initialized with correct parameters")
        
        # Test 2: Check if new position can be opened
        print("\n📊 Test 2: Position Opening Validation")
        can_open, reason = risk_controller.can_open_new_position()
        
        assert can_open, f"Should be able to open new position: {reason}"
        print("✅ New position can be opened")
        
        # Test 3: Create a position
        print("\n📊 Test 3: Position Creation")
        position = risk_controller.create_position(
            pair="SOL/USDC",
            trade_size=100.0,
            entry_spread=0.005,
            binance_order_id="binance_123",
            drift_order_id="drift_456",
            entry_prices={"binance_price": 150.0, "drift_price": 150.5}
        )
        
        assert position.pair == "SOL/USDC", "Position should have correct pair"
        assert position.status == PositionStatus.OPEN, "Position should be open"
        assert len(risk_controller.open_positions) == 1, "Should have one open position"
        print(f"✅ Position created: {position.id}")
        
        # Test 4: Position age calculation
        print("\n📊 Test 4: Position Age Calculation")
        age = position.get_age_seconds()
        assert age >= 0, "Position age should be non-negative"
        assert age < 2, "Position should be very young"
        print(f"✅ Position age: {age:.2f} seconds")
        
        # Test 5: Position limits
        print("\n📊 Test 5: Position Limits")
        # Create more positions to test limits
        for i in range(2):
            risk_controller.create_position(
                pair=f"ETH/USDC",
                trade_size=50.0,
                entry_spread=0.003
            )
        
        assert len(risk_controller.open_positions) == 3, "Should have 3 open positions"
        
        can_open, reason = risk_controller.can_open_new_position()
        assert not can_open, "Should not be able to open more positions"
        assert "Maximum concurrent positions" in reason, "Should mention position limit"
        print("✅ Position limits working correctly")
        
        # Test 6: Position timeout detection
        print("\n📊 Test 6: Position Timeout Detection")
        print("Waiting 6 seconds for positions to expire...")
        await asyncio.sleep(6)  # Wait for positions to expire
        
        expired_positions = risk_controller.get_expired_positions()
        assert len(expired_positions) == 3, f"All positions should be expired, got {len(expired_positions)}"
        print("✅ Position timeout detection working")
        
        # Test 7: Auto-close marking
        print("\n📊 Test 7: Auto-Close Marking")
        first_position = list(risk_controller.open_positions.values())[0]
        success = risk_controller.mark_position_for_auto_close(first_position.id)
        
        assert success, "Should successfully mark position for auto-close"
        assert first_position.auto_close_triggered, "Position should be marked for auto-close"
        assert first_position.status == PositionStatus.CLOSING, "Position status should be CLOSING"
        print("✅ Auto-close marking working")
        
        # Test 8: Position closing
        print("\n📊 Test 8: Position Closing")
        closed_position = risk_controller.close_position(
            first_position.id,
            exit_prices={"binance_price": 149.0, "drift_price": 149.5},
            profit_loss=-1.0,
            close_reason="Test close"
        )
        
        assert closed_position is not None, "Should return closed position"
        assert closed_position.status == PositionStatus.CLOSED, "Position should be closed"
        assert len(risk_controller.open_positions) == 2, "Should have 2 open positions remaining"
        assert len(risk_controller.closed_positions) == 1, "Should have 1 closed position"
        print("✅ Position closing working")
        
        # Test 9: Position monitoring
        print("\n📊 Test 9: Position Monitoring")
        await risk_controller.start_monitoring()
        
        assert risk_controller.is_monitoring, "Should be monitoring"
        print("Monitoring for 3 seconds...")
        await asyncio.sleep(3)
        
        await risk_controller.stop_monitoring()
        assert not risk_controller.is_monitoring, "Should stop monitoring"
        print("✅ Position monitoring working")
        
        # Test 10: Position summary
        print("\n📊 Test 10: Position Summary")
        summary = risk_controller.get_position_summary()
        
        assert 'open_positions_count' in summary, "Summary should include open positions count"
        assert 'daily_pnl' in summary, "Summary should include daily P&L"
        assert summary['open_positions_count'] == len(risk_controller.open_positions), "Summary should match actual count"
        print("✅ Position summary working")
        
        # Test 11: Force close all positions
        print("\n📊 Test 11: Force Close All Positions")
        
        # First, create some new positions for this test
        new_positions = []
        for i in range(2):
            pos = risk_controller.create_position(
                pair=f"TEST{i}/USDC",
                trade_size=25.0,
                entry_spread=0.002
            )
            new_positions.append(pos)
        
        initial_open_count = len(risk_controller.open_positions)
        initial_closed_count = len(risk_controller.closed_positions)
        
        print(f"Before force close: {initial_open_count} open, {initial_closed_count} closed")
        
        risk_controller.force_close_all_positions("Test emergency close")
        
        final_open_count = len(risk_controller.open_positions)
        final_closed_count = len(risk_controller.closed_positions)
        
        print(f"After force close: {final_open_count} open, {final_closed_count} closed")
        
        assert final_open_count == 0, f"Should have no open positions after force close, got {final_open_count}"
        assert final_closed_count == initial_closed_count + initial_open_count, f"All positions should be closed: expected {initial_closed_count + initial_open_count}, got {final_closed_count}"
        print("✅ Force close all positions working")
        
        # Test 12: Position persistence
        print("\n📊 Test 12: Position Persistence")
        # Create a new position
        test_position = risk_controller.create_position(
            pair="BTC/USDC",
            trade_size=200.0,
            entry_spread=0.004
        )
        
        # Create new risk controller to test loading
        risk_controller2 = RiskController(config)
        
        assert len(risk_controller2.open_positions) == 1, "Should load open positions"
        assert len(risk_controller2.closed_positions) > 0, "Should load closed positions"
        print("✅ Position persistence working")
        
        # Test 13: Daily statistics reset
        print("\n📊 Test 13: Daily Statistics")
        daily_trades = risk_controller2.daily_trades_count
        daily_pnl = risk_controller2.daily_pnl
        
        assert daily_trades > 0, "Should have daily trades recorded"
        print(f"✅ Daily statistics: {daily_trades} trades, ${daily_pnl:.2f} P&L")
        
        print("\n🎉 All Risk Controller tests passed!")
        
        # Display final summary
        print("\n📋 Final Risk Summary:")
        final_summary = risk_controller2.get_position_summary()
        for key, value in final_summary.items():
            print(f"  {key}: {value}")
        
        # Clean up
        cleanup_test_files()
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        cleanup_test_files()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_risk_controller())
    print(f"\n{'✅ SUCCESS' if success else '❌ FAILURE'}")
    sys.exit(0 if success else 1)
