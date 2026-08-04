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
# Round 18 候选 — 拓展 OOS 窗口至 2019-2026 (覆盖 COVID + 2022 熊市)
# Trigger: 2026-08-04-4
#
# R17 结果 (15 OOS windows, 实际只覆盖 2023-2026):
#   KC_AGGRESSIVE:     11.561% ★ BEST (R16 复现)
#   MO_MILD_KC:        10.805%
#   FULL_REGIME:        8.179% — 极端 regime 权重失败, 证实 overengineering
#
# R17 关键发现:
#   - FULL_REGIME 差异化 regime weights 表现最差
#   - KC_AGGRESSIVE/R16 复现成功 (11.561% 完全一致)
#   - 极端差异化 = overfitting 信号
#
# 用户过拟合质疑 (正确):
#   - July 单测: KC_AGGRESSIVE 在 2026 年 7 月崩盘时亏损 -20.18% (score 6/25)
#   - 只有 1 个崩盘数据点就加 cash 档位是典型 overfitting
#   - 正确方向: 先扩展 OOS 窗口到 2019-2026, 用 COVID/2022 等多崩盘周期验证
#
# R18 方向: 扩展 OOS 覆盖至 2019 年初
#   - 数据: NAV 自 2001 年覆盖, 2020 年初已有 2300 只基金
#   - 去掉 smart_money (仅 2023-07 起), 使用 4D 模型 (Quality/Cost/Manager/Momentum)
#   - 窗口跨度: 2019-01 ~ 2026-08 (7.6 年)
#   - 60-day slide, 42 windows (21 train / 21 test)
#
# 预注册候选 (2026-08-04, 跑 OOS 数据前):
#   0. KC_AGGRESSIVE (R16/R17 winner): kelly_bull=0.7, kelly_bear=0.4, equal weights
#   1. PURE_4D_EQUAL: 纯 4D 均等权重, 无 regime shift (无 overfitting 基线)
#   2. MO_TILT_BALANCED: 轻微 momentum 倾斜 + 中等 regime 偏移
#
# 3 candidates × 42 windows = 126 train + 126 test = 252 jobs
# ============================================================

ROUND = 18

# ─── 权重方案 ───

# 4D 均等 (无 regime shift 基线)
WTS_EQUAL = {"quality": 25, "cost": 25, "manager": 25, "momentum": 25, "smart_money": 0}

# KC_AGGRESSIVE: 均等 + 适度 regime 偏移
WTS_KC_EQUAL = {"quality": 25, "cost": 25, "manager": 25, "momentum": 25, "smart_money": 0}
WTS_KC_BULL = {"quality": 20, "cost": 20, "manager": 15, "momentum": 45, "smart_money": 0}
WTS_KC_BEAR = {"quality": 35, "cost": 25, "manager": 30, "momentum": 10, "smart_money": 0}

# MO_TILT_BALANCED: 轻 momentum + 中等 regime
WTS_MO_BAL = {"quality": 22, "cost": 22, "manager": 21, "momentum": 35, "smart_money": 0}
WTS_MO_BAL_BULL = {"quality": 18, "cost": 20, "manager": 17, "momentum": 45, "smart_money": 0}
WTS_MO_BAL_BEAR = {"quality": 30, "cost": 25, "manager": 28, "momentum": 17, "smart_money": 0}

CANDIDATES = [
    # 0: KC_AGGRESSIVE (R16/R17 winner, sanity baseline)
    ("KC_AGGRESSIVE", {
        "max_holdings": 12,
        "weights": WTS_KC_EQUAL,
        "weights_bull": WTS_KC_BULL,
        "weights_bear": WTS_KC_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
    }),

    # 1: PURE_4D_EQUAL — 无 regime shift 基线
    ("PURE_4D_EQUAL", {
        "max_holdings": 12,
        "weights": WTS_EQUAL,
        "weights_bull": WTS_EQUAL,   # same as neutral
        "weights_bear": WTS_EQUAL,   # same as neutral
        "kelly_cap_bull": 0.5,
        "kelly_cap_bear": 0.5,       # no change in bear
    }),

    # 2: MO_TILT_BALANCED
    ("MO_TILT_BALANCED", {
        "max_holdings": 12,
        "weights": WTS_MO_BAL,
        "weights_bull": WTS_MO_BAL_BULL,
        "weights_bear": WTS_MO_BAL_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
    }),
]


# ─── 时间窗口定义 ───
# R18: 扩展至 2019 年初，覆盖 COVID (2020), 2022 bear, 2026 crash
ALL_WINDOWS = []
base_start = datetime(2019, 1, 1)
base_end = datetime(2026, 9, 30)  # extend to cover July 2026 crash window

idx = 0
while True:
    current = base_start + timedelta(days=60 * idx)  # 60-day slide
    train_end = current + timedelta(days=180)
    test_end = current + timedelta(days=270)
    if test_end > base_end:
        break
    ALL_WINDOWS.append({
        "train_end": train_end.strftime("%Y-%m-%d"),
        "test_end": test_end.strftime("%Y-%m-%d"),
    })
    idx += 1

# 21 train / 22 test
TRAIN_WINDOWS = ALL_WINDOWS[:21]
TEST_WINDOWS = ALL_WINDOWS[21:]
assert len(TRAIN_WINDOWS) + len(TEST_WINDOWS) == len(ALL_WINDOWS)

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
    """Run a single (ci, wi_global) backtest."""
    train_end, test_end = window_range(wi_global)
    cfg = copy.deepcopy(BASE_CFG)
    cfg_override = CANDIDATES[ci][1]
    cfg.update(cfg_override)
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
        "avg_hold_days": res.get("avg_hold_days", 0),
    }


def aggregate_train():
    results = []
    for fname in os.listdir("."):
        if fname.startswith("strict_ci") and fname.endswith(".json"):
            try:
                with open(fname) as f:
                    results.append(json.load(f))
            except Exception:
                pass
    if not results:
        print("No train results found!")
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
    selection = {
        "best_ci": best_ci,
        "best_candidate": best_name,
        "summary": summary,
        "round": ROUND,
    }

    with open("strict_train_selection.json", "w") as f:
        json.dump(selection, f, ensure_ascii=False, indent=2)

    print("=== Train Aggregation ===")
    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        marker = " ★ BEST" if name == best_name else ""
        print(f"  {name:20s}: {s['avg_return']:8.3f}% ({s['count']} windows){marker}")
    return selection


def aggregate_test():
    results = []
    for fname in os.listdir("."):
        if fname.startswith("strict_test_ci") and fname.endswith(".json"):
            try:
                with open(fname) as f:
                    results.append(json.load(f))
            except Exception:
                pass
    if not results:
        print("No test results found!")
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
        beats_count = sum(1 for x in items if x["return"] > x["benchmark"])
        summary[name] = {
            "avg_return": avg_ret,
            "avg_benchmark": avg_bench,
            "avg_max_drawdown": avg_max_dd,
            "beats_count": beats_count,
            "beats_rate": beats_count / len(items),
            "count": len(items),
            "per_window": [
                {"period": x["period"], "return": x["return"], "benchmark": x["benchmark"], "max_dd": x["max_dd"]}
                for x in items
            ],
        }

    for name in sorted(summary, key=lambda k: -summary[k]["avg_return"]):
        s = summary[name]
        print(f"\n  {name}:")
        print(f"    Avg Return: {s['avg_return']:8.3f}%")
        print(f"    Avg Bench:  {s['avg_benchmark']:8.3f}%")
        print(f"    Avg MaxDD:  {s['avg_max_drawdown']:8.3f}%")
        print(f"    Beat Bench: {s['beats_count']}/{s['count']} ({s['beats_rate']:.0%})")

    eval_result = {
        "round": ROUND,
        "window_count": len(TEST_WINDOWS),
        "period": f"{TEST_WINDOWS[0]['train_end']}~{TEST_WINDOWS[-1]['test_end']}",
        "summary": summary,
    }
    with open("strict_test_evaluation.json", "w") as f:
        json.dump(eval_result, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to strict_test_evaluation.json")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python exp_strict_oos.py run_train <ci> <wi>")
        print("  python exp_strict_oos.py run_test <ci> <wi>")
        print("  python exp_strict_oos.py aggregate_train")
        print("  python exp_strict_oos.py aggregate_test")
        print("  python exp_strict_oos.py list_windows")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "run_train":
        ci, wi = int(sys.argv[2]), int(sys.argv[3])
        r = _run_one(ci, wi)
        out = f"strict_ci{ci}_wi{wi}.json"
        with open(out, "w") as f:
            json.dump(r, f)
        print(f"[R{r['round']}] Train c{ci} w{wi} ({r['period']}): {r['return']:.3f}%")
    elif cmd == "run_test":
        ci, wi = int(sys.argv[2]), int(sys.argv[3])
        wi_global = wi + len(TRAIN_WINDOWS)
        r = _run_one(ci, wi_global)
        out = f"strict_test_ci{ci}_wi{wi}.json"
        with open(out, "w") as f:
            json.dump(r, f)
        print(f"[R{r['round']}] Test c{ci} w{wi} ({r['period']}): {r['return']:.3f}%")
    elif cmd == "aggregate_train":
        aggregate_train()
    elif cmd == "aggregate_test":
        aggregate_test()
    elif cmd == "list_windows":
        for i, w in enumerate(ALL_WINDOWS):
            phase = "TRAIN" if i < len(TRAIN_WINDOWS) else "TEST"
            print(f"  W{i:2d} [{phase:5s}]: train_end={w['train_end']}  test_end={w['test_end']}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
