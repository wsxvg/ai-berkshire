#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, glob, sys
BASELINE = 56.93
results = []
for f in sorted(glob.glob("backtest/results_round6/*/*.json")):
    with open(f, "r") as fh:
        results.append(json.load(fh))
results.sort(key=lambda x: x["total_return"], reverse=True)
out = []
out.append(f"Matrix 6 results (baseline={BASELINE}%)")
out.append("-" * 85)
for r in results:
    d = r["total_return"] - BASELINE
    m = "  " if abs(d) < 0.5 else (" +" if d > 0 else " -")
    out.append(f"{m} {r['name']:<28} {r['total_return']:>7.2f}% {d:>+7.2f}pp dd={r['max_drawdown']:>5.1f}% sh={r['sharpe']:.2f} trades={r['trade_count']}")
out.append("-" * 85)
out.append(f"Total: {len(results)} results (V-series LGB failed)")
text = "\n".join(out)
sys.stdout.buffer.write(text.encode("utf-8"))
sys.stdout.buffer.write(b"\n")
