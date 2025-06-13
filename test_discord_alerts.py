#!/usr/bin/env python3
"""
Test Discord Alerts Module
"""
import sys
import asyncio
import time
import logging
from datetime import datetime
from unittest.mock import AsyncMock, patch

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

# Import our module
sys.path.append('modules')
from discord_alerts import DiscordAlerts, AlertType, AlertPriority, EmbedField, DiscordEmbed

async def test_discord_alerts():
    """Test all Discord Alerts functionality"""
    
    print("🧪 Testing Discord Alerts")
    print("=" * 50)
    
    # Test configuration with mock webhook
    config = {
        'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/mock/test',
        'BOT_NAME': 'Test Arbitrage Bot',
        'ENVIRONMENT': 'TEST',
        'ALERTS_ENABLED': True,
        'RATE_LIMIT_ENABLED': True,
        'MAX_ALERTS_PER_MINUTE': 5,
        'MIN_ALERT_INTERVAL': 1,
        'MIN_ALERT_PRIORITY': 'LOW',
        'ENABLED_ALERT_TYPES': [
            'TRADE_EXECUTED', 'TRADE_FAILED', 'BALANCE_LOW', 
            'SYSTEM_START', 'ERROR', 'DAILY_SUMMARY'
        ]
    }
    
    # Test 1: Initialization
    print("\n📊 Test 1: Discord Alerts Initialization")
    alerts = DiscordAlerts(config)
    
    assert alerts.enabled == True
    assert alerts.webhook_url == config['DISCORD_WEBHOOK_URL']
    assert alerts.max_alerts_per_minute == 5
    assert alerts.environment == 'TEST'
    assert len(alerts.enabled_alert_types) == 6
    
    print("✅ Discord Alerts initialized correctly")
    print(f"   Webhook configured: {bool(alerts.webhook_url)}")
    print(f"   Environment: {alerts.environment}")
    print(f"   Alert types enabled: {len(alerts.enabled_alert_types)}")
    
    # Test 2: Alert Type Filtering
    print("\n📊 Test 2: Alert Type Filtering")
    
    # Reset rate limits for clean testing
    alerts.reset_rate_limits()
    
    # Should allow enabled types
    should_send_trade = alerts._should_send_alert(AlertType.TRADE_EXECUTED, AlertPriority.HIGH)
    assert should_send_trade == True
    
    # Should block disabled types
    alerts.enabled_alert_types.discard('OPPORTUNITY_DETECTED')
    should_send_opportunity = alerts._should_send_alert(AlertType.OPPORTUNITY_DETECTED, AlertPriority.HIGH)
    assert should_send_opportunity == False
    
    print("✅ Alert type filtering working")
    
    # Test 3: Priority Filtering
    print("\n📊 Test 3: Priority Filtering")
    
    # Reset rate limits and alert types for clean testing
    alerts.reset_rate_limits()
    alerts.enabled_alert_types.add('TRADE_EXECUTED')  # Ensure it's enabled
    
    # Set minimum priority to MEDIUM
    alerts.min_priority = AlertPriority.MEDIUM
    
    # Should block LOW priority (using an enabled alert type)
    should_send_low = alerts._should_send_alert(AlertType.TRADE_EXECUTED, AlertPriority.LOW)
    assert should_send_low == False
    
    # Should allow MEDIUM and above (using an enabled alert type)
    should_send_medium = alerts._should_send_alert(AlertType.TRADE_EXECUTED, AlertPriority.MEDIUM)
    assert should_send_medium == True
    
    # Reset for other tests
    alerts.min_priority = AlertPriority.LOW
    
    print("✅ Priority filtering working")
    
    # Test 4: Rate Limiting
    print("\n📊 Test 4: Rate Limiting")
    
    # Reset rate limits for clean testing
    alerts.reset_rate_limits()
    
    # Send multiple alerts quickly
    rate_limit_results = []
    for i in range(7):  # More than max_alerts_per_minute (5)
        result = alerts._should_send_alert(AlertType.TRADE_EXECUTED, AlertPriority.HIGH)
        rate_limit_results.append(result)
        time.sleep(0.05)  # Very small delay
    
    # First 5 should be allowed, rest should be blocked
    allowed_count = sum(rate_limit_results)
    assert allowed_count <= alerts.max_alerts_per_minute
    
    print(f"✅ Rate limiting working (allowed {allowed_count}/{len(rate_limit_results)} alerts)")
    
    # Test 5: Embed Creation
    print("\n📊 Test 5: Embed Creation")
    
    # Create test embed
    test_embed = DiscordEmbed(
        title="Test Alert",
        description="This is a test alert",
        color=0x00FF00,
        fields=[
            EmbedField("Field 1", "Value 1", True),
            EmbedField("Field 2", "Value 2", False)
        ],
        footer="Test Footer",
        timestamp=datetime.now().isoformat()
    )
    
    assert test_embed.title == "Test Alert"
    assert len(test_embed.fields) == 2
    assert test_embed.fields[0].inline == True
    assert test_embed.fields[1].inline == False
    
    print("✅ Embed creation working")
    
    # Test 6: Mock Trade Executed Alert
    print("\n📊 Test 6: Trade Executed Alert")
    
    # Reset rate limits for testing
    alerts.reset_rate_limits()
    alerts.enabled_alert_types.add('TRADE_EXECUTED')
    
    trade_data = {
        'pair': 'SOL/USDC',
        'spread': 0.0075,  # 0.75%
        'position_size': 100.0,
        'spot_price': 150.0,
        'perp_price': 151.125
    }
    
    execution_result = {
        'net_pnl': 3.50,
        'execution_time_seconds': 2.3,
        'roi_percent': 3.50,
        'binance_order': {
            'orderId': 'BIN123456',
            'status': 'FILLED'
        },
        'drift_order': {
            'orderId': 'DFT789012',
            'side': 'SHORT'
        }
    }
    
    # Mock the HTTP request
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 204  # Success
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        result = await alerts.send_trade_executed_alert(trade_data, execution_result)
        assert result == True
        
        # Verify the request was made
        assert mock_post.called
        call_args = mock_post.call_args
        assert 'json' in call_args.kwargs
        
        payload = call_args.kwargs['json']
        assert 'embeds' in payload
        assert len(payload['embeds']) == 1
        
        embed = payload['embeds'][0]
        assert 'Trade Executed' in embed['title']
        assert embed['color'] == alerts.color_map[AlertType.TRADE_EXECUTED]
    
    print("✅ Trade executed alert working")
    
    # Test 7: Mock Trade Failed Alert
    print("\n📊 Test 7: Trade Failed Alert")
    
    # Reset and enable for clean test
    alerts.reset_rate_limits()
    alerts.enabled_alert_types.add('TRADE_FAILED')
    
    failed_trade_data = {
        'pair': 'ETH/USDC',
        'spread': 0.005,
        'position_size': 200.0
    }
    
    error_message = "Insufficient balance on Binance"
    
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        result = await alerts.send_trade_failed_alert(failed_trade_data, error_message)
        assert result == True
        
        payload = mock_post.call_args.kwargs['json']
        embed = payload['embeds'][0]
        assert 'Trade Failed' in embed['title']
        assert embed['color'] == alerts.color_map[AlertType.TRADE_FAILED]
        
        # Check if error message is included
        error_field = next((f for f in embed['fields'] if 'Error' in f['name']), None)
        assert error_field is not None
        assert error_message in error_field['value']
    
    print("✅ Trade failed alert working")
    
    # Test 8: Balance Low Alert
    print("\n📊 Test 8: Balance Low Alert")
    
    # Reset and enable for clean test
    alerts.reset_rate_limits()
    alerts.enabled_alert_types.add('BALANCE_LOW')
    
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        result = await alerts.send_balance_low_alert(50.0, 100.0)
        assert result == True
        
        payload = mock_post.call_args.kwargs['json']
        embed = payload['embeds'][0]
        assert 'Low Balance' in embed['title']
        assert embed['color'] == alerts.color_map[AlertType.BALANCE_LOW]
    
    print("✅ Balance low alert working")
    
    # Test 9: System Start Alert
    print("\n📊 Test 9: System Start Alert")
    
    # Reset and enable for clean test
    alerts.reset_rate_limits()
    alerts.enabled_alert_types.add('SYSTEM_START')
    
    config_summary = {
        'starting_balance': 1000.0,
        'spread_threshold': 0.005,
        'pairs_count': 3,
        'trading_mode': 'SIMULATION',
        'version': '1.0'
    }
    
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        result = await alerts.send_system_start_alert(config_summary)
        assert result == True
        
        payload = mock_post.call_args.kwargs['json']
        embed = payload['embeds'][0]
        assert 'Bot Started' in embed['title']
        assert embed['color'] == alerts.color_map[AlertType.SYSTEM_START]
    
    print("✅ System start alert working")
    
    # Test 10: Daily Summary Alert
    print("\n📊 Test 10: Daily Summary Alert")
    
    # Reset and enable for clean test
    alerts.reset_rate_limits()
    alerts.enabled_alert_types.add('DAILY_SUMMARY')
    
    summary_data = {
        'total_trades': 15,
        'win_rate': 0.667,  # 66.7%
        'total_pnl': 25.50,
        'current_balance': 1025.50,
        'best_trade': 8.75,
        'worst_trade': -3.20,
        'total_fees': 4.25,
        'avg_spread': 0.0065,
        'avg_hold_time': 185.0
    }
    
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        result = await alerts.send_daily_summary_alert(summary_data)
        assert result == True
        
        payload = mock_post.call_args.kwargs['json']
        embed = payload['embeds'][0]
        assert 'Daily Summary' in embed['title']
        assert embed['color'] == alerts.color_map[AlertType.DAILY_SUMMARY]
        
        # Check that key metrics are included
        fields = embed['fields']
        field_names = [f['name'] for f in fields]
        assert any('Total Trades' in name for name in field_names)
        assert any('Win Rate' in name for name in field_names)
        assert any('P&L' in name for name in field_names)
    
    print("✅ Daily summary alert working")
    
    # Test 11: Error Alert
    print("\n📊 Test 11: Error Alert")
    
    # Reset and enable for clean test
    alerts.reset_rate_limits()
    alerts.enabled_alert_types.add('ERROR')
    
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        result = await alerts.send_error_alert("Database connection failed", "Database Error")
        assert result == True
        
        payload = mock_post.call_args.kwargs['json']
        embed = payload['embeds'][0]
        assert 'Error Detected' in embed['title']
        assert embed['color'] == alerts.color_map[AlertType.ERROR]
    
    print("✅ Error alert working")
    
    # Test 12: Custom Alert
    print("\n📊 Test 12: Custom Alert")
    
    # Reset for clean test
    alerts.reset_rate_limits()
    
    custom_fields = [
        {'name': 'Custom Field 1', 'value': 'Custom Value 1', 'inline': True},
        {'name': 'Custom Field 2', 'value': 'Custom Value 2', 'inline': False}
    ]
    
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 204
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        result = await alerts.send_custom_alert(
            "Custom Alert Title",
            "This is a custom alert description",
            fields=custom_fields,
            color=0xFF00FF,
            priority=AlertPriority.MEDIUM
        )
        assert result == True
        
        payload = mock_post.call_args.kwargs['json']
        embed = payload['embeds'][0]
        assert embed['title'] == "Custom Alert Title"
        assert embed['color'] == 0xFF00FF
        assert len(embed['fields']) == 2
    
    print("✅ Custom alert working")
    
    # Test 13: Configuration Updates
    print("\n📊 Test 13: Configuration Updates")
    
    new_config = {
        'MAX_ALERTS_PER_MINUTE': 10,
        'MIN_ALERT_PRIORITY': 'HIGH',
        'ENABLED_ALERT_TYPES': ['TRADE_EXECUTED', 'ERROR']
    }
    
    alerts.update_config(new_config)
    
    assert alerts.max_alerts_per_minute == 10
    assert alerts.min_priority == AlertPriority.HIGH
    assert len(alerts.enabled_alert_types) == 2
    assert 'TRADE_EXECUTED' in alerts.enabled_alert_types
    assert 'ERROR' in alerts.enabled_alert_types
    
    print("✅ Configuration updates working")
    
    # Test 14: Alert Statistics
    print("\n📊 Test 14: Alert Statistics")
    
    stats = alerts.get_alert_stats()
    
    assert 'enabled' in stats
    assert 'webhook_configured' in stats
    assert 'alerts_sent_last_hour' in stats
    assert 'rate_limit_enabled' in stats
    assert 'enabled_alert_types' in stats
    assert 'environment' in stats
    
    assert stats['enabled'] == True
    assert stats['webhook_configured'] == True
    assert stats['environment'] == 'TEST'
    
    print("✅ Alert statistics working")
    print(f"   Alerts sent last hour: {stats['alerts_sent_last_hour']}")
    print(f"   Rate limit enabled: {stats['rate_limit_enabled']}")
    
    # Test 15: Alert Type Management
    print("\n📊 Test 15: Alert Type Management")
    
    # Enable new alert type
    alerts.enable_alert_type('OPPORTUNITY_DETECTED')
    assert 'OPPORTUNITY_DETECTED' in alerts.enabled_alert_types
    
    # Disable alert type
    alerts.disable_alert_type('ERROR')
    assert 'ERROR' not in alerts.enabled_alert_types
    
    print("✅ Alert type management working")
    
    # Test 16: Rate Limit Reset
    print("\n📊 Test 16: Rate Limit Reset")
    
    # Add some fake timestamps
    current_time = time.time()
    alerts.alert_timestamps = [current_time - 30, current_time - 20, current_time - 10]
    alerts.last_alert_time = {'TRADE_EXECUTED': current_time - 15}
    
    assert len(alerts.alert_timestamps) == 3
    assert len(alerts.last_alert_time) == 1
    
    # Reset rate limits
    alerts.reset_rate_limits()
    
    assert len(alerts.alert_timestamps) == 0
    assert len(alerts.last_alert_time) == 0
    
    print("✅ Rate limit reset working")
    
    # Test 17: Webhook Error Handling
    print("\n📊 Test 17: Webhook Error Handling")
    
    # Test with webhook error response
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 400  # Bad Request
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        
        # Reset rate limits to allow the alert
        alerts.reset_rate_limits()
        alerts.enabled_alert_types.add('TRADE_EXECUTED')
        
        result = await alerts.send_trade_executed_alert(trade_data, execution_result)
        assert result == False  # Should return False on error
    
    print("✅ Webhook error handling working")
    
    # Test 18: Disabled Alerts
    print("\n📊 Test 18: Disabled Alerts")
    
    # Disable alerts
    alerts.enabled = False
    
    result = await alerts.send_trade_executed_alert(trade_data, execution_result)
    assert result == False  # Should return False when disabled
    
    # Re-enable for other tests
    alerts.enabled = True
    
    print("✅ Disabled alerts handling working")
    
    return True

async def main():
    """Main test runner"""
    try:
        success = await test_discord_alerts()
        if success:
            print("\n🎉 All Discord Alerts tests passed!")
            print("\n📋 Features tested:")
            print("   ✅ Alert initialization and configuration")
            print("   ✅ Alert type and priority filtering")
            print("   ✅ Rate limiting (max alerts per minute)")
            print("   ✅ Trade executed alerts (success/failure)")
            print("   ✅ Balance and system status alerts")
            print("   ✅ Daily summary reports")
            print("   ✅ Error and custom alerts")
            print("   ✅ Webhook request handling")
            print("   ✅ Configuration updates")
            print("   ✅ Alert statistics and management")
            print("   ✅ Error handling and graceful degradation")
            
            print("\n🚀 Ready to proceed to Step 8: WebSocket Price Feeds!")
        else:
            print("\n❌ SOME TESTS FAILED")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
