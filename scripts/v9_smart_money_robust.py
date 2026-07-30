#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V9 聪明钱稳健策略

核心思路：
- 保留 V8 的聪明钱信号（真金白银买入，不是未来函数）
- 强化共识：多人、多日确认（降低噪音）
- 加趋势过滤：基金自身60日动量为正才买（顺势）
- 波动率目标仓位：根据市场波动率调整总仓位（恐慌时减仓）
- 月度再平衡（减少T+N结算摩擦）

参数：
- consensus_window_days: 共识窗口天数（多人多日确认）
- min_weighted_buy: 加权买入阈值
- momentum_filter: 是否启用60日动量过滤
- rebalance_days: 再平衡周期
- kelly_cap_bull/bear: Kelly仓位上限
"""

import json
import sys
import copy
from pathlib import Path
from collections import defaultdict

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest.engine.backtest import run_backtest


def run_config(base_config, overrides, label=""):
    """运行单个配置并返回结果"""
    config = copy.deepcopy(base_config)
    config.update(overrides)

    print(f"\n{'='*60}")
    print(f"[{label}] Running: {overrides}")
    print(f"{'='*60}")

    result = run_backtest(config)

    print(f"  Return: {result.get('total_return', 'N/A')}%")
    print(f"  Drawdown: {result.get('max_drawdown', 'N/A')}%")
    print(f"  Sharpe: {result.get('sharpe_ratio', 'N/A')}")
    print(f"  Trades: {result.get('trade_count', 'N/A')}")

    return {
        "label": label,
        "config_overrides": overrides,
        "total_return": result.get("total_return", 0),
        "max_drawdown": result.get("max_drawdown", 0),
        "sharpe_ratio": result.get("sharpe_ratio", 0),
        "trade_count": result.get("trade_count", 0),
        "final_value": result.get("final_value", 0),
    }


def main():
    print("=" * 70)
    print("V9 聪明钱稳健策略回测")
    print("=" * 70)

    # V8 冠军基线
    v8_champion = {
        "start_date": "2023-07-17",
        "end_date": "2026-07-24",
        "initial_cash": 10000,
        "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
        "min_score": 3.0,
        "no_stop_loss": True,
        "take_profit_pct": 0.50,
        "min_consensus": 3,
        "max_holdings": 5,
        "kelly_cap_bull": 0.5,
        "kelly_cap_bear": 0.25,
        "pyramiding_enabled": False,
        "smart_swap": True,
        "regime_specific": True,
    }

    # V8 基线（step_take_profit 版本，之前验证最好的）
    v8_baseline = {
        "start_date": "2023-07-17",
        "end_date": "2026-07-24",
        "initial_cash": 10000,
        "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
        "min_score": 3.0,
        "no_stop_loss": True,
        "take_profit_pct": 0.50,
        "min_consensus": 3,
        "max_holdings": 5,
        "kelly_cap_bull": 0.5,
        "kelly_cap_bear": 0.25,
        "pyramiding_enabled": False,
        "smart_swap": True,
        "regime_specific": True,
        "step_take_profit": True,
    }

    results = []

    # 1. V8 基线
    results.append(run_config(v8_baseline, {}, "V8_BASELINE"))

    # 2. V9a: 强化共识窗口 (5天)
    results.append(run_config(v8_baseline, {"consensus_window_days": 5}, "V9A_CONSENSUS5"))

    # 3. V9b: 强化共识窗口 (10天)
    results.append(run_config(v8_baseline, {"consensus_window_days": 10}, "V9B_CONSENSUS10"))

    # 4. V9c: 降低 min_consensus 到 2（放宽买入门槛但加长观察期）
    results.append(run_config(v8_baseline, {"min_consensus": 2, "consensus_window_days": 5}, "V9C_RELAX2_WIN5"))

    # 5. V9d: 提高 min_score 到 3.3
    results.append(run_config(v8_baseline, {"min_score": 3.3}, "V9D_SCORE33"))

    # 6. V9e: 最大持仓 8 只（分散）
    results.append(run_config(v8_baseline, {"max_holdings": 8}, "V9E_HOLD8"))

    # 7. V9f: 降低 Kelly cap（更保守仓位）
    results.append(run_config(v8_baseline, {"kelly_cap_bull": 0.3}, "V9F_KELLY03"))

    # 8. V9g: 组合：强化共识 + 降低 Kelly
    results.append(run_config(v8_baseline, {
        "consensus_window_days": 5,
        "kelly_cap_bull": 0.3,
        "max_holdings": 8,
    }, "V9G_COMBO"))

    # 9. V9h: 加权共识（大佬权重更高）
    results.append(run_config(v8_baseline, {
        "use_weighted_consensus": True,
        "weighted_consensus_threshold": 2.5,
        "consensus_window_days": 0,
    }, "V9H_WEIGHTED"))

    # 排序
    results.sort(key=lambda x: x["total_return"], reverse=True)

    print("\n" + "=" * 70)
    print("排名（按收益）")
    print("=" * 70)
    print(f"{'排名':<4} {'策略':<18} {'收益':>8} {'回撤':>8} {'夏普':>6} {'交易':>5}")
    print("-" * 60)
    for i, r in enumerate(results, 1):
        print(f"{i:<4} {r['label']:<18} {r['total_return']:>7.1f}% {r['max_drawdown']:>7.1f}% {r['sharpe_ratio']:>5.2f} {r['trade_count']:>4}")

    # 保存
    output_file = PROJECT_DIR / "v9-results" / "v9_smart_money_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n已保存: {output_file}")


if __name__ == "__main__":
    main()
