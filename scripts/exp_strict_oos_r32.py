#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R32 严格 OOS — 仓位收紧 + smart_money 共识活跃门控 (user-directions 1+4)
========================================================================
R24-R31 结论: WIDE 配置(修饰符, boost0.6/0.4/0.2, 回调-15~-2%, amount top3) 是甜点 (~+0.86%),
  10 个信号内部/组合维度全验证到头 (~+0.86% CAGR).

用户反馈: 16% CAGR 太低 (宽基 ETF 也差不多), 需要实质提升.
R32 方向 (用户的 #1 + #4):
  ① 仓位收紧: max_holdings 12→4/6 — 只持有 top 4/6 只基金, 信号更集中, alpha 更浓缩
  ④ 活跃门控: 引擎新增 sm_active_gate — 统计窗口内 max net_buy 净买人数 + 合格基金数,
     双低 → 该窗口大佬集体失声 → 全仓货基 (0% 窗口收益, 无交易), 避免低共识弱窗"空转"

候选:
  ci0: BASELINE (R21)
  ci1: WIDE_NARROW4    max_holdings=4, WIDE 修饰符, 无 gate — 纯收紧测试
  ci2: WIDE_NARROW4_GATE  max_holdings=4 + 活跃门控(窗口级, min 3只合格 + max nb>=5)
  ci3: WIDE_NARROW6_GATE  max_holdings=6 + 活跃门控 — 适度收紧 + gate
全部基于 amount top3 信号 + WIDE sm_params. BASELINE(ci0) 复用 R21 ci0.
引擎改动: backtest.py R32 共识门控 + continue-loop 关闭.
========================================================================
"""
import sys, copy, json, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

ROUND = 32
OUT_TAG = "r32"

WTS_EQUAL = {"quality": 33, "cost": 33, "momentum": 34, "smart_money": 0}
WTS_BULL = {"quality": 22, "cost": 22, "momentum": 56, "smart_money": 0}
WTS_BEAR = {"quality": 40, "cost": 30, "momentum": 30, "smart_money": 0}
WTS_MOD = {"quality": 33, "cost": 33, "momentum": 34, "smart_money": 0}
WTS_MOD_BULL = {"quality": 22, "cost": 22, "momentum": 56, "smart_money": 0}
WTS_MOD_BEAR = {"quality": 40, "cost": 30, "momentum": 30, "smart_money": 0}

WIDE_SM = {"cb_lo": -15, "cb_hi": -2, "nb_hi": 5, "nb_mid": 3, "nb_lo": 3,
           "tg_hi": 4, "tg_mid": 2, "boost_hi": 0.6, "boost_mid": 0.4, "boost_lo": 0.2}

SM_ACTIVE_GATE = {"min_qualified_funds": 3, "min_max_nb": 5}

def _wide_cfg(max_holdings, with_gate=False):
    return {
        "max_holdings": max_holdings,
        "weights": WTS_MOD,
        "weights_bull": WTS_MOD_BULL,
        "weights_bear": WTS_MOD_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": True,
        "use_prebuilt_signal": True,
        "smart_money_modifier": True,
        "consensus_layers": True,
        "signal_line": "amount",
        "sm_params": WIDE_SM,
        **({"sm_active_gate": SM_ACTIVE_GATE} if with_gate else {}),
    }

CANDIDATES = [
    ("KC_AGGRESSIVE_BASELINE", {
        "max_holdings": 12,
        "weights": WTS_EQUAL, "weights_bull": WTS_BULL, "weights_bear": WTS_BEAR,
        "kelly_cap_bull": 0.7, "kelly_cap_bear": 0.40, "no_stop_loss": True,
    }),
    ("KC_WIDE_NARROW4",       _wide_cfg(4, False)),
    ("KC_WIDE_NARROW4_GATE",  _wide_cfg(4, True)),
    ("KC_WIDE_NARROW6_GATE",  _wide_cfg(6, True)),
]

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
    ALL_WINDOWS.append({"train_end": train_end.strftime("%Y-%m-%d"), "test_end": test_end.strftime("%Y-%m-%d")})
    idx += 1

TRAIN_WINDOWS = ALL_WINDOWS[:21]
TEST_WINDOWS = ALL_WINDOWS[21:]
print(f"[R{ROUND}] Total windows: {len(ALL_WINDOWS)} ({len(TRAIN_WINDOWS)} train / {len(TEST_WINDOWS)} test)")

BASE_CFG = {
    "initial_cash": 10000, "no_stop_loss": True, "take_profit_pct": 50.0,
    "min_consensus": 3, "max_holdings": 5, "kelly_cap_bull": 0.5, "kelly_cap_bear": 0.25,
    "pyramiding_enabled": False, "smart_swap": True, "regime_specific": True,
}

def window_range(wi):
    return (ALL_WINDOWS[wi]["train_end"], ALL_WINDOWS[wi]["test_end"]) if 0 <= wi < len(ALL_WINDOWS) else (None, None)

def _run_one(ci, wi_global):
    train_end, test_end = window_range(wi_global)
    cfg = copy.deepcopy(BASE_CFG)
    cfg.update(CANDIDATES[ci][1])
    cfg['start_date'] = train_end
    cfg['end_date'] = test_end
    res = run_backtest(cfg, clear_cache=True)
    return {
        "phase": "test" if wi_global >= len(TRAIN_WINDOWS) else "train",
        "round": ROUND, "candidate": CANDIDATES[ci][0], "ci": ci,
        "wi": wi_global - len(TRAIN_WINDOWS) if wi_global >= len(TRAIN_WINDOWS) else wi_global,
        "period": f"{train_end}~{test_end}",
        "return": res.get("total_return", 0), "trades": res.get("trade_count", 0),
        "fees": res.get("total_fees", 0), "max_dd": res.get("max_drawdown", 0),
        "benchmark": res.get("benchmark_return", 0), "win_rate": res.get("win_rate", 0),
    }

def _load_r21_baseline():
    import glob
    rows = []
    for f in sorted(glob.glob("strict_test_ci0_wi*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        d = dict(d); d["candidate"] = "KC_AGGRESSIVE_BASELINE"; d["ci"] = 0; d["round"] = ROUND
        rows.append(d)
    return rows

def aggregate_test():
    import glob
    results, seen = [], set()
    for f in sorted(glob.glob(f"strict_test_{OUT_TAG}_ci*.json")):
        if f in seen: continue
        seen.add(f)
        try: results.append(json.load(open(f)))
        except Exception: pass
    results.extend(_load_r21_baseline())

    print(f"\n[aggregate_test] Found {len(results)} results", flush=True)
    if not results:
        print(f"No R{ROUND} test results found!", flush=True); sys.exit(1)

    by_cand = defaultdict(list)
    for r in results:
        by_cand[r["candidate"]].append(r)

    summary = {}
    for name, items in by_cand.items():
        avg_ret = sum(x["return"] for x in items) / len(items)
        summary[name] = {
            "avg_return": avg_ret,
            "avg_benchmark": sum(x["benchmark"] for x in items) / len(items),
            "avg_max_drawdown": sum(x["max_dd"] for x in items) / len(items),
            "peak_max_dd": max(x["max_dd"] for x in items),
            "beats_count": sum(1 for x in items if x["return"] > x["benchmark"]),
            "beats_rate": sum(1 for x in items if x["return"] > x["benchmark"]) / len(items),
            "count": len(items),
            "per_window": [{"period": x["period"], "return": x["return"], "benchmark": x["benchmark"], "max_dd": x["max_dd"]}
                           for x in sorted(items, key=lambda x: x["period"])],
        }

    os.makedirs("v9-results", exist_ok=True)
    with open(f"v9-results/strict_oos_r{ROUND}_eval.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}\n=== R{ROUND} OOS Eval ({len(TEST_WINDOWS)} windows) ===\n{'='*70}")
    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        alpha = s["avg_return"] - summary["KC_AGGRESSIVE_BASELINE"]["avg_return"] if "KC_AGGRESSIVE_BASELINE" in summary else 0
        print(f"  {name:28s}: avg {s['avg_return']:>+8.3f}%  alpha {alpha:>+7.3f}%  maxdd {s['avg_max_drawdown']:>5.2f}%  beats {s['beats_count']}/{s['count']}")

    base_periods = {x["period"]: x["return"] for x in by_cand.get("KC_AGGRESSIVE_BASELINE", [])}
    for name, items in by_cand.items():
        if name == "KC_AGGRESSIVE_BASELINE": continue
        print(f"\n--- {name} vs BASELINE ---")
        for x in sorted(items, key=lambda x: x["period"]):
            b = base_periods.get(x["period"], 0)
            print(f"  {x['period']:<26}{x['return']:>+10.3f}%  base {b:>+9.3f}%  diff {x['return']-b:>+7.3f}%")
    return summary

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python exp_strict_oos_r{ROUND}.py <test|run>"); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "test":
        aggregate_test()
    elif cmd == "run" and len(sys.argv) == 4:
        ci, wi = int(sys.argv[2]), int(sys.argv[3])
        r = _run_one(ci, wi)
        out_name = f"strict_test_{OUT_TAG}_ci{ci}_wi{wi}.json"
        with open(out_name, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"Saved: {out_name}\n  Return: {r['return']:.3f}%  Bench: {r['benchmark']:+.3f}%  MaxDD: {r['max_dd']:.3f}%  Trades: {r['trades']}")
    else:
        print(f"Unknown cmd: {cmd}"); sys.exit(1)
