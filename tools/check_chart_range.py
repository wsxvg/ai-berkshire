import json
d = json.load(open(r'c:\项目\A基金\基金\data\fund_cache\fund_chart_full_002112.json', 'r', encoding='utf-8'))
print('点数:', len(d))
print('首日:', d[0])
print('末日:', d[-1])
# 5年范围: 2021-07-12 ~ 2026-07-11
dates = [p.get('xAxis', '')[:10] for p in d]
print('数据范围:', dates[0], '~', dates[-1])
print('5年起点 2021-07-12 之前点数:', sum(1 for x in dates if x < '2021-07-12'))
print('3年起点 2023-07-12 之前点数:', sum(1 for x in dates if x < '2023-07-12'))
print('1年起点 2025-07-12 之前点数:', sum(1 for x in dates if x < '2025-07-12'))
