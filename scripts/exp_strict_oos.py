#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
严格 OOS (Out-of-Sample) 回测框架 — 零作弊协议

规则:
1. train_windows = 前 14 个 window (W0-W13) → 只用这些选参数
2. test_windows  = 后 14 个 window (W14-W27) → 只用这些报最终结果
3. 选参数时禁止看 test_windows 表现
4. 最终结论只能基于 test_windows
"""
import sys, copy, json, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest


# ============================================================
# 候选配置 (预注册 — 在看到任何回测结果前定义)
# 每轮实验最多 5 个，避免多重比较
# ============================================================
CANDIDATES = [
    ("V8_BASE", {
        "max_holdings": 5,
    }),
    ("V8_HOLD9", {
        "max_holdings": 9,
    }),
    ("V8_HOLD12", {
        "max_holdings": 12,
    }),
    ("V8_TP40", {
        "max_holdings": 9,
        "take_profit_pct": 40.0,
    }),
    ("V8_TP60", {
        "max_holdings": 9,
        "take_profit_pct": 60.0,
    }),
]

# 基线配置（所有候选共享）
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

# 窗口生成 (28 windows, 6mo train + 3mo test, slide 1mo)
base_start = datetime(2023, 7, 17)
base_end = datetime(2026, 7, 24)

ALL_WINDOWS = []
current = base_start
while current + timedelta(days=270) <= base_end:
    train_end = (current + timedelta(days=180)).strftime("%Y-%m-%d")
    test_end = (current + timedelta(days=270)).strftime("%Y-%m-%d")
    ALL_WINDOWS.append((train_end, test_end))
    current += timedelta(days=30)

TRAIN_WINDOWS = ALL_WINDOWS[:14]   # W0-W13
TEST_WINDOWS = ALL_WINDOWS[14:]    # W14-W27

print(f"[STRICT_OOS] {len(TRAIN_WINDOWS)} train + {len(TEST_WINDOWS)} test windows")
print(f"[STRICT_OOS] {len(CANDIDATES)} candidates × {len(TRAIN_WINDOWS)} train + {len(TEST_WINDOWS)} test runs")


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
        # 跑训练集，保存结果给 aggregate 用
        ci = int(sys.argv[2])
        wi = int(sys.argv[3])
        name, override = CANDIDATES[ci]
        train_end, test_end = TRAIN_WINDOWS[wi]
        res = run_single(override, train_end, test_end)
        out = {"phase": "train", "candidate": name, "ci": ci, "wi": wi, 
               "period": f"{train_end}~{test_end}", **res}
        with open(f"strict_ci{ci}_wi{wi}.json", "w") as f:
            json.dump(out, f)
        print(f"[TRAIN] {name} W{wi}: Ret={res['return']:+.2f}% Bench={res['benchmark']:+.2f}%")
        sys.stdout.flush()
    
    elif mode == "run_test":
        # 跑测试集（只跑 best config）
        ci = int(sys.argv[2])
        wi = int(sys.argv[3])
        name, override = CANDIDATES[ci]
        train_end, test_end = TEST_WINDOWS[wi]
        res = run_single(override, train_end, test_end)
        out = {"phase": "test", "candidate": name, "ci": ci, "wi": wi,
               "period": f"{train_end}~{test_end}", **res}
        with open(f"strict_test_ci{ci}_wi{wi}.json", "w") as f:
            json.dump(out, f)
        print(f"[TEST] {name} W{wi}: Ret={res['return']:+.2f}% Bench={res['benchmark']:+.2f}%")
        sys.stdout.flush()
    
    elif mode == "aggregate_train":
        # 收集训练集结果，选出 best config
        results = []
        for ci in range(len(CANDIDATES)):
            for wi in range(len(TRAIN_WINDOWS)):
                fname = f"strict_ci{ci}_wi{wi}.json"
                if os.path.exists(fname):
                    with open(fname) as f:
                        results.append(json.load(f))
        
        # 按 candidate 聚合
        by_cand = defaultdict(list)
        for r in results:
            by_cand[r['candidate']].append(r)
        
        summary = {}
        for name, ress in by_cand.items():
            avg_ret = sum(r['return'] for r in ress) / len(ress) if ress else 0
            avg_bench = sum(r['benchmark'] for r in ress) / len(ress) if ress else 0
            beats = sum(1 for r in ress if r['return'] > r['benchmark'])
            summary[name] = {
                "avg_return": avg_ret,
                "avg_benchmark": avg_bench,
                "beats_count": beats,
                "total_windows": len(ress),
                "win_rate_vsbench": beats / len(ress) if ress else 0,
                "avg_trades": sum(r['trades'] for r in ress) / len(ress) if ress else 0,
            }
        
        # 选最佳 (只看 avg_return)
        best_name = max(summary.keys(), key=lambda k: summary[k]['avg_return'])
        best_ci = [c[0] for c in CANDIDATES].index(best_name)
        
        out = {
            "phase": "train_selection",
            "summary": summary,
            "best_candidate": best_name,
            "best_ci": best_ci,
            "selection_metric": "avg_return_on_train_windows",
        }
        with open("strict_train_selection.json", "w") as f:
            json.dump(out, f, indent=2)
        print(f"[SELECT] Best on TRAIN: {best_name} (ci={best_ci})")
        for name, s in sorted(summary.items(), key=lambda x: -x[1]['avg_return']):
            print(f"  {name}: +{s['avg_return']:.3f}% (bench {s['avg_benchmark']:+.3f}%) beats={s['beats_count']}/{s['total_windows']}")
    
    elif mode == "aggregate_test":
        # 收集测试集结果
        results = []
        for fname in os.listdir('.'):
            if fname.startswith("strict_test_") and fname.endswith(".json"):
                with open(fname) as f:
                    results.append(json.load(f))
        
        if not results:
            print("[TEST_AGG] No test results found!")
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
                "avg_return": avg_ret,
                "avg_benchmark": avg_bench,
                "beats_count": beats,
                "total_windows": len(ress),
                "win_rate_vsbench": beats / len(ress) if ress else 0,
                "avg_trades": sum(r['trades'] for r in ress) / len(ress) if ress else 0,
                "avg_fees": sum(r['fees'] for r in ress) / len(ress) if ress else 0,
                "avg_max_dd": sum(r['max_dd'] for r in ress) / len(ress) if ress else 0,
                "details": ress,
            }
        
        out = {
            "phase": "test_evaluation",
            "note": "THIS IS THE FINAL RESULT — OUT-OF-SAMPLE, NO CHEATING",
            "summary": summary,
        }
        with open("strict_test_evaluation.json", "w") as f:
            json.dump(out, f, indent=2)
        
        print("\n" + "="*60)
        print("STRICT OOS — FINAL OUT-OF-SAMPLE RESULT")
        print("="*60)
        for name, s in sorted(summary.items(), key=lambda x: -x[1]['avg_return']):
            status = "✅ BEAT" if s['avg_return'] > s['avg_benchmark'] else "❌ LOSE"
            print(f"{name}: +{s['avg_return']:.3f}%/q vs CSI300 {s['avg_benchmark']:+.3f}%/q [{status}] beats {s['beats_count']}/{s['total_windows']}")
    
    else:
        print("Usage: python exp_strict_oos.py [run_train|run_test|aggregate_train|aggregate_test] [ci] [wi]")


if __name__ == "__main__":
    main()
