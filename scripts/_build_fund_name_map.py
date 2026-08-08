#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建双向映射: chart_code ↔ fund_name (基于 eastmoney_all_funds.json)
同时从 trading 数据建立 JD内部码 ↔ fund_name 映射

输出:
  data/chart_to_name.json  — chart_code → fund_name
  data/name_to_chart.json  — fund_name → [chart_codes]
  data/jdcode_to_chart.json — JD内部码("基金111317") → chart_code
"""
import json, sys, re, os
from collections import defaultdict

sys.path.insert(0, '.')

# === Step 1: 加载 eastmoney_all_founds 建立 code ↔ name ===
print("加载 eastmoney_all_funds.json...")
with open('data/eastmoney_all_funds.json', 'r', encoding='utf-8') as f:
    all_funds = json.load(f)

chart_to_name = {}
name_to_charts = defaultdict(set)

for fund in all_funds:
    code = str(fund.get('code', ''))
    name = fund.get('name', '')
    if code and name:
        chart_to_name[code] = name
        name_to_charts[name].add(code)

print(f"  chart→name: {len(chart_to_name)} 条")
print(f"  name→charts: {len(name_to_charts)} 个唯一名称")

# === Step 2: 加载 trading 数据, 建立 JD code ↔ fund_name ===
print("\n加载 trading_by_date_fixed.json...")
with open('backtest/data/trading_by_date_fixed.json', 'r', encoding='utf-8') as f:
    tbd = json.load(f)

jdcode_to_name = {}
name_from_trades = set()

for d in tbd:
    for rec in tbd[d]:
        fund_name = rec.get('fund_name', '')
        detail = rec.get('detail', '')
        # 提取 JD 内部码
        m = re.search(r'基金(\d+)', detail)
        if m and fund_name:
            jd_code = m.group(1)
            jdcode_to_name[jd_code] = fund_name
            name_from_trades.add(fund_name)

print(f"  JD内部码→name: {len(jdcode_to_name)} 条")
print(f"  唯一 fund_name (from trades): {len(name_from_trades)}")

# === Step 3: 桥接 JD内部码 → chart_code ===
print("\n构建桥接映射...")
success = 0
failed_examples = []

for jd_code, fund_name in list(jdcode_to_name.items()):
    if fund_name in name_to_charts:
        # 可能有多个 chart_code 对应同一个 name (A/C类)
        charts = list(name_to_charts[fund_name])
        # 优先选择 C 类 (通常 C 类份额较多, 场外持有者更多)
        best = None
        for c in charts:
            if c.endswith('C') or 'C' in c:
                best = c
                break
        if not best:
            best = charts[0]
        # 存储
        if f"jd_{jd_code}" not in jdcode_to_name:
            jdcode_to_name[f"jd_{jd_code}"] = {"fund_name": fund_name, "chart_code": best}
            success += 1
    else:
        if len(failed_examples) < 10:
            failed_examples.append((jd_code, fund_name))

# 原始 JD码也保留
jdcode_to_chart = {}
for jd_code, fund_name in [(k,v) for k,v in list(jdcode_to_name.items()) if not str(k).startswith('jd_')]:
    if fund_name in name_to_charts:
        charts = list(name_to_charts[fund_name])
        best = charts[0]
        for c in charts:
            name_c = chart_to_name.get(c, '')
            if 'C' in name_c.split(' ')[-1:] or name_c.endswith('C'):
                best = c
                break
        jdcode_to_chart[jd_code] = best

print(f"  JD码→chart映射: {len(jdcode_to_chart)}")
if failed_examples:
    print(f"  未匹配样例 (fund_name 在 charts 中找不到):")
    for jd, fn in failed_examples[:5]:
        print(f"    基金{jd}: {fn}")

# === Step 4: 输出 ===
os.makedirs('data', exist_ok=True)

with open('data/chart_to_name.json', 'w', encoding='utf-8') as f:
    json.dump(chart_to_name, f, ensure_ascii=False, indent=2)

name_to_chart_single = {k: list(v)[0] for k, v in name_to_charts.items()}
with open('data/name_to_chart.json', 'w', encoding='utf-8') as f:
    json.dump(name_to_chart_single, f, ensure_ascii=False, indent=2)

with open('data/jdcode_to_chart.json', 'w', encoding='utf-8') as f:
    json.dump(jdcode_to_chart, f, ensure_ascii=False, indent=2)

# 计算覆盖率
trade_funds_with_chart = sum(1 for fn in name_from_trades if fn in name_to_charts)
print(f"\n=== 汇总 ===")
print(f"交易中的 fund_name 数: {len(name_from_trades)}")
print(f"成功映射到 chart_code: {trade_funds_with_chart} ({trade_funds_with_chart/len(name_from_trades)*100:.1f}%)")
print(f"输出: data/chart_to_name.json, data/name_to_chart.json, data/jdcode_to_chart.json")
