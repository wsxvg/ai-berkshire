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

res = run_backtest(cfg, clear_cache=False)
trades = res.get('trades', [])
for t in trades:
    print('%s|%s|%s|%.0f|%s' % (t.get('date',''), t.get('action',''), t.get('fund_name','')[:35], t.get('amount',0), t.get('reason','')))
