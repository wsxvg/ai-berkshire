#!/usr/bin/env python3
"""单测试运行脚本 — 供GitHub Actions调用

用法: python backtest/run_single_test.py <test_name>
结果: 写入 backtest/results/<test_name>.json
"""
import sys, json, copy, time, os

# 所有测试配置
TEST_CONFIGS = {
    # 基线
    "baseline": {},
    # 方案A
    "A1_macd_div": {"weekly_macd_divergence": True, "divergence_top_discount": 0.6},
    "A2_bollinger": {"weekly_bollinger_adjust": True},
    "A3_yearly_ma": {"yearly_ma_filter": True},
    "A4_rsi70": {"block_overbought": True},
    "A5_all_combined": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True},
    # 方案B
    "B1_risk60": {"market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30},
    "B2_risk50": {"market_risk_filter": True, "market_risk_threshold": 50, "market_risk_caution": 20},
    "B3_risk40": {"market_risk_filter": True, "market_risk_threshold": 40, "market_risk_caution": 20},
    # 方案C
    "C1_predictor60": {"market_predictor": True, "predictor_prob_threshold": 0.6, "predictor_retrain_days": 20},
    "C2_predictor55": {"market_predictor": True, "predictor_prob_threshold": 0.55, "predictor_retrain_days": 20},
    # OpenClaw
    "OC_time_stop120": {"time_stop_days": 120, "time_stop_min_profit": 5},
    "OC_rsi_sell80": {"rsi_sell_threshold": 80, "rsi_sell_pct": 0.3},
    "OC_no_new_high20": {"no_new_high_days": 20},
    "OC_ma_cross": {"ma_death_cross_sell": True},
    "OC_dd_breaker12": {"portfolio_dd_breaker": 12, "portfolio_dd_pause_days": 5},
    # 方案D：新策略
    "D1_step_tp": {"step_take_profit": True},
    "D2_atr_stop": {"atr_stop_loss_mult": 2.0},
    "D3_macd_buy": {"macd_golden_cross_buy": True},
    "D4_dyn_kelly": {"market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30, "kelly_fraction": 0.5},
    # 混合组合
    "E1_A5_B1": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True, "market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30},
    "E2_A5_C1": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True, "market_predictor": True, "predictor_prob_threshold": 0.6},
    "E3_B1_C1": {"market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30, "market_predictor": True, "predictor_prob_threshold": 0.6},
    "E4_all": {"weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True, "market_risk_filter": True, "market_risk_threshold": 60, "market_risk_caution": 30, "market_predictor": True, "predictor_prob_threshold": 0.6},
    # 参数扫描
    "F1_rsi65": {"block_overbought": True, "rsi_block_threshold": 65},
    "F2_rsi75": {"block_overbought": True, "rsi_block_threshold": 75},
    "F3_tp40": {"take_profit_pct": 40},
    "F4_tp60": {"take_profit_pct": 60},
    "F5_trail5": {"trailing_tp_activate": 20, "trailing_tp_drawdown": 5},
    "F6_trail12": {"trailing_tp_activate": 20, "trailing_tp_drawdown": 12},
    "F7_sector30": {"rebalance": True, "max_sector_pct": 30},
    # D2 + B1 组合
    "G1_atr_risk": {"atr_stop_loss_mult": 2.0, "market_risk_filter": True, "market_risk_threshold": 50, "market_risk_caution": 30},
    # D1 + D2 组合
    "G2_step_atr": {"step_take_profit": True, "atr_stop_loss_mult": 2.0},
    # 全部组合（所有策略全开）
    "H1_all_in": {"step_take_profit": True, "atr_stop_loss_mult": 2.0, "macd_golden_cross_buy": True, "market_risk_filter": True, "market_risk_threshold": 50, "market_risk_caution": 30, "weekly_macd_divergence": True, "weekly_bollinger_adjust": True, "yearly_ma_filter": True, "block_overbought": True},
}

LABELS = {
    "baseline": "基线",
    "A1_macd_div": "A1:周线MACD顶背离",
    "A2_bollinger": "A2:周线布林带",
    "A3_yearly_ma": "A3:年线过滤",
    "A4_rsi70": "A4:RSI超买70",
    "A5_all_combined": "A5:全部前瞻指标",
    "B1_risk60": "B1:风险>60停买",
    "B2_risk50": "B2:风险>50停买",
    "B3_risk40": "B3:风险>40停买",
    "C1_predictor60": "C1:Transformer P跌>0.6",
    "C2_predictor55": "C2:Transformer P跌>0.55",
    "OC_time_stop120": "OC:时间止损120天",
    "OC_rsi_sell80": "OC:RSI>80卖30%",
    "OC_no_new_high20": "OC:20日不创新高",
    "OC_ma_cross": "OC:MA5下穿MA20",
    "OC_dd_breaker12": "OC:组合回撤12%熔断",
    "D1_step_tp": "D1:阶梯止盈(30/50/80分批)",
    "D2_atr_stop": "D2:ATR动态止损(2×ATR)",
    "D3_macd_buy": "D3:MACD金叉买入过滤",
    "D4_dyn_kelly": "D4:动态凯利(风险分调仓)",
    "E1_A5_B1": "E1:A5+B1(指标+风险)",
    "E2_A5_C1": "E2:A5+C1(指标+Transformer)",
    "E3_B1_C1": "E3:B1+C1(风险+Transformer)",
    "E4_all": "E4:全部组合(A+B+C)",
    "F1_rsi65": "F1:RSI超买65(更严格)",
    "F2_rsi75": "F2:RSI超买75(较宽松)",
    "F3_tp40": "F3:止盈40%(更早)",
    "F4_tp60": "F4:止盈60%(更晚)",
    "F5_trail5": "F5:移动止盈回撤5%(紧)",
    "F6_trail12": "F6:移动止盈回撤12%(松)",
    "F7_sector30": "F7:行业集中度30%",
    "G1_atr_risk": "G1:ATR止损+风险50停买",
    "G2_step_atr": "G2:阶梯止盈+ATR止损",
    "H1_all_in": "H1:全部策略全开",
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python backtest/run_single_test.py <test_name>")
        sys.exit(1)

    test_name = sys.argv[1]
    if test_name not in TEST_CONFIGS:
        print(f"Unknown test: {test_name}")
        print(f"Available: {', '.join(TEST_CONFIGS.keys())}")
        sys.exit(1)

    # 确定项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    from backtest.engine.backtest import run_backtest

    base_cfg = json.loads(
        open("data/evolution/best_config.json", "r", encoding="utf-8").read()
    )["config"]

    cfg = copy.deepcopy(base_cfg)
    cfg.update(TEST_CONFIGS[test_name])
    cfg["start_date"] = "2023-07-17"
    cfg["end_date"] = "2026-07-17"
    cfg["initial_cash"] = 100000

    t0 = time.time()
    label = LABELS.get(test_name, test_name)
    print(f"{'='*60}")
    print(f"Test: {label} ({test_name})")
    print(f"{'='*60}")

    r = run_backtest(cfg)
    elapsed = time.time() - t0

    result = {
        "name": test_name,
        "label": label,
        "total_return": round(r["total_return"], 2),
        "max_drawdown": round(r["max_drawdown"], 2),
        "sharpe": round(r["sharpe_ratio"], 2),
        "trade_count": r["trade_count"],
        "elapsed_sec": round(elapsed, 1),
    }
    print(f"\n{'='*60}")
    print(f"Result: {label}")
    print(f"  return={result['total_return']}% dd={result['max_drawdown']}% "
          f"sharpe={result['sharpe']} trades={result['trade_count']} "
          f"time={result['elapsed_sec']}s")
    print(f"{'='*60}")

    os.makedirs("backtest/results", exist_ok=True)
    outpath = f"backtest/results/{test_name}.json"
    with open(outpath, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Saved: {outpath}")


if __name__ == "__main__":
    main()
