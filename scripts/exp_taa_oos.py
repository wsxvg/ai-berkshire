#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R34 TAA OOS — Tactical Asset Allocation 宽基配置
===================================================
候选策略:
  ci0: Equal-Weight 13-asset (买入持有均等)
  ci1: TAA momentum top-K=4 (月度再平衡)
  ci2: TAA momentum top-K=3 (更集中)
  ci3: TAA momentum top-K=5 + bear defense (股票牛熊择时)

Walk-forward: 同 R21/R33 框架，43 窗 (21 train / 22 test)
"""
import sys, copy, json, os, glob, time
from collections import defaultdict

sys.path.insert(0, '.')
from backtest.engine.alloc_backtest import load_navseries, run_taa_backtest, dates_aligned

ROUND = 34
OUT_TAG = "taa"

# 加载数据
t0 = time.time()
nav, meta, bm_series = load_navseries()
print(f"[R{ROUND}] Loaded {len(nav)} assets in {time.time()-t0:.1f}s", flush=True)

ALL_WINDOWS = []
base_start = __import__('datetime').datetime(2013, 1, 1)
base_end = __import__('datetime').datetime(2026, 9, 30)
idx = 0
while True:
    current = base_start + __import__('datetime').timedelta(days=60 * idx)
    train_end = current + __import__('datetime').timedelta(days=180)
    test_end = current + __import__('datetime').timedelta(days=270)
    if test_end > base_end:
        break
    ALL_WINDOWS.append({
        "train_end": train_end.strftime("%Y-%m-%d"),
        "test_end": test_end.strftime("%Y-%m-%d"),
    })
    idx += 1

TRAIN_WINDOWS = ALL_WINDOWS[:21]
TEST_WINDOWS = ALL_WINDOWS[21:]
print(f"[R{ROUND}] Windows: {len(ALL_WINDOWS)} ({len(TRAIN_WINDOWS)} train / {len(TEST_WINDOWS)} test)", flush=True)

def _run_one(ci, wi_global):
    train_end, test_end = ALL_WINDOWS[wi_global]["train_end"], ALL_WINDOWS[wi_global]["test_end"]
    train_start = ALL_WINDOWS[max(0, wi_global-21)]["train_end"]
    
    if ci == 0:
        # Equal-weight buy & hold all 13 assets → mimic with top_k=13
        res = run_taa_backtest(nav, meta, bm_series, train_end, test_end,
                               rebalance_days=99999, top_k=13, bear_max_equity=999)
    elif ci == 1:
        res = run_taa_backtest(nav, meta, bm_series, train_end, test_end,
                               rebalance_days=21, top_k=4, bear_max_equity=0)
    elif ci == 2:
        res = run_taa_backtest(nav, meta, bm_series, train_end, test_end,
                               rebalance_days=21, top_k=3, bear_max_equity=0)
    elif ci == 3:
        res = run_taa_backtest(nav, meta, bm_series, train_end, test_end,
                               rebalance_days=21, top_k=5, bear_max_equity=0)
    
    if res is None:
        return None
    return {
        "phase": "test" if wi_global >= len(TRAIN_WINDOWS) else "train",
        "round": ROUND,
        "candidate": ["C_EQW13","C_TAA_K4","C_TAA_K3","C_TAA_K5"][ci],
        "ci": ci,
        "wi": wi_global - len(TRAIN_WINDOWS) if wi_global >= len(TRAIN_WINDOWS) else wi_global,
        "period": res["period"],
        "return": res["return"],
        "ann_return": res["ann_return"],
        "max_dd": res["max_drawdown"],
        "benchmark": res["benchmark"],
    }

def _full_span_cagr(ci, span_start="2016-12-12", span_end="2026-08-07"):
    if ci == 0:
        res = run_taa_backtest(nav, meta, bm_series, span_start, span_end,
                               rebalance_days=99999, top_k=13, bear_max_equity=999)
    elif ci == 1:
        res = run_taa_backtest(nav, meta, bm_series, span_start, span_end,
                               rebalance_days=21, top_k=4, bear_max_equity=0)
    elif ci == 2:
        res = run_taa_backtest(nav, meta, bm_series, span_start, span_end,
                               rebalance_days=21, top_k=3, bear_max_equity=0)
    elif ci == 3:
        res = run_taa_backtest(nav, meta, bm_series, span_start, span_end,
                               rebalance_days=21, top_k=5, bear_max_equity=0)
    if res is None:
        return None
    from datetime import datetime
    d = (datetime.strptime(span_end, "%Y-%m-%d") - datetime.strptime(span_start, "%Y-%m-%d")).days
    yrs = d / 365.25
    cagr = ((res["final_value"] / 10000) ** (1/yrs) - 1) * 100
    return {
        "total_return": res["return"],
        "cagr": round(cagr, 2),
        "final_value": res["final_value"],
        "peak_mdd": res["max_drawdown"],
        "years": round(yrs, 2),
    }


def aggregate_test():
    results = []
    seen = set()
    for f in sorted(glob.glob(f"strict_test_{OUT_TAG}_ci*.json")):
        if f in seen: continue
        seen.add(f)
        try:
            results.append(json.load(open(f)))
        except: pass
    
    if not results:
        print(f"No R{FOUND if False else ROUND} results!", flush=True)
        sys.exit(1)
    
    ci_map = {"C_EQW13": 0, "C_TAA_K4": 1, "C_TAA_K3": 2, "C_TAA_K5": 3}
    by_candidate = defaultdict(list)
    for r in results:
        by_candidate[r["candidate"]].append(r)
    
    summary = {}
    for name, items in by_candidate.items():
        n = len(items)
        avg_r = sum(x["return"] for x in items) / n
        avg_ann = sum(x["ann_return"] for x in items) / n
        avg_b = sum(x["benchmark"] for x in items) / n
        avg_dd = sum(x["max_dd"] for x in items) / n
        peak_dd = max(x["max_dd"] for x in items)
        beats = sum(1 for x in items if x["return"] > x["benchmark"])
        
        # Full-span CAGR (true annualized)
        ci = ci_map.get(name, 0)
        fs = _full_span_cagr(ci)
        
        summary[name] = {
            "avg_return": avg_r,
            "avg_ann_return_per_window": avg_ann,
            "full_span": fs,
            "avg_benchmark": avg_b,
            "avg_mdd": avg_dd,
            "peak_mdd": peak_dd,
            "beats": beats,
            "beats_rate": beats / n,
            "count": n,
            "per_window": [{"period": x["period"], "return": x["return"],
                           "benchmark": x["benchmark"], "max_dd": x["max_dd"]}
                          for x in sorted(items, key=lambda x: x["period"])],
        }
    
    os.makedirs("v9-results", exist_ok=True)
    with open(f"v9-results/strict_oos_{OUT_TAG}_eval.json","w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*95}")
    print(f"=== R{ROUND} TAA OOS ({len(TEST_WINDOWS)} test windows, walk-forward + full-span) ===")
    print(f"{'='*95}")
    print(f"  (avg/w = per-window arithmetic mean; CAGR = true compounded annualized over full span)\n")
    for name, s in sorted(summary.items(), key=lambda x: -(x[1]["full_span"]["cagr"] if x[1]["full_span"] else 0)):
        fs = s["full_span"]
        alpha = 0
        # best baseline = highest full-span CAGR (likely EQW13)
        best_base = max((v["full_span"]["cagr"] if v["full_span"] else 0) for v in summary.values())
        alpha = (fs["cagr"] if fs else 0) - best_base
        marker = f"  ({alpha:+.2f}% CAGR vs BEST)" if alpha != 0 else "  (BEST CAGR)"
        cagr_str = f"CAGR={fs['cagr']:+.2f}%" if fs else "CAGR=N/A"
        total_str = f"total={fs['total_return']:+.1f}%" if fs else ""
        print(f"  {name:14s}: avg/w {s['avg_return']:+.2f}%  {cagr_str}  {total_str}  "
              f"mdd_avg {s['avg_mdd']:.1f}%  peak {s['peak_mdd']:.1f}%  beats {s['beats']}/{s['count']}{marker}")
    
    # Benchmark full-span
    bm_fs = _full_span_cagr(0)  # dummy, compute CSI300 directly
    bm_start = sorted(bm_series.keys())[0]
    bm_end = sorted(bm_series.keys())[-1]
    # actually benchmark doesn't need nav, just use idx
    bms = [d for d in sorted(bm_series.keys()) if "2016-12-12" <= d <= "2026-08-07"]
    if len(bms) >= 2:
        btotal = (bm_series[bms[-1]] / bm_series[bms[0]] - 1) * 100
        byrs = 9.65
        bcagr = ((1 + btotal/100) ** (1/byrs) - 1) * 100
        print(f"  {'CSI300':14s}: {'':12s} CAGR={bcagr:+.2f}%  total={btotal:+.1f}%")
    
    return summary

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"usage: python exp_taa_oos_<test|run>")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "test":
        aggregate_test()
    elif cmd == "run" and len(sys.argv) == 4:
        ci, wi = int(sys.argv[2]), int(sys.argv[3])
        t0 = time.time()
        r = _run_one(ci, wi)
        dt = time.time() - t0
        if r is None:
            print(f"ci{ci} wi{wi}: SKIPPED ({dt:.1f}s)", flush=True)
        else:
            with open(f"strict_test_{OUT_TAG}_ci{ci}_wi{wi}.json","w") as f:
                json.dump(r, f, ensure_ascii=False, indent=2)
            print(f"ci{ci} wi{wi}: {r['return']:+.3f}%  bench {r['benchmark']:+.3f}%  dd {r['max_dd']:.2f}%  ({dt:.1f}s)", flush=True)
