#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业动量轮动 + 波动率目标仓位策略

核心逻辑：
1. 行业动量：每月排名行业收益，只持有前 N 个行业
2. 波动率目标：根据当前波动率调整仓位，目标年化波动率 10%
3. 月度再平衡，纪律执行

参数：
- momentum_lookback: 动量回看天数（默认 63≈3个月）
- top_n_sectors: 持有前 N 个行业（默认 4）
- target_vol: 目标年化波动率（默认 10%）
- rebalance_days: 再平衡周期（默认 21≈1个月）
"""

import json
import sys
import copy
import math
from pathlib import Path
from collections import defaultdict

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest.engine.backtest import Portfolio, _bisect_valid
from tools.fund_scorer import _float

# 行业映射：基金代码前缀 -> 行业分类
# 基于京东金融基金名称中的关键词
SECTOR_KEYWORDS = {
    "科技": ["科技", "半导体", "芯片", "AI", "人工智能", "互联网", "数字经济", "信息技术", "电子", "通信", "计算机", "软件", "科创"],
    "医药": ["医药", "医疗", "生物", "创新药", "医疗器械", "健康", "制药"],
    "消费": ["消费", "白酒", "食品", "饮料", "家电", "零售", "旅游", "餐饮", "农业"],
    "金融": ["金融", "银行", "保险", "证券", "地产", "基建"],
    "周期": ["周期", "煤炭", "钢铁", "有色", "化工", "能源", "电力", "石油", "黄金", "资源"],
    "制造": ["制造", "军工", "汽车", "新能源", "光伏", "锂电", "机械", "工业"],
    "QDII": ["QDII", "全球", "海外", "纳斯达克", "标普", "港股", "恒生"],
}

def classify_sector(fund_name):
    """根据基金名称分类行业"""
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in fund_name:
                return sector
    return "其他"


def run_sector_momentum_backtest(config):
    """
    运行行业动量轮动策略回测
    """
    start_date = config.get("start_date", "2023-07-17")
    end_date = config.get("end_date", "2026-07-24")
    initial_cash = config.get("initial_cash", 10000)
    momentum_lookback = config.get("momentum_lookback", 63)
    top_n_sectors = config.get("top_n_sectors", 4)
    target_vol = config.get("target_vol", 0.10)  # 10% 年化
    rebalance_days = config.get("rebalance_days", 21)

    # 加载数据
    data_file = PROJECT_DIR / "backtest" / "data" / "trading_by_date_fixed.json"
    if not data_file.exists():
        data_file = PROJECT_DIR / "backtest" / "data" / "trading_by_date.json"
    with open(data_file, "r", encoding="utf-8") as f:
        trading_by_date = json.load(f)

    from tools.chart_loader import load_all_charts
    fund_charts = load_all_charts()

    # 加载基金名称映射
    name_map_path = PROJECT_DIR / "data" / "fund_name_map.json"
    name_to_code = {}
    if name_map_path.exists():
        name_to_code = json.loads(name_map_path.read_text("utf-8"))

    # 获取所有交易日期
    all_dates = sorted(trading_by_date.keys())
    backtest_dates = [d for d in all_dates if start_date <= d <= end_date]

    if not backtest_dates:
        return {"error": "No trading dates in range"}

    # 初始化组合
    portfolio = Portfolio(initial_cash=initial_cash)
    portfolio.daily_values = []

    # 为每个基金计算行业分类
    fund_sectors = {}
    for code, pts in fund_charts.items():
        if pts:
            # 从净值数据中获取基金名称
            name = pts[0].get("name", "") if pts else ""
            if not name:
                # 尝试从 name_map 反查
                for n, c in name_to_code.items():
                    if c == code:
                        name = n
                        break
            fund_sectors[code] = classify_sector(name)

    # 按行业聚合基金
    sector_funds = defaultdict(list)
    for code, sector in fund_sectors.items():
        sector_funds[sector].append(code)

    # 回测主循环
    last_rebalance_idx = -rebalance_days  # 确保第一天就再平衡
    current_target_sectors = set()
    daily_values = []

    for idx, day in enumerate(backtest_dates):
        # 结算待处理交易
        portfolio.settle_pending(day)
        portfolio.settle_pending_sells(day)

        # 计算当前持仓市值
        holdings_value = 0
        for code, holding in portfolio.holdings.items():
            pts = fund_charts.get(code, [])
            valid = _bisect_valid(pts, day)
            if valid:
                nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                holdings_value += holding["shares"] * nav

        total_value = portfolio.cash + holdings_value

        # 再平衡日
        if (idx - last_rebalance_idx) >= rebalance_days:
            last_rebalance_idx = idx

            # Step 1: 计算各行业动量（过去 N 日收益率）
            sector_returns = {}
            for sector, codes in sector_funds.items():
                sector_navs = []
                for code in codes:
                    pts = fund_charts.get(code, [])
                    valid = _bisect_valid(pts, day)
                    if len(valid) > momentum_lookback:
                        navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                        # 取最近 momentum_lookback 天的收益
                        if len(navs) >= momentum_lookback:
                            ret = (navs[-1] / navs[-momentum_lookback] - 1)
                            sector_navs.append(ret)

                if sector_navs:
                    # 行业收益 = 行业内基金中位数收益
                    sector_navs.sort()
                    sector_returns[sector] = sector_navs[len(sector_navs) // 2]

            # Step 2: 选前 N 个行业
            sorted_sectors = sorted(sector_returns.items(), key=lambda x: x[1], reverse=True)
            target_sectors = set([s[0] for s in sorted_sectors[:top_n_sectors]])
            current_target_sectors = target_sectors

            # Step 3: 计算当前组合波动率
            if len(daily_values) >= 20:
                recent = daily_values[-20:]
                returns = []
                for i in range(1, len(recent)):
                    if recent[i-1] > 0:
                        returns.append(recent[i] / recent[i-1] - 1)
                if returns:
                    daily_vol = (sum((r - sum(returns)/len(returns))**2 for r in returns) / len(returns)) ** 0.5
                    annual_vol = daily_vol * (252 ** 0.5)
                else:
                    annual_vol = target_vol
            else:
                annual_vol = target_vol

            # Step 4: 波动率目标仓位
            if annual_vol > 0:
                vol_scalar = target_vol / annual_vol
                vol_scalar = max(0.3, min(1.5, vol_scalar))  # 限制在 30%-150%
            else:
                vol_scalar = 1.0

            target_equity = total_value * vol_scalar

            # Step 5: 卖出不在目标行业的持仓
            for code in list(portfolio.holdings.keys()):
                if fund_sectors.get(code, "其他") not in target_sectors:
                    pts = fund_charts.get(code, [])
                    valid = _bisect_valid(pts, day)
                    if valid:
                        nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                        portfolio.sell(code, 0, nav, day, "sector_rotation_sell", force_sell=True)

            # Step 6: 买入目标行业基金（等权）
            target_per_sector = target_equity / max(len(target_sectors), 1)
            for sector in target_sectors:
                codes = sector_funds.get(sector, [])
                if not codes:
                    continue
                # 选该行业内动量最强的 1-2 只基金
                fund_momentum = []
                for code in codes:
                    pts = fund_charts.get(code, [])
                    valid = _bisect_valid(pts, day)
                    if len(valid) > momentum_lookback:
                        navs = [(100 + _float(p.get("yAxis", 0))) / 100 for p in valid]
                        if len(navs) >= momentum_lookback:
                            ret = (navs[-1] / navs[-momentum_lookback] - 1)
                            fund_momentum.append((code, ret))

                fund_momentum.sort(key=lambda x: x[1], reverse=True)
                top_funds = fund_momentum[:2]  # 每个行业最多 2 只

                per_fund = target_per_sector / max(len(top_funds), 1)
                for code, _ in top_funds:
                    pts = fund_charts.get(code, [])
                    valid = _bisect_valid(pts, day)
                    if valid:
                        nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                        if nav > 0 and portfolio.cash > per_fund * 0.8:
                            buy_amount = min(per_fund, portfolio.cash * 0.9)
                            portfolio.buy(code, f"sector_{sector}", buy_amount, nav, day)

        # 记录每日净值（包含 T+N 结算中的买入）
        current_value = portfolio.cash

        # 已确认持仓
        for code, holding in portfolio.holdings.items():
            pts = fund_charts.get(code, [])
            valid = _bisect_valid(pts, day)
            if valid:
                nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                current_value += holding["shares"] * nav

        # 待确认买入（T+N 结算中）
        for pb in portfolio.pending_buys:
            if pb["confirm_date"] > day:
                pts = fund_charts.get(pb["code"], [])
                valid = _bisect_valid(pts, day)
                if valid:
                    nav = (100 + _float(valid[-1].get("yAxis", 0))) / 100
                    current_value += pb.get("shares", 0) * nav

        daily_values.append(current_value)

    # 计算回测指标
    if len(daily_values) < 2:
        return {"error": "Insufficient data"}

    total_return = (daily_values[-1] / initial_cash - 1) * 100

    # 最大回撤（以初始资金为起点，首日T+N结算中的买入按成本计入）
    peak = max(initial_cash, daily_values[0])
    max_dd = 0
    for v in daily_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # 年化收益
    days = len(daily_values)
    years = days / 252
    annualized = ((daily_values[-1] / daily_values[0]) ** (1/years) - 1) * 100 if years > 0 else 0

    # 夏普比率
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
        "daily_values": daily_values,
        "trades": portfolio.trades,
    }


def main():
    print("=" * 70)
    print("行业动量轮动 + 波动率目标仓位策略")
    print("=" * 70)

    # 参数组合
    configs = [
        {"name": "SM1", "momentum_lookback": 63, "top_n_sectors": 4, "target_vol": 0.10, "rebalance_days": 21},
        {"name": "SM2", "momentum_lookback": 63, "top_n_sectors": 3, "target_vol": 0.10, "rebalance_days": 21},
        {"name": "SM3", "momentum_lookback": 63, "top_n_sectors": 4, "target_vol": 0.08, "rebalance_days": 21},
        {"name": "SM4", "momentum_lookback": 63, "top_n_sectors": 4, "target_vol": 0.12, "rebalance_days": 21},
        {"name": "SM5", "momentum_lookback": 42, "top_n_sectors": 4, "target_vol": 0.10, "rebalance_days": 21},
        {"name": "SM6", "momentum_lookback": 126, "top_n_sectors": 4, "target_vol": 0.10, "rebalance_days": 21},
        {"name": "SM7", "momentum_lookback": 63, "top_n_sectors": 5, "target_vol": 0.10, "rebalance_days": 21},
        {"name": "SM8", "momentum_lookback": 63, "top_n_sectors": 4, "target_vol": 0.10, "rebalance_days": 14},
        {"name": "SM9", "momentum_lookback": 63, "top_n_sectors": 4, "target_vol": 0.10, "rebalance_days": 42},
    ]

    results = []
    for cfg in configs:
        print(f"\n--- {cfg['name']}: lookback={cfg['momentum_lookback']}d, top{cfg['top_n_sectors']}, vol={cfg['target_vol']*100}%, rebal={cfg['rebalance_days']}d ---")
        result = run_sector_momentum_backtest(cfg)
        result["name"] = cfg["name"]
        result["config"] = cfg
        results.append(result)
        print(f"  Return: {result['total_return']:.2f}%, DD: {result['max_drawdown']:.2f}%, Sharpe: {result['sharpe_ratio']:.2f}, Trades: {result['trade_count']}")

    # 排序
    results.sort(key=lambda x: x["total_return"], reverse=True)

    print("\n" + "=" * 70)
    print("排名（按收益）")
    print("=" * 70)
    print(f"{'排名':<4} {'策略':<6} {'收益':>8} {'回撤':>8} {'夏普':>6} {'交易':>5}")
    print("-" * 50)
    for i, r in enumerate(results, 1):
        print(f"{i:<4} {r['name']:<6} {r['total_return']:>7.1f}% {r['max_drawdown']:>7.1f}% {r['sharpe_ratio']:>5.2f} {r['trade_count']:>4}")

    # 保存
    output_file = PROJECT_DIR / "v9-results" / "sector_momentum_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
