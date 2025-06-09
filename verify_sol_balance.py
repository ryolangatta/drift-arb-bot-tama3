#!/usr/bin/env python3
"""
SOL Balance Verification Script
This script ONLY reads data - it does NOT place any orders
"""
import os
import sys
from binance.client import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_binance_testnet():
    """Check Binance testnet balances and SOL price - READ ONLY"""
    try:
        # Get API credentials from environment
        api_key = os.getenv('BINANCE_TESTNET_API_KEY')
        api_secret = os.getenv('BINANCE_TESTNET_SECRET')
        
        if not api_key or not api_secret:
            print("❌ ERROR: Missing Binance testnet credentials")
            print("   Please set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_SECRET")
            return False
        
        # Initialize testnet client
        client = Client(api_key, api_secret, testnet=True)
        client.API_URL = "https://testnet.binance.vision/api"
        
        print("🔍 VERIFICATION SCRIPT - READ ONLY")
        print("=" * 50)
        
        # 1. Check account balances
        print("\n📊 Current Balances:")
        account = client.get_account()
        
        # Find relevant balances
        sol_balance = 0
        usdt_balance = 0
        usdc_balance = 0
        
        for balance in account['balances']:
            if balance['asset'] == 'SOL' and float(balance['free']) > 0:
                sol_balance = float(balance['free'])
                print(f"   SOL: {sol_balance:.4f}")
            elif balance['asset'] == 'USDT' and float(balance['free']) > 0:
                usdt_balance = float(balance['free'])
                print(f"   USDT: {usdt_balance:.4f}")
            elif balance['asset'] == 'USDC' and float(balance['free']) > 0:
                usdc_balance = float(balance['free'])
                print(f"   USDC: {usdc_balance:.4f}")
        
        # 2. Check SOL/USDT price
        print("\n💰 Current SOL Price:")
        try:
            ticker = client.get_ticker(symbol='SOLUSDT')
            sol_price = float(ticker['lastPrice'])
            print(f"   SOLUSDT: ${sol_price:.2f}")
            
            # 3. Calculate potential USDT from selling SOL
            print("\n🧮 Potential SOL → USDT Conversion:")
            print("   If you sell 1 SOL:")
            print(f"     You'd get: ~${sol_price:.2f} USDT")
            print(f"     Your new USDT balance: ~${usdt_balance + sol_price:.2f}")
            
            print("   If you sell 2 SOL:")
            print(f"     You'd get: ~${sol_price * 2:.2f} USDT")
            print(f"     Your new USDT balance: ~${usdt_balance + (sol_price * 2):.2f}")
            
            # 4. Check if SOLUSDT trading is available
            print("\n📈 Trading Pair Status:")
            exchange_info = client.get_exchange_info()
            
            solusdt_found = False
            for symbol in exchange_info['symbols']:
                if symbol['symbol'] == 'SOLUSDT':
                    solusdt_found = True
                    print(f"   SOLUSDT: {symbol['status']}")
                    print(f"   Trading allowed: {'✅' if symbol['status'] == 'TRADING' else '❌'}")
                    
                    # Check trading rules
                    for filter_item in symbol['filters']:
                        if filter_item['filterType'] == 'LOT_SIZE':
                            print(f"   Min quantity: {filter_item['minQty']} SOL")
                            print(f"   Step size: {filter_item['stepSize']} SOL")
                    break
            
            if not solusdt_found:
                print("   ❌ SOLUSDT pair not found!")
                return False
            
            # 5. Recommendation
            print("\n💡 Recommendation:")
            if sol_balance >= 2:
                needed_usdt = 100  # For your bot's trade size
                sols_to_sell = needed_usdt / sol_price
                print(f"   To get ${needed_usdt} USDT for trading:")
                print(f"   Sell {sols_to_sell:.4f} SOL")
                print(f"   This leaves you with {sol_balance - sols_to_sell:.4f} SOL")
                print(f"   ✅ You have enough SOL for this conversion")
            else:
                print(f"   ⚠️  You only have {sol_balance:.4f} SOL")
                print(f"   Consider selling {sol_balance * 0.5:.4f} SOL to get some USDT")
            
        except Exception as e:
            print(f"   ❌ Error getting SOL price: {e}")
            return False
        
        print("\n" + "=" * 50)
        print("✅ Verification complete - NO ORDERS PLACED")
        print("   This was READ-ONLY - your balances are unchanged")
        
        return True
        
    except Exception as e:
        print(f"❌ Error connecting to Binance testnet: {e}")
        print(f"   Make sure your API keys are correct")
        return False

if __name__ == "__main__":
    print("🚀 Starting SOL verification...")
    success = check_binance_testnet()
    
    if success:
        print("\n🎯 Ready for next step!")
        print("   If everything looks good, we can create the SOL→USDT conversion script")
    else:
        print("\n❌ Fix the issues above before proceeding")
