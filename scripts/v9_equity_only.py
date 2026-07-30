#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V9 仅股票型/混合型基金测试
- 排除债券型、货币型、QDII、商品（黄金）
- 仅在中证800相关股票基金中选
"""

import sys, json, copy
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

base = {
    'start_date': '2023-07-17',
    'end_date': '2026-07-24',
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

# V8 步阶止盈基线（最好记录）
v8_best = {
    'start_date': '2023-07-17',
    'end_date': '2026-07-24',
    'initial_cash': 10000,
    'weights': {'quality': 25, 'cost': 20, 'manager': 20, 'momentum': 15, 'smart_money': 20},
    'min_score': 3.0,
    'no_stop_loss': True,
    'take_profit_pct': 0.50,
    'min_consensus': 3,
    'max_holdings': 5,
    'kelly_cap_bull': 0.5,
    'kelly_cap_bear': 0.25,
    'pyramiding_enabled': False,
    'smart_swap': True,
    'regime_specific': True,
    'step_take_profit': True,
}

# 排除债券/黄金/货基的基金代码（通过名称含关键词识别，然后在回测中过滤）
EXCLUDE_LARGE_DEBT = True  # 排除规模大的债券型基金

configs = [
    ('V8_BASELINE', {}),
    ('V8_MIN25', {'min_score': 2.5}),
    ('V8_WIN5', {'consensus_window_days': 5}),
    ('V8_WIN5_MIN25', {'consensus_window_days': 5, 'min_score': 2.5}),
    ('MOM_63_5', {'signal_source': 'momentum', 'momentum_lookback': 63, 'momentum_top_n': 5, 'momentum_rebalance_days': 21}),
    ('MOM_42_10', {'signal_source': 'momentum', 'momentum_lookback': 42, 'momentum_top_n': 10, 'momentum_rebalance_days': 21}),
    ('MOM_126_5', {'signal_source': 'momentum', 'momentum_lookback': 126, 'momentum_top_n': 5, 'momentum_rebalance_days': 42}),
]

results = []
for label, params in configs:
    cfg = copy.deepcopy(v8_best if 'V8' in label or 'WIN' in label else base)
    cfg.update(params)
    print(f'\n--- {label} ---')
    res = run_backtest(cfg)
    result = {
        'name': label,
        'total_return': res.get('total_return', 0),
        'max_drawdown': res.get('max_drawdown', 0),
        'sharpe_ratio': res.get('sharpe_ratio', 0),
        'trade_count': res.get('trade_count', 0),
        'final_value': res.get('final_value', 0),
    }
    results.append(result)
    print(f"  Return: {result['total_return']:.2f}%, DD: {result['max_drawdown']:.2f}%, Sharpe: {result['sharpe_ratio']:.2f}, Trades: {result['trade_count']}")

results.sort(key=lambda x: x['total_return'], reverse=True)

print('\n' + '='*80)
print('排名')
print('='*80)
for i, r in enumerate(results, 1):
    print(f"{i}. {r['name']:<20} {r['total_return']:>8.1f}%  DD={r['max_drawdown']:.1f}%  Sharpe={r['sharpe_ratio']:.2f}  Trades={r['trade_count']}")

with open('v9-results/v9_equity_test.json', 'w') as f:
    json.dump(results, f, indent=2)
