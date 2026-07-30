#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V9 不依赖聪明钱的策略
测试两件事：
1. 纯质量分数（买好基金长期持有）
2. 纯动量（V8引擎的momentum模式）
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

configs = [
    # 纯质量：只用品质分数选基金（不用聪明钱信号）
    ('QUALITY_ONLY', {
        'weights': {'quality': 100, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 0},
        'min_score': 2.0,
    }),
    ('QUALITY_HIGH', {
        'weights': {'quality': 100, 'cost': 0, 'manager': 0, 'momentum': 0, 'smart_money': 0},
        'min_score': 3.0,
    }),
    # 纯动量：V8引擎的momentum模式，不用聪明钱
    ('MOMENTUM_63_5', {
        'signal_source': 'momentum',
        'momentum_lookback': 63,
        'momentum_top_n': 5,
        'momentum_rebalance_days': 21,
    }),
    ('MOMENTUM_42_5', {
        'signal_source': 'momentum',
        'momentum_lookback': 42,
        'momentum_top_n': 5,
        'momentum_rebalance_days': 21,
    }),
    ('MOMENTUM_126_5', {
        'signal_source': 'momentum',
        'momentum_lookback': 126,
        'momentum_top_n': 5,
        'momentum_rebalance_days': 21,
    }),
    # 质量+动量组合
    ('QUALITY_MOM', {
        'signal_source': 'momentum',
        'momentum_lookback': 63,
        'momentum_top_n': 5,
        'momentum_rebalance_days': 21,
        'weights': {'quality': 40, 'cost': 0, 'manager': 0, 'momentum': 40, 'smart_money': 20},
        'min_score': 2.0,
    }),
]

results = []
for label, params in configs:
    cfg = copy.deepcopy(base)
    cfg.update(params)
    print(f'\n--- {label}: {params} ---')
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
    print(f"  Return: {result['total_return']:.1f}%, DD: {result['max_drawdown']:.1f}%, Sharpe: {result['sharpe_ratio']:.2f}")

results.sort(key=lambda x: x['total_return'], reverse=True)

print('\n' + '='*60)
print('排名（按收益）')
print('='*60)
print(f"{'排名':<4} {'策略':<15} {'收益':>8} {'回撤':>8} {'夏普':>6} {'交易':>5}")
for i, r in enumerate(results, 1):
    print(f"{i:<4} {r['name']:<15} {r['total_return']:>7.1f}% {r['max_drawdown']:>7.1f}% {r['sharpe_ratio']:>5.2f} {r['trade_count']:>4}")

with open('v9-results/v9_no_smart_money.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nSaved: v9-results/v9_no_smart_money.json')
