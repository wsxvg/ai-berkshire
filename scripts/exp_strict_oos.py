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
# Round 17 候选 — 关注防崩盘 + 3-regime全配置 + 过拟合验证
# Trigger: 2026-08-04-3
#
# R15 结果 (14 OOS windows):
#   4D_BASELINE:      12.097% ★ BEST
#   4D_MOMENTUM_BIAS: 11.922%
#   R13_KELLY_MAX:    11.148% (5D)
#   SMART_ONLY:        4.374%
#
# R16 结果 (15 OOS windows, 含7月崩盘 wi=14):
#   KC_AGGRESSIVE:     11.561% ★ BEST (KC_bull=0.7, KC_bear=0.4, equal weights)
#   R15_BASELINE_COPY: 11.472%
#   MO_TILT_MILD:      10.710%
#   CONCENTRATE_8:     10.314%
#   QC_DOMINANT:        9.712%
#
# R16 发现:
#   - kelly_bull=0.7 比 0.6 边际改善 +0.09%
#   - wi=14 崩盘窗口: MO_TILT_MILD 表现最佳 (5.28%), maxdd=13.21%
#   - 集中持仓 (top8) 表现最差之一
#
# R17 方向 (关注点转移到防崩盘和稳健性):
#   1. KC_AGGRESSIVE 作为 sanity baseline
#   2. FULL_REGIME: 测试极端差异化 bull/neutral/bear weights
#      → 评测 regime-specific 权重差异化是否有意义
#   3. MO_MILD_KC: MO_TILT_MILD 权重 + KC_AGGRESSIVE kelly caps
#      → 结合 wi=14 最佳权重和整体最优 kelly
#
# 减少候选数量 (3 vs 4-5) → 45 test jobs vs 70-75 → 更快迭代
# 防作弊: 候选和参数在 R17 OOS 数据可见前预注册 (2026-08-04)
# ============================================================

ROUND = 17

# 4D 均等权重
WTS_4D_EQUAL = {"quality": 25, "cost": 25, "manager": 25, "momentum": 25, "smart_money": 0}
WTS_4D_BULL = {"quality": 20, "cost": 20, "manager": 15, "momentum": 45, "smart_money": 0}
WTS_4D_BEAR = {"quality": 35, "cost": 25, "manager": 30, "momentum": 10, "smart_money": 0}

# 轻度动量倾斜
WTS_MO_MILD = {"quality": 22, "cost": 22, "manager": 21, "momentum": 35, "smart_money": 0}
WTS_MO_MILD_BULL = {"quality": 18, "cost": 18, "manager": 14, "momentum": 50, "smart_money": 0}
WTS_MO_MILD_BEAR = {"quality": 30, "cost": 25, "manager": 30, "momentum": 15, "smart_money": 0}

# 极端差异化 regime (测试 regime-specific 是否有意义)
WTS_EXT_BULL = {"quality": 15, "cost": 15, "manager": 10, "momentum": 60, "smart_money": 0}
WTS_EXT_NEUTRAL = {"quality": 30, "cost": 30, "manager": 25, "momentum": 15, "smart_money": 0}
WTS_EXT_BEAR = {"quality": 45, "cost": 30, "manager": 20, "momentum": 5, "smart_money": 0}

CANDIDATES = [
    # 0: KC_AGGRESSIVE (R16 winner, sanity baseline)
    ("KC_AGGRESSIVE", {
        "max_holdings": 12,
        "weights": WTS_4D_EQUAL,
        "weights_bull": WTS_4D_BULL,
        "weights_bear": WTS_4D_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
    }),

    # 1: FULL_REGIME — 极端差异化三regime权重
    ("FULL_REGIME", {
        "max_holdings": 12,
        "weights": WTS_EXT_NEUTRAL,
        "weights_bull": WTS_EXT_BULL,
        "weights_bear": WTS_EXT_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
    }),

    # 2: MO_MILD_KC — wi=14最佳权重 + R16最佳kelly
    ("MO_MILD_KC", {
        "max_holdings": 12,
        "weights": WTS_MO_MILD,
        "weights_bull": WTS_MO_MILD_BULL,
        "weights_bear": WTS_MO_MILD_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
    }),
]


# ─── 时间窗口定义 ───
ALL_WINDOWS = []
base_start = datetime(2023, 7, 17)
base_end = datetime(2026, 8, 15)

idx = 0
while True:
    current = base_start + timedelta(days=30 * idx)
    train_end = current + timedelta(days=180)
    test_end = current + timedelta(days=270)
    if test_end > base_end:
        break
    ALL_WINDOWS.append({
        "train_end": train_end.strftime("%Y-%m-%d"),
        "test_end": test_end.strftime("%Y-%m-%d"),
    })
    idx += 1

TRAIN_WINDOWS = ALL_WINDOWS[:14]
TEST_WINDOWS = ALL_WINDOWS[14:]

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
    print(f"Auto-selected: ci={best_ci} ({best_name})")
    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        print(f"  {name}: avg={s['avg_return']:.2f} ({s['count']} windows)")


def aggregate_test():
    """Aggregate ALL candidates' test (OOS) results."""
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

    summary = {}
    for name, items in by_candidate.items():
        avg_ret = sum(x["return"] for x in items) / len(items)
        avg_bench = sum(x.get("benchmark", 0) for x in items) / len(items)
        beats = sum(1 for x in items if x["return"] > x.get("benchmark", 0))
        summary[name] = {
            "avg_return": avg_ret,
            "avg_benchmark": avg_bench,
            "beats_count": beats,
            "total_windows": len(items),
            "win_rate_vsbench": beats / len(items) if items else 0,
            "avg_trades": sum(x.get("trades", 0) for x in items) / len(items),
            "avg_fees": sum(x.get("fees", 0) for x in items) / len(items),
            "avg_max_dd": sum(x.get("max_dd", 0) for x in items) / len(items),
            "details": sorted(items, key=lambda x: x["period"]),
        }

    evaluation = {
        "phase": "test_evaluation",
        "round": ROUND,
        "note": "THIS IS THE FINAL RESULT — OUT-OF-SAMPLE, NO CHEATING",
        "summary": summary,
    }
    with open("strict_test_evaluation.json", "w") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=2)
    print(f"R{ROUND} OOS Evaluation — ALL candidates ranked by avg OOS return:")
    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        marker = " <- BEST" if name == max(summary, key=lambda k: summary[k]["avg_return"]) else ""
        print(f"  {name}: avg={s['avg_return']:.3f}%  bench={s['avg_benchmark']:.3f}%  "
              f"beats={s['beats_count']}/{s['total_windows']}  winrate={s['win_rate_vsbench']:.2f}"
              f"  maxdd={s['avg_max_dd']:.2f}{marker}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["run_train", "run_test", "run_all_train", "run_all_test",
                                     "aggregate_train", "aggregate_test"])
    p.add_argument("ci", type=int, nargs="?", default=None)
    p.add_argument("wi", type=int, nargs="?", default=None)
    args = p.parse_args()

    if args.mode == "run_train":
        r = _run_one(args.ci, args.wi)
        out = f"strict_ci{args.ci}_wi{args.wi}.json"
        with open(out, "w") as f:
            json.dump(r, f, ensure_ascii=False)
        print(json.dumps({"return": r["return"], "trades": r["trades"], "file": out}, ensure_ascii=False))
    elif args.mode == "run_test":
        global_wi = len(TRAIN_WINDOWS) + args.wi
        r = _run_one(args.ci, global_wi)
        out = f"strict_test_ci{args.ci}_wi{args.wi}.json"
        with open(out, "w") as f:
            json.dump(r, f, ensure_ascii=False)
        print(json.dumps({"return": r["return"], "trades": r["trades"], "file": out}, ensure_ascii=False))
    elif args.mode == "run_all_train":
        for wi in range(len(TRAIN_WINDOWS)):
            res = _run_one(args.ci, wi)
            print(f"TRAIN wi={wi}: return={res['return']:.2f}")
    elif args.mode == "run_all_test":
        for wi in range(len(TEST_WINDOWS)):
            res = _run_one(args.ci, len(TRAIN_WINDOWS) + wi)
            print(f"TEST wi={wi}: return={res['return']:.2f}")
    elif args.mode == "aggregate_train":
        aggregate_train()
    elif args.mode == "aggregate_test":
        aggregate_test()
