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
# Round 8 候选 — 广度防御 + 组合回撤减仓 (Defensive Risk Management)
#
# R4-R7 发现:
#   - 单基金价格滤波 (MACD/Bollinger/MA250) 在绝大多数窗口与 BASELINE 完全相同
#   - R7 WEEKLY_MACD 仅 W12/W13 有微弱改善，W7 完全无效 (-9.29% vs -9.29% 不变)
#   - 核心矛盾: CSI300 仅 -1.16% 时选股策略 -9.29% → smart_money 在选股失灵期产生严重负 alpha
#   - 价格型预测滤波本质上是"预测"大盘，但对"选股相对大盘的 alpha 失效"无解
#
# R8 假设 (被动式, 非预测):
#   1. 广度防御: 全市场基金 20 日上涨占比 < 阈值 → 选股 alpha 系统性失效 → 减仓 (非预测!)
#   2. 组合回撤减仓: 组合净值回撤 > X% 时每只减仓 Y% (被动式, 无未来函数)
#   3. 组合: 广度 + 组合回撤 双保险
#
# 关键金融学原理: 被动式风控不预测市场，只对已发生损失做出反应
#   - 广度用的是 T 日截止的 chart 数据 (先验, 无未来函数)
#   - 组合回撤用当前组合净值 vs 历史峰值 (先验, 无未来函数)
#
# R8 候选 (预注册, 2026-08-02):
#   0. R4_BASELINE — 对照 (无防御)
#   1. BREADTH_30 — 广度 < 0.30 → 减仓 (宽松阈值, 早期入场)
#   2. BREADTH_20 — 广度 < 0.20 → 减仓 (激进阈值, 只在极度恐慌触发)
#   3. COMBO_DEFENSE — 广度 < 0.35 + 组合回撤 6% → 双重防御
#   4. PORTFOLIO_DD_8 — 仅组合回撤 8% → 减仓 30% (测试纯组合回撤效果)
# ============================================================

ROUND = 8

CANDIDATES = [
    # 0: R4 winner, 对照 (无防御滤波)
    ("R4_BASELINE", {"max_holdings": 12, "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30}}),
    # 1: 广度 < 30% → 减仓 (宽松阈值, 对选股失灵早期反应)
    ("BREADTH_30", {
        "max_holdings": 12,
        "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
        "breadth_defense": True,
        "breadth_threshold": 0.30,
        "breadth_lookback": 20,
    }),
    # 2: 广度 < 20% → 减仓 (激进阈值, 只在极度恐慌触发)
    ("BREADTH_20", {
        "max_holdings": 12,
        "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
        "breadth_defense": True,
        "breadth_threshold": 0.20,
        "breadth_lookback": 20,
    }),
    # 3: 双重防御: 广度 + 组合回撤
    ("COMBO_DEFENSE", {
        "max_holdings": 12,
        "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
        "breadth_defense": True,
        "breadth_threshold": 0.35,
        "breadth_lookback": 20,
        "portfolio_dd_reduce_pct": 1,  # enable > 0
        "portfolio_dd_reduce_threshold": 6,
        "portfolio_dd_reduce_frac": 0.3,
    }),
    # 4: 仅组合回撤 (测试减仓自救效果)
    ("PORTFOLIO_DD_8", {
        "max_holdings": 12,
        "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
        "portfolio_dd_reduce_pct": 1,
        "portfolio_dd_reduce_threshold": 8,
        "portfolio_dd_reduce_frac": 0.3,
    }),
]

BASE_CFG = {
    "initial_cash": 10000,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "min_score": 3.0,
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

base_start = datetime(2023, 7, 17)
base_end = datetime(2026, 7, 24)

ALL_WINDOWS = []
current = base_start
while current + timedelta(days=270) <= base_end:
    train_end = (current + timedelta(days=180)).strftime("%Y-%m-%d")
    test_end = (current + timedelta(days=270)).strftime("%Y-%m-%d")
    ALL_WINDOWS.append((train_end, test_end))
    current += timedelta(days=30)

TRAIN_WINDOWS = ALL_WINDOWS[:14]
TEST_WINDOWS = ALL_WINDOWS[14:]

print(f"[STRICT_OOS] {len(TRAIN_WINDOWS)} train + {len(TEST_WINDOWS)} test windows, ROUND {ROUND}, {len(CANDIDATES)} candidates")


def run_single(cfg_override, train_end, test_end):
    cfg = copy.deepcopy(BASE_CFG)
    cfg.update(cfg_override)
    cfg['start_date'] = train_end
    cfg['end_date'] = test_end
    res = run_backtest(cfg, clear_cache=True)
    return {
        'return': res.get('total_return', 0),
        'trades': res.get('trade_count', 0),
        'fees': res.get('total_fees', 0),
        'max_dd': res.get('max_drawdown', 0),
        'benchmark': res.get('benchmark_csi300', res.get('benchmark_return', 0)),
        'win_rate': res.get('win_rate', 0),
        'avg_hold_days': res.get('avg_hold_days', 0),
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if mode == "run_train":
        ci = int(sys.argv[2])
        wi = int(sys.argv[3])
        name, override = CANDIDATES[ci]
        train_end, test_end = TRAIN_WINDOWS[wi]
        res = run_single(override, train_end, test_end)
        out = {"phase": "train", "round": ROUND, "candidate": name, "ci": ci, "wi": wi,
               "period": f"{train_end}~{test_end}", **res}
        with open(f"strict_ci{ci}_wi{wi}.json", "w") as f:
            json.dump(out, f)
        print(f"[TRAIN] R{ROUND} {name} W{wi}: Ret={res['return']:+.2f}% Bench={res['benchmark']:+.2f}%", flush=True)
    
    elif mode == "run_test":
        ci = int(sys.argv[2])
        wi = int(sys.argv[3])
        name, override = CANDIDATES[ci]
        train_end, test_end = TEST_WINDOWS[wi]
        res = run_single(override, train_end, test_end)
        out = {"phase": "test", "round": ROUND, "candidate": name, "ci": ci, "wi": wi,
               "period": f"{train_end}~{test_end}", **res}
        with open(f"strict_test_ci{ci}_wi{wi}.json", "w") as f:
            json.dump(out, f)
        print(f"[TEST] R{ROUND} {name} W{wi}: Ret={res['return']:+.2f}% Bench={res['benchmark']:+.2f}%", flush=True)
    
    elif mode == "aggregate_train":
        results = []
        for ci in range(len(CANDIDATES)):
            for wi in range(len(TRAIN_WINDOWS)):
                fname = f"strict_ci{ci}_wi{wi}.json"
                if os.path.exists(fname):
                    with open(fname) as f:
                        results.append(json.load(f))
        by_cand = defaultdict(list)
        for r in results:
            by_cand[r['candidate']].append(r)
        summary = {}
        for name, ress in by_cand.items():
            avg_ret = sum(r['return'] for r in ress) / len(ress) if ress else 0
            avg_bench = sum(r['benchmark'] for r in ress) / len(ress) if ress else 0
            beats = sum(1 for r in ress if r['return'] > r['benchmark'])
            summary[name] = {"avg_return": avg_ret, "avg_benchmark": avg_bench,
                           "beats_count": beats, "total_windows": len(ress),
                           "win_rate_vsbench": beats / len(ress) if ress else 0,
                           "avg_trades": sum(r['trades'] for r in ress) / len(ress) if ress else 0}
        best_name = max(summary.keys(), key=lambda k: summary[k]['avg_return'])
        best_ci = [c[0] for c in CANDIDATES].index(best_name)
        out = {"phase": "train_selection", "round": ROUND, "summary": summary,
               "best_candidate": best_name, "best_ci": best_ci}
        with open("strict_train_selection.json", "w") as f:
            json.dump(out, f, indent=2)
        print(f"[SELECT] Best on TRAIN: {best_name} (ci={best_ci})")
        for name, s in sorted(summary.items(), key=lambda x: -x[1]['avg_return']):
            print(f"  {name}: +{s['avg_return']:.3f}% (bench {s['avg_benchmark']:+.3f}%) beats={s['beats_count']}/{s['total_windows']}")
    
    elif mode == "aggregate_test":
        results = []
        for fname in os.listdir('.'):
            if fname.startswith("strict_test_") and fname.endswith(".json"):
                with open(fname) as f:
                    results.append(json.load(f))
        if not results:
            print("[TEST_AGG] No test results found!", flush=True)
            return
        by_cand = defaultdict(list)
        for r in results:
            by_cand[r['candidate']].append(r)
        summary = {}
        for name, ress in by_cand.items():
            avg_ret = sum(r['return'] for r in ress) / len(ress) if ress else 0
            avg_bench = sum(r['benchmark'] for r in ress) / len(ress) if ress else 0
            beats = sum(1 for r in ress if r['return'] > r['benchmark'])
            summary[name] = {
                "avg_return": avg_ret, "avg_benchmark": avg_bench,
                "beats_count": beats, "total_windows": len(ress),
                "win_rate_vsbench": beats / len(ress) if ress else 0,
                "avg_trades": sum(r['trades'] for r in ress) / len(ress) if ress else 0,
                "avg_fees": sum(r['fees'] for r in ress) / len(ress) if ress else 0,
                "avg_max_dd": sum(r['max_dd'] for r in ress) / len(ress) if ress else 0,
                "details": ress,
            }
        out = {"phase": "test_evaluation", "round": ROUND,
               "note": "THIS IS THE FINAL RESULT — OUT-OF-SAMPLE, NO CHEATING",
               "summary": summary}
        with open("strict_test_evaluation.json", "w") as f:
            json.dump(out, f, indent=2)
        print("\n" + "="*60)
        print(f"STRICT OOS Round {ROUND} — FINAL OUT-OF-SAMPLE RESULT")
        print("="*60)
        for name, s in sorted(summary.items(), key=lambda x: -x[1]['avg_return']):
            status = "✅ BEAT" if s['avg_return'] > s['avg_benchmark'] else "❌ LOSE"
            print(f"{name}: +{s['avg_return']:.3f}%/q vs CSI300 {s['avg_benchmark']:+.3f}%/q [{status}] beats {s['beats_count']}/{s['total_windows']}")
    
    else:
        print("Usage: python exp_strict_oos.py [run_train|run_test|aggregate_train|aggregate_test] [ci] [wi]")


if __name__ == "__main__":
    main()
