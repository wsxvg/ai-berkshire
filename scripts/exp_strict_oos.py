#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
严格 OOS (Out-of-Sample) 回测框架 — 零作弊协议
"""
import sys, copy, json, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest


# ============================================================
# Round 20 候选 — Smart Money 回调信号集成
# Trigger: 2026-08-07
#
# R18/R19 结果 (22 OOS windows, 2022-12 到 2026-08):
#   KC_AGGRESSIVE_BASELINE: 4.536% avg, maxdd 4.38%, beat bench 64%
#   STOP-LOSS 8%: FAILED (return decreased)
#   DYNAMIC SL: FAILED (return decreased)
#
# R20 新发现 (信号优化扫描结果):
#   smart_money "回调 + 共识" 信号: 90天超额 +9.76%, 胜率 66.4%
#   最优参数: 单日 -10%~-3% 回调, topgain_hold>=4, net_buy>=1
#   原始版本 (topgain>=2): 90天超额 +6.08%
#
# R20 方向: 将预计算信号引入 4D 评分作为 smart_money 维度
#   - 候选 0: KC_AGGRESSIVE_BASELINE (复现 R18)
#   - 候选 1: KC_SMART_BUY_15 — 启用预计算信号, smart_money weight=15
#   - 候选 2: KC_SMART_BUY_25 — 启用预计算信号, smart_money weight=25
#
# 防作弊: 信号参数 (topgain>=4, -10%~-3%, net_buy>=1) 通过独立验证集确定，
#         不接触 R20 OOS 窗口数据。R20 只验证"是否能在 OOS 中复现 alpha"。
# ============================================================

ROUND = 21

# ─── 权重方案 ───
# 注意: 经理维度已禁用（无历史数据），权重归零
WTS_EQUAL = {"quality": 33, "cost": 33, "momentum": 34, "smart_money": 0}
WTS_BULL = {"quality": 22, "cost": 22, "momentum": 56, "smart_money": 0}
WTS_BEAR = {"quality": 40, "cost": 30, "momentum": 30, "smart_money": 0}

# R20: 信号启用权重（给 smart_money 分配一定权重）
WTS_SIGNAL_15 = {"quality": 27, "cost": 27, "momentum": 31, "smart_money": 15}
WTS_SIGNAL_15_BULL = {"quality": 21, "cost": 21, "momentum": 43, "smart_money": 15}
WTS_SIGNAL_15_BEAR = {"quality": 35, "cost": 26, "momentum": 24, "smart_money": 15}

WTS_SIGNAL_25 = {"quality": 25, "cost": 25, "momentum": 25, "smart_money": 25}
WTS_SIGNAL_25_BULL = {"quality": 19, "cost": 19, "momentum": 37, "smart_money": 25}
WTS_SIGNAL_25_BEAR = {"quality": 31, "cost": 25, "momentum": 19, "smart_money": 25}

# R21: 修饰符模式 — smart_money 不占维度权重，只作为加减分
WTS_MOD = {"quality": 33, "cost": 33, "momentum": 34, "smart_money": 0}
WTS_MOD_BULL = {"quality": 22, "cost": 22, "momentum": 56, "smart_money": 0}
WTS_MOD_BEAR = {"quality": 40, "cost": 30, "momentum": 30, "smart_money": 0}

CANDIDATES = [
    # 0: KC_AGGRESSIVE_BASELINE (复现 R18)
    ("KC_AGGRESSIVE_BASELINE", {
        "max_holdings": 12,
        "weights": WTS_EQUAL,
        "weights_bull": WTS_BULL,
        "weights_bear": WTS_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": True,
    }),

    # 1: KC_SMART_BUY_15 — 启用预计算信号, smart_money weight=15
    ("KC_SMART_BUY_15", {
        "max_holdings": 12,
        "weights": WTS_SIGNAL_15,
        "weights_bull": WTS_SIGNAL_15_BULL,
        "weights_bear": WTS_SIGNAL_15_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": True,
        "use_prebuilt_signal": True,
    }),

    # 2: KC_SMART_BUY_25 — 启用预计算信号, smart_money weight=25
    ("KC_SMART_BUY_25", {
        "max_holdings": 12,
        "weights": WTS_SIGNAL_25,
        "weights_bull": WTS_SIGNAL_25_BULL,
        "weights_bear": WTS_SIGNAL_25_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": True,
        "use_prebuilt_signal": True,
    }),

    # 3: KC_SMART_MOD — R21: 修饰符模式
    #    不占维度权重，上涨基金不扣分，回调+信号满足时 +0.3~+0.5 加成
    ("KC_SMART_MOD", {
        "max_holdings": 12,
        "weights": WTS_MOD,
        "weights_bull": WTS_MOD_BULL,
        "weights_bear": WTS_MOD_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": True,
        "use_prebuilt_signal": True,
        "smart_money_modifier": True,
    }),
]


# ─── 时间窗口定义 (同 R18-R19) ───
ALL_WINDOWS = []
base_start = datetime(2019, 1, 1)
base_end = datetime(2026, 9, 30)

idx = 0
while True:
    current = base_start + timedelta(days=60 * idx)
    train_end = current + timedelta(days=180)
    test_end = current + timedelta(days=270)
    if test_end > base_end:
        break
    ALL_WINDOWS.append({
        "train_end": train_end.strftime("%Y-%m-%d"),
        "test_end": test_end.strftime("%Y-%m-%d"),
    })
    idx += 1

TRAIN_WINDOWS = ALL_WINDOWS[:21]
TEST_WINDOWS = ALL_WINDOWS[21:]

print(f"[R{ROUND}] Total windows: {len(ALL_WINDOWS)} ({len(TRAIN_WINDOWS)} train / {len(TEST_WINDOWS)} test)")
print(f"  First test window: {TEST_WINDOWS[0]['train_end']} ~ {TEST_WINDOWS[0]['test_end']}")
print(f"  Last test window:  {TEST_WINDOWS[-1]['train_end']} ~ {TEST_WINDOWS[-1]['test_end']}")


# ─── 配置基线 ───
BASE_CFG = {
    "initial_cash": 10000,
    "no_stop_loss": True,
    "take_profit_pct": 50.0,
    "min_consensus": 3,
    "max_holdings": 5,
    "kelly_cap_bull": 0.5,
    "kelly_cap_bear": 0.25,
    "pyramiding_enabled": False,
    "smart_swap": True,
    "regime_specific": True,
}


def window_range(wi):
    if 0 <= wi < len(ALL_WINDOWS):
        return ALL_WINDOWS[wi]["train_end"], ALL_WINDOWS[wi]["test_end"]
    return None, None


def _run_one(ci, wi_global):
    train_end, test_end = window_range(wi_global)
    cfg = copy.deepcopy(BASE_CFG)
    cfg.update(CANDIDATES[ci][1])
    cfg['start_date'] = train_end
    cfg['end_date'] = test_end
    res = run_backtest(cfg, clear_cache=True)
    return {
        "phase": "test" if wi_global >= len(TRAIN_WINDOWS) else "train",
        "round": ROUND,
        "candidate": CANDIDATES[ci][0],
        "ci": ci,
        "wi": wi_global - len(TRAIN_WINDOWS) if wi_global >= len(TRAIN_WINDOWS) else wi_global,
        "period": f"{train_end}~{test_end}",
        "return": res.get("total_return", 0),
        "trades": res.get("trade_count", 0),
        "fees": res.get("total_fees", 0),
        "max_dd": res.get("max_drawdown", 0),
        "benchmark": res.get("benchmark_return", 0),
        "win_rate": res.get("win_rate", 0),
    }


def aggregate_train():
    """聚合 train 阶段的 JSON 结果。"""
    import os, glob
    results = []
    seen = set()

    # 搜索所有位置的 strict_ci*.json
    for root, dirs, files in os.walk(".", topdown=True):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if not (fname.startswith("strict_ci") and fname.endswith(".json")):
                continue
            if "strict_train_selection" in fname or "strict_oos_" in fname:
                continue
            if fname in seen:
                continue
            seen.add(fname)
            try:
                data = json.load(open(os.path.join(root, fname)))
                results.append(data)
            except Exception:
                pass

    print(f"[aggregate] Found {len(results)} results", flush=True)
    if not results:
        print("No train results found!", flush=True)
        sys.exit(1)

    by_candidate = defaultdict(list)
    for r in results:
        by_candidate[r["candidate"]].append(r)

    summary = {}
    for name, items in by_candidate.items():
        avg_ret = sum(x["return"] for x in items) / len(items)
        summary[name] = {"avg_return": avg_ret, "count": len(items)}

    best_name = max(summary, key=lambda k: summary[k]["avg_return"])
    best_ci = next(i for i, c in enumerate(CANDIDATES) if c[0] == best_name)
    selection = {"best_ci": best_ci, "best_candidate": best_name, "summary": summary, "round": ROUND}

    with open("strict_train_selection.json", "w") as f:
        json.dump(selection, f, ensure_ascii=False, indent=2)

    print("=== Train Aggregation ===")
    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        marker = " ★ BEST" if name == best_name else ""
        print(f"  {name:30s}: {s['avg_return']:8.3f}% ({s['count']} windows){marker}")
    return selection


def aggregate_test():
    """聚合 test 阶段的 JSON 结果。"""
    import os
    results = []
    seen = set()

    for root, dirs, files in os.walk(".", topdown=True):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if not (fname.startswith("strict_test_ci") and fname.endswith(".json")):
                continue
            if fname in seen:
                continue
            seen.add(fname)
            try:
                results.append(json.load(open(os.path.join(root, fname))))
            except Exception:
                pass

    print(f"[aggregate_test] Found {len(results)} results", flush=True)
    if not results:
        print("No test results found!", flush=True)
        sys.exit(1)

    by_candidate = defaultdict(list)
    for r in results:
        by_candidate[r["candidate"]].append(r)

    print(f"\n{'='*70}")
    print(f"=== R{ROUND} OOS Evaluation ({len(TEST_WINDOWS)} test windows) ===")
    print(f"=== Period: {TEST_WINDOWS[0]['train_end']} ~ {TEST_WINDOWS[-1]['test_end']}")
    print(f"{'='*70}")

    summary = {}
    for name, items in by_candidate.items():
        avg_ret = sum(x["return"] for x in items) / len(items)
        avg_bench = sum(x["benchmark"] for x in items) / len(items)
        avg_max_dd = sum(x["max_dd"] for x in items) / len(items)
        max_max_dd = max(x["max_dd"] for x in items)
        beats_count = sum(1 for x in items if x["return"] > x["benchmark"])
        summary[name] = {
            "avg_return": avg_ret,
            "avg_benchmark": avg_bench,
            "avg_max_drawdown": avg_max_dd,
            "peak_max_dd": max_max_dd,
            "beats_count": beats_count,
            "beats_rate": beats_count / len(items),
            "count": len(items),
            "per_window": [{
                "period": x["period"],
                "return": x["return"],
                "benchmark": x["benchmark"],
                "max_dd": x["max_dd"],
            } for x in sorted(items, key=lambda x: x["period"])],
        }

    with open(f"v9-results/strict_oos_r{ROUND}_eval.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        marker = ""
        if name != "KC_AGGRESSIVE_BASELINE":
            if name in summary and "KC_AGGRESSIVE_BASELINE" in summary:
                diff = s["avg_return"] - summary["KC_AGGRESSIVE_BASELINE"]["avg_return"]
                marker = f" ({diff:+.3f}% vs BASELINE)"
        print(f"\n  {name}:")
        print(f"    Avg Return:    {s['avg_return']:8.3f}%  (bench {s['avg_benchmark']:+.3f}%){marker}")
        print(f"    Avg MaxDD:     {s['avg_max_drawdown']:8.3f}%  (peak {s['peak_max_dd']:.3f}%)")
        print(f"    Beat Bench:    {s['beats_count']}/{s['count']} ({s['beats_rate']*100:.0f}%)")

    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python exp_strict_oos.py <train|test|all>")
        print("  train: aggregate train results")
        print("  test: aggregate test results")
        print("  both: train then test")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "train":
        aggregate_train()
    elif cmd == "test":
        aggregate_test()
    elif cmd == "both":
        aggregate_train()
        aggregate_test()
    elif cmd == "run" and len(sys.argv) == 4:
        ci, wi = int(sys.argv[2]), int(sys.argv[3])
        r = _run_one(ci, wi)
        prefix = "strict_test_ci" if wi >= len(TRAIN_WINDOWS) else "strict_ci"
        out_name = f"{prefix}{ci}_wi{wi}.json"
        with open(out_name, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"Saved: {out_name}")
        print(f"  Return: {r['return']:.3f}%  Bench: {r['benchmark']:+.3f}%  MaxDD: {r['max_dd']:.3f}%")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
