#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R30 严格 OOS — 降低净买入共识门槛 (nb_lo: 低共识信号价值)
================================================================
R24-R29 结论: WIDE配置(回调-15~-2% + amount top3 + boost0.6/0.4/0.2)是信号甜点位,
  回调窗口/boost/线路/topN/动量门控/信号有效期/回调深度 7 维度全验证到头 (最优 ~+0.86%)。
R30 目标: R24 HICONS 提高 nb 门槛(7/5/3) → +0.12% 更差, 强烈暗示**低共识方向有空间**
  (R24 结论"信号越多越有效, 卡太严错过 alpha")。当前 boost 三档 nb 门槛为 5/3/3,
  **没有一档接受 nb<3**。R30 引擎加 nb_lo 参数(boost_lo 净买入门槛, 默认3), 测低门槛:
  ci1: nb_lo=1        → 只要 1 个大佬买 + tg>=2 + 回调达标 就给 boost_lo(0.2)
  ci2: nb_lo=2        → 2 个大佬买
  ci3: nb_lo=1 + boost_lo=0.3 → 低共识但基础 boost 提高
全部基于 WIDE 最优配置 + amount top3 信号。BASELINE(ci0) 复用 R21 strict_test_ci0_wi*.json;
对照 = R24 WIDE(nb_lo=3, boost_lo=0.2) +0.859%。引擎改动见 backtest/engine/backtest.py 的 nb_lo。
========================================================================
"""
import sys, copy, json, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

ROUND = 30
OUT_TAG = "r30"

# ─── 权重方案 (同 R23-R29) ───
WTS_EQUAL = {"quality": 33, "cost": 33, "momentum": 34, "smart_money": 0}
WTS_BULL = {"quality": 22, "cost": 22, "momentum": 56, "smart_money": 0}
WTS_BEAR = {"quality": 40, "cost": 30, "momentum": 30, "smart_money": 0}
WTS_MOD = {"quality": 33, "cost": 33, "momentum": 34, "smart_money": 0}
WTS_MOD_BULL = {"quality": 22, "cost": 22, "momentum": 56, "smart_money": 0}
WTS_MOD_BEAR = {"quality": 40, "cost": 30, "momentum": 30, "smart_money": 0}

# WIDE 最优配置 (R24-R29 获胜)
WIDE_SM = {"cb_lo": -15, "cb_hi": -2, "nb_hi": 5, "nb_mid": 3,
           "tg_hi": 4, "tg_mid": 2, "boost_hi": 0.6, "boost_mid": 0.4, "boost_lo": 0.2}

def _wide_cfg(nb_lo, boost_lo=0.2):
    return {
        "max_holdings": 12,
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
        "sm_params": {**WIDE_SM, "nb_lo": nb_lo, "boost_lo": boost_lo},
    }

CANDIDATES = [
    # ci0: BASELINE (复用 R21 ci0)
    ("KC_AGGRESSIVE_BASELINE", {
        "max_holdings": 12,
        "weights": WTS_EQUAL,
        "weights_bull": WTS_BULL,
        "weights_bear": WTS_BEAR,
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": True,
    }),
    # ci1: WIDE + nb_lo=1 (只要1个大佬买就给boost_lo)
    ("KC_WIDE_NBLO1", _wide_cfg(nb_lo=1)),
    # ci2: WIDE + nb_lo=2
    ("KC_WIDE_NBLO2", _wide_cfg(nb_lo=2)),
    # ci3: WIDE + nb_lo=1 + boost_lo=0.3 (低共识但boost提高)
    ("KC_WIDE_NBLO1_BOOST", _wide_cfg(nb_lo=1, boost_lo=0.3)),
]

# ─── 时间窗口 (同 R21-R29) ───
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


def _load_r21_baseline():
    import glob
    rows = []
    for f in sorted(glob.glob("strict_test_ci0_wi*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        d = dict(d)
        d["candidate"] = "KC_AGGRESSIVE_BASELINE"
        d["ci"] = 0
        d["round"] = ROUND
        rows.append(d)
    return rows


def aggregate_test():
    import glob
    results = []
    seen = set()
    for f in sorted(glob.glob(f"strict_test_{OUT_TAG}_ci*.json")):
        if f in seen:
            continue
        seen.add(f)
        try:
            results.append(json.load(open(f)))
        except Exception:
            pass
    results.extend(_load_r21_baseline())

    print(f"[aggregate_test] Found {len(results)} results", flush=True)
    if not results:
        print(f"No R{ROUND} test results found!", flush=True)
        sys.exit(1)

    by_candidate = defaultdict(list)
    for r in results:
        by_candidate[r["candidate"]].append(r)

    print(f"\n{'='*70}")
    print(f"=== R{ROUND} OOS Evaluation ({len(TEST_WINDOWS)} test windows) ===")
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

    os.makedirs("v9-results", exist_ok=True)
    with open(f"v9-results/strict_oos_r{ROUND}_eval.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    for name, s in sorted(summary.items(), key=lambda x: -x[1]["avg_return"]):
        marker = ""
        if name != "KC_AGGRESSIVE_BASELINE" and "KC_AGGRESSIVE_BASELINE" in summary:
            diff = s["avg_return"] - summary["KC_AGGRESSIVE_BASELINE"]["avg_return"]
            marker = f"  ({diff:+.3f}% vs BASELINE)"
        print(f"  {name:28s}: avg {s['avg_return']:8.3f}%  maxdd {s['avg_max_drawdown']:5.2f}%  peak {s['peak_max_dd']:5.2f}%  beats {s['beats_count']}/{s['count']}{marker}")

    base_periods = {x["period"]: x["return"] for x in by_candidate.get("KC_AGGRESSIVE_BASELINE", [])}
    for name, items in by_candidate.items():
        if name == "KC_AGGRESSIVE_BASELINE":
            continue
        print(f"\n--- {name} vs BASELINE (逐窗口) ---")
        print(f"{'period':<26}{'candidate':>12}{'baseline':>12}{'diff':>10}")
        for x in sorted(items, key=lambda x: x["period"]):
            b = base_periods.get(x["period"])
            d = (x["return"] - b) if b is not None else None
            dstr = f"{d:+.3f}%" if d is not None else "  n/a"
            print(f"{x['period']:<26}{x['return']:>11.3f}%{(b if b is not None else 0):>11.3f}%{dstr:>10}")
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python exp_strict_oos_r{ROUND}.py <test|run>")
        print(f"  run <ci> <wi>: 跑单个窗口 (ci=1 nb_lo=1, ci=2 nb_lo=2, ci=3 nb_lo=1+boost0.3)")
        print("  test: 聚合 (自动读 R21 BASELINE + R30 候选)")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "test":
        aggregate_test()
    elif cmd == "run" and len(sys.argv) == 4:
        ci, wi = int(sys.argv[2]), int(sys.argv[3])
        r = _run_one(ci, wi)
        out_name = f"strict_test_{OUT_TAG}_ci{ci}_wi{wi}.json"
        with open(out_name, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"Saved: {out_name}")
        print(f"  Return: {r['return']:.3f}%  Bench: {r['benchmark']:+.3f}%  MaxDD: {r['max_dd']:.3f}%")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)