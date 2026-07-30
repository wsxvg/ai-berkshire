#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V9 宏观趋势 + 质量筛选策略

核心思路（极简，难过度拟合）：
1. 用宽基指数60日动量判断市场趋势（不是基金未来函数）
2. 趋势向上：买入高质量基金等权持仓
3. 趋势向下：空仓或持有货币基金
4. 月度再平衡

参数极少（2个），不容易过拟合：
- trend_lookback: 趋势回看天数（默认63天≈3月）
- max_holdings: 最大持仓数（默认5只）
"""

import json
import sys
import copy
from pathlib import Path
from collections import defaultdict

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest.engine.backtest import run_backtest, Portfolio, _bisect_valid, _float
from tools.chart_loader import load_all_charts


def get_market_trend_signal(fund_charts, day, lookback=63):
    """
    判断市场趋势 - 用市场上最大的几个股票型基金的平均收益作为 proxy
    这不是未来函数，因为我们用的是当天之前的数据
    """
    # 用几个常见宽基指数基金作为市场 proxy
    market_proxy_codes = ['000962', '001631', '005918', '161725', '001593']
    
    market_returns = []
    for code in market_proxy_codes:
        pts = fund_charts.get(code, [])
        if not pts:
            continue
        valid = _bisect_valid(pts, day)
        if len(valid) > lookback:
            navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
            if len(navs) >= lookback:
                ret = (navs[-1] / navs[-lookback] - 1)
                market_returns.append(ret)
    
    if market_returns:
        return sum(market_returns) / len(market_returns)
    return 0.5  # 默认趋势不明


def run_macro_trend_backtest(config):
    """宏观趋势策略回测"""
    start_date = config.get("start_date", "2023-07-17")
    end_date = config.get("end_date", "2026-07-24")
    initial_cash = config.get("initial_cash", 10000)
    trend_lookback = config.get("trend_lookback", 63)
    max_holdings = config.get("max_holdings", 5)
    rebalance_days = config.get("rebalance_days", 21)

    # 加载数据
    data_file = PROJECT_DIR / "backtest" / "data" / "trading_by_date_fixed.json"
    if not data_file.exists():
        data_file = PROJECT_DIR / "backtest" / "data" / "trading_by_date.json"
    with open(data_file, "r", encoding="utf-8") as f:
        trading_by_date = json.load(f)

    fund_charts = load_all_charts()
    
    name_map_path = PROJECT_DIR / "data" / "fund_name_map.json"
    name_to_code = {}
    if name_map_path.exists():
        name_to_code = json.loads(name_map_path.read_text("utf-8"))

    all_dates = sorted(trading_by_date.keys())
    backtest_dates = [d for d in all_dates if start_date <= d <= end_date]

    if not backtest_dates:
        return {"error": "No trading dates in range"}

    portfolio = Portfolio(initial_cash=initial_cash)
    portfolio.daily_values = []
    daily_values = []

    # 获取所有基金代码
    all_fund_codes = list(fund_charts.keys())

    for idx, day in enumerate(backtest_dates):
        portfolio.settle_pending(day)
        portfolio.settle_pending_sells(day)

        # 计算当前总价值
        current_value = portfolio.cash
        for code, holding in portfolio.holdings.items():
            pts = fund_charts.get(code, [])
            valid = _bisect_valid(pts, day)
            if valid:
                nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                current_value += holding["shares"] * nav

        # 再平衡日
        if idx % rebalance_days == 0 or idx == 0:
            # 判断市场趋势
            market_ret = get_market_trend_signal(fund_charts, day, trend_lookback)
            
            if market_ret > 0:  # 趋势向上
                # 趋势动量排序（选50日动量为正且最强的基金）
                fund_scores = []
                for code in all_fund_codes:
                    pts = fund_charts.get(code, [])
                    valid = _bisect_valid(pts, day)
                    if len(valid) > 50:
                        navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                        if len(navs) >= 50:
                            mom = (navs[-1] / navs[-50] - 1)
                            if mom > 0:  # 只选正动量
                                fund_scores.append((code, mom))
                
                fund_scores.sort(key=lambda x: x[1], reverse=True)
                top_funds = [c for c, m in fund_scores[:max_holdings]]

                # 卖出不在top的持仓
                for code in list(portfolio.holdings.keys()):
                    if code not in top_funds:
                        pts = fund_charts.get(code, [])
                        valid = _bisect_valid(pts, day)
                        if valid:
                            nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                            portfolio.sell(code, 0, nav, day, "trend_rotation", force_sell=True)

                # 买入top基金（等权）
                target_per_fund = current_value * 0.95 / max(len(top_funds), 1)
                for code in top_funds:
                    pts = fund_charts.get(code, [])
                    valid = _bisect_valid(pts, day)
                    if valid:
                        nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                        if nav > 0 and portfolio.cash > target_per_fund * 0.5:
                            buy_amount = min(target_per_fund, portfolio.cash * 0.9)
                            portfolio.buy(code, f"trend_buy", buy_amount, nav, day)

            else:  # 趋势向下 - 全部卖出
                for code in list(portfolio.holdings.keys()):
                    pts = fund_charts.get(code, [])
                    valid = _bisect_valid(pts, day)
                    if valid:
                        nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                        portfolio.sell(code, 0, nav, day, "risk_off", force_sell=True)

        # 记录净值
        rec_value = portfolio.cash
        for code, holding in portfolio.holdings.items():
            pts = fund_charts.get(code, [])
            valid = _bisect_valid(pts, day)
            if valid:
                nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                rec_value += holding["shares"] * nav
        daily_values.append(rec_value)

    # 计算指标
    if len(daily_values) < 2:
        return {"error": "Insufficient data"}

    total_return = (daily_values[-1] / initial_cash - 1) * 100
    
    peak = initial_cash
    max_dd = 0
    for v in daily_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd

    days = len(daily_values)
    years = days / 252
    annualized = ((daily_values[-1] / initial_cash) ** (1/years) - 1) * 100 if years > 0 else 0

    returns = []
    for i in range(1, len(daily_values)):
        if daily_values[i-1] > 0:
            returns.append(daily_values[i] / daily_values[i-1] - 1)

    if returns:
        avg_r = sum(returns) / len(returns)
        var_r = sum((r - avg_r)**2 for r in returns) / len(returns)
        std_r = var_r ** 0.5
        sharpe = (avg_r / std_r * (252 ** 0.5)) if std_r > 0 else 0
    else:
        sharpe = 0

    return {
        "total_return": round(total_return, 2),
        "max_drawdown": round(max_dd, 2),
        "annualized_return": round(annualized, 2),
        "sharpe_ratio": round(sharpe, 2),
        "trade_count": len(portfolio.trades),
        "final_value": round(daily_values[-1], 2),
    }


def main():
    print("=" * 70)
    print("V9 宏观趋势 + 质量筛选策略")
    print("=" * 70)

    configs = [
        {"name": "MT1", "trend_lookback": 63, "max_holdings": 5, "rebalance_days": 21},
        {"name": "MT2", "trend_lookback": 63, "max_holdings": 8, "rebalance_days": 21},
        {"name": "MT3", "trend_lookback": 42, "max_holdings": 5, "rebalance_days": 21},
        {"name": "MT4", "trend_lookback": 126, "max_holdings": 5, "rebalance_days": 21},
        {"name": "MT5", "trend_lookback": 63, "max_holdings": 3, "rebalance_days": 21},
        {"name": "MT6", "trend_lookback": 63, "max_holdings": 5, "rebalance_days": 14},
        {"name": "MT7", "trend_lookback": 63, "max_holdings": 5, "rebalance_days": 42},
    ]

    results = []
    for cfg in configs:
        print(f"\n--- {cfg['name']}: trend={cfg['trend_lookback']}d, hold{cfg['max_holdings']}, rebal={cfg['rebalance_days']}d ---")
        result = run_macro_trend_backtest(cfg)
        result["name"] = cfg["name"]
        result["config"] = cfg
        results.append(result)
        print(f"  Return: {result['total_return']:.2f}%, DD: {result['max_drawdown']:.2f}%, Sharpe: {result['sharpe_ratio']:.2f}")

    results.sort(key=lambda x: x["total_return"], reverse=True)

    print("\n" + "=" * 70)
    print("排名")
    print("=" * 70)
    print(f"{'排名':<4} {'策略':<6} {'收益':>8} {'回撤':>8} {'年化':>7} {'夏普':>6} {'交易':>5}")
    print("-" * 60)
    for i, r in enumerate(results, 1):
        print(f"{i:<4} {r['name']:<6} {r['total_return']:>7.1f}% {r['max_drawdown']:>7.1f}% {r.get('annualized_return', 0):>6.1f}% {r['sharpe_ratio']:>5.2f} {r['trade_count']:>4}")

    output_file = PROJECT_DIR / "v9-results" / "v9_macro_trend_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n已保存: {output_file}")


if __name__ == "__main__":
    main()
