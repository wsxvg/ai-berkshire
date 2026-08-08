#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V2: 纯权益 proxy + 大跌抄底
改进:
1. 只保留权益类基金 (排除债基/货基/理财)
2. 多样本随机基准
3. 分行业/分市值测试
"""
import json, sys, os, statistics, random
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, '.')

print("=== V2 大跌回测: 纯权益 proxy ===")

# 加载数据
from tools.chart_loader import load_all_charts
charts = load_all_charts()

# 名称分类
BOND_KW = ['债', '债券', '可转债', '转债']
MONEY_KW = ['货币', '现金', '理财', '钱包', '宝', '货基']

# 加载代码→名称映射
with open('data/fund_name_map.json', encoding='utf-8') as f:
    CODE_TO_NAME = json.load(f)
# 反向: name → code (用于分类)
NAME_TO_CODE = {v: k for k, v in CODE_TO_NAME.items()}

# chart_to_name.json 可能更新
with open('data/chart_to_name.json', encoding='utf-8') as f:
    CHART_TO_NAME = json.load(f)

def classify_code(code):
    """基于基金代码对应的名称分类"""
    name = CODE_TO_NAME.get(code, CHART_TO_NAME.get(code, ''))
    if not name:
        return 'equity'  # 默认权益
    
    for kw in MONEY_KW:
        if kw in name:
            return 'money'
    for kw in BOND_KW:
        if kw in name:
            return 'bond'
    return 'equity'

# 构建按日期索引
print("构建日频权益 NAV 索引...")
dates_funds_all = defaultdict(dict)
dates_funds_eq = defaultdict(dict)  # 只含权益基金

for code, pts in charts.items():
    ftype = classify_code(code)
    for p in pts:
        d = p['xAxis']
        y = p['yAxis']
        if isinstance(y, list):
            y = y[0]
        try:
            y = float(y)
        except (ValueError, TypeError):
            continue
        nav = 1.0 + y / 100.0
        dates_funds_all[d][code] = nav
        if ftype == 'equity':
            dates_funds_eq[d][code] = nav

all_dates = sorted(dates_funds_all.keys())
print(f"交易日: {len(all_dates)}, 范围 {all_dates[0]}~{all_dates[-1]}")

# 市场 proxy: 全市场 vs 纯权益
def build_proxy(funds_dict, label):
    proxy = {}
    for i in range(1, len(all_dates)):
        d, d_prev = all_dates[i], all_dates[i-1]
        cur = funds_dict[d]
        prev = funds_dict[d_prev]
        rets = [(cur[c] - prev[c]) / prev[c] for c in cur if c in prev and prev[c] > 0]
        if rets:
            proxy[d] = sum(rets) / len(rets)
    return proxy

print("构建全市场 proxy...")
market_all = build_proxy(dates_funds_all, "all")
print(f"  全市场: {len(market_all)} 天")

print("构建纯权益 proxy...")
market_eq = build_proxy(dates_funds_eq, "equity")
print(f"  纯权益: {len(market_eq)} 天")

# 统计对比
print(f"\n=== 大跌日对比 ===")
for thresh in [-0.03, -0.05, -0.07]:
    n_all = sum(1 for r in market_all.values() if r <= thresh)
    n_eq = sum(1 for r in market_eq.values() if r <= thresh)
    print(f"  单日 <= {thresh*100:+.0f}%: 全市场={n_all:3d}, 纯权益={n_eq:3d}")

# 回测函数
def backtest(crash_dict, funds_dict, hold_days, name, min_cov=20):
    dates_list = all_dates
    date_idx = {d: i for i, d in enumerate(dates_list)}
    results = []
    for d in crash_dict:
        if d not in date_idx:
            continue
        idx = date_idx[d]
        if idx + 1 >= len(dates_list):
            continue
        buy_date = dates_list[idx + 1]
        sell_target = datetime.strptime(buy_date, '%Y-%m-%d') + timedelta(days=hold_days)
        sell_str = sell_target.strftime('%Y-%m-%d')
        sell_date = next((dt for dt in dates_list if dt >= sell_str), None)
        if not sell_date:
            continue
        
        buy_navs = funds_dict.get(buy_date, {})
        sell_navs = funds_dict.get(sell_date, {})
        if len(buy_navs) < min_cov:
            continue
        
        rets = [(sell_navs[c] - b) / b for c, b in buy_navs.items() if c in sell_navs and b > 0]
        if len(rets) >= min_cov:
            results.append(sum(rets) / len(rets))
    
    if not results:
        return None
    avg = sum(results) / len(results) * 100
    med = statistics.median(results) * 100
    wr = sum(1 for r in results if r > 0) / len(results) * 100
    return {'n': len(results), 'avg': avg, 'med': med, 'wr': wr}

def benchmark(funds_dict, hold_days, n=200, min_cov=20):
    valid = [d for d in all_dates[:-hold_days] if len(funds_dict.get(d, {})) >= min_cov]
    if not valid:
        return None
    picks = random.sample(valid, min(n, len(valid)))
    results = []
    for buy_date in picks:
        sell_target = datetime.strptime(buy_date, '%Y-%m-%d') + timedelta(days=hold_days)
        sell_str = sell_target.strftime('%Y-%m-%d')
        sell_date = next((dt for dt in all_dates if dt >= sell_str), None)
        if not sell_date:
            continue
        buy_navs = funds_dict[buy_date]
        sell_navs = funds_dict.get(sell_date, {})
        rets = [(sell_navs[c] - b) / b for c, b in buy_navs.items() if c in sell_navs and b > 0]
        if len(rets) >= min_cov:
            results.append(sum(rets) / len(rets))
    if not results:
        return None
    return {'n': len(results), 'avg': sum(results)/len(results)*100, 'med': statistics.median(results)*100, 'wr': sum(1 for r in results if r > 0)/len(results)*100}

# 筛选 2010+ 且覆盖率 >= 200
print("\n=== 回测 (2010+, min cov=200) ===")
min_year = '2010'
min_cov = 200

def filter_by_coverage(proxy, funds_dict, min_y, min_c):
    return {d: r for d, r in proxy.items() if d[:4] >= min_y and len(funds_dict.get(d, {})) >= min_c}

eq_proxy = filter_by_coverage(market_eq, dates_funds_eq, min_year, min_cov)
all_proxy = filter_by_coverage(market_all, dates_funds_all, min_year, min_cov)
print(f"纯权益有效日: {len(eq_proxy)}, 全市场有效日: {len(all_proxy)}")

# 大跌信号
for thresh_name, thresh in [('<= -3%', -0.03), ('<= -5%', -0.05), ('<= -7%', -0.07)]:
    eq_dip = {d: r for d, r in eq_proxy.items() if r <= thresh}
    all_dip = {d: r for d, r in all_proxy.items() if r <= thresh}
    print(f"\n--- 大跌阈值 {thresh_name}: 纯权益={len(eq_dip)}, 全市场={len(all_dip)} ---")
    
    for hold in [10, 20, 30, 60, 90]:
        eq_res = backtest(eq_dip, dates_funds_eq, hold, f"EQ {thresh_name}")
        all_res = backtest(all_dip, dates_funds_all, hold, f"ALL {thresh_name}")
        eq_bench = benchmark(dates_funds_eq, hold)
        all_bench = benchmark(dates_funds_all, hold)
        
        if eq_res:
            eq_alpha = eq_res['avg'] - (eq_bench['avg'] if eq_bench else 0)
            all_alpha = all_res['avg'] - (all_bench['avg'] if all_bench else 0) if all_res else None
            
            print(f"  持有{hold:3d}d | EQ 抄底: n={eq_res['n']:3d} avg={eq_res['avg']:+.2f}% med={eq_res['med']:+.2f}% wr={eq_res['wr']:.0f}% (α={eq_alpha:+.2f}%)")
            if all_res:
                print(f"{'':13} | ALL 抄底: n={all_res['n']:3d} avg={all_res['avg']:+.2f}% med={all_res['med']:+.2f}% wr={all_res['wr']:.0f}% (α={all_alpha:+.2f}%)")
            if eq_bench:
                print(f"{'':13} | EQ 基准: n={eq_bench['n']:3d} avg={eq_bench['avg']:+.2f}%")

# 月度收益分布
print("\n=== 年度胜场分布 (纯权益, 持有 30 天) ===")
eq_3d = {d: r for d, r in eq_proxy.items() if r <= -0.03}
monthly = defaultdict(list)
didx = {d: i for i, d in enumerate(all_dates)}
for d in eq_3d:
    if d in didx and didx[d]+1 < len(all_dates):
        buy = all_dates[didx[d]+1]
        yr = buy[:4]
        st = datetime.strptime(buy, '%Y-%m-%d') + timedelta(days=30)
        sell = next((dt for dt in all_dates if dt >= st.strftime('%Y-%m-%d')), None)
        if sell and buy in dates_funds_eq and sell in dates_funds_eq:
            rets = [(dates_funds_eq[sell][c] - dates_funds_eq[buy][c]) / dates_funds_eq[buy][c]
                    for c in dates_funds_eq[buy] if c in dates_funds_eq[sell] and dates_funds_eq[buy][c] > 0]
            if len(rets) >= 200:
                monthly[yr].append(sum(rets)/len(rets)*100)

print(f"{'年份':>6} | {'信号日':>6} | {'平均':>8} | {'中位数':>8} | {'胜率':>6}")
print("-" * 50)
for yr in sorted(monthly):
    rets = monthly[yr]
    avg = sum(rets)/len(rets)
    wr = sum(1 for r in rets if r > 0)/len(rets)*100
    print(f"{yr:>6} | {len(rets):>6} | {avg:>+7.2f}% | {statistics.median(rets):>+7.2f}% | {wr:>5.1f}%")

print("\n=== 完成 ===")
