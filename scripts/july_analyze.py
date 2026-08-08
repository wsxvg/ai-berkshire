#!/usr/bin/env python3
"""July 2026 detailed trace."""
import sys, json
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

cfg = {
    'initial_cash': 10000, 'no_stop_loss': True, 'take_profit_pct': 50.0,
    'min_consensus': 3, 'max_holdings': 12,
    'kelly_cap_bull': 0.5, 'kelly_cap_bear': 0.25,
    'pyramiding_enabled': False, 'smart_swap': True, 'regime_specific': True,
    'start_date': '2026-06-15', 'end_date': '2026-08-01',
    'weights': {'quality': 20, 'cost': 25, 'manager': 15, 'momentum': 10, 'smart_money': 30},
    'weights_bull': {'quality': 15, 'cost': 20, 'manager': 10, 'momentum': 20, 'smart_money': 35},
    'weights_bear': {'quality': 25, 'cost': 25, 'manager': 30, 'momentum': 10, 'smart_money': 10},
}

print('Running detailed July backtest...')
res = run_backtest(cfg, clear_cache=True)

# Save full result for parsing
with open('july_detail.json', 'w') as f:
    json.dump(res, f, ensure_ascii=False, indent=2, default=str)

print('Done. Saved to july_detail.json')
print('Keys:', list(res.keys()))
print('Return:', res.get('total_return'))
print('Benchmark:', res.get('benchmark_return'))
print('Trades:', res.get('trade_count'))

# Show trades
trades = res.get('trades', [])
print('\n--- ALL TRADES ---')
for t in trades:
    print('  %s %s %s amt=%.0f reason=%s' % (
        t.get('date',''), t.get('action',''), 
        t.get('fund_name', t.get('fund_code',''))[:40],
        t.get('amount', 0), t.get('reason', '')))
