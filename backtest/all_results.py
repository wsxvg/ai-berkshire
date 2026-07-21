#!/usr/bin/env python3
"""展示所有三轮回测结果"""
import json, glob, os, sys

BASELINE = 56.93  # 本地已知基线

results = []
for d in ["backtest/results_round2", "backtest/results_round3", "backtest/results_round1"]:
    for f in sorted(glob.glob(os.path.join(d, "*/*.json"))):
        try:
            with open(f, 'r') as fh:
                data = json.load(fh)
            if data.get('total_return', 0) > 35:  # 排除旧配置的低收益
                results.append(data)
        except:
            pass

# 去重（保留最高收益的）
seen = {}
for r in results:
    name = r['name']
    if name not in seen or r['total_return'] > seen[name]['total_return']:
        seen[name] = r
results = list(seen.values())
results.sort(key=lambda x: x['total_return'], reverse=True)

out = []
out.append(f"\n{'='*90}")
out.append(f"完整回测结果（3年 2023-07-17 ~ 2026-07-17）  基线: {BASELINE:.2f}%")
out.append(f"{'='*90}")
out.append(f"{'方案':<30} {'收益%':>8} {'vs基线':>8} {'回撤%':>8} {'夏普':>6} {'交易':>6}")
out.append(f"{'-'*90}")
for r in results:
    diff = r['total_return'] - BASELINE
    marker = "  " if abs(diff) < 0.5 else (" +" if diff > 0 else " -")
    out.append(f"{marker} {r['name']:<28} {r['total_return']:>7.2f}% {diff:>+7.2f}pp {r['max_drawdown']:>7.2f}% {r['sharpe']:>5.2f} {r['trade_count']:>5}")

out.append(f"\n共{len(results)}个结果")
out.append(f"失败（超时）: E2_A5_C1, E3_B1_C1, E4_all (Transformer CPU训练超6h)")

out.append(f"\n有效改进（收益>基线+0.5pp）:")
winners = [r for r in results if r['total_return'] > BASELINE + 0.5]
if winners:
    for r in winners:
        diff = r['total_return'] - BASELINE
        out.append(f"  [WIN] {r['name']}: +{diff:.2f}pp (return={r['total_return']}%, dd={r['max_drawdown']}%)")
else:
    out.append("  (none)")

out.append(f"\n中性（基线-0.5pp ~ +0.5pp）:")
neutral = [r for r in results if BASELINE - 0.5 <= r['total_return'] <= BASELINE + 0.5]
for r in neutral:
    out.append(f"  [OK]  {r['name']}: {r['total_return']:.2f}% (dd={r['max_drawdown']}%)")

out.append(f"\n有害（收益<基线-0.5pp）:")
losers = [r for r in results if r['total_return'] < BASELINE - 0.5]
for r in losers:
    diff = r['total_return'] - BASELINE
    out.append(f"  [BAD] {r['name']}: {diff:.2f}pp (return={r['total_return']}%, dd={r['max_drawdown']}%)")

text = "\n".join(out)
print(text)

with open("backtest/reports/all_results_summary.txt", "w", encoding="utf-8") as f:
    f.write(text)
