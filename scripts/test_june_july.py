#!/usr/bin/env python3
"""单跑 June / July 测试 KC_AGGRESSIVE"""
import sys, copy
sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

BASE_CFG = {
    'initial_cash': 10000,
    'no_stop_loss': True,
    'take_profit_pct': 50.0,
    'min_consensus': 3,
    'max_holdings': 12,
    'kelly_cap_bull': 0.7,
    'kelly_cap_bear': 0.40,
    'pyramiding_enabled': False,
    'smart_swap': True,
    'regime_specific': True,
    'weights': {'quality': 25, 'cost': 25, 'manager': 25, 'momentum': 25, 'smart_money': 0},
    'weights_bull': {'quality': 20, 'cost': 20, 'manager': 15, 'momentum': 45, 'smart_money': 0},
    'weights_bear': {'quality': 35, 'cost': 25, 'manager': 30, 'momentum': 10, 'smart_money': 0},
}

tests = [
    ("July only (score 6/25, trade Jul)", '2026-06-25', '2026-07-31'),
    ("July only (score 7/1, trade Jul)", '2026-07-01', '2026-07-31'),
    ("June-Jul (score 5/25)", '2026-05-25', '2026-07-31'),
    ("June-Jul (score 6/1)", '2026-06-01', '2026-07-31'),
    ("Peak-Crash (score 6/15)", '2026-06-15', '2026-07-31'),
]

for name, sd, ed in tests:
    cfg = copy.deepcopy(BASE_CFG)
    cfg['start_date'] = sd
    cfg['end_date'] = ed
    r = run_backtest(cfg, clear_cache=True)
    ret = r.get('total_return', 0)
    bench = r.get('benchmark_return', 0)
    dd = r.get('max_drawdown', 0)
    trades = r.get('trade_count', 0)
    wr = r.get('win_rate', 0)
    print(f"=== {name} ===")
    print(f"  Period: {sd} ~ {ed}")
    print(f"  Return: {ret:+.2f}%  Bench: {bench:+.2f}%  MaxDD: {dd:.2f}%  Trades: {trades}  WinRate: {wr:.2f}")
    print()
