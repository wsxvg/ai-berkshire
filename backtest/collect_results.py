#!/usr/bin/env python3
"""汇总所有回测结果，生成对比表"""
import json, glob, os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
for f in sorted(glob.glob("backtest/results/*.json")):
    with open(f) as fh:
        results.append(json.load(fh))

results.sort(key=lambda x: x["total_return"], reverse=True)
baseline = next((r["total_return"] for r in results if r["name"] == "baseline"), 56.93)

print(f"\n{'='*80}")
print(f"统一回测最终结果（3年 2023-07-17 ~ 2026-07-17）")
print(f"{'='*80}")
print(f"{'方案':<30} {'收益%':>8} {'vs基线':>8} {'回撤%':>8} {'夏普':>6} {'交易':>6}")
print(f"{'-'*80}")
for r in results:
    diff = r["total_return"] - baseline
    marker = "  " if abs(diff) < 0.5 else ("+ " if diff > 0 else "  ")
    print(f"{marker}{r['name']:<28} {r['total_return']:>7.2f}% {diff:>+7.2f}pp {r['max_drawdown']:>7.2f}% {r['sharpe']:>5.2f} {r['trade_count']:>5}")

output = {"results": results, "baseline": baseline}
os.makedirs("backtest/reports", exist_ok=True)
with open("backtest/reports/unified_backtest_summary.json", "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSummary saved to backtest/reports/unified_backtest_summary.json")
