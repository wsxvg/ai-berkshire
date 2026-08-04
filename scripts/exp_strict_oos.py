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
# Round 19 候选 — 止损机制验证 (降低 peak maxdd)
# Trigger: 2026-08-04-5
#
# R18 结果 (22 OOS windows, 2022-12 到 2026-08, 覆盖 COVID+2022+2026):
#   KC_AGGRESSIVE:     4.536% avg, maxdd 4.38%, beat bench 64%
#   MO_TILT_BALANCED:  4.588% avg, maxdd 4.50%, beat bench 59%
#   PURE_4D_EQUAL:     3.478% avg, maxdd 4.50%, beat bench 55%
#
# R18 关键发现:
#   - W42 (2026-05-24~08-22, 含 July crash): net -1.34%, peak maxdd=14.63%
#   - 长期 alpha ~3%/q (vs benchmark 1.65%/q), 防摔能力本身不错
#   - R16 的 11.56% 是牛市红利; 真实长期 OOS ~4.5%
#
# R19 方向: 降低 peak maxdd (14.6% → 目标 ~8%)
#   - 候选 0: KC_AGGRESSIVE_BASELINE (同 R18, 复现 baseline)
#   - 候选 1: KC_AGGRESSIVE_STOPLOSS_8 — 启用 8% 止损线
#   - 候选 2: KC_AGGRESSIVE_DYN_SL — 动态止盈(盈利>20%后回撤15%止损)
#
# 复用 R18 配置: 43 windows (2019-01~2026-09), 21 train / 22 test
# 防作弊: 候选参数在 OOS 数据可见前预注册 (2026-08-04)
# ============================================================

ROUND = 19

# ─── 权重方案 (与 R18 一致) ───
WTS_EQUAL = {"quality": 25, "cost": 25, "manager": 25, "momentum": 25, "smart_money": 0}
WTS_BULL = {"quality": 20, "cost": 20, "manager": 15, "momentum": 45, "smart_money": 0}
WTS_BEAR = {"quality": 35, "cost": 25, "manager": 30, "momentum": 10, "smart_money": 0}

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

    # 1: KC_AGGRESSIVE_STOPLOSS_8 — 8% 单基金止损
    ("KC_AGGRESSIVE_STOPLOSS_8", {
        "max_holdings": 12,
        "weights": WTS_EQUAL,
        "weights_bull": WTS_BULL,
        "weights_bear": WTS_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": False,
        "stop_loss_pct": -8,
    }),

    # 2: KC_AGGRESSIVE_DYN_SL — 动态止盈
    ("KC_AGGRESSIVE_DYN_SL", {
        "max_holdings": 12,
        "weights": WTS_EQUAL,
        "weights_bull": WTS_BULL,
        "weights_bear": WTS_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": False,
        "stop_loss_pct": -30,  # 硬止损 30% (宽松)
        "dynamic_stop_loss": True,  # 盈利>20%后回撤15%止盈
    }),
]


# ─── 时间窗口定义 (同 R18) ───
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
    selection = {"best_ci": best_ci, "best_candidate": best_name, "summary": summary, "round": ROUND}

    with open("strict_train_selection.json", "w") as f:
        json.dump(selection, f, ensure_ascii=False, indent=2)

    print("=== Train Aggregation ===")
    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        marker = " ★ BEST" if name == best_name else ""
        print(f"  {name:30s}: {s['avg_return']:8.3f}% ({s['count']} windows){marker}")
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
        max_max_dd = max(x["max_dd"] for x in items)
        beats_count = sum(1 for x in items if x["return"] > x["benchmark"])
        summary[name] = {
            "avg_return": avg_ret,
            "avg_benchmark": avg_bench,
            "avg_max_drawdown": avg_max_dd,
            "peak_max_drawdown": max_max_dd,
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
        print(f"    Peak MaxDD: {s['peak_max_drawdown']:8.3f}%  ← key metric")
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
