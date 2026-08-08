#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速验证：宽基大跌后抄底策略 (使用 chart_loader, 2001-2026)
"""
import json, sys, os, statistics, random
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, '.')

print("加载基金图表数据 (2001-2026)...")
from tools.chart_loader import load_all_charts

charts = load_all_charts()
print(f"Charts 覆盖: {len(charts)} 只基金")

# 1. 构建按日期索引: {date: {code: nav_float}}
print("构建日频 NAV 索引 (约 2-3 分钟)...")
dates_funds = defaultdict(dict)
for code, pts in charts.items():
    for p in pts:
        d = p['xAxis']
        y = p['yAxis']
        if isinstance(y, list):
            y = y[0]
        try:
            y = float(y)
        except (ValueError, TypeError):
            continue
        dates_funds[d][code] = 1.0 + y / 100.0

all_dates = sorted(dates_funds.keys())
print(f"交易日范围: {all_dates[0]} ~ {all_dates[-1]}, 共 {len(all_dates)} 天")

# 2. 每日市场 proxy
print("构建市场 proxy (等权日收益)...")
market_ret = {}
for i in range(1, len(all_dates)):
    d, d_prev = all_dates[i], all_dates[i - 1]
    cur = dates_funds[d]
    prev = dates_funds[d_prev]
    rets = []
    for code, nav in cur.items():
        p = prev.get(code)
        if p and p > 0:
            rets.append((nav - p) / p)
    if rets:
        market_ret[d] = sum(rets) / len(rets)

print(f"市场 proxy: {len(market_ret)} 天")
date_to_idx = {d: i for i, d in enumerate(all_dates)}

# 3. 5日累计跌幅
def cum_ret_n(date_idx, n):
    if date_idx < n:
        return None
    s = 0
    cnt = 0
    for j in range(n):
        d = all_dates[date_idx - j]
        if d in market_ret:
            s += market_ret[d]
            cnt += 1
    return s if cnt >= n - 1 else None

# 4. 回测函数
def backtest_dip(crash_dict, hold_days, name, min_cov=20):
    results = []
    for d in crash_dict:
        if d not in date_to_idx:
            continue
        idx = date_to_idx[d]
        if idx + 1 >= len(all_dates):
            continue
        buy_date = all_dates[idx + 1]
        
        sell_target = datetime.strptime(buy_date, '%Y-%m-%d') + timedelta(days=hold_days)
        sell_str = sell_target.strftime('%Y-%m-%d')
        sell_date = next((dt for dt in all_dates if dt >= sell_str), None)
        if not sell_date:
            continue
        
        buy_navs = dates_funds.get(buy_date, {})
        sell_navs = dates_funds.get(sell_date, {})
        
        if len(buy_navs) < min_cov:
            continue
        
        fund_rets = []
        for code, bnav in buy_navs.items():
            snav = sell_navs.get(code)
            if snav and bnav > 0:
                fund_rets.append((snav - bnav) / bnav)
        
        if len(fund_rets) >= min_cov:
            results.append(sum(fund_rets) / len(fund_rets))
    
    if not results:
        print(f"  {name}: 无结果")
        return None
    
    avg = sum(results) / len(results) * 100
    med = statistics.median(results) * 100
    wr = sum(1 for r in results if r > 0) / len(results) * 100
    losses = [r for r in results if r < 0]
    avg_neg = sum(losses) / len(losses) * 100 if losses else 0
    
    print(f"  {name}:")
    print(f"    n={len(results)} | 平均 {avg:+.2f}% | 中位数 {med:+.2f}% | 胜率 {wr:.1f}% | 亏损日均价 {avg_neg:+.2f}%")
    return avg

def backtest_random(hold_days, n=500, min_cov=20):
    valid = [d for d in all_dates[:-hold_days] if len(dates_funds.get(d, {})) >= min_cov]
    if not valid:
        return
    picks = random.sample(valid, min(n, len(valid)))
    results = []
    for buy_date in picks:
        sell_target = datetime.strptime(buy_date, '%Y-%m-%d') + timedelta(days=hold_days)
        sell_str = sell_target.strftime('%Y-%m-%d')
        sell_date = next((dt for dt in all_dates if dt >= sell_str), None)
        if not sell_date:
            continue
        buy_navs = dates_funds[buy_date]
        sell_navs = dates_funds.get(sell_date, {})
        fund_rets = [(sell_navs[c] - b) / b for c, b in buy_navs.items() if c in sell_navs and b > 0]
        if len(fund_rets) >= min_cov:
            results.append(sum(fund_rets) / len(fund_rets))
    
    if results:
        avg = sum(results) / len(results) * 100
        med = statistics.median(results) * 100
        wr = sum(1 for r in results if r > 0) / len(results) * 100
        print(f"  随机买入 {hold_days}天: n={len(results)} | 平均 {avg:+.2f}% | 中位数 {med:+.2f}% | 胜率 {wr:.1f}%")

# 5. 主逻辑
print("\n=== 回测: 大跌后抄底 vs 随机买入 ===")
random.seed(42)

coverages = defaultdict(int)
for d in all_dates:
    coverages[d[:4]] = max(coverages[d[:4]], len(dates_funds[d]))
print("\n年度最大基金覆盖:")
for yr in sorted(coverages):
    print(f"  {yr}: {coverages[yr]} 只")

min_year = "2010"
valid_dates = [d for d in all_dates if d[:4] >= min_year and d in market_ret]
print(f"\n{min_year}+ 交易日: {len(valid_dates)}")

# 单日大跌
dip_3 = {d: market_ret[d] for d in valid_dates if market_ret[d] <= -0.03}
dip_5 = {d: market_ret[d] for d in valid_dates if market_ret[d] <= -0.05}
dip_7 = {d: market_ret[d] for d in valid_dates if market_ret[d] <= -0.07}
dip_10 = {d: market_ret[d] for d in valid_dates if market_ret[d] <= -0.10}

# 5日累计大跌
cum_dip = {}
for d in valid_dates:
    idx = date_to_idx[d]
    cr = cum_ret_n(idx, 5)
    if cr is not None and cr <= -0.07:
        cum_dip[d] = cr

print(f"\n大跌日统计 (2010+):")
print(f"  单日 <= -3%: {len(dip_3)}")
print(f"  单日 <= -5%: {len(dip_5)}")
print(f"  单日 <= -7%: {len(dip_7)}")
print(f"  单日 <= -10%: {len(dip_10)}")
print(f"  5日累计 <= -7%: {len(cum_dip)}")

for hold in [30, 60, 90]:
    print(f"\n{'='*50}")
    print(f"=== 持有 {hold} 天 ===")
    print(f"{'='*50}")
    backtest_random(hold)
    backtest_dip(dip_3, hold, f"单日 <= -3% (n={len(dip_3)}) 抄底 {hold}d")
    backtest_dip(dip_5, hold, f"单日 <= -5% (n={len(dip_5)}) 抄底 {hold}d")
    backtest_dip(cum_dip, hold, f"5日累计 <= -7% (n={len(cum_dip)}) 抄底 {hold}d")

print(f"\n{'='*50}")
print("=== 最优参数: 持有 90 天分桶 ===")
print(f"{'='*50}")
backtest_random(90)
backtest_dip(dip_3, 90, "单日 <= -3%")
backtest_dip(dip_5, 90, "单日 <= -5%")
backtest_dip(dip_7, 90, "单日 <= -7%")
backtest_dip(dip_10, 90, "单日 <= -10%")
backtest_dip(cum_dip, 90, "5日累计 <= -7%")
