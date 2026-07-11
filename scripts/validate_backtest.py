#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测稳健性验证脚本

测试多组参数组合，评估回测结果的稳定性。
解决"参数微调导致46%→0%的极端变化"问题。

用法:
  python scripts/validate_backtest.py
  python scripts/validate_backtest.py --quick   # 快速模式(少跑几组)
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.engine.backtest import run_backtest

PARAM_GRID = {
    "min_score": [2.5, 3.0, 3.3],
    "dynamic_ranking": [False, True],
    "max_position_pct": [15, 20, 25],
}

BASE_CONFIG = {
    "start_date": "2026-01-05",
    "end_date": "2026-06-30",
    "initial_cash": 10000,
    "weights": {"quality": 25, "cost": 20, "manager": 20, "momentum": 15, "smart_money": 20},
    "use_weighted_consensus": False,
    "cost_penalty": 0, "min_consensus": 2, "top_n": 0, "top_n_pct": 0,
    "consensus_priority": False, "net_signal": False, "limit_boost": 0,
    "max_sector_pct": 100, "max_qdii_pct": 100,
    "take_profit_pct": 30, "take_profit_sell_pct": 0.5, "stop_loss_pct": -15,
    "momentum_sell": 2.0, "kelly_cap": 0.2,
    "cash_reserve_pct": 0.2, "max_holdings": 0, "rebalance": False,
    "monthly_injection": 0, "fund_type_filter": "all",
    "sell_consensus": 0, "profit_mode": "half", "no_stop_loss": False,
    # ── 新增功能参数 ──
    "trailing_tp_activate": 15, "trailing_tp_drawdown": 8,  # 移动止盈
    "cooldown_days": 15, "cooldown_profit_days": 10, "cooldown_loss_days": 30,  # 冷却期
    "bear_market_no_buy": True,  # 熊市趋势过滤
    "min_score_bull": 2.5, "min_score_neutral": 3.0, "min_score_bear": 3.5,  # 动态评分门槛
    "max_correlation": 0.85,  # 相关性过滤
    "ml_signal": True, "ml_weight": 1.5, "ml_retrain_days": 30,  # ML信号增强
    "timing_filter": True, "block_overbought": False, "downtrend_penalty": 0.5,  # 技术择时
}


def generate_configs(ms_range, dr_range, mp_range, quick=False):
    configs = []
    for ms in ms_range:
        for dr in dr_range:
            for mp in mp_range:
                cfg = BASE_CONFIG.copy()
                cfg["min_score"] = ms
                cfg["dynamic_ranking"] = dr
                cfg["max_position_pct"] = mp
                configs.append(cfg)
    return configs


def run_single(cfg):
    cfg_id = f'ms={cfg["min_score"]} dr={cfg["dynamic_ranking"]} mp={cfg["max_position_pct"]}'
    print(f"  [{cfg_id}] ...", end=" ", flush=True)
    t0 = time.time()
    try:
        result = run_backtest(cfg)
        elapsed = time.time() - t0
        trades = len(result.get("trades", []))
        ret = result.get("total_return", 0)
        dd = result.get("max_drawdown", 0)
        sharpe = result.get("sharpe_ratio", 0)
        calmar = result.get("calmar_ratio", 0)
        ann_ret = result.get("annualized_return", 0)
        print(f"ret={ret:.1f}% ann={ann_ret:.1f}% trades={trades} dd={dd:.0f}% sharpe={sharpe:.2f} calmar={calmar:.2f} ({elapsed:.0f}s)")
        return {"config": cfg, "return": ret, "trades": trades, "max_drawdown": dd,
                "sharpe": sharpe, "calmar": calmar, "annualized_return": ann_ret}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"ERROR: {e} ({elapsed:.0f}s)")
        return {"config": cfg, "return": None, "trades": 0, "error": str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="回测稳健性验证")
    parser.add_argument("--quick", action="store_true", help="快速模式")
    args = parser.parse_args()

    if args.quick:
        ms_range = [2.5, 3.3]
        dr_range = [False, True]
        mp_range = [20, 25]
    else:
        ms_range = PARAM_GRID["min_score"]
        dr_range = PARAM_GRID["dynamic_ranking"]
        mp_range = PARAM_GRID["max_position_pct"]

    configs = generate_configs(ms_range, dr_range, mp_range, args.quick)
    print(f"参数组合数: {len(configs)}")
    print(f"参数网格: min_score={ms_range} dynamic_ranking={dr_range} max_position_pct={mp_range}")
    print(f"区间: {BASE_CONFIG['start_date']} ~ {BASE_CONFIG['end_date']}")
    print()

    results = []
    for cfg in configs:
        r = run_single(cfg)
        results.append(r)

    print("\n" + "=" * 60)
    print("结果汇总")
    print("=" * 60)

    valid = [r for r in results if r["return"] is not None]
    if not valid:
        print("所有回测均失败!")
        return

    returns = [r["return"] for r in valid]
    trades_list = [r["trades"] for r in valid]

    import statistics
    print(f"有效结果: {len(valid)}/{len(results)}")
    print(f"收益率: 平均={sum(returns)/len(returns):+.1f}% 中位数={sorted(returns)[len(returns)//2]:+.1f}%")
    print(f"  范围: {min(returns):+.1f}% ~ {max(returns):+.1f}% 标准差={statistics.stdev(returns):.1f}%")
    print(f"  正收益组数: {sum(1 for r in returns if r > 0)}/{len(returns)}")
    print(f"交易次数: 平均={sum(trades_list)/len(trades_list):.0f} 范围={min(trades_list)}~{max(trades_list)}")

    print("\n详细结果 (按夏普比率排序):")
    for r in sorted(valid, key=lambda x: x.get("sharpe", 0), reverse=True):
        cfg = r["config"]
        print(f"  ms={cfg['min_score']} dr={cfg['dynamic_ranking']} mp={cfg['max_position_pct']}: "
              f"ret={r['return']:+.1f}% ann={r.get('annualized_return',0):+.1f}% "
              f"dd={r.get('max_drawdown',0):.0f}% sharpe={r.get('sharpe',0):.2f} "
              f"calmar={r.get('calmar',0):.2f} trades={r['trades']}")

    report = {
        "config_grid": {"min_score": ms_range, "dynamic_ranking": dr_range, "max_position_pct": mp_range, "base": BASE_CONFIG},
        "summary": {
            "mean_return": sum(returns)/len(returns),
            "median_return": sorted(returns)[len(returns)//2],
            "min_return": min(returns), "max_return": max(returns),
            "std_return": statistics.stdev(returns) if len(returns) > 1 else 0,
            "positive_count": sum(1 for r in returns if r > 0), "total_count": len(returns),
        },
        "results": valid,
    }
    out_path = Path("backtest/reports/validation_report.json")
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n已保存到 {out_path}")


if __name__ == "__main__":
    main()