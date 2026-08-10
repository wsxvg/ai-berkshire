#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R31 严格 OOS — smart_money 作为独立维度重测 (非修饰符)
================================================================
R24-R30 结论: WIDE配置(回调-15~-2% + amount top3 + 修饰符boost0.6/0.4/0.2)是信号甜点位,
  回调窗口/boost/线路/topN/动量门控/信号有效期/回调深度/共识门槛 8 维度全验证到头 (~+0.86%)。
R31 初案(nb 连续值映射)已证伪: 3候选在 wi26/30/36 全部与 WIDE 平局, 与 R25 boost量级冗余。
  → 证明 **boost 量级(修饰符强度)不改变组合决策, alpha 来自"选哪些基金"而非"加权多强"**。

R31 转向: smart_money 作为**独立维度**(带权重直接参与 4D 加权)重测。
  自 R23 修复 look-ahead bug 后, smart_money 只测过"修饰符"形式(加减分, w_sm=0);
  "独立维度"形式(R22 测过但用了被污染的信号)在修复后**从未重测**。
  独立维度让 smart_money 分数与 quality/cost/momentum 直接竞争, 是结构性不同的形式。

  引擎改动(R31): backtest.py 非修饰符分支加 consensus_layers 评分(用 WIDE 阈值给 4.8/4.2/3.6/2.5)。
  候选 (weights 从 momentum/quality 让渡给 smart_money, 保持总和100):
  ci1: SM_IND20   quality26 cost26 momentum28 smart_money20
  ci2: SM_IND30   quality23 cost23 momentum24 smart_money30
  ci3: SM_IND40   quality20 cost20 momentum20 smart_money40  (重仓 smart_money)
全部基于 WIDE 最优配置 + amount top3 信号 + consensus_layers 独立评分。
BASELINE(ci0) 复用 R21 ci0; 对照 = R24 WIDE(修饰符) +0.859%。
========================================================================
"""
import sys, copy, json, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, '.')
from backtest.engine.backtest import run_backtest

ROUND = 31
OUT_TAG = "r31"

# WIDE 最优配置 (R24-R30 获胜)
WIDE_SM = {"cb_lo": -15, "cb_hi": -2, "nb_hi": 5, "nb_mid": 3,
           "tg_hi": 4, "tg_mid": 2, "boost_hi": 0.6, "boost_mid": 0.4, "boost_lo": 0.2,
           "nb_lo": 3}

# 独立维度权重: smart_money 参与 4D 加权 (总和 100)
def _ind_wts(sm_w):
    """从 momentum 与 quality/cost 让渡给 smart_money, 保持总和 100"""
    base_q = max(20, 33 - sm_w // 3)
    base_c = max(20, 33 - sm_w // 3)
    base_mo = 100 - base_q - base_c - sm_w
    return {"quality": base_q, "cost": base_c, "momentum": base_mo, "smart_money": sm_w}

def _ind_cfg(sm_w):
    return {
        "max_holdings": 12,
        "weights": _ind_wts(sm_w),          # 独立维度权重 (smart_money>0)
        "weights_bull": _ind_wts(sm_w),
        "weights_bear": _ind_wts(sm_w),
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": True,
        "use_prebuilt_signal": True,
        "smart_money_modifier": False,      # 关键: 独立维度, 非修饰符
        "consensus_layers": True,           # 用 WIDE 共识阈值给分
        "signal_line": "amount",
        "sm_params": dict(WIDE_SM),
    }

CANDIDATES = [
    # ci0: BASELINE (复用 R21 ci0)
    ("KC_AGGRESSIVE_BASELINE", {
        "max_holdings": 12,
        "weights": {"quality": 33, "cost": 33, "momentum": 34, "smart_money": 0},
        "weights_bull": {"quality": 22, "cost": 22, "momentum": 56, "smart_money": 0},
        "weights_bear": {"quality": 40, "cost": 30, "momentum": 30, "smart_money": 0},
        "kelly_cap_bull": 0.7,
        "kelly_cap_bear": 0.40,
        "no_stop_loss": True,
    }),
    # ci1: smart_money 独立维度 20% (让渡 momentum)
    ("KC_SM_IND20", _ind_cfg(sm_w=20)),
    # ci2: smart_money 独立维度 30%
    ("KC_SM_IND30", _ind_cfg(sm_w=30)),
    # ci3: smart_money 独立维度 40% (重仓)
    ("KC_SM_IND40", _ind_cfg(sm_w=40)),
]

# ─── 时间窗口 (同 R21-R30) ───
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
        print(f"  run <ci> <wi>: 跑单个窗口 (ci=1 SM_IND20, ci=2 SM_IND30, ci=3 SM_IND40)")
        print("  test: 聚合 (自动读 R21 BASELINE + R31 候选)")
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