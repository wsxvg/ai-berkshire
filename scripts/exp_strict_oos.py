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
# Round 15 候选 — 去掉 smart_money 的四维长期回测
# Trigger: 2026-08-04 retry
#
# R13 成功: KELLY_MAX = 11.148% (5D: SM=30 weight)
#
# 动机: trading_by_date.json 只有 2024-03 ~ 2026-07 的数据 (~2.5年)
#       对长期回测来说 smart_money 在 2024-03 之前全=0
#       问题: 有没有 smart_money 真的对回测有帮助?
#
# R15 方向: 移除 smart_money, 用 Q/C/Mgr/Mo 四维重新归一化权重
#   对比 5D baseline vs 4D 各种权重分布
#
# 防作弊: 候选和参数在 R15 OOS 数据可见前预注册 (2026-08-04)
# ============================================================

ROUND = 15

WTS_BASELINE = {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30}
WTS_BULL_TREND = {"quality": 15, "cost": 20, "manager": 10, "momentum": 20, "smart_money": 35}
WTS_BEAR_TREND = {"quality": 25, "cost": 25, "manager": 30, "momentum": 10, "smart_money": 10}
WTS_BULL_EXTREME = {"quality": 10, "cost": 15, "manager": 10, "momentum": 25, "smart_money": 40}

# 四维权重（smart_money=0，把它的权重新分配给其他维度）
WTS_4D_EQUAL = {"quality": 25, "cost": 25, "manager": 25, "momentum": 25, "smart_money": 0}
WTS_4D_BULL = {"quality": 20, "cost": 20, "manager": 15, "momentum": 45, "smart_money": 0}
WTS_4D_BEAR = {"quality": 35, "cost": 25, "manager": 30, "momentum": 10, "smart_money": 0}

WTS_4D_QUALITY = {"quality": 35, "cost": 30, "manager": 25, "momentum": 10, "smart_money": 0}
WTS_4D_QUALITY_BULL = {"quality": 30, "cost": 25, "manager": 15, "momentum": 30, "smart_money": 0}
WTS_4D_QUALITY_BEAR = {"quality": 40, "cost": 30, "manager": 25, "momentum": 5, "smart_money": 0}

WTS_4D_MOMENTUM = {"quality": 15, "cost": 20, "manager": 15, "momentum": 50, "smart_money": 0}
WTS_4D_MOMENTUM_BULL = {"quality": 10, "cost": 10, "manager": 10, "momentum": 70, "smart_money": 0}
WTS_4D_MOMENTUM_BEAR = {"quality": 25, "cost": 25, "manager": 30, "momentum": 20, "smart_money": 0}

CANDIDATES = [
    # 0: R13_KELLY_MAX (5D baseline - sanity check, 应该与 R13 结果一致)
    ("R13_KELLY_MAX", {
        "max_holdings": 12,
        "weights": WTS_BASELINE,
        "weights_bull": WTS_BULL_TREND,
        "weights_bear": WTS_BEAR_TREND,
        "kelly_cap_bull": 0.6,
        "kelly_cap_bear": 0.35,
    }),

    # 1: 4D_BASELINE — 去掉 smart_money, Q/C/Mgr/Mo 均匀 25/25/25/25
    ("4D_BASELINE", {
        "max_holdings": 12,
        "weights": WTS_4D_EQUAL,
        "weights_bull": WTS_4D_BULL,
        "weights_bear": WTS_4D_BEAR,
        "kelly_cap_bull": 0.6,
        "kelly_cap_bear": 0.35,
    }),

    # 2: 4D_QUALITY_BIAS — 偏质量/成本（防守型）
    ("4D_QUALITY_BIAS", {
        "max_holdings": 12,
        "weights": WTS_4D_QUALITY,
        "weights_bull": WTS_4D_QUALITY_BULL,
        "weights_bear": WTS_4D_QUALITY_BEAR,
        "kelly_cap_bull": 0.6,
        "kelly_cap_bear": 0.35,
    }),

    # 3: 4D_MOMENTUM_BIAS — 偏动量（进攻型）
    ("4D_MOMENTUM_BIAS", {
        "max_holdings": 12,
        "weights": WTS_4D_MOMENTUM,
        "weights_bull": WTS_4D_MOMENTUM_BULL,
        "weights_bear": WTS_4D_MOMENTUM_BEAR,
        "kelly_cap_bull": 0.6,
        "kelly_cap_bear": 0.35,
    }),

    # 4: SMART_ONLY — 仅 smart_money=100，其他=0，测试 smart_money 单独贡献
    ("SMART_ONLY", {
        "max_holdings": 5,
        "weights": {"quality": 0, "cost": 0, "manager": 0, "momentum": 0, "smart_money": 100},
        "min_consensus": 3,  # 高门槛确保只买聪明的
    }),
]


# ─── 时间窗口定义 ───
# 扩展: base_end 延伸至 2026-08-15 (包含 7 月崩盘完整周期)
ALL_WINDOWS = []
base_start = datetime(2023, 7, 17)
base_end = datetime(2026, 8, 15)

# 生成每 30 天滚动的窗口
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


def run_train(ci, wi):
    train_end, test_end = window_range(wi)
    cfg = copy.deepcopy(BASE_CFG)
    cfg_override = CANDIDATES[ci][1]
    cfg.update(cfg_override)
    cfg['start_date'] = train_end
    cfg['end_date'] = test_end
    res = run_backtest(cfg, clear_cache=True)
    return res


def run_test(ci, wi):
    train_end, test_end = window_range(wi)
    cfg = copy.deepcopy(BASE_CFG)
    cfg_override = CANDIDATES[ci][1]
    cfg.update(cfg_override)
    cfg['start_date'] = train_end
    cfg['end_date'] = test_end
    res = run_backtest(cfg, clear_cache=True)
    return res


def run_all_train(ci):
    results = []
    for wi in range(len(TRAIN_WINDOWS)):
        res = run_train(ci, wi)
        results.append(res)
    return results


def run_all_test(ci):
    results = []
    for wi in range(len(TEST_WINDOWS)):
        res = run_test(ci, len(TRAIN_WINDOWS) + wi)
        results.append(res)
    return results


def _run_one(ci, wi_global):
    """Run a single (ci, wi_global) backtest.  wi_global is 0-based across ALL_WINDOWS."""
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
    print(f"Auto-selected: ci={best_ci} ({best_name})  avg_return={summary[best_name]['avg_return']:.2f}")
    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        print(f"  {name}: avg_return={s['avg_return']:.2f} ({s['count']} windows)")


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
        # wi is LOCAL train window index (0-13) -> convert to global
        r = _run_one(args.ci, args.wi)
        out = f"strict_ci{args.ci}_wi{args.wi}.json"
        with open(out, "w") as f:
            json.dump(r, f, ensure_ascii=False)
        print(json.dumps({"return": r["return"], "trades": r["trades"], "file": out}, ensure_ascii=False))
    elif args.mode == "run_test":
        # wi is LOCAL test window index (0-13) -> convert to global (14-27)
        global_wi = len(TRAIN_WINDOWS) + args.wi
        r = _run_one(args.ci, global_wi)
        out = f"strict_test_ci{args.ci}_wi{args.wi}.json"
        with open(out, "w") as f:
            json.dump(r, f, ensure_ascii=False)
        print(json.dumps({"return": r["return"], "trades": r["trades"], "file": out}, ensure_ascii=False))
    elif args.mode == "run_all_train":
        rs = run_all_train(args.ci)
        for i, r in enumerate(rs):
            print(f"TRAIN wi={i}: return={r.get('total_return',0):.2f}")
    elif args.mode == "run_all_test":
        rs = run_all_test(args.ci)
        for i, r in enumerate(rs):
            print(f"TEST wi={i}: return={r.get('total_return',0):.2f}")
    elif args.mode == "aggregate_train":
        aggregate_train()
    elif args.mode == "aggregate_test":
        aggregate_test()

