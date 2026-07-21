#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""展示S系列卖出优化结果"""
import json, glob, os, sys

BASELINE = 56.93

results = []
for f in sorted(glob.glob("backtest/results_round4/*/*.json")):
    with open(f, "r") as fh:
        results.append(json.load(fh))

results.sort(key=lambda x: x["total_return"], reverse=True)

out = []
out.append("")
out.append("=" * 90)
out.append(f"S系列卖出优化结果（3年 2023-07-17 ~ 2026-07-17）  基线: {BASELINE:.2f}%")
out.append("=" * 90)
out.append(f"{'方案':<30} {'收益%':>8} {'vs基线':>8} {'回撤%':>8} {'夏普':>6} {'交易':>6}")
out.append("-" * 90)
for r in results:
    diff = r["total_return"] - BASELINE
    marker = "  " if abs(diff) < 0.5 else (" +" if diff > 0 else " -")
    out.append(f"{marker} {r['name']:<28} {r['total_return']:>7.2f}% {diff:>+7.2f}pp {r['max_drawdown']:>7.2f}% {r['sharpe']:>5.2f} {r['trade_count']:>5}")

out.append(f"\n共{len(results)}个结果")

out.append("\n有效改进（收益>基线+0.5pp）:")
winners = [r for r in results if r["total_return"] > BASELINE + 0.5]
if winners:
    for r in winners:
        diff = r["total_return"] - BASELINE
        out.append(f"  [WIN] {r['name']}: +{diff:.2f}pp (return={r['total_return']:.2f}%, dd={r['max_drawdown']:.2f}%, sharpe={r['sharpe']:.2f})")
else:
    out.append("  (none)")

out.append("\n中性（基线-0.5pp ~ +0.5pp）:")
neutral = [r for r in results if BASELINE - 0.5 <= r["total_return"] <= BASELINE + 0.5]
for r in neutral:
    out.append(f"  [OK]  {r['name']}: {r['total_return']:.2f}% (dd={r['max_drawdown']:.2f}%, sharpe={r['sharpe']:.2f})")

out.append("\n有害（收益<基线-0.5pp）:")
losers = [r for r in results if r["total_return"] < BASELINE - 0.5]
for r in losers:
    diff = r["total_return"] - BASELINE
    out.append(f"  [BAD] {r['name']}: {diff:.2f}pp (return={r['total_return']:.2f}%, dd={r['max_drawdown']:.2f}%, trades={r['trade_count']})")

text = "\n".join(out)
sys.stdout.buffer.write(text.encode("utf-8"))
sys.stdout.buffer.write(b"\n")
