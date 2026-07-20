#!/usr/bin/env python3
"""统一并行回测测试 — 方案A+B+C全部配置

方案A：激活已有前瞻指标（配置修改，无代码改动）
方案B：市场风险预警系统（market_risk.py）
方案C：Transformer市场方向预测（market_predictor.py）
+ 之前的OpenClaw策略

所有测试通过multiprocessing并行运行，结果写入JSON。
"""
import sys, json, copy, os, time, multiprocessing
from pathlib import Path

os.chdir("c:/fund")
sys.path.insert(0, ".")

BASE_CFG = json.loads(
    open("data/evolution/best_config.json", "r", encoding="utf-8").read()
)["config"]

ALL_TESTS = [
    # ── 基线 ──
    {"name": "baseline", "label": "基线", "group": "baseline", "overrides": {}},

    # ── 方案A：激活已有前瞻指标 ──
    {"name": "A1_macd_div", "label": "A1:周线MACD顶背离+仓位×0.6", "group": "A", "overrides": {"weekly_macd_divergence": True, "divergence_top_discount": 0.6}},
    {"name": "A2_bollinger", "label": "A2:周线布林带仓位调节", "group": "A", "overrides": {"weekly_bollinger_adjust": True}},
    {"name": "A3_yearly_ma", "label": "A3:年线牛熊过滤(跌破减半)", "group": "A", "overrides": {"yearly_ma_filter": True}},
    {"name": "A4_rsi70", "label": "A4:RSI超买阈值70(原80)", "group": "A", "overrides": {"block_overbought": True, "rsi_block_threshold": 70}},
    {"name": "A5_all_combined", "label": "A5:全部前瞻指标组合", "group": "A", "overrides": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True}},

    # ── 方案B：市场风险预警 ──
    {"name": "B1_risk60", "label": "B1:市场风险>60停买+>30减半", "group": "B", "overrides": {"market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30}},
    {"name": "B2_risk50", "label": "B2:市场风险>50停买+>20减半", "group": "B", "overrides": {"market_risk_filter": True, "market_risk_threshold": 50, "market_risk_caution": 20}},
    {"name": "B3_risk40", "label": "B3:市场风险>40停买(保守)", "group": "B", "overrides": {"market_risk_filter": True, "market_risk_threshold": 40, "market_risk_caution": 20}},

    # ── 方案C：Transformer市场预测 ──
    {"name": "C1_predictor60", "label": "C1:Transformer P(跌)>0.6停买", "group": "C", "overrides": {"market_predictor": True, "predictor_prob_threshold": 0.6, "predictor_retrain_days": 20}},
    {"name": "C2_predictor55", "label": "C2:Transformer P(跌)>0.55停买(敏感)", "group": "C", "overrides": {"market_predictor": True, "predictor_prob_threshold": 0.55, "predictor_retrain_days": 20}},

    # ── OpenClaw策略（之前已验证有效的继续测）──
    {"name": "OC_time_stop120", "label": "OC:时间止损120天", "group": "OC", "overrides": {"time_stop_days": 120, "time_stop_min_profit": 5}},
    {"name": "OC_rsi_sell80", "label": "OC:RSI>80卖30%", "group": "OC", "overrides": {"rsi_sell_threshold": 80, "rsi_sell_pct": 0.3}},
    {"name": "OC_no_new_high20", "label": "OC:20日不创新高卖", "group": "OC", "overrides": {"no_new_high_days": 20}},
    {"name": "OC_ma_cross", "label": "OC:MA5下穿MA20卖", "group": "OC", "overrides": {"ma_death_cross_sell": True}},
    {"name": "OC_dd_breaker12", "label": "OC:组合回撤12%熔断", "group": "OC", "overrides": {"portfolio_dd_breaker": 12, "portfolio_dd_pause_days": 5}},
]


def run_single_test(test_config, result_dict):
    """单个测试进程"""
    from backtest.engine.backtest import run_backtest

    cfg = copy.deepcopy(BASE_CFG)
    cfg.update(test_config["overrides"])
    cfg["start_date"] = "2023-07-17"
    cfg["end_date"] = "2026-07-17"
    cfg["initial_cash"] = 100000

    t0 = time.time()
    print(f"\n{'='*60}\n测试: {test_config['label']}\n{'='*60}", flush=True)
    r = run_backtest(cfg)
    elapsed = time.time() - t0

    result = {
        "name": test_config["name"],
        "label": test_config["label"],
        "group": test_config["group"],
        "overrides": test_config["overrides"],
        "total_return": round(r["total_return"], 2),
        "max_drawdown": round(r["max_drawdown"], 2),
        "sharpe": round(r["sharpe_ratio"], 2),
        "trade_count": r["trade_count"],
        "elapsed_sec": round(elapsed, 1),
    }
    print(f"\n结果: {test_config['label']}")
    print(f"  收益={result['total_return']:.2f}% 回撤={result['max_drawdown']:.2f}% "
          f"夏普={result['sharpe']:.2f} 交易={result['trade_count']} 耗时={result['elapsed_sec']:.0f}s", flush=True)

    result_dict[test_config["name"]] = result
    return result


def main():
    print(f"统一回测测试 — 方案A+B+C+OpenClaw 共{len(ALL_TESTS)}个测试")
    print(f"基线: 收益56.93% 回撤9.64% 夏普1.09 交易172次")

    n_workers = min(6, multiprocessing.cpu_count(), len(ALL_TESTS))
    print(f"并行进程数: {n_workers}")

    manager = multiprocessing.Manager()
    result_dict = manager.dict()
    pool = multiprocessing.Pool(processes=n_workers)

    t_start = time.time()
    for test in ALL_TESTS:
        pool.apply_async(run_single_test, args=(test, result_dict))

    pool.close()
    pool.join()

    total_elapsed = time.time() - t_start
    results = list(result_dict.values())
    results.sort(key=lambda x: x["total_return"], reverse=True)

    baseline_ret = next((r["total_return"] for r in results if r["name"] == "baseline"), 56.93)

    print(f"\n{'='*90}")
    print(f"统一回测最终结果（3年 2023-07-17 ~ 2026-07-17）")
    print(f"{'='*90}")
    print(f"{'方案':<35} {'收益%':>8} {'vs基线':>8} {'回撤%':>8} {'夏普':>6} {'交易':>6}")
    print(f"{'-'*90}")
    for r in results:
        diff = r["total_return"] - baseline_ret
        marker = "  " if abs(diff) < 0.5 else ("+" if diff > 0 else " ")
        print(f"{marker} {r['label']:<32} {r['total_return']:>7.2f}% {diff:>+7.2f}pp "
              f"{r['max_drawdown']:>7.2f}% {r['sharpe']:>5.2f} {r['trade_count']:>5}")

    print(f"\n总耗时: {total_elapsed:.0f}s ({total_elapsed/60:.1f}分钟)")

    output = {
        "test_date": "2026-07-20",
        "period": "2023-07-17 ~ 2026-07-17",
        "baseline_return": baseline_ret,
        "total_elapsed_sec": round(total_elapsed, 1),
        "results": results,
    }
    os.makedirs("backtest/reports", exist_ok=True)
    with open("backtest/reports/unified_backtest_3y.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: backtest/reports/unified_backtest_3y.json")


if __name__ == "__main__":
    main()
