#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V9 Walk-Forward 滚动验证（高效版）

核心思路：
1. 不对每个窗口做暴力搜索（太慢）
2. 而是用 V8 冠军参数作为基准
3. 在每个窗口上跑微调过的参数组合（只调 2-3 个敏感参数）
4. 比较样本内 vs 样本外表现差异
"""

import json
import sys
import copy
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest.engine.backtest import run_backtest

# V8 冠军基准参数
BASE_CONFIG = {
    "start_date": "2023-07-17",
    "end_date": "2026-07-24",
    "initial_cash": 10000,
    "monthly_injection": 0,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "min_score": 3.0,
    "no_stop_loss": True,
    "take_profit_pct": 1000,
    "profit_mode": "half",
    "cost_penalty": 0,
    "min_consensus": 2,       # V8 冠军值
    "fund_type_filter": "all",
    "momentum_sell": 0,
    "max_candidates_per_day": 30,
    "max_holdings": 8,        # V8 冠军值
    "kelly_cap": 0.35,
    "smart_swap": True,
    "smart_swap_margin": 1.0,
    "smart_swap_min_hold_days": 30,
    "dynamic_max_holdings": True,
    "max_holdings_bull_mult": 1.5,
    "max_holdings_bear_mult": 0.6,
    "contrarian_buy_drop": 0.03,
    "pyramiding_enabled": True,
    "regime_specific": True,
    "kelly_cap_bull": 0.5,
    "kelly_cap_bear": 0.15,
}

# 小范围搜索：只调 min_score 和 kelly_cap_bull
PARAM_SETS = [
    {"min_score": 2.5, "kelly_cap_bull": 0.4},
    {"min_score": 2.5, "kelly_cap_bull": 0.5},
    {"min_score": 2.5, "kelly_cap_bull": 0.6},
    {"min_score": 3.0, "kelly_cap_bull": 0.3},
    {"min_score": 3.0, "kelly_cap_bull": 0.4},
    {"min_score": 3.0, "kelly_cap_bull": 0.5},   # V8 冠军
    {"min_score": 3.0, "kelly_cap_bull": 0.6},
    {"min_score": 3.3, "kelly_cap_bull": 0.4},
    {"min_score": 3.3, "kelly_cap_bull": 0.5},
    {"min_score": 3.3, "kelly_cap_bull": 0.6},
]

# Walk-Forward 窗口（滑动窗口，每月一步）
TRAIN_TEST_WINDOWS = [
    # 训练 6 个月 → 测试 3 个月
    {
        "name": "WF1",
        "train": ("2023-07-17", "2024-01-16"),
        "test":  ("2024-01-17", "2024-04-16"),
    },
    {
        "name": "WF2",
        "train": ("2023-10-17", "2024-04-16"),
        "test":  ("2024-04-17", "2024-07-16"),
    },
    {
        "name": "WF3",
        "train": ("2024-01-17", "2024-07-16"),
        "test":  ("2024-07-17", "2024-10-16"),
    },
    {
        "name": "WF4",
        "train": ("2024-04-17", "2024-10-16"),
        "test":  ("2024-10-17", "2025-01-16"),
    },
    {
        "name": "WF5",
        "train": ("2024-07-17", "2025-01-16"),
        "test":  ("2025-01-17", "2025-04-16"),
    },
    {
        "name": "WF6",
        "train": ("2025-01-17", "2025-07-16"),
        "test":  ("2025-07-17", "2025-10-16"),
    },
    {
        "name": "WF7",
        "train": ("2025-04-17", "2025-10-16"),
        "test":  ("2025-10-17", "2026-01-16"),
    },
    {
        "name": "WF8",
        "train": ("2025-07-17", "2026-01-16"),
        "test":  ("2026-01-17", "2026-04-16"),
    },
    {
        "name": "WF9",
        "train": ("2025-10-17", "2026-04-16"),
        "test":  ("2026-04-17", "2026-07-24"),
    },
]


def make_config(start, end, overrides=None):
    cfg = copy.deepcopy(BASE_CONFIG)
    cfg["start_date"] = start
    cfg["end_date"] = end
    if overrides:
        cfg.update(overrides)
    return cfg


def run_window(window):
    """跑单个 walk-forward 窗口"""
    train_start, train_end = window["train"]
    test_start, test_end = window["test"]

    print(f"\n{window['name']}: 训练 {train_start}~{train_end} → 测试 {test_start}~{test_end}")

    # 训练集：跑所有参数组合
    train_results = []
    for i, params in enumerate(PARAM_SETS):
        cfg = make_config(train_start, train_end, params)
        result = run_backtest(cfg, clear_cache=False)
        train_results.append({
            "params": params,
            "return": result["total_return"],
            "dd": result["max_drawdown"],
            "sharpe": result["sharpe_ratio"],
        })
        if i % 3 == 0:
            print(f"  训练进度: {i+1}/{len(PARAM_SETS)}")

    # 训练集最优
    train_results.sort(key=lambda x: x["return"], reverse=True)
    best = train_results[0]

    # 用训练最优参数跑测试集
    test_cfg = make_config(test_start, test_end, best["params"])
    test_result = run_backtest(test_cfg, clear_cache=False)

    degradation = best["return"] - test_result["total_return"]

    print(f"  训练收益: {best['return']:.2f}% → 样本外: {test_result['total_return']:.2f}%  (衰减: {degradation:.1f}p)")

    return {
        "window": window["name"],
        "train_period": f"{train_start}~{train_end}",
        "test_period": f"{test_start}~{test_end}",
        "best_params": best["params"],
        "train_return": best["return"],
        "test_return": test_result["total_return"],
        "test_dd": test_result["max_drawdown"],
        "degradation": round(degradation, 2),
        "top3_train": train_results[:3],
    }


def main():
    print("=" * 70)
    print("V9 Walk-Forward 验证（高效版）")
    print("9 个滑动窗口，每窗口 10 组参数")
    print("=" * 70)

    results = []
    for w in TRAIN_TEST_WINDOWS:
        result = run_window(w)
        results.append(result)

    # 总结
    print("\n" + "=" * 70)
    print("Walk-Forward 结果汇总")
    print("=" * 70)

    print(f"\n{'窗口':<6} {'min_score':>9} {'kelly_bull':>10} {'训练收益':>9} {'样本外':>9} {'衰减p':>6} {'衰减%':>7}")
    print("-" * 70)

    for r in results:
        p = r["best_params"]
        # 计算衰减百分比
        pct_deg = (r["degradation"] / r["train_return"] * 100) if r["train_return"] > 0 else 0
        print(f"{r['window']:<6} {p['min_score']:>9} {p['kelly_cap_bull']:>10} "
              f"{r['train_return']:>8.1f}% {r['test_return']:>8.1f}% {r['degradation']:>5.1f}  {pct_deg:>5.0f}%")

    # 统计参数稳定性
    ms_vals = [r["best_params"]["min_score"] for r in results]
    kb_vals = [r["best_params"]["kelly_cap_bull"] for r in results]

    print(f"\n参数稳定性:")
    print(f"  min_score: 值={set(ms_vals)}, 出现次数={max(ms_vals.count(v) for v in set(ms_vals))}/{len(results)}")
    print(f"  kelly_cap_bull: 值={set(kb_vals)}, 出现次数={max(kb_vals.count(v) for v in set(kb_vals))}/{len(results)}")

    # 样本外统计
    positive_oos = sum(1 for r in results if r["test_return"] > 0)
    avg_deg = sum(r["degradation"] for r in results) / len(results)
    avg_train = sum(r["train_return"] for r in results) / len(results)
    avg_test = sum(r["test_return"] for r in results) / len(results)

    print(f"\n整体统计:")
    print(f"  训练期平均收益: {avg_train:.1f}%")
    print(f"  样本外平均收益: {avg_test:.1f}%")
    print(f"  平均衰减: {avg_deg:.1f} 个百分点")
    print(f"  样本外正向窗口: {positive_oos}/{len(results)}")

    # 稳健参数：中位数
    import statistics
    robust_ms = round(statistics.median(ms_vals), 1)
    robust_kb = round(statistics.median(kb_vals), 2)
    robust_params = {"min_score": robust_ms, "kelly_cap_bull": robust_kb}

    print(f"\n稳健参数（中位数）: {robust_params}")

    # 用稳健参数跑全周期
    print("\n用稳健参数跑全周期验证...")
    full_cfg = make_config("2023-07-17", "2026-07-24", robust_params)
    full_result = run_backtest(full_cfg, clear_cache=False)
    print(f"  稳健参数全周期: {full_result['total_return']:.2f}%")

    # V8 冠军全周期
    print("\nV8 冠军参数跑同期对照...")
    v8_cfg = make_config("2023-07-17", "2026-07-24", {"min_score": 3.0, "kelly_cap_bull": 0.5})
    v8_result = run_backtest(v8_cfg, clear_cache=False)
    print(f"  V8 冠军全周期: {v8_result['total_return']:.2f}%")

    # 对比
    print(f"\n对比:")
    print(f"  V8 冠军（原始搜索最优）: {v8_result['total_return']:.2f}%")
    print(f"  稳健参数（Walk-Forward中位数）: {full_result['total_return']:.2f}%")
    diff = full_result['total_return'] - v8_result['total_return']
    print(f"  差异: {diff:.2f} 个百分点")
    if abs(diff) < 5:
        print(f"  结论: V8 参数未被过拟合（差异<5p，在噪声范围内）")
    elif diff > 0:
        print(f"  结论: 稳健参数反而更好")
    else:
        print(f"  结论: V8 参数存在过拟合迹象")

    # 保存结果
    output = {
        "version": "V9_WalkForward",
        "method": "9 sliding windows, 10 param sets per window",
        "results": results,
        "stability": {
            "min_score_mode": max(set(ms_vals), key=ms_vals.count),
            "min_score_stability": f"{max(ms_vals.count(v) for v in set(ms_vals))}/{len(results)}",
            "kelly_bull_mode": max(set(kb_vals), key=kb_vals.count),
            "kelly_bull_stability": f"{max(kb_vals.count(v) for v in set(kb_vals))}/{len(results)}",
        },
        "statistics": {
            "avg_train_return": avg_train,
            "avg_test_return": avg_test,
            "avg_degradation": avg_deg,
            "positive_oos_windows": f"{positive_oos}/{len(results)}",
        },
        "robust_params": robust_params,
        "robust_performance": {
            "return": full_result["total_return"],
            "dd": full_result["max_drawdown"],
            "sharpe": full_result["sharpe_ratio"],
        },
        "v8_champion_performance": {
            "return": v8_result["total_return"],
            "dd": v8_result["max_drawdown"],
            "sharpe": v8_result["sharpe_ratio"],
        }
    }

    output_file = PROJECT_DIR / "v9-results" / "walkforward_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
