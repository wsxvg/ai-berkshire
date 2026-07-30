#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V9 纯动量策略 - 使用 V8 引擎内置的 momentum 信号模式

核心思路：
- 不用聪明钱信号（避免过拟合），用基金自身收益率排名
- 每月选前 N 只收益率最高的基金
- 结合波动率目标仓位
- 极简参数

参数：
- momentum_lookback: 回看天数
- momentum_top_n: 选前N只
- momentum_rebalance_days: 再平衡周期
"""

import json
import sys
import copy
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest.engine.backtest import run_backtest


def main():
    print("=" * 70)
    print("V9 纯动量策略（V8引擎内置 momentum 模式）")
    print("=" * 70)

    base_config = {
        "start_date": "2023-07-17",
        "end_date": "2026-07-24",
        "initial_cash": 10000,
        "signal_source": "momentum",
        "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
        "min_score": 2.5,
        "no_stop_loss": True,
        "take_profit_pct": 0.50,
        "max_holdings": 5,
        "kelly_cap_bull": 0.5,
        "kelly_cap_bear": 0.25,
        "pyramiding_enabled": False,
        "smart_swap": True,
        "regime_specific": True,
        "step_take_profit": True,
    }

    configs = [
        {"name": "PM1", "momentum_lookback": 63, "momentum_top_n": 5, "momentum_rebalance_days": 21},
        {"name": "PM2", "momentum_lookback": 63, "momentum_top_n": 8, "momentum_rebalance_days": 21},
        {"name": "PM3", "momentum_lookback": 42, "momentum_top_n": 5, "momentum_rebalance_days": 21},
        {"name": "PM4", "momentum_lookback": 126, "momentum_top_n": 5, "momentum_rebalance_days": 21},
        {"name": "PM5", "momentum_lookback": 63, "momentum_top_n": 5, "momentum_rebalance_days": 14},
        {"name": "PM6", "momentum_lookback": 63, "momentum_top_n": 5, "momentum_rebalance_days": 42},
        {"name": "PM7", "momentum_lookback": 63, "momentum_top_n": 3, "momentum_rebalance_days": 21},
        {"name": "PM8", "momentum_lookback": 63, "momentum_top_n": 10, "momentum_rebalance_days": 21},
        {"name": "PM9", "momentum_lookback": 21, "momentum_top_n": 5, "momentum_rebalance_days": 21},
    ]

    results = []
    for cfg in configs:
        overrides = {
            "momentum_lookback": cfg["momentum_lookback"],
            "momentum_top_n": cfg["momentum_top_n"],
            "momentum_rebalance_days": cfg["momentum_rebalance_days"],
        }
        config = copy.deepcopy(base_config)
        config.update(overrides)

        print(f"\n--- {cfg['name']}: mom={cfg['momentum_lookback']}d, top{cfg['momentum_top_n']}, rebal={cfg['momentum_rebalance_days']}d ---")
        result = run_backtest(config)
        result["name"] = cfg["name"]
        result["config"] = cfg
        results.append(result)
        print(f"  Return: {result.get('total_return', 0):.2f}%, DD: {result.get('max_drawdown', 0):.2f}%, Sharpe: {result.get('sharpe_ratio', 0):.2f}")

    results.sort(key=lambda x: x["total_return"], reverse=True)

    print("\n" + "=" * 70)
    print("排名")
    print("=" * 70)
    print(f"{'排名':<4} {'策略':<6} {'收益':>8} {'回撤':>8} {'年化':>7} {'夏普':>6} {'交易':>5}")
    print("-" * 60)
    for i, r in enumerate(results, 1):
        print(f"{i:<4} {r['name']:<6} {r['total_return']:>7.1f}% {r['max_drawdown']:>7.1f}% {r.get('annualized_return', 0):>6.1f}% {r['sharpe_ratio']:>5.2f} {r['trade_count']:>4}")

    output_file = PROJECT_DIR / "v9-results" / "v9_pure_momentum_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n已保存: {output_file}")


if __name__ == "__main__":
    main()
