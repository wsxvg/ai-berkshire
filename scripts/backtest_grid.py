#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多参数扫描, 找最优策略组合"""
import sys
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# 复用 backtest_daily_check 的函数
from scripts.backtest_daily_check import run_backtest

# 扫描网格
GRID = []
for min_buyers in [1, 2, 3]:
    for max_hold in [3, 5, 8]:
        for start in ["2024-03-11", "2024-09-01", "2025-03-11"]:
            GRID.append((min_buyers, max_hold, start, "2026-07-01"))

print(f"扫描 {len(GRID)} 组参数...")
print(f"{'config':<35} {'年化':>8} {'夏普':>6} {'回撤':>7} {'胜率':>6} {'#买':>4} {'#卖':>4}")
print("─" * 80)

results = []
for min_b, max_h, start, end in GRID:
    r = run_backtest(start, end, 100000, max_h, min_b, False)
    if not r:
        continue
    res = r["result"]
    label = f"b={min_b} h={max_h} {start[2:7]}"
    print(f"{label:<35} {res['annualized']:>7.2f}% {res['sharpe']:>5.2f} {res['max_drawdown']:>6.2f}% {res['win_rate']:>5.1f}% {res['n_buys']:>4} {res['n_sells']:>4}")
    results.append({"label": label, "config": r["config"], "result": res})

# 排序: 夏普最高
results.sort(key=lambda x: -x["result"]["sharpe"])

print("\n" + "=" * 80)
print("📊 TOP 5 (按夏普):")
print("─" * 80)
for i, r in enumerate(results[:5], 1):
    res = r["result"]
    print(f"  {i}. {r['label']}")
    print(f"     年化 {res['annualized']:+.2f}%  夏普 {res['sharpe']:.2f}  回撤 {res['max_drawdown']:.2f}%  胜率 {res['win_rate']:.0f}%")

# 落盘
out = PROJECT / "reports" / "backtest_daily_check_grid.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n💾 {out.relative_to(PROJECT)}")
