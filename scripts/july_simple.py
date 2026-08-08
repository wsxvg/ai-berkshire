import sys, json
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

cfg = {
    'initial_cash': 10000, 'no_stop_loss': True, 'take_profit_pct': 50.0,
    'min_consensus': 3, 'max_holdings': 12,
    'kelly_cap_bull': 0.5, 'kelly_cap_bear': 0.25,
    'pyramiding_enabled': False, 'smart_swap': True, 'regime_specific': True,
    'start_date': '2026-07-01', 'end_date': '2026-07-31',
    'weights': {'quality': 20, 'cost': 25, 'manager': 15, 'momentum': 10, 'smart_money': 30},
    'weights_bull': {'quality': 15, 'cost': 20, 'manager': 10, 'momentum': 20, 'smart_money': 35},
    'weights_bear': {'quality': 25, 'cost': 25, 'manager': 30, 'momentum': 10, 'smart_money': 10},
}

print('Running...')
res = run_backtest(cfg, clear_cache=True)

# Print trades summary
trades = res.get('trades', [])
buys = [t for t in trades if t.get('action') == 'BUY']
sells = [t for t in trades if t.get('action') in ('SELL', 'SELL_REDUCE')]

print('\n=== BUYS (%d) ===' % len(buys))
for t in buys:
    print('  %s  %-40s  amt=%-8.0f  reason=%s' % (
        t.get('date',''), t.get('fund_name','')[:40], t.get('amount',0), t.get('reason','')))

print('\n=== SELLS (%d) ===' % len(sells))
for t in sells:
    print('  %s  %-40s  amt=%-8.0f  reason=%s' % (
        t.get('date',''), t.get('fund_name','')[:40], t.get('amount',0), t.get('reason','')))

# Daily values
print('\n=== DAILY VALUES ===')
daily = res.get('daily_values', [])
for d in daily:
    print('  %s  val=%-8.0f  pos=%d' % (d.get('date',''), d.get('value',0), d.get('positions',0)))

print('\nReturn=%.4f  Benchmark=%.4f  Trades=%d' % (
    res.get('total_return',0), res.get('benchmark_return',0), res.get('trade_count',0)))
