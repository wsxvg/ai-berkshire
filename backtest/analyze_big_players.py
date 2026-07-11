#!/usr/bin/env python3
"""分析各大佬的历史选基表现"""
import sys, json
from pathlib import Path
from collections import defaultdict, Counter
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

records = json.load(open('backtest/data/trading_history_fixed.json','r',encoding='utf-8'))
charts = json.load(open('backtest/data/fund_charts.json','r',encoding='utf-8'))

# 每个大佬买了啥，表现如何
user_buys = defaultdict(lambda: defaultdict(list))  # user -> fund_code -> [buy_dates]
user_perf = defaultdict(list)  # user -> [forward_returns]

for r in records:
    user = r.get('_user', '')
    fn = r.get('fund_name', '')
    date = r.get('_full_date', '')
    action = r.get('action', '')
    if not user or not date or '买入' not in action:
        continue

    # 找基金代码
    detail = r.get('detail', '')
    import re
    m = re.search(r'基金(\d{6})', detail)
    code = m.group(1) if m else ''
    if code:
        user_buys[user][code].append(date)

# 计算每只买入后30天的表现
for user, funds in user_buys.items():
    for code, dates in funds.items():
        pts = charts.get(code, [])
        if not pts:
            continue
        # 取第一次买入日期
        buy_date = min(dates)
        # 找买入后30天的净值
        buy_idx = None
        for i, p in enumerate(pts):
            if p.get('xAxis', '') >= buy_date:
                buy_idx = i
                break
        if buy_idx is None or buy_idx + 20 >= len(pts):
            continue
        buy_val = _float(pts[buy_idx].get('yAxis', 0))
        sell_val_30d = _float(pts[buy_idx + 20].get('yAxis', 0)) if buy_idx + 20 < len(pts) else buy_val
        ret_30d = sell_val_30d - buy_val
        user_perf[user].append(ret_30d)

def _float(v):
    try: return float(v)
    except: return 0.0

# 按表现排名
print(f"{'大佬':20s} {'买入次数':>6s} {'平均30天收益':>14s} {'胜率(>0)':>10s}")
print("-"*60)
for user in sorted(user_perf.keys(), key=lambda u: sum(user_perf[u])/max(len(user_perf[u]),1), reverse=True):
    perf = user_perf[user]
    if len(perf) < 3:
        continue
    avg = sum(perf) / len(perf)
    win_rate = sum(1 for p in perf if p > 0) / len(perf) * 100
    print(f"{user:20s} {len(perf):>6d} {avg:>+10.2f}% {win_rate:>8.1f}%")

# 找出买入次数最多的基金
fund_buys = Counter()
for r in records:
    if '买入' in r.get('action',''):
        fn = r.get('fund_name','')
        if fn:
            fund_buys[fn] += 1

print(f"\n\n买入次数最多的基金：")
for fn, cnt in fund_buys.most_common(20):
    print(f"  {cnt:>4d}次 {fn}")

# 买入后30天表现最好的基金
print(f"\n\n买入后30天表现最好的基金（至少5次买入）：")
fund_perf = defaultdict(list)
for r in records:
    if '买入' not in r.get('action',''):
        continue
    fn = r.get('fund_name','')
    date = r.get('_full_date','')
    if not date:
        continue
    detail = r.get('detail','')
    import re
    m = re.search(r'基金(\d{6})', detail)
    code = m.group(1) if m else ''
    if not code:
        continue
    pts = charts.get(code, [])
    if not pts:
        continue
    for i, p in enumerate(pts):
        if p.get('xAxis','') >= date:
            if i + 20 < len(pts):
                bv = _float(pts[i].get('yAxis',0))
                sv = _float(pts[i+20].get('yAxis',0))
                fund_perf[fn].append(sv - bv)
            break

for fn in sorted(fund_perf.keys(), key=lambda f: sum(fund_perf[f])/max(len(fund_perf[f]),1), reverse=True):
    perf = fund_perf[fn]
    if len(perf) < 5:
        continue
    avg = sum(perf)/len(perf)
    print(f"  {avg:>+7.2f}% ({len(perf):>3d}次) {fn}")

print(f"\n\n表现最差的基金：")
for fn in sorted(fund_perf.keys(), key=lambda f: sum(fund_perf[f])/max(len(fund_perf[f]),1)):
    perf = fund_perf[fn]
    if len(perf) < 5:
        continue
    avg = sum(perf)/len(perf)
    print(f"  {avg:>+7.2f}% ({len(perf):>3d}次) {fn}")