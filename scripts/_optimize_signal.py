#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化 smart_money 信号参数

扫描维度:
- callback 阈值: -2% ~ -15% (1日跌幅)
- topgain_hold 阈值: 1 ~ 5
- net_buy 要求: >= 0, >= 1, >= 2
- 持有期: 30/60/90 天
- 多日累计回调: 1日 vs 3日 vs 5日

目标: 找到最优参数使 90天信号超额最大化
"""
import json, sys, statistics
from datetime import datetime, timedelta
from itertools import product

sys.path.insert(0, '.')

with open('data/smart_money_signals.json', encoding='utf-8') as f:
    signals = json.load(f)

from tools.chart_loader import load_all_charts
charts = load_all_charts()
fund_nav = {}
for code, pts in charts.items():
    fund_nav[code] = {p['xAxis']: (p['yAxis'][0] if isinstance(p['yAxis'], list) else p['yAxis']) for p in pts}

dates = sorted(signals.keys())

# 计算多日累计回调 (1/3/5日)
def calc_multi_day_callback(fcode, date, days):
    """计算截至 date 的 N 日累计跌幅"""
    if fcode not in fund_nav:
        return 0
    navs = fund_nav[fcode]
    nav_dates = sorted(navs.keys())
    idx = nav_dates.index(date) if date in nav_dates else -1
    if idx < days:
        return 0
    past_nav = navs[nav_dates[idx - days]]
    cur_nav = navs[nav_dates[idx]]
    if past_nav <= 0:
        return 0
    return (cur_nav / past_nav - 1) * 100

# 前向收益计算
def forward_return(fcode, date, hold_days):
    if fcode not in fund_nav:
        return None
    navs = fund_nav[fcode]
    nav_dates = sorted(navs.keys())
    buy_candidates = [d for d in nav_dates if d >= date]
    if not buy_candidates:
        return None
    buy_price = navs[buy_candidates[0]]
    if buy_price <= 0:
        return None
    dt = datetime.strptime(date, '%Y-%m-%d')
    target_str = (dt + timedelta(days=hold_days)).strftime('%Y-%m-%d')
    sell_candidates = [d for d in nav_dates if d >= target_str]
    if not sell_candidates:
        return None
    sell_price = navs[sell_candidates[0]]
    return (sell_price / buy_price - 1) * 100

# 参数扫描
param_grid = {
    'callback_min': [-15, -10, -8, -5, -3],
    'callback_max': [-2, -3, -5],
    'topgain_min': [1, 2, 3, 4],
    'netbuy_min': [0, 1, 2],
    'hold_days': [30, 60, 90],
    'callback_days': [1, 2, 3, 5],
}

print("=== 信号参数优化扫描 ===")
results = []

for cmin, cmax, tmin, nmin, hdays, cdays in product(
    param_grid['callback_min'],
    param_grid['callback_max'],
    param_grid['topgain_min'],
    param_grid['netbuy_min'],
    param_grid['hold_days'],
    param_grid['callback_days'],
):
    if cmin >= cmax:
        continue
    
    sig_rets = []
    all_rets = []
    
    for date in dates:
        for fcode, sig in signals.get(date, {}).items():
            # 使用 N 日累计回调 (而非单日)
            multi_cb = calc_multi_day_callback(fcode, date, cdays)
            one_cb = sig.get("callback_pct", 0)
            
            # 综合: 用 N日回调
            cb = multi_cb
            
            ret = forward_return(fcode, date, hdays)
            if ret is None:
                continue
            
            all_rets.append(ret)
            
            is_signal = (cmin <= cb <= cmax and 
                        sig.get("topgain_hold", 0) >= tmin and
                        sig.get("net_buy", 0) >= nmin)
            
            if is_signal:
                sig_rets.append(ret)
    
    if len(sig_rets) < 50:
        continue
    
    s_avg = sum(sig_rets) / len(sig_rets)
    a_avg = sum(all_rets) / len(all_rets) if all_rets else 0
    s_med = statistics.median(sig_rets)
    s_wr = sum(1 for r in sig_rets if r > 0) / len(sig_rets) * 100
    diff = s_avg - a_avg
    
    results.append({
        'callback': f"{cmin}~{cmax}",
        'topgain': tmin,
        'netbuy': nmin,
        'hold': hdays,
        'cdays': cdays,
        'sig_avg': s_avg,
        'sig_med': s_med,
        'sig_wr': s_wr,
        'sig_cnt': len(sig_rets),
        'all_avg': a_avg,
        'excess': diff,
    })

# 排序: 按 90天超额 top 20
r90 = [r for r in results if r['hold'] == 90]
r90.sort(key=lambda x: -x['excess'])

print(f"\n=== Top 20 参数组合 (持有90天, 按超额排序) ===")
print(f"{'回调区间':>10} | {'topgain':>7} | {'netbuy':>7} | {'N日':>4} | {'信号数':>6} | {'均值':>8} | {'中位数':>8} | {'胜率':>7} | {'超额':>8}")
print("-" * 95)
for r in r90[:20]:
    print(f"{r['callback']:>10} | {r['topgain']:>7} | {r['netbuy']:>7} | {r['cdays']:>4} | {r['sig_cnt']:>6} | {r['sig_avg']:>7.2f}% | {r['sig_med']:>7.2f}% | {r['sig_wr']:>6.1f}% | {r['excess']:>+7.2f}%")

# 60天 top 10
r60 = [r for r in results if r['hold'] == 60]
r60.sort(key=lambda x: -x['excess'])
print(f"\n=== Top 10 参数组合 (持有60天) ===")
print(f"{'回调区间':>10} | {'topgain':>7} | {'netbuy':>7} | {'N日':>4} | {'信号数':>6} | {'均值':>8} | {'中位数':>8} | {'胜率':>7} | {'超额':>8}")
print("-" * 95)
for r in r60[:10]:
    print(f"{r['callback']:>10} | {r['topgain']:>7} | {r['netbuy']:>7} | {r['cdays']:>4} | {r['sig_cnt']:>6} | {r['sig_avg']:>7.2f}% | {r['sig_med']:>7.2f}% | {r['sig_wr']:>6.1f}% | {r['excess']:>+7.2f}%")

# 30天 top 5
r30 = [r for r in results if r['hold'] == 30]
r30.sort(key=lambda x: -x['excess'])
print(f"\n=== Top 5 参数组合 (持有30天) ===")
print(f"{'回调区间':>10} | {'topgain':>7} | {'netbuy':>7} | {'N日':>4} | {'信号数':>6} | {'均值':>8} | {'中位数':>8} | {'胜率':>7} | {'超额':>8}")
print("-" * 95)
for r in r30[:5]:
    print(f"{r['callback']:>10} | {r['topgain']:>7} | {r['netbuy']:>7} | {r['cdays']:>4} | {r['sig_cnt']:>6} | {r['sig_avg']:>7.2f}% | {r['sig_med']:>7.2f}% | {r['sig_wr']:>6.1f}% | {r['excess']:>+7.2f}%")

# 保存最优
best_90 = r90[0] if r90 else None
best_60 = r60[0] if r60 else None
if best_90:
    print(f"\n=== 最优 90天参数 ===")
    print(f"回调: {best_90['callback']}% (累计 {best_90['cdays']} 日)")
    print(f"topgain_hold >= {best_90['topgain']}")
    print(f"net_buy >= {best_90['netbuy']}")
    print(f"信号数: {best_90['sig_cnt']}")
    print(f"超额: {best_90['excess']:+.2f}%")
    
    with open('data/best_signal_params.json', 'w') as f:
        json.dump({'90d': best_90, '60d': best_60}, f, indent=2)
    print("保存至 data/best_signal_params.json")
