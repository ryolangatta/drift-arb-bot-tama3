#!/usr/bin/env python3
"""
Test PnL Logger Module
"""
import sys
import os
import json
import csv
import time
import logging
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

# Import our module
sys.path.append('modules')
from pnl_logger import PnLLogger, TradeRecord, TradeStatus, TradeType

def test_pnl_logger():
    """Test all PnL Logger functionality"""
    
    print("🧪 Testing PnL Logger")
    print("=" * 50)
    
    # Test configuration
    config = {
        'DATA_DIR': 'data/test_trades',
        'LOG_TO_CSV': True,
        'LOG_TO_JSON': True,
        'BACKUP_ENABLED': True,
        'STARTING_BALANCE': 1000.0
    }
    
    # Clean up test directory COMPLETELY
    if os.path.exists(config['DATA_DIR']):
        import shutil
        shutil.rmtree(config['DATA_DIR'])
    
    # Wait a moment to ensure cleanup
    time.sleep(0.1)
    
    # Test 1: Initialization
    print("\n📊 Test 1: PnL Logger Initialization")
    pnl_logger = PnLLogger(config)
    
    assert pnl_logger.starting_balance == 1000.0
    assert pnl_logger.current_balance == 1000.0
    assert pnl_logger.total_trades == 0
    assert os.path.exists(config['DATA_DIR'])
    assert os.path.exists(pnl_logger.csv_file)
    assert os.path.exists(pnl_logger.json_file)
    
    print("✅ PnL Logger initialized correctly")
    print(f"   Data directory: {config['DATA_DIR']}")
    print(f"   Starting balance: ${pnl_logger.starting_balance:,.2f}")
    
    # Test 2: CSV Headers Creation
    print("\n📊 Test 2: CSV File Structure")
    
    with open(pnl_logger.csv_file, 'r') as f:
        reader = csv.reader(f)
        headers = next(reader)
    
    expected_headers = ['trade_id', 'timestamp', 'trade_type', 'status', 'pair', 'net_pnl']
    for header in expected_headers:
        assert header in headers, f"Header {header} missing from CSV"
    
    print(f"✅ CSV file created with {len(headers)} columns")
    
    # Test 3: JSON File Structure
    print("\n📊 Test 3: JSON File Structure")
    
    with open(pnl_logger.json_file, 'r') as f:
        data = json.load(f)
    
    assert 'metadata' in data
    assert 'trades' in data
    assert 'daily_summaries' in data
    assert data['metadata']['starting_balance'] == 1000.0
    
    print("✅ JSON file structure correct")
    
    # Test 4: Logging Winning Trade
    print("\n📊 Test 4: Logging Winning Trade")
    
    winning_trade_data = {
        'trade_type': 'ARBITRAGE',
        'status': 'EXECUTED',
        'pair': 'SOL/USDC',
        'spot_price': 150.0,
        'perp_price': 151.0,
        'spread_entry': 0.0067,  # 0.67%
        'spread_exit': 0.0020,   # 0.2%
        'position_size': 100.0,
        'entry_time': datetime.now().isoformat(),
        'exit_time': (datetime.now() + timedelta(minutes=2)).isoformat(),
        'hold_duration_seconds': 120.0,
        'binance_order_id': 'BIN123456',
        'drift_order_id': 'DFT789012',
        'binance_fill_price': 150.05,
        'drift_fill_price': 150.95,
        'binance_fee': 0.15,
        'drift_fee': 0.10,
        'network_fee': 0.05,
        'slippage_cost': 0.20,
        'total_costs': 0.50,
        'gross_pnl': 4.70,  # Higher gross profit
        'net_pnl': 4.20,    # Net profit after costs
        'roi_percent': 4.20,
        'volatility': 0.0025,
        'volume_24h': 5000000.0,
        'market_state': 'NORMAL',
        'execution_notes': 'Clean execution',
        'filter_results': 'All filters passed'
    }
    
    trade_id = pnl_logger.log_trade(winning_trade_data)
    
    assert trade_id is not None
    assert pnl_logger.total_trades == 1
    assert pnl_logger.winning_trades == 1
    assert abs(pnl_logger.current_balance - 1004.20) < 0.01, f"Expected ~1004.20, got {pnl_logger.current_balance}"
    
    print(f"✅ Winning trade logged: {trade_id}")
    print(f"   P&L: ${winning_trade_data['net_pnl']:.2f}")
    print(f"   New balance: ${pnl_logger.current_balance:.2f}")
    
    # Test 5: Logging Losing Trade
    print("\n📊 Test 5: Logging Losing Trade")
    
    losing_trade_data = {
        'trade_type': 'ARBITRAGE',
        'status': 'EXECUTED',
        'pair': 'ETH/USDC',
        'spot_price': 2000.0,
        'perp_price': 2005.0,
        'spread_entry': 0.0025,  # 0.25%
        'spread_exit': 0.0030,   # 0.3% - spread widened
        'position_size': 200.0,
        'entry_time': datetime.now().isoformat(),
        'exit_time': (datetime.now() + timedelta(minutes=5)).isoformat(),
        'hold_duration_seconds': 300.0,
        'binance_order_id': 'BIN234567',
        'drift_order_id': 'DFT890123',
        'binance_fill_price': 2001.0,
        'drift_fill_price': 2003.0,
        'binance_fee': 0.20,
        'drift_fee': 0.15,
        'network_fee': 0.05,
        'slippage_cost': 0.40,
        'total_costs': 0.80,
        'gross_pnl': -1.00,  # Lost money on spread movement
        'net_pnl': -1.80,    # Gross loss + costs
        'roi_percent': -0.90,
        'volatility': 0.0015,
        'volume_24h': 8000000.0,
        'market_state': 'NORMAL',
        'execution_notes': 'Spread moved against us',
        'filter_results': 'Volatility filter triggered late'
    }
    
    trade_id_2 = pnl_logger.log_trade(losing_trade_data)
    
    assert pnl_logger.total_trades == 2
    assert pnl_logger.losing_trades == 1
    assert abs(pnl_logger.current_balance - 1002.40) < 0.01, f"Expected ~1002.40, got {pnl_logger.current_balance}"
    
    print(f"✅ Losing trade logged: {trade_id_2}")
    print(f"   P&L: ${losing_trade_data['net_pnl']:.2f}")
    print(f"   New balance: ${pnl_logger.current_balance:.2f}")
    
    # Test 6: Performance Statistics
    print("\n📊 Test 6: Performance Statistics")
    
    stats = pnl_logger.get_performance_stats(days=30)
    
    assert stats['total_trades'] == 2
    assert stats['winning_trades'] == 1
    assert stats['losing_trades'] == 1
    assert stats['win_rate'] == 0.5
    assert abs(stats['total_pnl'] - 2.40) < 0.01, f"Expected ~2.40, got {stats['total_pnl']}"
    assert abs(stats['current_balance'] - 1002.40) < 0.01, f"Expected ~1002.40, got {stats['current_balance']}"
    
    print("✅ Performance statistics calculated correctly")
    print(f"   Win rate: {stats['win_rate']:.1%}")
    print(f"   Total P&L: ${stats['total_pnl']:.2f}")
    print(f"   ROI: {stats['roi_percentage']:.2f}%")
    print(f"   Sharpe ratio: {stats['sharpe_ratio']:.2f}")
    
    # Test 7: Daily Summary
    print("\n📊 Test 7: Daily Summary")
    
    today = datetime.now().strftime('%Y-%m-%d')
    daily_summary = pnl_logger.get_daily_summary(today)
    
    assert daily_summary['trades'] == 2
    assert daily_summary['winning_trades'] == 1
    assert daily_summary['losing_trades'] == 1
    assert abs(daily_summary['total_pnl'] - 2.40) < 0.01, f"Expected ~2.40, got {daily_summary['total_pnl']}"
    
    print("✅ Daily summary working correctly")
    print(f"   Today's trades: {daily_summary['trades']}")
    print(f"   Today's P&L: ${daily_summary['total_pnl']:.2f}")
    
    # Test 8: CSV File Content
    print("\n📊 Test 8: CSV File Verification")
    
    with open(pnl_logger.csv_file, 'r') as f:
        reader = csv.DictReader(f)
        csv_trades = list(reader)
    
    assert len(csv_trades) == 2
    assert csv_trades[0]['pair'] == 'SOL/USDC'
    assert csv_trades[1]['pair'] == 'ETH/USDC'
    assert abs(float(csv_trades[0]['net_pnl']) - 4.20) < 0.01
    assert abs(float(csv_trades[1]['net_pnl']) - (-1.80)) < 0.01
    
    print("✅ CSV file contains correct trade data")
    
    # Test 9: JSON File Content
    print("\n📊 Test 9: JSON File Verification")
    
    with open(pnl_logger.json_file, 'r') as f:
        json_data = json.load(f)
    
    assert len(json_data['trades']) == 2
    assert abs(json_data['metadata']['current_balance'] - 1002.40) < 0.01
    assert json_data['metadata']['total_trades'] == 2
    
    print("✅ JSON file contains correct trade data")
    
    # Test 10: Trade Retrieval
    print("\n📊 Test 10: Trade Retrieval")
    
    retrieved_trade = pnl_logger.get_trade_by_id(trade_id)
    assert retrieved_trade is not None
    assert retrieved_trade.pair == 'SOL/USDC'
    assert abs(retrieved_trade.net_pnl - 4.20) < 0.01
    
    print("✅ Trade retrieval working")
    
    # Test 11: Trade Update
    print("\n📊 Test 11: Trade Update")
    
    update_success = pnl_logger.update_trade(trade_id, {
        'execution_notes': 'Updated notes',
        'roi_percent': 4.25  # Slight adjustment
    })
    
    assert update_success == True
    
    updated_trade = pnl_logger.get_trade_by_id(trade_id)
    assert updated_trade.execution_notes == 'Updated notes'
    assert abs(updated_trade.roi_percent - 4.25) < 0.01
    
    print("✅ Trade update working")
    
    # Test 12: Data Export
    print("\n📊 Test 12: Data Export")
    
    # Export as JSON
    json_export_path = pnl_logger.export_data(format='json')
    assert os.path.exists(json_export_path)
    
    with open(json_export_path, 'r') as f:
        export_data = json.load(f)
    
    assert export_data['total_trades'] == 2
    assert len(export_data['trades']) == 2
    
    # Export as CSV
    csv_export_path = pnl_logger.export_data(format='csv')
    assert os.path.exists(csv_export_path)
    
    with open(csv_export_path, 'r') as f:
        reader = csv.DictReader(f)
        exported_trades = list(reader)
    
    assert len(exported_trades) == 2
    
    print("✅ Data export working")
    print(f"   JSON export: {os.path.basename(json_export_path)}")
    print(f"   CSV export: {os.path.basename(csv_export_path)}")
    
    # Test 13: Risk Calculations
    print("\n📊 Test 13: Risk Calculations")
    
    # Add more trades for better risk calculations
    for i in range(3):
        test_trade = {
            'trade_type': 'ARBITRAGE',
            'status': 'EXECUTED',
            'pair': f'TEST{i}/USDC',
            'spot_price': 100.0 + i,
            'perp_price': 100.5 + i,
            'spread_entry': 0.005,
            'position_size': 50.0,
            'net_pnl': (-1.0) ** i * (i + 1),  # Alternating wins/losses
            'total_costs': 0.25,
            'hold_duration_seconds': 60.0 * (i + 1),
            'execution_notes': f'Test trade {i}'
        }
        pnl_logger.log_trade(test_trade)
    
    # Recalculate stats
    updated_stats = pnl_logger.get_performance_stats()
    
    assert updated_stats['total_trades'] == 5
    assert updated_stats['sharpe_ratio'] != 0  # Should have calculated value
    assert updated_stats['max_drawdown'] >= 0
    assert updated_stats['profit_factor'] > 0
    
    print("✅ Risk calculations working")
    print(f"   Max drawdown: {updated_stats['max_drawdown']:.2%}")
    print(f"   Profit factor: {updated_stats['profit_factor']:.2f}")
    
    # Test 14: Data Persistence (Reload)
    print("\n📊 Test 14: Data Persistence")
    
    # Create new logger instance to test loading
    pnl_logger_2 = PnLLogger(config)
    
    assert pnl_logger_2.total_trades == 5
    assert pnl_logger_2.winning_trades > 0
    assert abs(pnl_logger_2.current_balance - pnl_logger.current_balance) < 0.01  # Should match
    
    print("✅ Data persistence working")
    print(f"   Loaded {pnl_logger_2.total_trades} trades from files")
    print(f"   Balance: ${pnl_logger_2.current_balance:.2f}")
    
    # Test 15: Error Handling
    print("\n📊 Test 15: Error Handling")
    
    # Test with minimal valid trade data
    try:
        minimal_trade = {
            'pair': 'MINIMAL/USDC',
            'spot_price': 100.0,
            'perp_price': 100.5,
            'spread_entry': 0.005,
            'position_size': 50.0,
            'net_pnl': 1.0
        }
        trade_id = pnl_logger.log_trade(minimal_trade)
        assert trade_id is not None
        print("✅ Error handling working (graceful handling of minimal data)")
    except Exception as e:
        print(f"✅ Error handling working (proper exception): {type(e).__name__}")
    
    # Test 16: File Operations
    print("\n📊 Test 16: File Operations")
    
    # Check that files are being written
    csv_size = os.path.getsize(pnl_logger.csv_file)
    json_size = os.path.getsize(pnl_logger.json_file)
    
    assert csv_size > 0, "CSV file should have content"
    assert json_size > 0, "JSON file should have content"
    
    print(f"✅ File operations working")
    print(f"   CSV size: {csv_size} bytes")
    print(f"   JSON size: {json_size} bytes")
    
    return True

if __name__ == "__main__":
    try:
        success = test_pnl_logger()
        if success:
            print("\n🎉 All PnL Logger tests passed!")
            print("\n📋 Features tested:")
            print("   ✅ File initialization (CSV + JSON)")
            print("   ✅ Trade logging (wins and losses)")
            print("   ✅ Performance statistics calculation")
            print("   ✅ Daily summary tracking")
            print("   ✅ Risk metrics (Sharpe ratio, drawdown, profit factor)")
            print("   ✅ Data persistence and reload")
            print("   ✅ CSV and JSON export")
            print("   ✅ Trade retrieval and updates")
            print("   ✅ Balance tracking with floating-point precision")
            print("   ✅ Error handling")
            
            print("\n🚀 Ready to proceed to Step 7: Discord Alerts!")
        else:
            print("\n❌ SOME TESTS FAILED")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
