#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Walk-Forward runner for no-smart-money strategies."""
import sys, json, copy
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

WINDOWS = [
    ('2023-07-17', '2024-01-17', '2024-01-17', '2024-04-17'),
    ('2023-08-17', '2024-02-17', '2024-02-17', '2024-05-17'),
    ('2023-09-17', '2024-03-17', '2024-03-17', '2024-06-17'),
    ('2023-10-17', '2024-04-17', '2024-04-17', '2024-07-17'),
    ('2023-11-17', '2024-05-17', '2024-05-17', '2024-08-17'),
    ('2023-12-17', '2024-06-17', '2024-06-17', '2024-09-17'),
    ('2024-01-17', '2024-07-17', '2024-07-17', '2024-10-17'),
    ('2024-02-17', '2024-08-17', '2024-08-17', '2024-11-17'),
    ('2024-03-17', '2024-09-17', '2024-09-17', '2026-07-24'),
]

WI = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ts, te, tts, tte = WINDOWS[WI]
print(f'=== Window {WI}: Train {ts}~{te} | Test {tts}~{tte} ===')

base = {
    'initial_cash': 10000,
    'weights': {'quality': 25, 'cost': 20, 'manager': 20, 'momentum': 15, 'smart_money': 20},
    'no_stop_loss': True,
    'take_profit_pct': 0.50,
    'pyramiding_enabled': False,
    'smart_swap': True,
    'regime_specific': True,
    'step_take_profit': True,
    'max_holdings': 5,
    'kelly_cap_bull': 0.5,
    'kelly_cap_bear': 0.25,
}

CONFIGS = [
    # 纯质量
    ('QUALITY_ONLY', {
        'weights': {'quality': 100, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 0},
        'min_score': 2.0,
    }),
    # 纯动量63天
    ('MOMENTUM_63_5', {
        'signal_source': 'momentum',
        'momentum_lookback': 63,
        'momentum_top_n': 5,
        'momentum_rebalance_days': 21,
    }),
    # 质量+动量混合
    ('QUALITY_MOM', {
        'signal_source': 'momentum',
        'momentum_lookback': 63,
        'momentum_top_n': 5,
        'momentum_rebalance_days': 21,
        'weights': {'quality': 40, 'cost': 0, 'manager': 0, 'momentum': 40, 'smart_money': 20},
        'min_score': 2.0,
    }),
]

results = {}
for i, (label, params) in enumerate(CONFIGS):
    train_cfg = copy.deepcopy(base)
    train_cfg.update(params)
    train_cfg['start_date'] = ts
    train_cfg['end_date'] = te
    clear = (WI == 0 and i == 0)
    train_res = run_backtest(train_cfg, clear_cache=clear)

    test_cfg = copy.deepcopy(base)
    test_cfg.update(params)
    test_cfg['start_date'] = tts
    test_cfg['end_date'] = tte
    test_res = run_backtest(test_cfg, clear_cache=False)

    results[label] = {
        'train_return': train_res.get('total_return', 0),
        'test_return': test_res.get('total_return', 0),
        'test_drawdown': test_res.get('max_drawdown', 0),
        'test_sharpe': test_res.get('sharpe_ratio', 0),
    }
    print(f'  {label}: Train={train_res.get("total_return",0):.2f}%, Test={test_res.get("total_return",0):.2f}%')

output = {'window': WI, 'train_period': f'{ts}~{te}', 'test_period': f'{tts}~{tte}', 'results': results}
outfile = f'wf_nosm_{WI}.json'
with open(outfile, 'w') as f:
    json.dump(output, f, indent=2)
print(f'Saved: {outfile}')
