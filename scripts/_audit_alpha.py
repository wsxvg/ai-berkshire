#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证大佬买入后 alpha — 基于 69.7% 的覆盖
"""
import json, sys, re
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, '.')

# 加载映射表
with open('data/jdcode_to_chart.json', encoding='utf-8') as f:
    jdcode_to_chart = json.load(f)
with open('data/chart_to_name.json', encoding='utf-8') as f:
    chart_to_name = json.load(f)
# 反向映射 (name末位去分额→chart_code)
name_to_chart = {}
with open('data/eastmoney_all_funds.json', encoding='utf-8') as f:
    for fund in json.load(f):
        code = str(fund.get('code', ''))
        name = fund.get('name', '')
        if code and name:
            name_to_chart[name] = code  # 最后写入的保留 (C类优先)

print(f"映射表: JD码→chart {len(jdcode_to_chart)}条, name→chart {len(name_to_chart)}条")

# 加载交易数据
with open('backtest/data/trading_by_date_fixed.json', encoding='utf-8') as f:
    tbd = json.load(f)

# 加载基金净值 (仅加载需要的)
from tools.chart_loader import load_all_charts
charts_raw = load_all_charts()
# 只保留映射到的 charts
needed_chart_codes = set(jdcode_to_chart.values()) | set(name_to_chart.values())
charts = {c: pts for c, pts in charts_raw.items() if c in needed_chart_codes}
print(f"缓存净值基金数: {len(charts)}")

fund_nav = {}
for code, pts in charts.items():
    fund_nav[code] = {}
    for p in pts:
        fund_nav[code][p['xAxis']] = p['yAxis'][0] if isinstance(p['yAxis'], list) else p['yAxis']

# 加载大佬分类
with open('data/big_player_audit.json') as f:
    audit = json.load(f)
legit_pids = set(audit.get('legit_pids', []))
susp_pids = set(s['pid'] for s in audit.get('suspicious_detail', []))
print(f"有效大佬 {len(legit_pids)} 人, 可疑 {len(susp_pids)} 人")

# 重放交易, 计算买入后 N 天收益
hold_periods = [30, 60, 90]
ret_after_buy = {pid: {h: [] for h in hold_periods} for pid in list(legit_pids) + list(susp_pids)}
match_count = 0
unmatch_count = 0

dates = sorted(tbd.keys())
for d in dates:
    for rec in tbd[d]:
        pid = rec.get('_uid')
        if pid not in ret_after_buy:
            continue
        action = rec.get('action', '')
        if '买入' not in action:
            continue
        detail = rec.get('detail', '')
        fund_name = rec.get('fund_name', '')

        # 尝试 JD code → chart code
        chart_code = None
        m = re.search(r'基金(\d+)', detail)
        if m:
            jd_code = m.group(1)
            if jd_code in jdcode_to_chart:
                chart_code = jdcode_to_chart[jd_code]
        if not chart_code and fund_name in name_to_chart:
            chart_code = name_to_chart[fund_name]
        if not chart_code or chart_code not in fund_nav:
            unmatch_count += 1
            continue

        match_count += 1
        dt = datetime.strptime(d, '%Y-%m-%d')
        navs = fund_nav[chart_code]
        # 找到买入日或最近的交易日
        trade_dates = sorted(navs.keys())
        future_dates = [dd for dd in trade_dates if dd >= d]
        if not future_dates:
            continue
        buy_price = navs[future_dates[0]]
        if buy_price <= 0:
            continue

        for h in hold_periods:
            target_dt = dt + timedelta(days=h)
            target_str = target_dt.strftime('%Y-%m-%d')
            fdates = [dd for dd in trade_dates if dd >= target_str]
            if not fdates:
                continue
            sell_price = navs[fdates[0]]
            ret = (sell_price / buy_price - 1) * 100
            ret_after_buy[pid][h].append(ret)

# 统计
def avg(lst):
    return sum(lst) / len(lst) if lst else float('-inf')
def median(lst):
    s = sorted(lst)
    return s[len(s)//2] if s else float('-inf')

all_legit = {h: [] for h in hold_periods}
all_susp = {h: [] for h in hold_periods}
for pid in legit_pids:
    for h in hold_periods:
        r = ret_after_buy[pid][h]
        if r:
            all_legit[h].extend(r)
for pid in susp_pids:
    for h in hold_periods:
        r = ret_after_buy[pid][h]
        if r:
            all_susp[h].extend(r)

print(f"\n=== 交易匹配 ===")
print(f"匹配成功: {match_count} 笔")
print(f"未匹配: {unmatch_count} 笔 (基金代码无法对应到 chart)")
print(f"覆盖率: {match_count/(match_count+unmatch_count)*100:.1f}%" if (match_count+unmatch_count) > 0 else "N/A")

print(f"\n=== 大佬买入后 N 天收益 ===")
print(f"{'N天':>6} | {'有效大佬买入':>12} | {'均值':>8} | {'中位数':>8} | {'胜率':>8} | {'可疑大佬买入':>12} | {'均值':>8} | {'中位数':>8} | {'胜率':>8}")
print("-" * 110)

for h in hold_periods:
    lr = all_legit[h]
    sr = all_susp[h]
    l_avg = avg(lr) if lr else 0
    l_med = median(lr) if lr else 0
    l_wr = sum(1 for r in lr if r > 0) / len(lr) * 100 if lr else 0
    s_avg = avg(sr) if sr else 0
    s_med = median(sr) if sr else 0
    s_wr = sum(1 for r in sr if r > 0) / len(sr) * 100 if sr else 0
    print(f"{h:>6}天 | {len(lr):>12}笔 | {l_avg:>7.2f}% | {l_med:>7.2f}% | {l_wr:>6.1f}% | {len(sr):>12}笔 | {s_avg:>7.2f}% | {s_med:>7.2f}% | {s_wr:>6.1f}%")

print(f"\n=== 结论 ===")
l60 = avg(all_legit[60]) if all_legit[60] else 0
s60 = avg(all_susp[60]) if all_susp[60] else 0
if l60 > s60:
    diff = l60 - s60
    print(f"✅ 有效大佬 60 天 alpha ({l60:.2f}%) > 可疑大佬 ({s60:.2f}%), 超额 {diff:.2f}% — 信号有效")
else:
    diff = s60 - l60
    print(f"❌ 有效大佬 60 天 alpha ({l60:.2f}%) ≤ 可疑大佬 ({s60:.2f}%), 跑输 {diff:.2f}% — 信号可能无效")

# 保存
result = {
    "match_count": match_count,
    "unmatch_count": unmatch_count,
    "legit_60d_alpha": round(l60, 3),
    "suspicious_60d_alpha": round(s60, 3),
    "legit_trade_samples": len(all_legit[60]),
    "suspicious_trade_samples": len(all_susp[60]),
}
with open('data/big_player_alpha.json', 'w') as f:
    json.dump(result, f, indent=2)
print(f"\n结果保存至 data/big_player_alpha.json")
