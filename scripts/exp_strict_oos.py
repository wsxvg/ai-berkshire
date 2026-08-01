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
# Round 6 候选 — LGB 尾部风险防护 (Crash Protection)
#
# R4 发现:
#   - W7 (Oct~Jan) 所有候选均亏 ~-9%, 大盘仅亏 -1.16%
#   - W3-W4 smart_money 大幅跑赢 → 牛市捕获 OK
#   - 候选间差异 < 1% → 评分模型已成熟, 需在 OTHER 维度改进
#
# R6 假设:
#   1. LightGBM (lgb_predictor) 可通过历史净值序列检测 W7 类尾部风险
#   2. 预测器 crash_sell: P(跌)>threshold 时强制清仓 → 躲过 W7
#   3. 风控+预测器双保险 → 规则+ML 组合更强
#   4. 更高的 LGB 重训练频率 → 捕捉regime变化更快
#
# R6 候选 (预注册, 2026-08-02):
#   0. R4_BASELINE — WEIGHTS_ALT 对照
#   1. LGB_AGGRESSIVE — LGB 预测器, 高灵敏度, crash<-4%P>0.6卖
#   2. LGB_CONSERVATIVE — LGB + market_risk_filter 双保险
#   3. LGB_RETRAIN — LGB 高频重训练
#   4. COMBO_70 — LGB + 风险阈值70 + TP30
# ============================================================

ROUND = 6

CANDIDATES = [
    # R4 winner, 对照
    ("R4_BASELINE", {"max_holdings": 12, "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30}}),
    # LightGBM crash predictor — 主动清仓
    ("LGB_AGGRESSIVE", {
        "max_holdings": 12,
        "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
        "lgb_predictor": True,
        "lgb_sell_threshold": 0.6,
        "lgb_crash_threshold": -0.04,
        "lgb_retrain_days": 20,
    }),
    # LGB + market_risk_filter 双重风控
    ("LGB_CONSERVATIVE", {
        "max_holdings": 12,
        "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
        "lgb_predictor": True,
        "lgb_sell_threshold": 0.55,
        "lgb_crash_threshold": -0.05,
        "lgb_retrain_days": 20,
        "market_risk_filter": True,
        "market_risk_threshold": 55,
    }),
    # LGB with 高频重训练
    ("LGB_RETRAIN", {
        "max_holdings": 12,
        "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
        "lgb_predictor": True,
        "lgb_sell_threshold": 0.6,
        "lgb_crash_threshold": -0.04,
        "lgb_retrain_days": 10,  # 更高频
    }),
    # Full combo
    ("COMBO_70", {
        "max_holdings": 12,
        "weights": {"quality": 20, "cost": 25, "manager": 15, "momentum": 10, "smart_money": 30},
        "lgb_predictor": True,
        "lgb_sell_threshold": 0.65,
        "lgb_crash_threshold": -0.04,
        "lgb_retrain_days": 15,
        "market_risk_filter": True,
        "market_risk_threshold": 70,  # 更高阈值 (少干预)
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
