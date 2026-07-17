#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
融合策略回测脚本 (2026-07-12 新增)

目的:
  1. 验证原 D / E 策略 + 机器基线(Buy-Hold/J无脑跟投)在多周期的回测表现
  2. 评估 1.txt 新端点 (getSimpleQuoteUseUniqueCodes / queryStallNew / getIndexDetail)
     接入后,构建"五维评分 + 行业估值 + 多指数择时"融合策略,相比单策略是否有增益

策略族:
  ── 原始基线 (回测引擎原生)
  D  智能费用  min_score=3.3, stop_loss=-10, tp=30, profit_mode=half,  cost_penalty=1.0,  min_consensus=2
  E  分批建仓  min_score=3.3, stop_loss=-8,  tp=25, profit_mode=quarter, cost_penalty=1.0,  min_consensus=2
  J  无脑跟投  min_score=0.0, stop_loss=-30, tp=50, profit_mode=half,  cost_penalty=0,    min_consensus=2
  BH BuyHold   机器基线 (回测引擎自动算 buyhold_return)

  ── 融合策略 (本次新设计)
  F-D  D基线 + 行业估值过滤  (sector_valuation=True, 拦截高估行业)
  F-E  E基线 + 多指数择时增强 (turn_off_buy_when_above_ma=True, 牛熊自适应min_score)
  F-AI 五维评分 + 行业估值 + 多指数共振 (核心) + ML信号

回测周期: 半年(0.5Y) / 1Y / 2Y / 3Y, 全部以回测数据为唯一金标准
"""

import sys
import json
import time
import math
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest.engine.backtest import run_backtest  # noqa: E402


# ======================================================================
# 策略族配置 (与 run_strategies.py 对齐)
# ======================================================================

WEIGHTS_BASE = {
    "quality": 25,
    "cost": 20,
    "manager": 20,
    "momentum": 15,
    "smart_money": 20,
}

# ── 基线策略 ──
BASE_STRATEGIES = {
    "D-智能费用": {
        "desc": "高费用惩罚+标准止损+半仓止盈 (回测引擎原生策略D)",
        "config": {
            "min_score": 3.3, "stop_loss_pct": -10, "take_profit_pct": 30,
            "profit_mode": "half", "cost_penalty": 1.0, "min_consensus": 2,
            "fund_type_filter": "all",
        },
    },
    "E-分批建仓": {
        "desc": "浅止损+25%止盈+1/4批止盈 (回测引擎原生策略E)",
        "config": {
            "min_score": 3.3, "stop_loss_pct": -8, "take_profit_pct": 25,
            "profit_mode": "quarter", "cost_penalty": 1.0, "min_consensus": 2,
            "fund_type_filter": "all",
        },
    },
    "J-无脑跟投": {
        "desc": "2人买我就买,无评分门槛 (回测引擎原生策略J,机器五维弱化基线)",
        "config": {
            "min_score": 0.0, "stop_loss_pct": -30, "take_profit_pct": 50,
            "profit_mode": "half", "cost_penalty": 0.0, "min_consensus": 2,
            "fund_type_filter": "all",
        },
    },
}

# ── 融合策略 (本次新设计) ──
FUSION_STRATEGIES = {
    "F-D-行业过滤": {
        "desc": "D基线 + 行业估值过滤(>70%扣分,>80%拦截) + ML信号",
        "config": {
            "min_score": 3.3, "stop_loss_pct": -10, "take_profit_pct": 30,
            "profit_mode": "half", "cost_penalty": 1.0, "min_consensus": 2,
            "fund_type_filter": "all",
            "sector_valuation": True,         # 1.txt getIndexDetail 估值信号
            "ml_signal": True,                # ML信号增强
            "ml_weight": 0.6,                 # ML权重0.6 (保守引入)
            "ml_retrain_days": 90,            # 90天重训一次
            "ml_min_samples": 80,
            "ml_label_threshold": 3.0,
        },
    },
    "F-E-多指数择时": {
        "desc": "E基线 + 沪深300+创业板+中证500多指数共振过滤 + ML信号",
        "config": {
            "min_score": 3.3, "stop_loss_pct": -8, "take_profit_pct": 25,
            "profit_mode": "quarter", "cost_penalty": 1.0, "min_consensus": 2,
            "fund_type_filter": "all",
            "dyn_max_pos_bull": 30,
            "dyn_max_pos_bear": 15,
            "dyn_cash_reserve_bull": 0.05,
            "dyn_cash_reserve_bear": 0.30,
            "dyn_cash_reserve_neutral": 0.15,
            "max_correlation": 0.85,
            "ml_signal": True,
            "ml_weight": 0.6,
            "ml_retrain_days": 90,
        },
    },
    "F-AI-融合": {
        "desc": "五维评分+行业估值+多指数+ML信号,核心持仓20%, ATR仓位",
        "config": {
            "min_score": 3.0, "stop_loss_pct": -10, "take_profit_pct": 30,
            "profit_mode": "half", "cost_penalty": 1.0, "min_consensus": 2,
            "fund_type_filter": "all",
            "sector_valuation": True,
            "ml_signal": True,
            "ml_weight": 0.8,
            "ml_retrain_days": 60,
            "ml_min_samples": 50,
            "dyn_max_pos_bull": 30,
            "dyn_max_pos_bear": 12,
            "dyn_cash_reserve_bull": 0.05,
            "dyn_cash_reserve_bear": 0.35,
            "dyn_cash_reserve_neutral": 0.20,
            "max_correlation": 0.80,
            "max_holdings": 8,
            "core_holding_pct": 0.20,           # 20%底仓沪深300
            "use_atr_sizing": True,
            "atr_baseline": 0.012,
        },
    },
}

# ======================================================================
# 回测周期
# ======================================================================

# 数据范围 (实测): trading_by_date 2024-03-11 ~ 2026-07-01, fund_charts 最长 2018-04 ~ 2026-07
# 半年/1Y/2Y/3Y 起点 (避免起点过前数据稀疏)
PERIODS = {
    "0.5Y": ("2026-01-01", "2026-07-01"),
    "1Y":   ("2025-07-01", "2026-07-01"),
    "2Y":   ("2024-07-01", "2026-07-01"),
    "3Y":   ("2023-07-01", "2026-07-01"),
}

# 排除因耗时过长的策略(只在半年/1Y跑全量,2Y/3Y跑快速组)
SKIP_LONG_PERIOD = {"F-AI-融合"}  # 3Y太慢,跳过该组


# ======================================================================
# 执行回测
# ======================================================================

def annualized_return(total_ret_pct, start_date, end_date):
    """年化收益率 (按真实天数,365天基准)"""
    from datetime import datetime
    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date, "%Y-%m-%d")
    days = (e - s).days
    if days <= 0:
        return 0
    ret = total_ret_pct / 100
    return ((1 + ret) ** (365 / days) - 1) * 100


def run_one(strategy_name, strategy_def, start_date, end_date, initial_cash=10000):
    """跑一个策略在一个周期的回测"""
    cfg = {
        "start_date": start_date,
        "end_date": end_date,
        "initial_cash": initial_cash,
        "weights": WEIGHTS_BASE,
    }
    cfg.update(strategy_def["config"])
    t0 = time.time()
    try:
        r = run_backtest(cfg)
        elapsed = round(time.time() - t0, 1)
        ann = annualized_return(r["total_return"], start_date, end_date)
        return {
            "strategy": strategy_name,
            "desc": strategy_def["desc"],
            "start": start_date,
            "end": end_date,
            "period_days": (
                __import__("datetime").datetime.strptime(end_date, "%Y-%m-%d")
                - __import__("datetime").datetime.strptime(start_date, "%Y-%m-%d")
            ).days,
            "total_return": round(r["total_return"], 2),
            "annualized": round(ann, 2),
            "max_drawdown": round(r["max_drawdown"], 2),
            "sharpe": round(r.get("sharpe_ratio", 0), 2),
            "calmar": round(r.get("calmar_ratio", 0), 2),
            "benchmark_return": round(r.get("benchmark_return", 0), 2),
            "buyhold_return": round(r.get("buyhold_return", 0), 2),
            "buyhold_code": r.get("buyhold_code", ""),
            "trades": r.get("trade_count", 0),
            "holdings": r.get("final_holdings", 0),
            "fees": round(r.get("total_fees", 0), 2),
            "vs_benchmark": round(r["total_return"] - r.get("benchmark_return", 0), 2),
            "vs_buyhold": round(r["total_return"] - r.get("buyhold_return", 0), 2),
            "elapsed_sec": elapsed,
            "status": "OK",
        }
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        import traceback
        return {
            "strategy": strategy_name,
            "desc": strategy_def["desc"],
            "start": start_date,
            "end": end_date,
            "status": "FAIL",
            "error": str(e)[:200],
            "traceback": traceback.format_exc()[:500],
            "elapsed_sec": elapsed,
        }


def main():
    """执行全量回测并输出报告"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--periods", type=str, default="0.5Y,1Y",
                        help="comma-separated periods: 0.5Y,1Y,2Y,3Y")
    parser.add_argument("--strategies", type=str, default="all",
                        help="all|baseline|fusion|comma-separated names")
    parser.add_argument("--output", type=str, default="backtest/reports/fusion_strategy_comparison.json")
    args = parser.parse_args()

    # 选周期
    periods_to_run = [p.strip() for p in args.periods.split(",") if p.strip() in PERIODS]
    if not periods_to_run:
        periods_to_run = ["0.5Y", "1Y"]

    # 选策略
    if args.strategies == "all":
        all_strategies = {**BASE_STRATEGIES, **FUSION_STRATEGIES}
    elif args.strategies == "baseline":
        all_strategies = BASE_STRATEGIES
    elif args.strategies == "fusion":
        all_strategies = FUSION_STRATEGIES
    else:
        names = [n.strip() for n in args.strategies.split(",")]
        all_strategies = {n: {**BASE_STRATEGIES.get(n, {}), **FUSION_STRATEGIES.get(n, {})}
                          for n in names if n in BASE_STRATEGIES or n in FUSION_STRATEGIES}

    print(f"\n{'=' * 70}")
    print(f"融合策略多周期回测: 周期={periods_to_run}, 策略={list(all_strategies.keys())}")
    print(f"{'=' * 70}\n")

    all_results = {}
    grand_t0 = time.time()
    for period in periods_to_run:
        start, end = PERIODS[period]
        print(f"\n### 周期: {period}  ({start} ~ {end})  ###")
        all_results[period] = []
        for sname, sdef in all_strategies.items():
            # 长周期跳过慢策略
            if period in ("2Y", "3Y") and sname in SKIP_LONG_PERIOD:
                print(f"  [SKIP] {sname} 在 {period} 跳过 (耗时过长)")
                continue
            print(f"  >> 跑 {sname} ...", end="", flush=True)
            r = run_one(sname, sdef, start, end)
            if r["status"] == "OK":
                print(f" ret={r['total_return']:+.2f}% ann={r['annualized']:+.1f}% "
                      f"vs_bm={r['vs_benchmark']:+.2f}%  ({r['elapsed_sec']}s)")
            else:
                print(f" FAIL ({r['elapsed_sec']}s) {r.get('error','')[:60]}")
            all_results[period].append(r)

    total_elapsed = round(time.time() - grand_t0, 1)
    print(f"\n\n总耗时: {total_elapsed}s")

    # 保存
    out_path = PROJECT_DIR / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "periods": periods_to_run,
            "strategies": list(all_strategies.keys()),
            "results": all_results,
            "total_elapsed_sec": total_elapsed,
        }, f, ensure_ascii=False, indent=2)
    print(f"结果已保存到 {out_path}")
    return all_results


if __name__ == "__main__":
    main()
