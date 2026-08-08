#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化 smart_money 信号参数 v2 — 精简版, 聚焦关键参数
预计算所有日期-基金的前向收益, 然后快速扫描参数组合
"""
import json, sys, statistics
from datetime import datetime, timedelta

sys.path.insert(0, '.')

with open('data/smart_money_signals.json', encoding='utf-8') as f:
    signals = json.load(f)

from tools.chart_loader import load_all_charts
print("加载基金净值...", flush=True)
charts = load_all_charts()

# 构建 NAV 查找表: {code: {date_str: nav_value}}
# 注意 yAxis 是累计收益率, 所以前向收益 = (sell_y - buy_y) / (1 + buy_y/100)
# 但我们只需比较相对大小, 可以直接用 sell_y - buy_y 作为近似,
# 或用 (1+sell/100)/(1+buy/100)-1 精确值
fund_nav = {}
for code, pts in charts.items():
    fund_nav[code] = {}
    for p in pts:
        y = p['yAxis'][0] if isinstance(p['yAxis'], list) else p['yAxis']
        fund_nav[code][p['xAxis']] = float(y)

print(f"完成: {len(fund_nav)} 只基金", flush=True)

dates = sorted(signals.keys())

# 预计算: 对所有信号日-基金对, 计算 1/2/3/5 日累计回调和前向收益
# 这样参数扫描时只需查表
print("预计算所有信号点的前向收益...", flush=True)

# 数据结构: list of (one_cb, three_cb, five_cb, topgain, net_buy, ret30, ret60, ret90)
signal_points = []
total = 0

for date in dates:
    dt = datetime.strptime(date, '%Y-%m-%d')
    for fcode, sig in signals.get(date, {}).items():
        if fcode not in fund_nav:
            continue
        navs = fund_nav[fcode]
        nav_dates = sorted(navs.keys())
        
        # 买入日 >= signal date
        buy_dates = [d for d in nav_dates if d >= date]
        if not buy_dates:
            continue
        buy_d = buy_dates[0]
        buy_y = navs[buy_d]  # 累计收益率%
        if buy_y <= -99:  # 除零保护
            continue
        
        # 计算多日回调 (基于当天的累计收益率变化)
        one_cb = sig.get("callback_pct", 0)
        idx = nav_dates.index(buy_d) if buy_d in nav_dates else -1
        
        three_cb = one_cb
        five_cb = one_cb
        if idx >= 3:
            past3_y = navs[nav_dates[idx-3]]
            three_cb = (1 + buy_y/100) / (1 + past3_y/100) * 100 - 100
        if idx >= 5:
            past5_y = navs[nav_dates[idx-5]]
            five_cb = (1 + buy_y/100) / (1 + past5_y/100) * 100 - 100
        
        # 前向收益 (精确)
        def fwd_ret(hold_days):
            target_dt = dt + timedelta(days=hold_days)
            target_str = target_dt.strftime('%Y-%m-%d')
            sell_dates = [d for d in nav_dates if d >= target_str]
            if not sell_dates:
                return None
            sell_y = navs[sell_dates[0]]
            return (1 + sell_y/100) / (1 + buy_y/100) * 100 - 100
        
        r30 = fwd_ret(30)
        r60 = fwd_ret(60)
        r90 = fwd_ret(90)
        
        if r30 is None:
            continue
        
        signal_points.append({
            'one_cb': one_cb,
            'three_cb': three_cb,
            'five_cb': five_cb,
            'topgain': sig.get('topgain_hold', 0),
            'netbuy': sig.get('net_buy', 0),
            'ret30': r30,
            'ret60': r60 if r60 is not None else 0,
            'ret90': r90 if r90 is not None else 0,
        })
        total += 1

print(f"共 {total} 个有效信号点", flush=True)

# 计算全局基准 (所有信号点的前向收益均值)
all_r30 = [p['ret30'] for p in signal_points]
all_r60 = [p['ret60'] for p in signal_points if p['ret60'] != 0]
all_r90 = [p['ret90'] for p in signal_points if p['ret90'] != 0]
base_30 = sum(all_r30) / len(all_r30)
base_60 = sum(all_r60) / len(all_r60)
base_90 = sum(all_r90) / len(all_r90)
print(f"基准收益 (所有信号点平均): 30d={base_30:.2f}%  60d={base_60:.2f}%  90d={base_90:.2f}%", flush=True)

# 参数扫描
print("\n=== 参数扫描 ===", flush=True)

results = []

# 精简参数网格
cb_configs = [
    ('one_cb', -10, -3),   # 原始: 单日 -10~-3
    ('one_cb', -8, -3),
    ('one_cb', -5, -3),
    ('one_cb', -10, -5),
    ('three_cb', -10, -3),
    ('three_cb', -8, -3),
    ('three_cb', -12, -5),
    ('five_cb', -10, -3),
    ('five_cb', -12, -3),
    ('five_cb', -15, -5),
]

topgain_cuts = [1, 2, 3, 4]
netbuy_cuts = [0, 1, 2, 3]

for cb_field, cbmin, cbmax in cb_configs:
    for tc in topgain_cuts:
        for nc in netbuy_cuts:
            sig_r30 = []
            sig_r60 = []
            sig_r90 = []
            
            for p in signal_points:
                cb = p[cb_field]
                if not (cbmin <= cb <= cbmax):
                    continue
                if p['topgain'] < tc:
                    continue
                if p['netbuy'] < nc:
                    continue
                sig_r30.append(p['ret30'])
                sig_r60.append(p['ret60'])
                sig_r90.append(p['ret90'])
            
            if len(sig_r30) < 30:
                continue
            
            s30 = sum(sig_r30) / len(sig_r30)
            s60 = sum(sig_r60) / len(sig_r60)
            s90 = sum(sig_r90) / len(sig_r90)
            
            wr90 = sum(1 for r in sig_r90 if r > 0) / len(sig_r90) * 100
            
            results.append({
                'cb_field': cb_field,
                'cb_range': f"{cbmin}~{cbmax}",
                'topgain': tc,
                'netbuy': nc,
                'sig_cnt': len(sig_r30),
                'excess_30': s30 - base_30,
                'excess_60': s60 - base_60,
                'excess_90': s90 - base_90,
                'sig_avg_90': s90,
                'base_90': base_90,
                'wr_90': wr90,
                'med_90': statistics.median(sig_r90),
            })

# 排序
r90_sorted = sorted(results, key=lambda x: -x['excess_90'])

print(f"\n{'回调字段':>10} | {'回调区间':>10} | {'topgain':>7} | {'netbuy':>7} | {'样本':>6} | {'信号均值':>8} | {'基准':>8} | {'EXCESS':>8} | {'中位数':>8} | {'胜率':>7}")
print("-" * 115)

for r in r90_sorted[:30]:
    mark = "✅" if r['excess_90'] > 0.5 else ("⚠️" if r['excess_90'] > 0 else "❌")
    print(f"{r['cb_field']:>10} | {r['cb_range']:>10} | {r['topgain']:>7} | {r['netbuy']:>7} | {r['sig_cnt']:>6} | {r['sig_avg_90']:>7.2f}% | {r['base_90']:>7.2f}% | {r['excess_90']:>+7.2f}% {mark} | {r['med_90']:>7.2f}% | {r['wr_90']:>6.1f}%")

# 特别展示: 高置信度 (样本>100, excess>1%)
print(f"\n=== 高置信度组合 (样本>100, 90天超额>1%) ===")
high_conf = [r for r in r90_sorted if r['sig_cnt'] > 100 and r['excess_90'] > 1.0]
if high_conf:
    for r in high_conf[:10]:
        print(f"  {r['cb_field']} [{r['cb_range']}] topgain>={r['topgain']} netbuy>={r['netbuy']}: {r['sig_cnt']}信号, 90d_excess={r['excess_90']:+.2f}%, 胜率={r['wr_90']:.1f}%")
else:
    print("  无满足条件的组合")

# 保存最优
best = r90_sorted[0]
with open('data/best_signal_params.json', 'w') as f:
    json.dump({
        'best': best,
        'baseline': {'30d': base_30, '60d': base_60, '90d': base_90},
        'top_10': r90_sorted[:10],
    }, f, indent=2, ensure_ascii=False)

print(f"\n保存至 data/best_signal_params.json")
print(f"最优参数: {best['cb_field']} [{best['cb_range']}] topgain>={best['topgain']} netbuy>={best['netbuy']}")
print(f"90天超额: {best['excess_90']:+.2f}%  (均值 {best['sig_avg_90']:.2f}% vs 基准 {best['base_90']:.2f}%)")
