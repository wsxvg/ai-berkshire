#!/usr/bin/env python3
"""OpenClaw策略融合测试 — 3年完整回测对比

测试5个从OpenClaw指南借鉴的策略改进：
1. 时间止损 (time_stop_days): 持仓满N天且收益不足 → 卖出
2. 组合级回撤熔断 (portfolio_dd_breaker): 总资产回撤>X% → 清仓+暂停
3. RSI超买卖出 (rsi_sell_threshold): RSI>阈值且盈利中 → 部分卖出
4. N日不创新高 (no_new_high_days): 连续N日未创新高 → 卖出
5. 均线死叉卖出 (ma_death_cross_sell): MA5下穿MA20 → 卖出
"""
import sys, json, copy, os, time
from pathlib import Path

os.chdir("c:/fund")
sys.path.insert(0, ".")
from backtest.engine.backtest import run_backtest

BASE_CFG = json.loads(
    open("data/evolution/best_config.json", "r", encoding="utf-8").read()
)["config"]

TESTS = [
    {"name": "baseline", "label": "基线（无OpenClaw策略）", "overrides": {}},
    {"name": "time_stop_120", "label": "时间止损120天+收益<5%", "overrides": {"time_stop_days": 120, "time_stop_min_profit": 5}},
    {"name": "time_stop_90", "label": "时间止损90天+收益<3%", "overrides": {"time_stop_days": 90, "time_stop_min_profit": 3}},
    {"name": "time_stop_180", "label": "时间止损180天+收益<8%", "overrides": {"time_stop_days": 180, "time_stop_min_profit": 8}},
    {"name": "dd_breaker_12", "label": "组合回撤12%熔断+暂停5天", "overrides": {"portfolio_dd_breaker": 12, "portfolio_dd_pause_days": 5}},
    {"name": "dd_breaker_15", "label": "组合回撤15%熔断+暂停5天", "overrides": {"portfolio_dd_breaker": 15, "portfolio_dd_pause_days": 5}},
    {"name": "rsi_sell_80", "label": "RSI>80卖30%", "overrides": {"rsi_sell_threshold": 80, "rsi_sell_pct": 0.3}},
    {"name": "rsi_sell_75", "label": "RSI>75卖20%", "overrides": {"rsi_sell_threshold": 75, "rsi_sell_pct": 0.2}},
    {"name": "no_new_high_20", "label": "20日不创新高卖出", "overrides": {"no_new_high_days": 20}},
    {"name": "no_new_high_15", "label": "15日不创新高卖出", "overrides": {"no_new_high_days": 15}},
    {"name": "ma_cross_sell", "label": "MA5下穿MA20卖出", "overrides": {"ma_death_cross_sell": True}},
]

results = []
for test in TESTS:
    cfg = copy.deepcopy(BASE_CFG)
    cfg.update(test["overrides"])
    cfg["start_date"] = "2023-07-17"
    cfg["end_date"] = "2026-07-17"
    cfg["initial_cash"] = 100000

    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"测试: {test['label']}")
    print(f"{'='*60}")

    r = run_backtest(cfg)
    elapsed = time.time() - t0

    result = {
        "name": test["name"],
        "label": test["label"],
        "overrides": test["overrides"],
        "total_return": round(r["total_return"], 2),
        "annualized": round(r["annualized_return"], 2),
        "max_drawdown": round(r["max_drawdown"], 2),
        "sharpe": round(r["sharpe_ratio"], 2),
        "trade_count": r["trade_count"],
        "elapsed_sec": round(elapsed, 1),
    }
    results.append(result)
    print(f"\n结果: {test['label']}")
    print(f"  收益={result['total_return']:.2f}% 年化={result['annualized']:.2f}% "
          f"回撤={result['max_drawdown']:.2f}% 夏普={result['sharpe']:.2f} "
          f"交易={result['trade_count']} 耗时={result['elapsed_sec']:.0f}s")

    # 每个测试完成后立即保存中间结果
    with open("backtest/reports/openclaw_strategy_test_3y_partial.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

# 最终结果
baseline_ret = results[0]["total_return"] if results else 56.93
print(f"\n{'='*80}")
print(f"OpenClaw策略融合测试最终结果")
print(f"{'='*80}")
print(f"{'方案':<30} {'收益%':>8} {'vs基线':>8} {'回撤%':>8} {'夏普':>6} {'交易':>6}")
print(f"{'-'*80}")
for r in sorted(results, key=lambda x: x["total_return"], reverse=True):
    diff = r["total_return"] - baseline_ret
    marker = "  " if abs(diff) < 0.5 else ("+" if diff > 0 else "-")
    print(f"{marker} {r['label']:<27} {r['total_return']:>7.2f}% {diff:>+7.2f}pp "
          f"{r['max_drawdown']:>7.2f}% {r['sharpe']:>5.2f} {r['trade_count']:>5}")

output = {
    "test_date": "2026-07-20",
    "period": "2023-07-17 ~ 2026-07-17",
    "baseline_return": baseline_ret,
    "results": results,
}
os.makedirs("backtest/reports", exist_ok=True)
with open("backtest/reports/openclaw_strategy_test_3y.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存: backtest/reports/openclaw_strategy_test_3y.json")
