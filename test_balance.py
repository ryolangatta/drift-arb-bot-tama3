import asyncio
import sys
import os
sys.path.append('.')
from core.main import DriftArbBot

async def test_balance_method():
    try:
        bot = DriftArbBot()
        result = await bot.calculate_dynamic_allocation()
        print('✅ Method works!')
        print(f'Can trade: {result["can_trade"]}')
        print(f'Allocation: ${result["allocation"]:.2f}')
        print(f'Reason: {result["reason"]}')
    except Exception as e:
        print(f'❌ Error: {e}')

asyncio.run(test_balance_method())
