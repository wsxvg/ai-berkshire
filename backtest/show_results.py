#!/usr/bin/env python3
"""读取已下载的回测结果并生成对比表"""
import json, glob, os

results = []
for f in sorted(glob.glob('backtest/results_round1/*/*.json')):
    with open(f, 'r') as fh:
        results.append(json.load(fh))

results.sort(key=lambda x: x['total_return'], reverse=True)
baseline = next((r['total_return'] for r in results if r['name'] == 'baseline'), 56.93)

print(f"\n{'='*85}")
print(f"第一轮回测结果（3年 2023-07-17 ~ 2026-07-17）  基线: {baseline}%")
print(f"{'='*85}")
print(f"{'方案':<35} {'收益%':>8} {'vs基线':>8} {'回撤%':>8} {'夏普':>6} {'交易':>6}")
print(f"{'-'*85}")
for r in results:
    diff = r['total_return'] - baseline
    marker = "  " if abs(diff) < 0.5 else ("+ " if diff > 0 else "- ")
    print(f"{marker}{r['name']:<33} {r['total_return']:>7.2f}% {diff:>+7.2f}pp {r['max_drawdown']:>7.2f}% {r['sharpe']:>5.2f} {r['trade_count']:>5}")

print(f"\n共{len(results)}个测试结果（C1/C2 Transformer结果缺失）")
print(f"\n有效改进（收益>基线）:")
winners = [r for r in results if r['total_return'] > baseline + 0.5]
for r in winners:
    diff = r['total_return'] - baseline
    print(f"  ✅ {r['name']}: +{diff:.2f}pp (收益{r['total_return']}%, 回撤{r['max_drawdown']}%)")

print(f"\n无效或有害（收益<基线）:")
losers = [r for r in results if r['total_return'] < baseline - 0.5]
for r in losers:
    diff = r['total_return'] - baseline
    print(f"  ❌ {r['name']}: {diff:.2f}pp (收益{r['total_return']}%, 回撤{r['max_drawdown']}%)")
