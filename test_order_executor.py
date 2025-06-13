#!/usr/bin/env python3
"""
Test script for Order Executor
Tests retry logic, order execution, and confirmation systems
"""
import asyncio
import sys
import os
import logging
import time
import random

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.order_executor import OrderExecutor, OrderStatus, ExchangeType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MockBinanceClient:
    """Mock Binance client for testing"""
    def __init__(self, should_fail_times=0):
        self.should_fail_times = should_fail_times
        self.call_count = 0
        self.orders = {}
    
    def order_market_buy(self, symbol, quantity):
        self.call_count += 1
        
        # Simulate failures for first N calls
        if self.call_count <= self.should_fail_times:
            raise Exception(f"Simulated Binance API error (attempt {self.call_count})")
        
        order_id = f"binance_{symbol}_{int(time.time() * 1000)}"
        order = {
            'orderId': order_id,
            'symbol': symbol,
            'side': 'BUY',
            'status': 'FILLED',
            'executedQty': str(quantity),
            'fills': [],
            'transactTime': int(time.time() * 1000)
        }
        
        self.orders[order_id] = order
        return order
    
    def get_order(self, symbol, orderId):
        return self.orders.get(orderId, {'status': 'UNKNOWN'})

class MockDriftUser:
    """Mock Drift user for testing"""
    def __init__(self, positions_count=0):
        self.positions_count = positions_count
    
    def get_active_perp_positions(self):
        return [{'base_asset_amount': 1e9} for _ in range(self.positions_count)]

class MockDriftClient:
    """Mock Drift client for testing"""
    def __init__(self, should_fail_times=0, positions_after_order=1):
        self.should_fail_times = should_fail_times
        self.call_count = 0
        self.positions_after_order = positions_after_order
        self.user = MockDriftUser(0)  # Start with no positions
    
    async def place_perp_order(self, market, size, price):
        self.call_count += 1
        
        # Simulate failures for first N calls
        if self.call_count <= self.should_fail_times:
            raise Exception(f"Simulated Drift API error (attempt {self.call_count})")
        
        # Simulate successful order - update positions
        self.user.positions_count = self.positions_after_order
        
        order_id = f"drift_{market}_{int(time.time() * 1000)}"
        return {
            'orderId': order_id,
            'market': market,
            'side': 'SHORT',
            'size': size,
            'price': price,
            'status': 'FILLED',
            'timestamp': time.time()
        }
    
    def get_user(self):
        return self.user

async def test_order_executor():
    """Test the order executor functionality"""
    try:
        print("🧪 Testing Order Executor")
        print("=" * 50)
        
        # Test config
        config = {
            'MAX_RETRIES': 3,
            'BASE_RETRY_DELAY': 0.1,  # Fast for testing
            'MAX_RETRY_DELAY': 1.0,   # Fast for testing
            'BACKOFF_MULTIPLIER': 2.0,
            'CONFIRMATION_TIMEOUT': 10,
            'CONFIRMATION_CHECK_INTERVAL': 0.5
        }
        
        # Test 1: Initialize Order Executor
        print("\n📊 Test 1: Order Executor Initialization")
        executor = OrderExecutor(config)
        
        assert executor.max_retries == 3, "Should use config max retries"
        assert executor.base_delay == 0.1, "Should use config base delay"
        print("✅ Order Executor initialized with correct parameters")
        
        # Test 2: Retry delay calculation
        print("\n📊 Test 2: Retry Delay Calculation")
        delay1 = executor.calculate_retry_delay(0)  # First retry
        delay2 = executor.calculate_retry_delay(1)  # Second retry
        delay3 = executor.calculate_retry_delay(2)  # Third retry
        
        assert delay1 >= 0.1, "First delay should be >= base delay"
        assert delay2 > delay1, "Second delay should be greater than first"
        assert delay3 > delay2, "Third delay should be greater than second"
        print(f"✅ Retry delays: {delay1:.3f}s, {delay2:.3f}s, {delay3:.3f}s")
        
        # Test 3: Successful operation without retries
        print("\n📊 Test 3: Successful Operation (No Retries)")
        
        async def successful_operation():
            await asyncio.sleep(0.01)  # Simulate work
            return "Success!"
        
        success, result, error = await executor.execute_with_retry(
            successful_operation,
            "Test Operation"
        )
        
        assert success, "Operation should succeed"
        assert result == "Success!", "Should return correct result"
        assert error == "", "Should have no error message"
        print("✅ Successful operation completed without retries")
        
        # Test 4: Operation with retries (eventually succeeds)
        print("\n📊 Test 4: Operation with Retries (Eventually Succeeds)")
        
        call_count = 0
        async def retry_operation():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first 2 times
                raise Exception(f"Simulated failure {call_count}")
            return f"Success on attempt {call_count}"
        
        success, result, error = await executor.execute_with_retry(
            retry_operation,
            "Retry Test Operation"
        )
        
        assert success, "Operation should eventually succeed"
        assert "Success on attempt 3" in result, "Should succeed on third attempt"
        assert call_count == 3, "Should have been called 3 times"
        print("✅ Operation succeeded after retries")
        
        # Test 5: Operation that fails all retries
        print("\n📊 Test 5: Operation That Fails All Retries")
        
        async def always_fail_operation():
            raise Exception("Always fails")
        
        success, result, error = await executor.execute_with_retry(
            always_fail_operation,
            "Always Fail Operation"
        )
        
        assert not success, "Operation should fail"
        assert result is None, "Should return None result"
        assert "Always fails" in error, "Should return error message"
        print("✅ Operation correctly failed after all retries")
        
        # Test 6: Binance order execution
        print("\n�� Test 6: Binance Order Execution")
        binance_client = MockBinanceClient()
        
        binance_order = await executor.place_binance_order(
            binance_client, "SOLUSDT", "BUY", 1.0
        )
        
        assert binance_order['symbol'] == 'SOLUSDT', "Should have correct symbol"
        assert binance_order['side'] == 'BUY', "Should have correct side"
        assert binance_order['status'] == 'FILLED', "Should be filled"
        print("✅ Binance order execution working")
        
        # Test 7: Drift order execution
        print("\n📊 Test 7: Drift Order Execution")
        drift_client = MockDriftClient()
        
        drift_order = await executor.place_drift_order(
            drift_client, "SOL-PERP", "SHORT", 1.0, 150.0
        )
        
        assert drift_order['market'] == 'SOL-PERP', "Should have correct market"
        assert drift_order['side'] == 'SHORT', "Should have correct side"
        print("✅ Drift order execution working")
        
        # Test 8: Order confirmation
        print("\n📊 Test 8: Order Confirmation")
        
        # Test Binance confirmation with the correct order
        confirmed, info = await executor.confirm_binance_order(
            binance_client, binance_order['orderId'], "SOLUSDT"
        )
        assert confirmed, f"Binance order should be confirmed: {info}"
        
        # Test Drift confirmation (should detect the position)
        confirmed, info = await executor.confirm_drift_order(drift_client, drift_order['orderId'])
        assert confirmed, f"Drift order should be confirmed: {info}"
        print("✅ Order confirmation working")
        
        # Test 9: Binance order with retries
        print("\n📊 Test 9: Binance Order with Retries")
        failing_binance = MockBinanceClient(should_fail_times=2)  # Fail first 2 attempts
        
        success, order, error = await executor.execute_with_retry(
            executor.place_binance_order,
            "Binance Order with Retries",
            failing_binance, "ETHUSDT", "BUY", 0.5
        )
        
        assert success, "Should succeed after retries"
        assert order['symbol'] == 'ETHUSDT', "Should have correct symbol"
        assert failing_binance.call_count == 3, "Should have retried 3 times"
        print("✅ Binance order with retries working")
        
        # Test 10: Drift order with retries
        print("\n📊 Test 10: Drift Order with Retries")
        failing_drift = MockDriftClient(should_fail_times=1)  # Fail first attempt
        
        success, order, error = await executor.execute_with_retry(
            executor.place_drift_order,
            "Drift Order with Retries",
            failing_drift, "ETH-PERP", "SHORT", 0.5, 2500.0
        )
        
        assert success, "Should succeed after retries"
        assert order['market'] == 'ETH-PERP', "Should have correct market"
        assert failing_drift.call_count == 2, "Should have retried 2 times"
        print("✅ Drift order with retries working")
        
        # Test 11: Full arbitrage execution
        print("\n📊 Test 11: Full Arbitrage Execution")
        
        # Create clean clients for full test
        clean_binance = MockBinanceClient()
        clean_drift = MockDriftClient(positions_after_order=1)
        
        opportunity = {
            'pair': 'SOL/USDC',
            'spread': 0.005,
            'spot_price': 150.0,
            'perp_price': 150.75,
            'potential_profit_usdc': 5.0
        }
        
        success, result = await executor.execute_arbitrage_orders(
            clean_binance, clean_drift, opportunity, 100.0
        )
        
        assert success, f"Arbitrage execution should succeed: {result.get('error', '')}"
        assert result['binance_order'] is not None, "Should have Binance order"
        assert result['drift_order'] is not None, "Should have Drift order"
        assert 'execution_time_seconds' in result, "Should track execution time"
        print(f"✅ Full arbitrage execution completed in {result['execution_time_seconds']:.2f}s")
        
        # Test 12: Single order execution
        print("\n📊 Test 12: Single Order Execution")
        
        order_params = {
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'quantity': 0.001,
            'type': 'MARKET'
        }
        
        success, result = await executor.execute_single_order(
            ExchangeType.BINANCE,
            clean_binance,
            order_params
        )
        
        assert success, "Single order execution should succeed"
        assert 'order' in result, "Should return order info"
        assert 'confirmation' in result, "Should return confirmation info"
        print("✅ Single order execution working")
        
        # Test 13: Execution statistics
        print("\n📊 Test 13: Execution Statistics")
        stats = executor.get_execution_stats()
        
        assert 'total_executions' in stats, "Should include total executions"
        assert 'max_retries' in stats, "Should include max retries"
        assert 'confirmation_timeout' in stats, "Should include confirmation timeout"
        print("✅ Execution statistics working")
        
        print("\n🎉 All Order Executor tests passed!")
        
        # Display final statistics
        print("\n📋 Final Execution Statistics:")
        final_stats = executor.get_execution_stats()
        for key, value in final_stats.items():
            print(f"  {key}: {value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_order_executor())
    print(f"\n{'✅ SUCCESS' if success else '❌ FAILURE'}")
    sys.exit(0 if success else 1)
